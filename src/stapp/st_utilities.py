'''
Utility functions and configurations for the Streamlit app.
Handles environment loading, database connection, and OpenAI API setup.
Revision 1: Initial Rev. Cesar C. 10/28/2026
Revision 2: Added utility functions for publication search and summaries. Cesar C. 11/10/2026

Neon. (n.d.). Understanding vector search and HNSW index with pgvector.
https://neon.com/blog/understanding-vector-search-and-hnsw-index-with-pgvector

OpenAI. (n.d.). Vector embeddings. https://developers.openai.com/api/docs/guides/embeddings
'''

import os
import pandas as pd
import psycopg2
import psycopg2.extras

from openai import OpenAI
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from streamlit_agraph import Node, Edge
from pgvector.psycopg2 import register_vector

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "prod.env")

connection_string = os.environ.get("NEON_DATABASE_URL")
openai_api_key = os.environ.get("OPENAI_KEY")

EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-6-luna" 
DIMENSION = 512
MIN_CONCEPT_SIMILARITY = 0.4  # cosine similarity cutoff for concept matches; tune with test queries
CONCEPTS_PER_QUERY = 5  # nearest concepts kept for each query


def get_embedding(text):
    '''Get the embedding for a given text using the OpenAI API.

    Args:
        text (str): The text to embed.

    Returns:
        list[float]: The embedding vector for the input text.
    '''
    embedder = OpenAIEmbeddings(model=EMBEDDING_MODEL, openai_api_key=openai_api_key, dimensions=DIMENSION)
    return embedder.embed_query(text)


def search_publications(prompt, top_k=10, abstract=False):
    '''Search for publications related to the given prompt using OpenAI embeddings.
    https://help.openai.com/en/articles/6824809-embeddings-faq

    Args:
        prompt (str): The search query to find related publications.
        top_k (int, optional): The number of top results to return. Defaults to 10.
        abstract (bool, optional): Whether to only include publications with abstracts. Defaults to False.

    Returns:
        pd.DataFrame: A DataFrame containing the search results with publication details and distance.
    '''
    embedding = get_embedding(prompt)
    conn = psycopg2.connect(connection_string)
    register_vector(conn.cursor())
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT  id, 
                source, 
                source_id, 
                publication_date, 
                doi, 
                url, 
                title, 
                abstract, 
                "references",
                authors,
                embedding <=> %s::vector AS distance
        FROM publications
        WHERE (
                    NOT %s
                    OR (abstract IS NOT NULL AND BTRIM(abstract) <> '')
                )
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (embedding, abstract, embedding, top_k))
    results = cursor.fetchall()
    conn.close()
    df = pd.DataFrame([dict(result) for result in results])
    return df

def publications_summary():
    '''Generate a summary of all publications in the database.

    Returns:
        pd.DataFrame: A DataFrame containing the publication counts grouped by source.
    '''
    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT p.source, count(p.source_id) as pub_count
        FROM publications p 
        GROUP BY p.source;""")
    results = cursor.fetchall()
    conn.close()
    df = pd.DataFrame([dict(result) for result in results])
    return df

def publication_date_distribution():
    '''Get the distribution of publication dates (max and min dates included).

    Returns:
        pd.DataFrame: A DataFrame containing the max and min publication dates.
    '''
    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT max(publication_date) as max_date, min(publication_date) as min_date
        FROM publications
        ;""")
    results = cursor.fetchall()
    conn.close()
    df = pd.DataFrame([dict(result) for result in results])

    # Ensure that the max and min publication dates do not exceed today's date.
    today = pd.Timestamp.now().date()
    if not df.empty:
        for column in ("max_date", "min_date"):
            value = df.at[0, column]
            if pd.notna(value) and value > today:
                df.at[0, column] = today

    return df

def top_topics(top_k=10):
    '''Get the top topics (sources) with the most publications.

    Args:
        top_k (int, optional): The number of top topics to return. Defaults to 10.

    Returns:
        pd.DataFrame: A DataFrame containing the top topics and their publication counts.
    '''
    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT p.source, count(p.source_id) as publication_count
        FROM publications p 
        GROUP BY p.source
        ORDER BY publication_count DESC
        LIMIT %s;""", (top_k,))
    results = cursor.fetchall()
    conn.close()
    df = pd.DataFrame([dict(result) for result in results])
    return df

def get_example_kg_publication():
    '''Return one random example: a medical condition, a paper studying it, and a method it uses.

    Returns:
        pd.DataFrame: A DataFrame containing one random example with columns for medical condition, paper title, and method.
    '''
    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # TABLESAMPLE reads only a random fraction of kg_edges (0.1% is ~23k of 23M rows) instead of
    # the whole table. ORDER BY random() over that small sample avoids always picking the
    # first rows of the table. If a sample has no match, retry with a larger one.
    for percent in (0.1, 1):
        cursor.execute(f"""
            SELECT c.name AS medical_condition, p.name AS paper_title, m.name AS method
            FROM kg_edges ce TABLESAMPLE SYSTEM ({percent})
            JOIN kg_nodes c ON c.id = ce.target AND c.label = 'Medical_Condition'
            JOIN kg_nodes p ON p.id = ce.source AND p.label = 'Publication'
            JOIN kg_edges me ON me.source = ce.source AND me.relation = 'USES_METHOD'
            JOIN kg_nodes m ON m.id = me.target AND m.label = 'Method'
            WHERE ce.relation = 'STUDIES_CONDITION'
            ORDER BY random()
            LIMIT 1;""")
        results = cursor.fetchall()
        if results:
            break
    conn.close()
    return pd.DataFrame([dict(result) for result in results])


def search_documents_via_graph(user_queries: list[str]):
    """
    Return (nodes, edges) for the concepts that match each query and the publications connected to them.
    Each query is matched on its own. Publications related to the most queries come first,
    then the ones with the closest concepts; publications related to only some queries still follow.
    Nodes include type and properties; edges include relation labels and properties.

    Args:
        user_queries (list[str]): A list of search queries to find related publications via the graph.

    Returns:
        pd.DataFrame: A DataFrame containing the matched nodes and edges for the queries, including publication details, concept details, and edge properties.
    """
    # 1. Embed each query on its own (already normalized by OpenAI)
    vectors = [get_embedding(query) for query in user_queries]
    terms = ", ".join(f"({index}, %s::vector)" for index in range(len(vectors)))

    # 2. SQL to hit the FlatNav index first for each query, then traverse the edges.
    # Concept edges are stored as publication -> concept, so e.target is the concept.
    sql_query = f"""
        WITH terms(term, embedding) AS (VALUES {terms}),
        matched_concepts AS (
            SELECT t.term, c.id, c.name, c.label, c.properties, c.similarity
            FROM terms t
            CROSS JOIN LATERAL (
                SELECT id, name, label, properties, -(embedding <#> t.embedding) AS similarity
                FROM kg_nodes
                WHERE label IN ('Method', 'Task', 'Medical_Condition', 'Data_Modality', 'Metric')
                ORDER BY embedding <#> t.embedding
                LIMIT {CONCEPTS_PER_QUERY}
            ) c
            WHERE c.similarity >= %s
        ),
        -- Rank on the edges only (no node details), so popular concepts stay cheap.
        paper_terms AS (
            SELECT e.source AS paper_id, m.term, MAX(m.similarity) AS best_similarity
            FROM matched_concepts m
            JOIN kg_edges e ON e.target = m.id
            GROUP BY e.source, m.term
        ),
        ranked_papers AS (
            -- More matched queries first, then the best concept similarity found for each query
            SELECT paper_id, COUNT(*) AS terms_matched, SUM(best_similarity) AS score
            FROM paper_terms
            GROUP BY paper_id
            ORDER BY terms_matched DESC, score DESC, paper_id
            LIMIT 10
        )
        -- Load the details only for the best papers and their matched concepts.
        SELECT DISTINCT n.id AS paper_id, n.name AS paper_title, n.properties AS paper_properties,
                        m.id AS concept_id, m.name AS matched_concept, m.label AS concept_type,
                        m.properties AS concept_properties,
                        e.source, e.target, e.relation, e.properties AS edge_properties,
                        r.terms_matched, r.score
        FROM ranked_papers r
        JOIN kg_nodes n ON n.id = r.paper_id AND n.label = 'Publication'
        JOIN kg_edges e ON e.source = r.paper_id
        JOIN matched_concepts m ON m.id = e.target
        ORDER BY r.terms_matched DESC, r.score DESC, n.id;
    """

    conn = psycopg2.connect(connection_string)
    try:
        with conn.cursor() as cur:
            #https://neon.com/blog/understanding-vector-search-and-hnsw-index-with-pgvector
            cur.execute("SET hnsw.ef_search = 100;")
            # Keep scanning the index until the label filter yields enough rows (pgvector >= 0.8)
            cur.execute("SET hnsw.iterative_scan = relaxed_order; SET hnsw.max_scan_tuples = 200000;")
            cur.execute(sql_query, (*vectors, MIN_CONCEPT_SIMILARITY))
            results = cur.fetchall()
    finally:
        conn.close()

    nodes = []
    edges = []
    node_ids = set()
    edge_keys = set()

    # Process each row from the query results to build the nodes and edges for the graph visualization.
    for row in results:
        (paper_id, paper_title, paper_properties,
         concept_id, matched_concept, concept_type, concept_properties,
         source, target, relation, edge_properties, _terms_matched, _score) = row
        if paper_id not in node_ids:
            nodes.append(Node(id=paper_id, label=paper_title, type="Publication", properties=paper_properties,widthConstraint={"maximum": 200}))
            node_ids.add(paper_id)
        if concept_id not in node_ids:
            nodes.append(Node(id=concept_id, label=matched_concept, type=concept_type, properties=concept_properties,widthConstraint={"maximum": 200}))
            node_ids.add(concept_id)
        edge_key = (source, target, relation)
        if edge_key not in edge_keys:
            edges.append(Edge(source=source, target=target, label=relation, properties=edge_properties))
            edge_keys.add(edge_key)

    return nodes, edges

def get_one_hop(target_paper_id: str):
    """Fetches a 1-hop subgraph for a specific paper.

    Args:
        target_paper_id (str): The ID of the target paper to fetch the 1-hop subgraph for.

    Returns:
        tuple[list[Node], list[Edge]]: A tuple containing the list of nodes and edges for the 1-hop subgraph.
    """
    
    # SQL Query to get all edges and node details connected to the paper
    query = """
        SELECT 
            e.source, sn.name AS source_name, sn.label AS source_label,
            e.target, tn.name AS target_name, tn.label AS target_label,
            e.relation, sn.properties AS source_properties,
            tn.properties AS target_properties
        FROM kg_edges e
        JOIN kg_nodes sn ON e.source = sn.id
        JOIN kg_nodes tn ON e.target = tn.id
        WHERE e.source = %s OR e.target = %s;
    """
    conn = psycopg2.connect(connection_string)
    try:
        with conn.cursor() as cur:
            cur.execute(query, (target_paper_id, target_paper_id))
            results = cur.fetchall()
    finally:
        conn.close()

    # Process the results to create nodes and edges for visualization
    nodes = []
    edges = []
    node_ids = set()
    edge_keys = set()

    for row in results:
        (src_id, src_name, src_label, tgt_id, tgt_name, tgt_label,
         relation, src_properties, tgt_properties) = row
        if src_id not in node_ids:
            nodes.append(Node(id=src_id, label=src_name, type=src_label, properties=src_properties,widthConstraint={"maximum": 200}))
            node_ids.add(src_id)
        if tgt_id not in node_ids:
            nodes.append(Node(id=tgt_id, label=tgt_name, type=tgt_label, properties=tgt_properties,widthConstraint={"maximum": 200}))
            node_ids.add(tgt_id)
        edge_key = (src_id, tgt_id, relation)
        if edge_key not in edge_keys:
            edges.append(Edge(source=src_id, target=tgt_id, label=relation))
            edge_keys.add(edge_key)

    return nodes, edges

def get_two_hops(target_paper_id: str, similar_per_concept: int = 3):
    """Keep the first hop and add up to 5 distinct publication titles.

    Papers are ranked by exact shared concepts first (100% match), then by
    concepts that are semantically similar to the paper's concepts. Only papers
    with a real edge to the first hop are shown, so none is left disconnected.

    Args:
        target_paper_id (str): The ID of the target paper to fetch the 2-hop subgraph for.
        similar_per_concept (int, optional): The number of similar concepts to consider per concept. Defaults to 3.

    Returns:
        tuple[list[Node], list[Edge]]: A tuple containing the list of nodes and edges for the 2-hop subgraph.
    """

    # First hop: reuse the one-hop lookup (paper + all directly connected nodes).
    nodes, edges = get_one_hop(target_paper_id)
    if not nodes:
        return nodes, edges

    # Concepts drive the second hop; authors and references are not used for ranking.
    concept_ids = [n.id for n in nodes if n.type not in ("Publication", "Author", "Reference")]
    if not concept_ids:
        return nodes, edges

    first_hop_ids = [n.id for n in nodes]
    # Skip papers already shown, including copies with the same exact title.
    first_hop_titles = [n.label for n in nodes if n.type == "Publication"]

    # Rank other papers by the paper's concepts they match.
    # A concept matches itself exactly, plus its few most similar concepts (embeddings,
    # HNSW index). The same concept can be stored under different labels or wording,
    # so similar concepts also link related papers. Exact matches always rank first.
    # Concept edges are always stored as paper -> concept, so e.target is the concept.
    ranking_query = """
        WITH paper_concepts AS (
            SELECT id, label, embedding
            FROM kg_nodes
            WHERE id = ANY(%(concept_ids)s)
        ),
        matched_concepts AS (
            SELECT id AS original_id, id AS concept_id, TRUE AS is_exact
            FROM paper_concepts
            UNION ALL
            -- Similar concepts are only searched for concept types where meaning matters.
            SELECT c.id, s.id, FALSE
            FROM paper_concepts c
            CROSS JOIN LATERAL (
                SELECT k.id
                FROM kg_nodes k
                WHERE k.embedding IS NOT NULL AND k.id <> c.id
                ORDER BY k.embedding <#> c.embedding
                LIMIT %(similar_per_concept)s
            ) s
            WHERE c.embedding IS NOT NULL
              AND c.label IN ('Method', 'Task', 'Medical_Condition', 'Condition',
                              'Data_Modality', 'Metric')
        ),
        -- Count on the edges only, then check and de-duplicate just the best candidates.
        counted AS (
            SELECT e.source AS id,
                   COUNT(DISTINCT m.original_id) FILTER (WHERE m.is_exact) AS exact_count,
                   COUNT(DISTINCT m.original_id) FILTER (WHERE NOT m.is_exact) AS similar_count
            FROM matched_concepts m
            JOIN kg_edges e ON e.target = m.concept_id
            WHERE e.source <> ALL(%(exclude_ids)s)
            GROUP BY e.source
            ORDER BY exact_count DESC, similar_count DESC, e.source
            LIMIT 100
        ),
        ranked AS (
            SELECT p.id, p.name, p.properties, c.exact_count, c.similar_count,
                   -- Keep only the best-ranked record for each exact title.
                   ROW_NUMBER() OVER (
                       PARTITION BY p.name
                       ORDER BY c.exact_count DESC, c.similar_count DESC, p.id
                   ) AS title_rank
            FROM counted c
            JOIN kg_nodes p ON p.id = c.id AND p.label = 'Publication'
            WHERE p.name <> ALL(%(exclude_titles)s)
        )
        SELECT id, name, properties
        FROM ranked
        WHERE title_rank = 1
        ORDER BY exact_count DESC, similar_count DESC, id
        LIMIT 5;
    """

    # Load only the edges linking the selected papers to nodes already in the graph.
    edges_query = """
        SELECT
            e.source, sn.name AS source_name, sn.label AS source_label,
            e.target, tn.name AS target_name, tn.label AS target_label,
            e.relation, sn.properties AS source_properties,
            tn.properties AS target_properties
        FROM kg_edges e
        JOIN kg_nodes sn ON sn.id = e.source
        JOIN kg_nodes tn ON tn.id = e.target
        WHERE (e.source = ANY(%s) AND e.target = ANY(%s))
           OR (e.target = ANY(%s) AND e.source = ANY(%s));
    """

    conn = psycopg2.connect(connection_string)
    try:
        with conn.cursor() as cur:
            cur.execute(ranking_query, {
                "concept_ids": concept_ids,
                "similar_per_concept": similar_per_concept,
                "exclude_ids": first_hop_ids,
                "exclude_titles": first_hop_titles,
            })
            related = cur.fetchall()
            if not related:
                return nodes, edges

            related_ids = [paper_id for paper_id, _, _ in related]
            allowed_ids = first_hop_ids + related_ids
            cur.execute(edges_query, (related_ids, allowed_ids, related_ids, allowed_ids))
            results = cur.fetchall()
    finally:
        conn.close()

    # Keep only the papers with a real edge to the first hop. A paper matched only through a
    # similar concept has no such edge, so it is left out instead of being shown disconnected.
    first_hop = set(first_hop_ids)
    linked_ids = set()
    for src_id, _, _, tgt_id, *_ in results:
        if src_id in related_ids and tgt_id in first_hop:
            linked_ids.add(src_id)
        if tgt_id in related_ids and src_id in first_hop:
            linked_ids.add(tgt_id)
    dropped_ids = set(related_ids) - linked_ids
    related = [row for row in related if row[0] in linked_ids]

    # Add the new papers and edges, skipping anything already in the graph.
    node_ids = set(first_hop_ids)
    edge_keys = {(e.source, e.to, e.label) for e in edges}

    for paper_id, paper_title, paper_properties in related:
        nodes.append(Node(id=paper_id, label=paper_title, type="Publication", properties=paper_properties,widthConstraint={"maximum": 200}))
        node_ids.add(paper_id)

    # Add edges for the new papers, ensuring no duplicates and skipping dropped papers.
    for row in results:
        (src_id, src_name, src_label, tgt_id, tgt_name, tgt_label,
         relation, src_properties, tgt_properties) = row
        if src_id in dropped_ids or tgt_id in dropped_ids:
            continue
        if src_id not in node_ids:
            nodes.append(Node(id=src_id, label=src_name, type=src_label, properties=src_properties,widthConstraint={"maximum": 200}))
            node_ids.add(src_id)
        if tgt_id not in node_ids:
            nodes.append(Node(id=tgt_id, label=tgt_name, type=tgt_label, properties=tgt_properties,widthConstraint={"maximum": 200}))
            node_ids.add(tgt_id)
        edge_key = (src_id, tgt_id, relation)
        if edge_key not in edge_keys:
            edges.append(Edge(source=src_id, target=tgt_id, label=relation))
            edge_keys.add(edge_key)

    return nodes, edges

if __name__ == "__main__":
    # Test the search_publications function with a sample prompt
    test_prompt = "X-ray"
    results = search_publications(test_prompt)
    for _, result in results.iterrows():
        print(result)