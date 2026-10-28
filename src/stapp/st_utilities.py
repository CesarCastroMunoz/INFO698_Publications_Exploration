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


if __name__ == "__main__":
    # Test the search_publications function with a sample prompt
    test_prompt = "X-ray"
    results = search_publications(test_prompt)
    for _, result in results.iterrows():
        print(result)