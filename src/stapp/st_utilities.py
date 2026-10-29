'''
Utility functions and configurations for the Streamlit app.
Handles environment loading, database connection, and OpenAI API setup.
Revision 1: Initial Rev. Cesar C. 10/28/2026
'''

import os
import pandas as pd
import psycopg2
import psycopg2.extras

from openai import OpenAI
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from pgvector.psycopg2 import register_vector

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "prod.env")

connection_string = os.environ.get("NEON_DATABASE_URL")
openai_api_key = os.environ.get("OPENAI_KEY")

EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-6-luna" 
DIMENSION = 512


def get_embedding(text):
    '''Get the embedding for a given text using the OpenAI API.'''
    embedder = OpenAIEmbeddings(model=EMBEDDING_MODEL, openai_api_key=openai_api_key, dimensions=DIMENSION)
    return embedder.embed_query(text)


def search_publications(prompt, top_k=10):
    '''Search for publications related to the given prompt using OpenAI embeddings.
    https://help.openai.com/en/articles/6824809-embeddings-faq'''
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
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (embedding, embedding, top_k))
    results = cursor.fetchall()
    conn.close()
    df = pd.DataFrame([dict(result) for result in results])
    return df

def publications_summary():
    '''Generate a summary of all publications in the database.'''
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

def top_topics(top_k=10):
    '''Get the top topics (sources) with the most publications.'''
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
    '''Get an example publication from the database.'''
    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
            WITH eligible_conditions AS (
                SELECT c.id, c.name
                FROM kg_nodes AS c
                WHERE c.label = 'Medical_Condition'
                AND EXISTS (
                    SELECT 1
                    FROM kg_edges AS condition_edge
                    JOIN kg_nodes AS paper
                        ON paper.id = condition_edge.source
                    AND paper.label = 'Publication'
                    JOIN kg_edges AS method_edge
                        ON method_edge.source = paper.id
                    AND method_edge.relation = 'USES_METHOD'
                    JOIN kg_nodes AS method
                        ON method.id = method_edge.target
                    AND method.label = 'Method'
                    WHERE condition_edge.target = c.id
                        AND condition_edge.relation = 'STUDIES_CONDITION'
                )
            ),
            random_conditions AS (
                SELECT id, name
                FROM eligible_conditions
                ORDER BY random()
                LIMIT 10
            )
            SELECT
                c.name AS medical_condition,
                associated.paper_title,
                associated.method
            FROM random_conditions AS c
            CROSS JOIN LATERAL (
                SELECT paper.name AS paper_title, method.name AS method
                FROM kg_edges AS condition_edge
                JOIN kg_nodes AS paper
                ON paper.id = condition_edge.source
                AND paper.label = 'Publication'
                JOIN kg_edges AS method_edge
                ON method_edge.source = paper.id
                AND method_edge.relation = 'USES_METHOD'
                JOIN kg_nodes AS method
                ON method.id = method_edge.target
                AND method.label = 'Method'
                WHERE condition_edge.target = c.id
                AND condition_edge.relation = 'STUDIES_CONDITION'
                ORDER BY random()
                LIMIT 1
            ) AS associated
            ORDER BY c.name;""")
    results = cursor.fetchall()
    conn.close()
    df = pd.DataFrame([dict(result) for result in results])
    return df

if __name__ == "__main__":
    # Test the search_publications function with a sample prompt
    test_prompt = "X-ray"
    results = search_publications(test_prompt)
    for _, result in results.iterrows():
        print(result)