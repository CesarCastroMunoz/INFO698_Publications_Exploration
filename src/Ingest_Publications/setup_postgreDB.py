'''
Ingest publications from JSONL files and store them in a vector DB.
Revision 1: Initial Rev. Cesar C. 10/14/2026
'''

import os
import psycopg2
from pgvector.psycopg2 import register_vector
from pathlib import Path

INPUT_DIR = Path(__file__).resolve().parent.parent / "publications"

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "prod.env")
connection_string = os.environ.get("NEON_DATABASE_URL")


def enable_pgvector():
    '''Enable the pgvector extension in the connected PostgreSQL database.'''
    conn = psycopg2.connect(connection_string)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                register_vector(cursor)
                cursor.execute("SELECT '[1,2,3]'::vector::text")
                print(f"pgvector enabled. Test vector: {cursor.fetchone()[0]}")
    finally:
        conn.close()

def test_connection():
    '''Test the connection to the PostgreSQL database and ensure pgvector is registered.'''
    try:
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        register_vector(cursor)
        print("Successfully connected to Neon.")
    except Exception as e:
        print(f"Connection failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()


def create_table():
    '''Create the publications table in the PostgreSQL database if it doesn't exist.
    --text-embedding-3-small-- generates 1536-dimensional vectors'''
    conn = psycopg2.connect(connection_string)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS publications (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    abstract TEXT,
                    authors TEXT,
                    embedding VECTOR(1536)
                )
                """)
                print("Table 'publications' ensured.")
    finally:
        conn.close()

def drop_table():
    '''Drop the publications table in the PostgreSQL database if it exists.'''
    conn = psycopg2.connect(connection_string)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS publications")
                print("Table 'publications' dropped if it existed.")
    finally:
        conn.close()

if __name__ == "__main__":
    test_connection()
    enable_pgvector()
    #drop_table()  # if we want to recreate the table
    create_table()
    