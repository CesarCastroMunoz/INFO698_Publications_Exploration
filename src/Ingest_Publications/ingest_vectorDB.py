'''
Ingest publications from JSONL files and store them in a vector DB.
Revision 1: Initial Rev. Cesar C. 10/14/2026
Revision 2: Added a check for publications before embedding (to avoid re-embedding existing records). Cesar C. 10/27/2026
'''

import os
import json
import psycopg2
import psycopg2.extras
from openai import OpenAI, OpenAIError
from pgvector.psycopg2 import register_vector
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "prod.env")

neon_connection_string = os.environ.get("NEON_DATABASE_URL")
openai_api_key = os.environ.get("OPENAI_KEY")

INPUT_DIR = Path(__file__).resolve().parent.parent / "publications"
MODEL = "text-embedding-3-small"
DIMENSION = 512

def read_jsonl(input_file):
    """Read one JSONL file into a list of publication records."""
    with open(input_file, "r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]

def ingest_publications(input_file, chunk_size=100):
    """Commit batches; on restart, skip committed identities before embedding."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    conn = psycopg2.connect(neon_connection_string)
    try:
        register_vector(conn)
        publications = read_jsonl(input_file)
        failed_batches = 0
        with conn.cursor() as cursor:
            for i in range(0, len(publications), chunk_size):
                batch = publications[i:i + chunk_size]
                try:
                    with conn:
                        # Check for existing publications to avoid re-embedding them.
                        cursor.execute(
                            """SELECT source, source_id, doi FROM publications
                               WHERE (source, source_id) IN %s OR doi = ANY(%s)""",
                            (tuple((pub["source"], pub["source_id"]) for pub in batch),
                             [pub["doi"] for pub in batch if pub.get("doi") is not None]),
                        )
                        existing = cursor.fetchall()
                        existing_ids = {(row[0], row[1]) for row in existing}
                        existing_dois = {row[2] for row in existing if row[2] is not None}
                        pending = []

                        # Filter out publications that already exist based on source/source_id or DOI.
                        for pub in batch:
                            key = (pub["source"], pub["source_id"])
                            doi = pub.get("doi")
                            if key not in existing_ids and (doi is None or doi not in existing_dois):
                                pending.append(pub)
                                existing_ids.add(key)
                                if doi is not None:
                                    existing_dois.add(doi)
                        if not pending:
                            print(f"Skipped batch at index {i}: all records already exist or are duplicates.")
                            continue

                        # Prepare the text for embedding
                        texts = [f"Title: {pub['title']}. Abstract: {pub['abstract']}" for pub in pending]
                        with OpenAI(api_key=openai_api_key) as client:
                            result = client.embeddings.create(model=MODEL, input=texts, dimensions=DIMENSION)
                        embeddings = sorted(result.data, key=lambda item: item.index)
                        if len(embeddings) != len(pending):
                            raise ValueError("Embedding response does not match the requested records")

                        # Prepare the records for insertion into the database with their embeddings.
                        records = [
                            (pub["source"], pub["source_id"], pub.get("publication_date"),
                             pub.get("doi"), pub.get("url"), pub.get("references", []),
                             pub["title"], pub["abstract"], pub.get("authors", []), item.embedding)
                            for pub, item in zip(pending, embeddings)
                        ]
                        inserted = psycopg2.extras.execute_values(
                            cursor,
                            """INSERT INTO publications
                               (source, source_id, publication_date, doi, url, "references",
                                title, abstract, authors, embedding)
                               VALUES %s ON CONFLICT DO NOTHING RETURNING source, source_id""",
                            records,
                            fetch=True,
                        )
                
                # Error handling for embedding and insertion operations.
                except (OpenAIError, psycopg2.Error, ValueError, KeyError, TypeError) as error:
                    failed_batches += 1
                    print(f"ERROR: {input_file} | Batch at index {i} failed: {error}. "
                          "Continuing with the next batch; rerun to retry unsaved records.")
                    continue
                print(f"Batch at index {i}: committed {len(inserted)}; "
                      f"skipped before embedding {len(batch) - len(pending)}.")
                if len(inserted) != len(pending):
                    print(f"WARNING: {len(pending) - len(inserted)} records conflicted after embedding; "
                          "another database writer may be inserting publications.")
        if failed_batches:
            print(f"WARNING: {input_file}: {failed_batches} failed batches remain incomplete.")
    finally:
        conn.close()

def ingest_files(quantity=None):
    """Process all files in stable order, or an explicitly limited subset."""

    if quantity is not None and quantity < 1:
        raise ValueError("quantity must be at least 1")

    all_files = sorted(INPUT_DIR.glob("*.jsonl"))[:quantity]
    total_files = len(all_files)
    for idx, file in enumerate(all_files, start=1):
        print(f"Ingesting file {idx}/{total_files}: {file}")
        ingest_publications(file)


if __name__ == "__main__":
    print("Starting ingestion process...")
    ingest_files()
