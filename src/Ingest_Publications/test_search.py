'''
Test searching publications in the PostgreSQL vector DB using OpenAI embeddings.
'''


import os
import json
import psycopg2
import psycopg2.extras
from openai import OpenAI
from pgvector.psycopg2 import register_vector
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "prod.env")

neon_connection_string = os.environ.get("NEON_DATABASE_URL")
openai_api_key = os.environ.get("OPENAI_KEY")

INPUT_DIR = Path(__file__).resolve().parent.parent / "publications"
client = OpenAI(api_key=openai_api_key)
MODEL = "text-embedding-3-small"


def get_embedding(text):
    '''Get the embedding for a given text using the OpenAI API.'''
    response = client.embeddings.create(
        model=MODEL,
        input=text
    )
    return response.data[0].embedding

def search_publications(prompt, top_k=5):
    '''Search for publications related to the given prompt using OpenAI embeddings.'''
    embedding = get_embedding(prompt)
    conn = psycopg2.connect(neon_connection_string)
    register_vector(conn.cursor())
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT id, title, abstract, authors, embedding <#> %s::vector AS distance
        FROM publications
        ORDER BY embedding <#> %s::vector
        LIMIT %s
    """, (embedding, embedding, top_k))
    results = cursor.fetchall()
    conn.close()
    return results


if __name__ == "__main__":
    prompt = "Find Publications related to Superior Colorectal Polyp Detection"
    results = search_publications(prompt)
    for result in results:
        print(f"ID: {result['id']}, Title: {result['title']}, Abstract: {result['abstract']}, Authors: {result['authors']}, Distance: {result['distance']}")
