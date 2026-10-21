# Knowledge Graph Approach

This guide describes the knowledge graph currently implemented by
[`create_graph.py`](../src/Ingest_Publications/create_graph.py), including how
publication records become graph data, how that data is stored, and what the
current design does and does not guarantee.

## Purpose

The graph organizes publications about medical AI around two kinds of
information:

1. **Bibliographic structure**, created directly from publication metadata:
   each publication is represented as a node, and its listed authors are
   connected to it.
2. **Research concepts**, extracted from each abstract: methods, tasks, medical
   conditions, data modalities, and evaluation metrics are represented as
   typed nodes connected to the publication.

Each graph node can also carry a vector embedding. This combines explicit,
traversable relationships with semantic similarity search over node names.
The graph is stored in PostgreSQL, with `pgvector` providing vector storage and
similarity indexing.

## End-to-end flow

```text
Publication JSONL
        |
        +-- Build a Publication node from source + source_id
        |
        +-- Build Author nodes and AUTHORED edges from metadata
        |
        +-- If an abstract exists:
        |       ask the structured-output LLM for up to 5 concepts and edges
        |       embed the extracted concept names in one batch
        |
        +-- Yield one graph per publication
                |
                +-- Validate edge endpoints and remove duplicate edge triples
                +-- Upsert nodes and edges into PostgreSQL
```

The input files are JSON Lines in `src/publications`. Each non-empty line is
parsed as one publication. The processing function reads the file's lines into
memory, then works through them in chunks (15 records by default). Publications
with abstracts in a chunk are sent together to the structured-output model;
their extracted semantic node names are then embedded in a bulk embedding
request.

## Graph model

### Node labels

The Pydantic schema allows these seven labels:

| Label | Created by | Meaning |
|---|---|---|
| `Publication` | Deterministic code | A source publication. |
| `Author` | Deterministic code | An author listed in the publication metadata. |
| `Method` | LLM extraction | An AI or analytical method discussed in the abstract. |
| `Task` | LLM extraction | A research or clinical task addressed by the work. |
| `Medical_Condition` | LLM extraction | A disease or condition studied. |
| `Data_Modality` | LLM extraction | A kind of data used, such as imaging or clinical text. |
| `Metric` | LLM extraction | A measure used to evaluate the work. |

The prompt allows the LLM to extract only the five semantic categories; it
explicitly excludes publications and authors because those are constructed
from metadata. It also asks for no more than five important semantic entities
per abstract.

### Relationship types

The structured schema restricts edges to these relationship names:

| Relation | Intended meaning |
|---|---|
| `AUTHORED` | Connects an author to a publication. |
| `USES_METHOD` | Publication uses a method. |
| `TARGETS_TASK` | Publication addresses a task. |
| `STUDIES_CONDITION` | Publication studies a medical condition. |
| `EVALUATED_ON` | Publication uses or is evaluated on a data modality. |
| `MEASURED_BY` | Publication is evaluated using a metric. |

The deterministic author edge is directed **from Author to Publication**:
`Author -[AUTHORED]-> Publication`. For semantic edges, the prompt asks the
model to connect extracted entities to the publication using its exact ID.
The intended pattern is `Publication -[relation]-> concept`; however, the
current code does not independently enforce the semantic edge direction or a
one-edge-per-concept shape. The generated graph is constrained by the response
schema and later checked for valid endpoints before insertion.

### Node and edge shape

Each node has:

- `id`: the graph's identity key.
- `label`: one of the seven labels above.
- `name`: the readable node name.
- `properties`: optional structured metadata, stored as JSONB.
- `embedding`: a 1,536-dimensional vector when one was generated.

Each edge has `source`, `target`, `relation`, and optional JSONB `properties`.
The edge table assigns its own database serial ID; graph identity for an edge
is the triple `(source, target, relation)`.

## Identity and deduplication

Publication IDs are deterministic and source-scoped:

```text
paper:{URL-quoted source}:{URL-quoted source_id}
```

This prevents two providers' records with the same provider ID from
accidentally becoming the same publication node. The node's properties also
retain the raw `source` and `source_id`.

Author IDs use provider IDs when available:

```text
author:provider:{URL-quoted source}:{URL-quoted provider author ID}
```

Including the source prevents provider-specific author IDs from colliding.
When an author ID is missing, the fallback is based on the containing
publication and the author's position in its metadata:

```text
{publication ID}:author:{zero-based author position}
```

That fallback is intentionally publication-specific: it preserves the
author-to-paper record but does not deduplicate the same person across papers.

Semantic node IDs are supplied by the LLM under a schema description asking
for unique snake-case identifiers. The extraction code does not add a
publication or provider namespace to these IDs. Consequently, semantic nodes
with the same exact ID from different publications can merge in PostgreSQL.
The `slugify()` helper exists in the module, but the current extraction path
does not call it to normalize or validate LLM-generated IDs.

At insertion time, repeated edge triples within one graph are removed, and the
database also enforces uniqueness for `(source, target, relation)`. Edges whose
source or target is absent from the current publication graph are warned about
and skipped.

## Extraction and embeddings

For a publication with an abstract, the script submits the title and abstract
to the configured chat model using a Pydantic structured-output schema. The
request asks for a compact graph of important medical-AI concepts rather than
an exhaustive information extraction of every phrase. Structured output
limits labels and relation names, but does not itself guarantee that every
extracted fact is correct; extracted nodes and edges should be treated as
machine-generated interpretations of the abstract.

The embedding model is `text-embedding-3-small`. The script embeds the
**names of newly extracted semantic nodes** together in one request per input
chunk. It does not embed publication titles, abstracts, or author names in
this graph-building path. Publications and authors therefore have no vector
unless a vector is supplied by another process or already exists in the
database.

If a publication has no abstract, the script yields its deterministic
publication and author graph immediately, without an LLM extraction or
semantic-node embeddings.

## PostgreSQL storage

[`setup_postgreDB.py`](../src/Ingest_Publications/setup_postgreDB.py) creates
the graph tables:

### `kg_nodes`

| Column | Role |
|---|---|
| `id TEXT PRIMARY KEY` | Stable graph node ID. |
| `label TEXT NOT NULL` | Node category. |
| `name TEXT NOT NULL` | Human-readable node name. |
| `properties JSONB` | Additional metadata, defaulting to an empty object. |
| `embedding VECTOR(1536)` | Optional vector from the embedding model. |

### `kg_edges`

| Column | Role |
|---|---|
| `id SERIAL PRIMARY KEY` | Database-generated edge row ID. |
| `source TEXT` | Foreign key to `kg_nodes.id`. |
| `target TEXT` | Foreign key to `kg_nodes.id`. |
| `relation TEXT NOT NULL` | Edge predicate. |
| `properties JSONB` | Additional edge metadata, defaulting to an empty object. |

The edge table cascades deletes from either endpoint and has a unique
constraint on `(source, target, relation)`. The setup script creates an HNSW
index using inner-product vector operations for node-vector lookup, plus
indexes on `(source, relation)` and `(target, relation)` to support directional
relationship traversal.

`create_graph.py` loads `prod.env` relative to the repository root and reads
`NEON_DATABASE_URL` and `OPENAI_KEY`. Keep both values private and configure
them in the environment rather than committing credentials.

## Upsert behavior

`insert_graph_data()` inserts nodes and edges in bulk and commits once per
publication graph. When a node ID already exists:

- Its `properties` JSONB is merged with the incoming properties, with incoming
  keys taking precedence.
- Its embedding is replaced only when the incoming graph has a non-null
  embedding; otherwise the existing embedding is retained.
- Its `label` and `name` are **not** updated by the conflict clause.

When an edge triple already exists, its properties are merged, again with
incoming keys taking precedence. The graph insertion function warns and skips
edges with missing endpoints, then commits node and valid-edge changes in the
same connection transaction.

This is an idempotent-style upsert for stable IDs, but it is not a refresh of
all data. In particular, changed publication titles or author names do not
automatically replace an existing node's `name`; semantic ID collisions can
also cause separate concepts to share a database node.

## Running and selecting input

Run from the repository root with the project's environment and dependencies
available:

```powershell
uv run python .\src\Ingest_Publications\create_graph.py
```

The current `__main__` block processes one hard-coded JSONL file:
`src/publications/batch-91539ee2bbe64518b0b919778476292c.jsonl`. It does not
call `ingest_files()`. The `ingest_files(quantity=20)` helper is available for
processing the first `quantity` paths returned by a directory glob, but that
selection is not explicitly sorted. To process another file or a controlled
set of files, update the target-selection code or call
`process_publication_batch()` for the chosen paths from a script.

The graph schema setup script's `__main__` block drops `kg_edges` and
`kg_nodes` before recreating them. **Running it against a populated database
deletes the existing graph data.** Use it only when initializing or
intentionally rebuilding those tables; normal graph ingestion uses the
existing tables and upserts records.

## Scope and limitations

- The graph captures publication metadata and a small set of abstract-level
  concepts; it does not process full-text PDFs.
- The LLM's five-entity cap favors a concise graph and can omit relevant
  details. The output is not independently fact-checked.
- Semantic IDs are not canonically normalized or namespaced in the extraction
  path. Exact ID reuse merges nodes; synonymous names with different IDs
  remain separate.
- Provider author IDs are source-scoped, and missing author IDs fall back to
  per-publication IDs; neither strategy performs person-level identity
  resolution.
- The graph ingestion path does not use the publication `references` field to
  create citation edges.
- This code creates embeddings for semantic-node names only. It does not
  currently provide an embedding for full publication text in the graph.
- The input file's non-empty lines are loaded into memory before chunking, so
  chunked LLM and embedding calls do not make file reading fully streaming.
- The default executable processes a single fixed batch file, rather than all
  files in the publications directory.

These boundaries are important when interpreting graph searches: a missing
node or edge can mean that the concept was not present in the abstract, was
omitted by the extraction limit, was not extracted by the model, or was not
included in the selected input file.
