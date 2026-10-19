'''
Ingest publications from JSONL files and store them in a vector DB.
Revision 1: Initial Rev. Cesar C. 10/14/2026
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

def read_jsonl(input_file):
    '''Read publications from a JSONL file and return them as a list of dictionaries.'''
    publications = []

    with open(input_file, "r", encoding="utf-8") as file:
        for line in file:
            publications.append(json.loads(line.strip()))
    return publications

def ingest_publications(input_file, chunk_size=250):
    '''Ingest publications from JSONL files and store them in the PostgreSQL vector DB.'''
    conn = psycopg2.connect(neon_connection_string)
    #It registers this custom type so you can pass a standard Python list of 1,536 floats
    register_vector(conn) 
    cursor = conn.cursor()

    publications = read_jsonl(input_file)

    if not publications:
        print("No publications found in the input file.")
        return
       
    for i in range(0, len(publications), chunk_size):
        batch = publications[i:i + chunk_size]

        #Extract the texts to embed from the batch of publications
        try:
            texts_to_embed = [f"Title: {pub['title']}. Abstract: {pub['abstract']}" for pub in batch]
            embeddings = client.embeddings.create(
                model=MODEL,
                input=texts_to_embed
            )
        except Exception as e:
            print(f"Error creating embeddings for batch starting at index {i}: {e}")
            continue

        # Skip the rest of the loop if embeddings creation failed
        if 'embeddings' not in locals():
            continue
       
        records_to_insert = []
        for pub, embedded_data in zip(batch, embeddings.data):
            vector = embedded_data.embedding
            records_to_insert.append((pub["source"], 
                                      pub["source_id"], 
                                      pub["publication_date"], 
                                      pub["doi"], pub["url"], 
                                      pub["title"], 
                                      pub["abstract"], 
                                      pub["authors"], 
                                      vector))

        insert_query = """
            INSERT INTO publications
                (source, source_id, publication_date, doi, url,
                title, abstract, authors, embedding)
            VALUES %s
            ON CONFLICT DO NOTHING;
        """

        try:
            psycopg2.extras.execute_values(
                cursor, insert_query, records_to_insert
            )
            conn.commit()
            print(f"Successfully ingested batch of {len(batch)} records.")
        except Exception as e:
            print(f"Error inserting batch starting at index {i}: {e}")
            continue
    
    cursor.close()
    conn.close()

def ingest_files(quantity=20):
    all_files = list(INPUT_DIR.glob("*.jsonl"))
    for file in all_files[:quantity]:
        ingest_publications(file)


if __name__ == "__main__":
    print("Starting ingestion process...")
    ingest_files()

