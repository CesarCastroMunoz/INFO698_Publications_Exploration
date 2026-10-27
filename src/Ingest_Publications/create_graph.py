'''Create a graph from publication data using LangChain and OpenAI embeddings.
Revision 1: Initial Rev. Cesar C. 10/20/2026'''

import json
import os
import warnings
from urllib.parse import quote
import numpy as np
import re
import psycopg2
from psycopg2.extras import execute_values, Json
from typing import Literal
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "prod.env")

INPUT_DIR = Path(__file__).resolve().parent.parent / "publications"

connection_string = os.environ.get("NEON_DATABASE_URL")
openai_api_key = os.environ.get("OPENAI_KEY")

EMBEDDING_MODEL = "text-embedding-3-small"
GRAPH_EXTRACTION_MODEL = "gpt-6-luna" 
DIMENSION = 512

ALLOWED_NODES = [
    "Method", "Task", "Condition", "Data_Modality", "Metric", 
    "Model_Architecture", "Dataset", "Algorithm", "Chemical_or_Drug", 
    "Institution", "Symptom"
]

ALLOWED_EDGES = [
    "USES_METHOD", "TARGETS_TASK", "EVALUATED_ON", "TRAINED_WITH", 
    "MEASURED_BY", "OUTPERFORMS", "STUDIES_CONDITION", "HAS_SYMPTOM", 
    "TREATS", "CAUSES", "INHIBITS"
]

# -----------------------------------------------------------
# 1. Schemas for Strict LLM Output
# -----------------------------------------------------------

class Node(BaseModel):
    id: str = Field(..., description="Unique identifier for the node")
    
    # Expanded to to fix schema for additional entity types
    label: Literal[
        "Method", "Task", "Condition", "Data_Modality", "Metric", 
        "Model_Architecture", "Dataset", "Algorithm", "Chemical_or_Drug", 
        "Institution", "Symptom"
    ] = Field(..., description="The category of the extracted entity.")
    
    name: str = Field(..., description="Standardized, lower-case name of the entity")
    properties: dict = Field(default_factory=dict, description="Additional properties")

class Edge(BaseModel):
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    
    # Fix: Ensure relation types are strictly defined as literals
    relation: Literal[
        "USES_METHOD", "TARGETS_TASK", "EVALUATED_ON", "TRAINED_WITH", 
        "MEASURED_BY", "OUTPERFORMS", "STUDIES_CONDITION", "HAS_SYMPTOM", 
        "TREATS", "CAUSES", "INHIBITS"
    ] = Field(..., description="The predicate connecting the source to the target.")
    
    properties: dict = Field(default_factory=dict, description="Additional properties")

class GraphExtraction(BaseModel):
    nodes: list[Node] = Field(..., description="List of nodes in the graph")
    edges: list[Edge] = Field(..., description="List of edges in the graph")

# ---------------------------------------------------------
# 2. Helper Functions
# ---------------------------------------------------------

def slugify(text: str) -> str:
    """Creates consistent, database-friendly IDs."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# ---------------------------------------------------------
# 3. Core Extraction Pipeline
# ---------------------------------------------------------
def process_publication_batch(file_path: str, batch_size: int = 15):
    """Reads a JSONL file and processes records in parallel batches."""
    llm = ChatOpenAI(
        model=GRAPH_EXTRACTION_MODEL,
        openai_api_key=openai_api_key,
        use_responses_api=True,
    )
    structured_llm = llm.with_structured_output(
        GraphExtraction, method="function_calling", strict=False
    )
    embedder = OpenAIEmbeddings(model=EMBEDDING_MODEL, openai_api_key=openai_api_key, dimensions=DIMENSION)

    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]

    # Process in chunks to leverage concurrent network I/O
    for i in range(0, len(lines), batch_size):
        chunk_lines = lines[i:i + batch_size]
        publications = [json.loads(line) for line in chunk_lines]
        
        prompts = []
        valid_pubs = []
        all_nodes_batch = []
        all_edges_batch = []
        
        # 1. Prepare deterministic metadata and prompts
        for pub in publications:
            source = pub["source"]
            paper_id = f"paper:{quote(source, safe='')}:{quote(pub['source_id'], safe='')}"

            # Initialize nodes and edges for this publication
            pub_nodes = {
                paper_id: {
                    "id": paper_id,
                    "label": "Publication",
                    "name": pub.get("title", ""),
                    "properties": {"source": source, "source_id": pub["source_id"]}
                }
            }
            pub_edges = []

            # Add Authors as nodes and edges
            authors = pub.get("authors", [])
            author_ids = pub.get("author_ids") or [None] * len(authors)
            
            for index, (author_name, provider_id) in enumerate(zip(authors, author_ids)):
                if provider_id:
                    author_id = f"author:provider:{quote(source, safe='')}:{quote(provider_id, safe='')}"
                else:
                    author_id = f"{paper_id}:author:{index}"
                
                pub_nodes[author_id] = {
                    "id": author_id, "label": "Author", "name": author_name
                }
                pub_edges.append({
                    "source": author_id, "target": paper_id, "relation": "AUTHORED"
                })

            # Add References as nodes and edges
            references = pub.get("references", [])
            for ref_index, ref in enumerate(references):
                ref_id = f"{paper_id}:reference:{ref_index}"
                pub_nodes[ref_id] = {
                    "id": ref_id, "label": "Reference", "name": ref
                }
                pub_edges.append({
                    "source": paper_id, "target": ref_id, "relation": "CITES"
                })

            abstract_text = pub.get("abstract", "")
            if abstract_text:
                prompt = (
                    f"Extract a knowledge graph from this medical-AI publication. Use only facts supported by its title or abstract.\n"
                    f"Extract up to 7 distinct, important entities. Labels must be: {', '.join(ALLOWED_NODES)}. "
                    f"Relations must be: {', '.join(ALLOWED_EDGES)}. Do not extract authors or the publication; "
                    f"they are supplied separately. Use concise, standardized lowercase names and unique snake_case IDs.\n"
                    f"Every extracted entity must have a direct edge from the publication ID '{paper_id}', using the "
                    f"most appropriate allowed relation. Add other supported edges between extracted entities when useful; "
                    f"do not invent facts or relations.\n"
                    f"Return only schema-conforming JSON with nodes (id, label, name, properties) and edges "
                    f"(source, target, relation, properties); use empty properties when none apply. No markdown or prose.\n\n"
                    f"Title: {pub['title']}\n"
                    f"Abstract: {abstract_text}"
                )
                prompts.append(prompt)
                valid_pubs.append((pub_nodes, pub_edges))
            else:
                # If no abstract, just yield the deterministic metadata immediately
                yield {"nodes": list(pub_nodes.values()), "edges": pub_edges}

        if not prompts:
            continue

        # 2. Execute LLM Extraction concurrently for the entire batch
        # This handles the heavy network delay in parallel
        llm_results = structured_llm.batch(prompts)

        # 3. Aggregate all nodes across the batch for a single embedding API call
        nodes_to_embed = []
        for (pub_nodes, pub_edges), llm_graph in zip(valid_pubs, llm_results):
            if llm_graph:
                for node in llm_graph.nodes:
                    if node.id not in pub_nodes:
                        node_dict = node.model_dump()
                        pub_nodes[node.id] = node_dict
                        nodes_to_embed.append(node_dict)
                for edge in llm_graph.edges:
                    pub_edges.append(edge.model_dump())
            
            all_nodes_batch.append(pub_nodes)
            all_edges_batch.append(pub_edges)

        # 4. Bulk Vectorization
        # OpenAI embeddings are pre-normalized, so we apply them directly
        if nodes_to_embed:
            node_texts = [n["name"] for n in nodes_to_embed]
            vectors = embedder.embed_documents(node_texts)
            for n, vec in zip(nodes_to_embed, vectors):
                n["embedding"] = vec

        # 5. Yield fully processed graphs
        for pub_nodes, pub_edges in zip(all_nodes_batch, all_edges_batch):
            yield {
                "nodes": list(pub_nodes.values()),
                "edges": pub_edges
            }

# ---------------------------------------------------------
# 4. Insertion into PostgreSQL
# ---------------------------------------------------------
def insert_graph_data(conn, graph_data: dict):
    """Upserts the graph data into the PostgreSQL database using an active connection."""
    nodes = []
    for n in graph_data["nodes"]:
        props = n.get("properties", {})
        embedding = n.get("embedding")
        nodes.append({
            "id": n["id"],
            "label": n["label"],
            "name": n["name"],
            "properties": Json(props),
            "embedding": embedding
        })

    edges = []
    node_ids = {node["id"] for node in graph_data["nodes"]}
    seen_edges = set()

    for e in graph_data["edges"]:
        if e["source"] not in node_ids or e["target"] not in node_ids:
            warnings.warn(f"Skipping edge referencing a missing node: {e}", stacklevel=2)
            continue

        edge_key = (e["source"], e["target"], e["relation"])
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        edges.append({
            "source": e["source"],
            "target": e["target"],
            "relation": e["relation"],
            "properties": Json(e.get("properties", {}))
        })

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO kg_nodes (id, label, name, properties, embedding)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                properties = kg_nodes.properties || EXCLUDED.properties,
                embedding = COALESCE(EXCLUDED.embedding, kg_nodes.embedding);
            """,
            nodes,
            template="(%(id)s, %(label)s, %(name)s, %(properties)s, %(embedding)s)",
        )
        if edges:
            execute_values(
                cur,
                """
                INSERT INTO kg_edges (source, target, relation, properties)
                VALUES %s
                ON CONFLICT (source, target, relation) DO UPDATE SET
                    properties = kg_edges.properties || EXCLUDED.properties;
                """,
                edges,
                template="(%(source)s, %(target)s, %(relation)s, %(properties)s)",
            )
    conn.commit()
        


# ---------------------------------------------------------
# 5. Execution
# ---------------------------------------------------------
def ingest_files(quantity=20):
    all_files = list(INPUT_DIR.glob("*.jsonl"))
    conn = psycopg2.connect(connection_string)
    
    try:
        for file in all_files[:quantity]:
            for graph_data in process_publication_batch(file, batch_size=15):
                print(f"Extracted {len(graph_data['nodes'])} nodes and {len(graph_data['edges'])} edges.")
                insert_graph_data(conn, graph_data)
    finally:
        conn.close()

if __name__ == "__main__":
    target_file = INPUT_DIR / "batch-1e65e590709742f3b40ba6684a695392.jsonl"
    conn = psycopg2.connect(connection_string)
    
    try:
        for graph_data in process_publication_batch(target_file, batch_size=15):
            print(f"Extracted {len(graph_data['nodes'])} nodes and {len(graph_data['edges'])} edges.")
            insert_graph_data(conn, graph_data)
    finally:
        conn.close()