# Knowledge Graph Approach

## One extractor, one embedding and loading stage

For the separate CPU-only GLiNER alternative, see the
[GLiNER quick start](GLiNER%20Quick%20Start.md). It does not replace the original
OpenAI/LM Studio extractor described below. Both use the shared loader.

Select the model in `graph_extraction.py`. Extraction writes the same JSONL
format for either provider and performs no embeddings or database operations.

| Script | Purpose | Default output |
|---|---|---|
| [graph_extraction.py](../src/Ingest_Publications/graph_extraction.py), local model selected | Extract with LM Studio `google/gemma-4-12b-qat` | `src/graph_extracted` |
| Same script, OpenAI model selected | Extract with OpenAI `gpt-6-luna` | `src/graph_extracted` |
| [embed_load_graphs.py](../src/Ingest_Publications/embed_load_graphs.py) | Embed and load `src/graph_extracted` | Existing PostgreSQL graph tables |

The extraction script contains the schema, prompt, metadata construction,
streaming input, and JSONL writer. No separate launcher scripts or additional
dependencies are needed.

```text
Publication JSONL -> Local OR OpenAI extraction -> Graph JSONL
                                                      |
                                            embed_load_graphs.py
                                                      |
                                   Ready JSONL in src/graph_output
                                                      |
                                              PostgreSQL/pgvector
```

## Running

Change only `USE_LOCAL` near the top of the extraction script:
`True` selects local Gemma 4; `False` selects OpenAI.
The model and endpoint are selected automatically.
Both models write unembedded graphs to the single `src/graph_extracted` folder.
The existing `src/graph_output` folder is reserved for previously embedded graph
archives and new ready-to-load graphs. Extraction never writes there.
The loader saves each newly prepared group there before database insertion.
Then run the extractor and loader using the project environment:

```powershell
python src\Ingest_Publications\graph_extraction.py
python src\Ingest_Publications\embed_load_graphs.py
```

There are no CLI arguments. Edit the calls at the bottom of the scripts:

- Extraction processes one publication at a time, saving it before moving on.
- Loader: `run(batch_size=100)`. To read only one directory, pass
  `input_dir=Path(...)` directly to this call instead.

The extractor streams **all** sorted JSONL input files in `src/publications`.
Start LM Studio's server and load the model before local extraction.
The local endpoint is `http://127.0.0.1:1234/v1`. It uses Chat Completions,
JSON-schema output, temperature 0, and `reasoning_effort="none"` to disable thinking.
Its output budget is 4,096 tokens; truncated responses are rejected.
OpenAI uses the Responses API with the same entity schema.
These are individual OpenAI requests, **not** the discounted Batch API.

`OPENAI_KEY` is needed for cloud extraction and embedding; `NEON_DATABASE_URL`
is needed only by the loader. Variables can come from the environment or root
`prod.env`. No secrets belong in source control.

## Extraction and file format

The model extracts at most seven important entities supported by the title or
abstract. Allowed labels:

`Method`, `Task`, `Condition`, `Data_Modality`, `Metric`,
`Model_Architecture`, `Dataset`, `Algorithm`, `Chemical_or_Drug`,
`Institution`, `Symptom`.

Each extracted entity supplies a snake_case ID, standardized lowercase name,
properties object, and `publication_relation`. IDs use lowercase letters, digits,
and underscores and may start with a digit (for example, `3d_u_net`).
Allowed relations:

`USES_METHOD`, `TARGETS_TASK`, `EVALUATED_ON`, `TRAINED_WITH`, `MEASURED_BY`,
`OUTPERFORMS`, `STUDIES_CONDITION`, `HAS_SYMPTOM`, `TREATS`, `CAUSES`, `INHIBITS`.

Python removes `publication_relation` from the saved node and builds its direct
Publication-to-entity edge. It also builds Author-to-Publication `AUTHORED` links
and Publication-to-Reference `CITES` links from metadata. There are **no
entity-to-entity edges**. Every edge identifies its supporting paper through an
endpoint; no provenance table is required. Relations remain compatible with
existing graph queries, but detailed entity-to-entity claims are not represented.

One graph is saved per line:

```json
{"paper_id":"paper:source:123","source":"source","source_id":"123","doi":null,"nodes":[],"edges":[]}
```

Actual records contain the Publication node plus metadata and extracted nodes.
Nodes have `id`, `label`, `name`, and `properties`. Edges have `source`, `target`,
`relation`, and `properties`. New extraction output has **no embeddings**.
Files are named `graph_publications-000001.jsonl` and rotate at 1,000 records.
Publications without abstracts produce metadata-only graphs without model calls.
Invalid inputs or model results print errors and processing continues.
Schema validation is not fact-checking: review representative extraction results.

## Restart and identity

At startup, each extractor scans its output directory once and stores completed
paper IDs in memory. Restarting skips those IDs before model calls and appends
to the final file. Failed extractions are not marked complete.
Progress prints the number already saved at startup, the current file, and
scanned/saved/skipped/failed counts plus graphs/minute after each extraction
attempt and file. Long skip-only scans report progress every 1,000 input records.
An incomplete final JSONL line must be repaired before appending.
Use only one writer per output directory.

Publication identity is `paper:{URL-quoted source}:{URL-quoted source_id}`.
Author provider IDs are source-scoped; missing IDs use the publication ID and
author position. Semantic IDs are shared across papers by exact ID, not DOI or
semantic similarity. Different IDs for synonyms remain separate.

The extractors no longer query PostgreSQL. Existing database-only papers can
therefore be extracted again, incurring cloud extraction cost, unless their
graphs already exist in the chosen output directory. Switching providers reuses
the same completion set in `src/graph_extracted`. The loader still skips already committed papers.
Do not delete extraction output if it is needed for restart or replay.

## Shared embedding and loading

The loader reads `src/graph_extracted`. It validates records and filters older entity-to-entity
edges without modifying source files. It checks committed Publication IDs before
paid calls and deduplicates repeated papers within a group.

Only semantic node names receive embeddings. It reuses stored vectors for
matching node IDs/names and deduplicates new names within a loading group.
OpenAI `text-embedding-3-small` produces **512-dimensional** vectors, with at
most 256 inputs per embedding request. Publication, Author, and Reference nodes
do not receive new embeddings through this pipeline.

Nodes and edges are deduplicated before bulk upsert. Nodes are inserted before
edges and the group commits atomically. Conflicting shared IDs/names are rejected
instead of silently replacing a stored vector with an unrelated one.
Node properties merge; existing names/labels are not overwritten. Edge identity
is `(source, target, relation)` and its properties merge on conflict.

The loader saves ready graphs, including 512-dimensional vector arrays, in
`src/graph_output/graph_publications-000001.jsonl`, rotating at **1,000 publication
graphs per file**, independently of the database batch size. It resumes the last
numbered file on restart and counts that file only once per startup. Existing
UUID archives are left untouched. Incomplete final lines must be repaired before
appending. Use one archive writer at a time. Raw extraction files remain unchanged.

Failed database groups roll back, print the paper IDs, and processing continues.
Ready files are saved **before** insertion: they mean ready to load, not confirmed
committed. PostgreSQL remains the authority for committed publications.
To replay ready files without regenerating embeddings, change the bottom call to
`run(input_dir=READY_DIR, batch_size=100)`. The loader uses their saved vectors,
skips committed papers, and does not create another archive when replaying this
directory. A normal rerun against raw extraction files can re-embed an uncommitted
group, so use the ready files after a database failure. Failure before the ready
file is saved can still require embedding again. No LLM re-extraction is needed.

Run the loader after extraction finishes, or rerun it afterward if reading while
an extractor is still appending. Run only one loader at a time to avoid
check/insert races and duplicate paid embedding calls.

## Database and existing data

The loader uses existing `kg_nodes` and `kg_edges` tables with vector(512).
No schema migration is required. **Do not rerun the table-dropping setup script
against populated tables.**

Existing saved files and database rows are not deleted or migrated. Previously
committed entity-to-entity edges remain until explicitly cleaned up.
Removing these edges reduces edge storage, not the number of shared node vectors.
Files previously written to `src/graph_local` are left untouched and are no longer
read by default. They can be loaded once with `run(input_dir=Path(...))`; do not
overwrite identically named files when consolidating old outputs.
