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


def enable_extensions():
    '''Enable the pgvector extension in the connected PostgreSQL database.'''
    conn = psycopg2.connect(connection_string)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
                cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
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
    --text-embedding-3-small-- generates 512-dimensional vectors'''
    conn = psycopg2.connect(connection_string)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS publications (
                    id SERIAL PRIMARY KEY,
                    source TEXT,
                    source_id TEXT,
                    publication_date DATE,
                    doi TEXT,
                    url TEXT,
                    "references" TEXT[] NOT NULL DEFAULT '{}',
                    title TEXT NOT NULL,
                    abstract TEXT,
                    authors TEXT,
                    embedding VECTOR(512),
                    CONSTRAINT publications_source_unique UNIQUE (source, source_id),
                    CONSTRAINT publications_doi_unique UNIQUE (doi)
                )
                """)
                print("Table 'publications' ensured.")
    finally:
        conn.close()

def drop_table(tablename = "publications"):
    '''Drop the publications table in the PostgreSQL database if it exists.'''
    conn = psycopg2.connect(connection_string)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {tablename}")
                print(f"Table '{tablename}' dropped if it existed.")
    finally:
        conn.close()

def create_node_table():
    '''Create the nodes table in the PostgreSQL database if it doesn't exist.'''
    conn = psycopg2.connect(connection_string)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    name TEXT NOT NULL,
                    properties JSONB DEFAULT '{}'::jsonb,
                    embedding vector(512) 
                    );
                """)
                print("Table 'nodes' created.")
    finally:
        conn.close()

def create_edge_table():
    '''Create the edges table in the PostgreSQL database if it doesn't exist.'''
    conn = psycopg2.connect(connection_string)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS kg_edges (
                    id SERIAL PRIMARY KEY,
                    source TEXT NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
                    target TEXT NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
                    relation TEXT NOT NULL,
                    properties JSONB DEFAULT '{}'::jsonb,
                    CONSTRAINT unique_edge_triple UNIQUE (source, target, relation)
                );
                """)
                print("Table 'edges' created.")
    finally:
        conn.close()

def create_flat_index_table():
    '''Create the flat index table in the PostgreSQL database if it doesn't exist.
       Create Graph traversal indexes'''
    conn = psycopg2.connect(connection_string)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    -- FlatNav-style HNSW index for fast semantic node lookups
                    CREATE INDEX IF NOT EXISTS idx_kg_nodes_flat 
                        ON kg_nodes USING hnsw (embedding vector_ip_ops)
                        WITH (m = 16, ef_construction = 100);

                    -- Edge traversal indexes for instant 1-hop and 2-hop routing
                    CREATE INDEX idx_kg_edges_source_rel ON kg_edges(source, relation);
                    CREATE INDEX idx_kg_edges_target_rel ON kg_edges(target, relation);
                """)
    finally:
        conn.close()

if __name__ == "__main__":
    test_connection()
    enable_extensions()
    drop_table("publications")  # if we want to recreate the table
    create_table()

    # Drop existing tables to start fresh
    drop_table("kg_edges") 
    drop_table("kg_nodes") 
    
    create_node_table()
    create_edge_table()
    create_flat_index_table()
    