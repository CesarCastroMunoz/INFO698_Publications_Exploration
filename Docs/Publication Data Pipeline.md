# Publication Data Pipeline

## Technical and Methodological Documentation

**Project:** Interactive Semantic Exploration of Academic Literature

**Implementation reviewed:** November 9, 2026

**Scope:** OpenAlex and Semantic Scholar retrieval; metadata normalization; publication-vector ingestion; local graph extraction; graph embedding, archiving, and database loading; downstream retrieval and visualization.

> **Documentation disclosure:** Prepared with AI assistance through code inspection. Descriptions refer to the implementation in this repository, not to an independently validated deployment or a completed evaluation study. Model accuracy, database completeness, and retrieval effectiveness require separate empirical assessment.

## 1. Purpose and Research Context

The pipeline constructs an exploratory literature collection concerning artificial intelligence, data science, and healthcare. It integrates bibliographic metadata from **OpenAlex** and **Semantic Scholar**, standardizes the records, and makes them available through two complementary retrieval representations:

1. **Publication-level semantic vectors**, generated from titles and abstracts.
2. **A publication-centered knowledge graph**, containing bibliographic relationships and extracted research concepts.

These representations support natural-language discovery, exploration of methods and medical conditions, and navigation to related publications. The system retrieves metadata and abstracts; it does not download PDFs or systematically process full article text.

The pipeline is a discovery and analysis infrastructure, not an automated systematic-review decision system. A Boolean query match, an extracted relationship, or a high embedding similarity does not establish study eligibility, scientific quality, clinical validity, or causal evidence.

### 1.1 Authoritative implementation

| Responsibility | Implementation |
|---|---|
| Main application navigation | [app.py](../src/stapp/app.py) |
| Home dashboard and publication example | [home.py](../src/stapp/pages/home.py) |
| Semantic publication search interface | [LSearch.py](../src/stapp/pages/LSearch.py) |
| Concept search and graph exploration interface | [Explorer.py](../src/stapp/pages/Explorer.py) |
| AI Assistant page (placeholder) | [AI_explorer.py](../src/stapp/pages/AI_explorer.py) |
| Operator interface and stage selection | [data_pipeline_ui.py](../src/Ingest_Publications/data_pipeline_ui.py) |
| OpenAlex retrieval and field mapping | [search_openalex.py](../src/data_pipeline/search_openalex.py) |
| Semantic Scholar retrieval and field mapping | [search_sem_scholar.py](../src/data_pipeline/search_sem_scholar.py) |
| Shared publication model, cleaning, and JSONL writing | [transform_clean.py](../src/data_pipeline/transform_clean.py) |
| Publication embedding and relational ingestion | [ingest_vectorDB.py](../src/Ingest_Publications/ingest_vectorDB.py) |
| Active local graph extractor | [graph_extraction_gliner.py](../src/Ingest_Publications/graph_extraction_gliner.py) |
| Alternative structured-generation extractor and legacy vocabulary | [graph_extraction.py](../src/Ingest_Publications/graph_extraction.py) |
| Graph validation, vector reuse, archiving, and loading | [embed_load_graphs.py](../src/Ingest_Publications/embed_load_graphs.py) |
| PostgreSQL schema and index setup | [setup_postgreDB.py](../src/Ingest_Publications/setup_postgreDB.py) |
| Application retrieval queries | [st_utilities.py](../src/stapp/st_utilities.py) |
| Graph rendering, duplicate merging, and graph caching | [graph_utilities.py](../src/stapp/graph_utilities.py) |

The separate ingestion interface selects the GLiNER extractor. The alternative extractor remains in the repository and supplies vocabulary constants imported by the graph loader; its presence does not mean that it executes during the active pipeline.

## 2. End-to-End Architecture

```text
Healthcare terms + AI terms + source-specific date/result settings
                              |
                +-------------+--------------+
                |                            |
            OpenAlex                  Semantic Scholar
                |                            |
                +-------------+--------------+
                              |
             Source adapters -> Publication records
                              |
          Cleaning + source/ID duplicate suppression
                              |
                  src/publications/*.jsonl
                              |
               +--------------+----------------+
               |                               |
     Title + abstract embedding        Local GLiNER extraction
               |                               |
       publications table           src/graph_extracted/*.jsonl
                                               |
                                 Validation + concept embeddings
                                               |
                          +--------------------+------------------+
                          |                                       |
              src/graph_output/*.jsonl                 kg_nodes + kg_edges
              embedding-enriched archive              one batch transaction
                          |                                       |
                          +---------------+-----------------------+
                                          |
                     Vector search + graph exploration in Streamlit
```

### 2.1 Independent branches

Publication-vector ingestion and graph extraction both read the local publication JSONL files. Graph extraction does **not** read the `publications` table, and graph loading does not require the publication-vector branch to finish.

Consequently:

- The publication table and graph can contain different sets of papers.
- DOI-based suppression in publication ingestion does not automatically suppress duplicate works in graph extraction.
- Selecting only a later stage processes existing local artifacts, not exclusively records downloaded during the current interface session.
- There is no distributed transaction encompassing API retrieval, files, embedding requests, and both database representations.

## 3. Pipeline Control and Execution

### 3.1 Stage-selection interface

The operator interface provides five checkboxes, all selected by default:

1. Search OpenAlex.
2. Search Semantic Scholar.
3. Ingest to VectorDB.
4. Extract Graphs.
5. Embed and Load Graphs.

Selected stages execute sequentially in this order. The interface rejects a submission with no selected steps.

Search input validation occurs only when at least one source search is enabled. It requires a nonempty healthcare-term group and AI-term group, rejects double quotes supplied in terms, and checks that the start date does not exceed the end date. Terms are stripped, deduplicated while preserving order, and automatically phrase-quoted.

The downstream stages can run without search terms or valid search dates when no source search is selected. This permits restart and partial processing, but prerequisites remain the operator's responsibility:

| Selected stage | Required artifacts or services |
|---|---|
| Search | Source API access; writable publication directory |
| Publication ingestion | Publication JSONL; database schema; embedding API credentials |
| Graph extraction | Publication JSONL; GLiNER dependencies; local model access |
| Graph embedding/loading | Extracted graph JSONL; graph schema; embedding API credentials |

The UI invokes publication ingestion over all matching files, GLiNER extraction over all matching publication files, and graph loading with `batch_size=100`.

### 3.2 Local commands

Run commands from the repository root so relative environment-file loading in the source adapters resolves consistently:

```powershell
uv sync --extra extraction
uv run streamlit run src\Ingest_Publications\data_pipeline_ui.py
```

Stages may also be invoked separately:

```powershell
uv run python src\data_pipeline\search_openalex.py
uv run python src\data_pipeline\search_sem_scholar.py
uv run python src\Ingest_Publications\ingest_vectorDB.py
uv run python src\Ingest_Publications\graph_extraction_gliner.py
uv run python src\Ingest_Publications\embed_load_graphs.py
```

The search scripts' main blocks contain their own topics, dates, and limits. These are not identical to the UI defaults. Record the actual invocation and parameters when describing an experimental collection.

## 4. Source Retrieval Strategy

### 4.1 Search formulation

The UI constructs a union of healthcare phrases and a union of AI phrases, requiring both groups:

```text
OpenAlex:
("health term 1" OR "health term 2") AND ("AI term 1" OR "AI term 2")

Semantic Scholar:
("health term 1" | "health term 2") + ("AI term 1" | "AI term 2")
```

Default healthcare topics include EHR, telemedicine, telehealth, wearables, genomics, bioinformatics, precision medicine, personalized medicine, radiology, pathology, oncology, cardiology, and epidemiology. Default method terms include artificial intelligence, machine learning, deep learning, data science, predictive analytics, neural networks, computer vision, and large language models.

These are broad discovery queries. Neither adapter implements manual eligibility screening, study-design classification, journal-quality filtering, or systematic-review inclusion/exclusion adjudication.

### 4.2 Source-specific behavior

| Property | OpenAlex | Semantic Scholar |
|---|---|---|
| Client or endpoint | `pyalex.Works` | Academic Graph API `/graph/v1/paper/search/bulk` |
| Search field implementation | `title_and_abstract.search` | Bulk query syntax over the provider's search fields |
| Abstract restriction | `has_abstract=True` | No abstract-required filter |
| Date restriction | `from_publication_date` | `year` range |
| End-date handling in UI | Not applied | End year applied, not exact end date |
| Ordering | Publication date descending | No explicit sort parameter |
| Pagination | Cursor; 100 records per page | Provider continuation token |
| Result-limit interpretation | Maximum fetched records in that invocation | Target newly accepted records |
| Credentials | `OPENALEX_API_KEY`, `USER_EMAIL` | Optional `S2_API_KEY` header |

**Date comparability:** Selecting the same dates does not produce identical temporal inclusion rules. OpenAlex receives only the start date. Semantic Scholar receives the start and end years, so records outside the selected months or days may qualify.

**Limit comparability:** OpenAlex can save fewer new records than `max_results` because previously downloaded identities are excluded after fetching. Semantic Scholar counts newly accepted records and can exceed the requested number by the remainder of an accepted page; it may need to fetch many duplicate records to reach its target.

### 4.3 Field adaptation

OpenAlex maps the terminal component of the work URL to `source_id`, reconstructs the abstract through `pyalex.Work` when an inverted index is present, and retains provider author IDs and referenced-work IDs. Its preferred link is the primary landing-page URL, with the work URL as fallback.

Semantic Scholar maps `paperId`, author names and IDs, year/date, citation count, publication types, DOI from `externalIds`, URL, and abstract. Its request does not ask for references; consequently the shared model's reference list remains empty for records collected by this adapter.

### 4.4 Rate limits, retries, and resumption

- OpenAlex configures five client retries, a backoff factor of two, and retry status codes `429`, `500`, `502`, `503`, and `504`.
- Semantic Scholar pauses one second before each request. On `429`, it waits another five seconds and retries without a configured overall retry ceiling.
- Other unsuccessful Semantic Scholar HTTP responses are logged and raised.
- Both search functions flush pending records after a caught request exception, print continuation information, and re-raise the error.
- OpenAlex accepts `cursor` and `start_batch`; Semantic Scholar accepts `start_token` and `start_batch`.
- Continuation values are printed, not persisted in a durable run manifest. Resume with the same query and source filters.
- Semantic Scholar's `requests.get` does not specify a timeout. This is an operational limitation rather than a bounded-response guarantee.

## 5. Canonical Publication Records and Local Persistence

### 5.1 Canonical data contract

The `Publication` dataclass provides a source-neutral interchange format:

| Field | Role |
|---|---|
| `source`, `source_id` | Provider namespace and provider identifier |
| `type` | Defaults to `Publication` |
| `title` | Cleaned title; falls back to `Untitled Work` |
| `authors`, `author_ids` | Author names and aligned optional provider identifiers |
| `references` | Provider referenced-work identifiers, when supplied |
| `publication_year`, `publication_date` | Bibliographic date information |
| `publication_type`, `citations` | Provider classification and citation count |
| `doi`, `url` | Canonical DOI string and external landing-page link |
| `abstract` | Cleaned abstract or null |

Unknown optional values remain null or empty lists rather than descriptive placeholder strings.

### 5.2 Cleaning decisions

The shared cleaner:

1. Rejects a blank publication identifier.
2. Collapses line breaks and repeated whitespace.
3. Removes blank author names while retaining their paired IDs.
4. Removes blank reference strings.
5. Derives the year from the first four date characters when the year is absent.
6. Removes DOI URL prefixes or a leading `doi:` and lowercases the result.
7. Normalizes blank optional text fields to null.

This is structural normalization, not comprehensive validation. It does not resolve DOI validity, identify retractions, normalize author identities across providers, reconcile synonymous titles, validate every date, or map concepts to a biomedical ontology.

Author-name/ID pairing uses `zip`; malformed records with mismatched nonempty list lengths can lose unmatched entries. Source adapters ordinarily supply aligned lists.

### 5.3 Duplicate control and JSONL batches

`get_existing_ids` scans saved publication JSONL files and builds a set of `(source, source_id)` pairs. `PublicationBuffer` also tracks pending identities, suppressing duplicates both across saved files and within the current buffer.

Records accumulate across API pages. A buffer flush occurs at **1,000 publications**, with a final partial flush at the end of retrieval. Output names are `batch-<UUID>.jsonl` under [src/publications](../src/publications).

Each file contains one UTF-8 JSON object per line. The buffer first writes a temporary `.tmp` file and renames it to `.jsonl`; saved identities are updated only after the write succeeds.

This reduces exposure to partially published batch files. It does not provide multi-process coordination, a global lock, or a query-specific manifest. Scanning all existing files also becomes more expensive as the local corpus grows.

Cross-provider DOI duplicates are intentionally not removed at this collection stage. Raw normalized records preserve source-specific metadata for later processing.

### 5.4 Optional Markdown export

The shared utility can export JSONL to source-grouped Markdown files with JSON-encoded YAML-compatible front matter and an abstract section. It is an optional presentation/export mechanism, not the database ingestion format.

## 6. Publication-Level Vector Ingestion

### 6.1 Input and processing

The ingestion script reads sorted `*.jsonl` files from the publication directory. `ingest_files(quantity=None)` processes all files unless an explicit positive file limit is supplied. Each file is read into memory, then processed in batches of **100** by default.

Before any embedding request, the script queries `publications` for existing source/ID pairs and non-null DOI values. It suppresses duplicates within the pending batch as well.

The embedding text is:

```text
Title: <title>. Abstract: <abstract>
```

The implementation uses OpenAI `text-embedding-3-small` with an explicitly requested dimension of **512**. Response entries are ordered by their returned index and checked for the expected record count.

### 6.2 Transactions and restart behavior

Each batch is committed independently using a connection transaction context. Inserts use `ON CONFLICT DO NOTHING`, providing a final database-level safeguard when another writer inserts the same identity after the initial check.

Expected embedding, database, and record-shape errors are printed; the failed batch is rolled back and processing continues. A later rerun skips committed identities and retries unsaved records.

Important boundaries:

- Already stored records are skipped, not updated when upstream metadata changes.
- A database rollback cannot reverse a completed external embedding request.
- Concurrent writers can still incur duplicate embedding cost before the uniqueness constraint resolves the conflict.
- JSONL parsing occurs before the per-batch handler; a malformed file can prevent its processing.
- The raw JSONL retains fields, such as citation counts and author IDs, that this relational ingestion path does not store.

## 7. Local Knowledge-Graph Extraction

### 7.1 Active model and design rationale

The UI executes [graph_extraction_gliner.py](../src/Ingest_Publications/graph_extraction_gliner.py), using **`fastino/gliner2.5-small-v1`** through GLiNER's `AutoExtractor`, explicitly loaded on CPU.

The design separates:

- **Deterministic bibliographic construction:** publication, author, and reference nodes and their relationships.
- **Predicted semantic extraction:** entity spans and their role in the publication.

Bibliographic metadata is therefore not regenerated by a language model. Local extraction avoids a paid remote generation request per paper, although model acquisition may require a first-run download. Later embedding stages still call an external API.

### 7.2 Deterministic identifiers

| Node | Identifier policy |
|---|---|
| Publication | `paper:<URL-encoded source>:<URL-encoded source_id>` |
| Author with provider ID | `author:provider:<encoded source>:<encoded author_id>` |
| Author without provider ID | `<paper_id>:author:<author position>` |
| Reference | `<paper_id>:reference:<reference position>` |
| Extracted concept | `<lowercase label>:<lowercased, whitespace-normalized span>` |

These policies preserve source provenance and avoid accidental reuse of a provider ID in another provider's namespace.

However:

- The same work in two providers can become two publication nodes.
- The same author in two providers is not automatically reconciled.
- References are paper-specific placeholders, not globally resolved publication nodes.
- Equal concept labels and normalized names share an ID; synonyms and abbreviations normally remain different nodes.
- Identical text under different labels remains distinct.

### 7.3 Node and relationship vocabulary

| Extracted node type | Meaning | Possible publication role |
|---|---|---|
| `Method` | Algorithms, architectures, analytical methods | `USES_METHOD` |
| `Task` | Prediction, classification, diagnosis, segmentation | `ADDRESSES_TASK` |
| `Medical_Condition` | Diseases and clinical conditions investigated | `STUDIES_CONDITION` |
| `Data_Modality` | MRI, CT, images, health records, other data types | `EVALUATED_ON` or `TRAINED_WITH` |
| `Metric` | Performance measures | `MEASURED_BY` |
| `Dataset` | Named research datasets | `EVALUATED_ON` or `TRAINED_WITH` |
| `Chemical_or_Drug` | Named medications and chemical substances | `MENTIONS` in the current role schema |
| `Institution` | Named hospitals, universities, organizations | `MENTIONS` |
| `Symptom` | Clinical signs or symptoms | `MENTIONS` |

Deterministic relationships are:

```text
Author      --AUTHORED-->          Publication
Publication --CITES-->             Reference
Publication --predicted role-->    Concept
```

The active extractor does not predict concept-to-concept causal relationships or create a complete citation network between resolved publications.

### 7.4 Extraction parameters and evidence checks

| Parameter | Value |
|---|---|
| Extraction input | Title, newline, abstract |
| Entity-confidence threshold | `0.5` |
| Publication-role confidence threshold | `0.75` |
| Maximum distinct semantic entities per paper | `7` |
| Long-text chunk size | `200` as passed to `extract_long` |
| Chunk overlap | `40` |
| Inference batch size | `1` |
| Returned evidence | Confidence and source spans |

Candidate entities are ordered with medical conditions first and then by descending confidence. This gives conditions priority under the seven-entity budget; it is a deliberate domain emphasis, not an unbiased sample of all concepts.

Each retained span must match the corresponding substring of the extraction input. Names are lowercased and whitespace-normalized. A specific relationship is retained only when the predicted role meets the role-confidence threshold and permits the entity's type. Otherwise the relation becomes `MENTIONS`.

If a target has a specific relationship, redundant `MENTIONS` edges to that target are removed. Duplicate `(source, target, relation)` triples are collapsed.

The span check establishes that an entity string occurs in the input; it does not prove that the relationship interpretation is correct. Role confidence is model output, not a calibrated probability of clinical truth. The graph currently stores empty properties for extracted concepts and their edges, so returned confidence/span evidence is not retained as structured graph provenance.

When an abstract is absent, the extractor produces bibliographic nodes and relationships only; it does not extract semantic entities from the title alone.

### 7.5 Output and restart semantics

Extracted graphs are appended to [src/graph_extracted](../src/graph_extracted) as `graph_publications-000001.jsonl`, rotating every **1,000 graphs**.

Each graph contains:

```json
{
  "paper_id": "paper:openalex:EXAMPLE",
  "source": "openalex",
  "source_id": "EXAMPLE",
  "doi": null,
  "nodes": [],
  "edges": []
}
```

Publication-node properties retain source, source ID, DOI, date, URL, and abstract.

On startup, completed output files are scanned for publication IDs and the last file's line count. Completed papers are skipped; failed papers remain eligible on the next run. Missing final newlines are treated as incomplete writes and require repair before append. Invalid input records and extraction failures are logged and counted.

The model is loaded lazily when the first unprocessed publication with an abstract is reached. Append-and-close behavior improves restartability, but it is not a transactional multi-writer journal.

## 8. Graph Validation, Embedding, Archiving, and Loading

### 8.1 Compatibility validation

The loader supports the active extraction vocabulary plus selected historical labels and relations imported from the alternative extractor. Examples include `Condition`, `Model_Architecture`, `Algorithm`, and `TARGETS_TASK`.

Before requesting embeddings, it checks:

- Object structure with node and edge lists.
- Nonempty, unique node IDs.
- Exactly one publication node matching `paper_id`.
- Recognized labels and relationships.
- Text node names and object-valued properties.
- Existing source and target endpoints for every edge.

Edges with recognized vocabulary but invalid publication-centered orientation are logged and skipped. Thus historical relation names in the accepted vocabulary do not imply that arbitrary concept-to-concept edges are loaded.

### 8.2 Batch deduplication and embedding reuse

Graph loading defaults to **100 graphs per group**. The loader:

1. Skips publication IDs already present as publication nodes.
2. Keeps one graph per new publication ID within the group.
3. Merges shared nodes and identical edge triples.
4. Rejects inconsistent name/label combinations for a shared node ID within the group.
5. Reuses stored concept embeddings when node ID and name agree.
6. Uses suitable vectors already attached to input nodes where available.
7. Embeds remaining unique concept names with `text-embedding-3-small`, dimension **512**, in API requests of at most **256 texts**.

Unlike the publication-vector branch, concept vectors encode the **concept name**, not the title, abstract, or complete graph neighborhood.

Publication, author, and reference nodes are not assigned new embeddings by this loader. A publication vector in `publications.embedding` is therefore not interchangeable with, or automatically copied into, `kg_nodes.embedding`.

### 8.3 Archive and commit order

Before database insertion, embedding-enriched graphs are saved to [src/graph_output](../src/graph_output). Archive files rotate every **1,000 graphs**, independently of the 100-graph database grouping.

The database write then:

- Upserts nodes by ID, merging JSONB properties with incoming values taking precedence.
- Preserves an existing embedding when the incoming value is null.
- Upserts edges by `(source, target, relation)` and merges their properties.
- Commits nodes and edges together.

The archive precedes the database commit. Therefore an archive record does not prove that its database load succeeded. A retry after database failure can append the same graph again to the archive.

Archived graphs can be supplied as loader input. When input and archive directories resolve to the same directory, the loader suppresses re-archiving. Existing committed paper IDs are skipped, so normal reruns do not refresh their graph or metadata automatically.

Failed groups are rolled back where possible, logged, and counted; processing continues. Original graph input files are unchanged.

## 9. PostgreSQL Database Design

The project uses PostgreSQL hosted on Neon, with **pgvector** for semantic vectors. The schema also enables **pg_trgm**, although the reviewed retrieval functions do not use trigram queries.

### 9.1 `publications`: document retrieval representation

| Column | SQL type / constraint | Purpose |
|---|---|---|
| `id` | `SERIAL PRIMARY KEY` | Internal relational identifier |
| `source`, `source_id` | `TEXT`; composite unique constraint | Provider identity |
| `publication_date` | `DATE` | Bibliographic date |
| `doi` | `TEXT UNIQUE` | Cross-provider duplicate suppression when non-null |
| `url` | `TEXT` | Publication landing page |
| `references` | `TEXT[] NOT NULL DEFAULT '{}'` | Referenced provider identifiers |
| `title` | `TEXT NOT NULL` | Publication title |
| `abstract` | `TEXT` | Abstract text |
| `authors` | `TEXT` | Author data as declared by the setup script |
| `embedding` | `VECTOR(512)` | Title-and-abstract vector |

PostgreSQL permits multiple null DOI values under the unique constraint. Records without DOI rely on source identity; same-title works with different source identities can remain separate.

**Schema alignment caveat:** the ingestion code passes author lists, whereas setup declares `authors TEXT`. This is not a normalized author table or an explicitly declared text-array column. Consumers should not assume that stored authors are consistently represented as an array.

### 9.2 `kg_nodes`: graph entities

| Column | SQL type / constraint | Purpose |
|---|---|---|
| `id` | `TEXT PRIMARY KEY` | Deterministic namespaced identity |
| `label` | `TEXT NOT NULL` | Entity class |
| `name` | `TEXT NOT NULL` | Human-readable title or concept name |
| `properties` | `JSONB DEFAULT '{}'` | Bibliographic or extensible metadata |
| `embedding` | `VECTOR(512)` | Concept-name vector, where available |

The database does not impose an enumerated type for `label`; allowed vocabulary is primarily enforced by application validation.

### 9.3 `kg_edges`: directed relationships

| Column | SQL type / constraint | Purpose |
|---|---|---|
| `id` | `SERIAL PRIMARY KEY` | Edge identifier |
| `source` | `TEXT NOT NULL`, foreign key to `kg_nodes.id` | Directed origin |
| `target` | `TEXT NOT NULL`, foreign key to `kg_nodes.id` | Directed destination |
| `relation` | `TEXT NOT NULL` | Relationship type |
| `properties` | `JSONB DEFAULT '{}'` | Extensible edge metadata |
| Triple constraint | `UNIQUE(source, target, relation)` | Prevent repeated identical relationships |

Both foreign keys use `ON DELETE CASCADE`. Deleting a node removes its incident edges. No foreign key connects publication graph nodes to `publications.id`; graph publication identity is source-derived, whereas the relational ID is generated.

### 9.4 Indexes and distance operators

| Index | Definition / role |
|---|---|
| Publication vector index | HNSW on `publications.embedding`, `vector_cosine_ops` |
| `idx_kg_nodes_flat` | HNSW on `kg_nodes.embedding`, `vector_ip_ops`, `m=16`, `ef_construction=100` |
| `idx_kg_edges_source_rel` | B-tree on `(source, relation)` |
| `idx_kg_edges_target_rel` | B-tree on `(target, relation)` |
| Primary/unique indexes | Entity IDs and publication/edge identity constraints |

Despite its historical name and comments, `idx_kg_nodes_flat` is a pgvector **HNSW index**, not a separate FlatNav database engine.

Publication search uses `<=>` for cosine distance. Concept search uses `<#>` for negative inner product, with ascending order selecting larger inner products. Their relationship to cosine rankings depends on vector normalization; these scores should not be presented as interchangeable percentages. HNSW is approximate nearest-neighbor retrieval and introduces recall/performance trade-offs.

### 9.5 Setup safety and implementation limitations

**Do not run the setup script unchanged against a populated graph.** Its current main block explicitly drops `kg_edges` and `kg_nodes` before recreating them.

The publication-table setup issues `CREATE INDEX CONCURRENTLY` inside a transaction context. PostgreSQL does not permit concurrent index creation within a transaction block. The index statement also lacks `IF NOT EXISTS`. Accordingly, the script is not a production migration system and must not be described as a safe, repeatable, non-destructive schema deployment.

The schema and index definitions above describe the source code. Their presence and consistency in a particular deployed database must be verified separately.

## 10. Downstream Search and Graph Exploration

### 10.1 Publication semantic search

`search_publications` embeds the user's query with the same model and dimension as publication ingestion, orders records by cosine distance, and returns a configurable number of results (`top_k=10` by default). An optional flag requires nonblank abstracts.

This compares a query vector with document vectors; it is not full-text keyword search or a relevance classifier trained on review decisions.

### 10.2 Concept-first publication discovery

`search_documents_via_graph` takes a list of queries (the Explorer passes the Medical Condition/Topic and Method/Task inputs). Each query is embedded on its own, and its five nearest concepts among `Method`, `Task`, `Medical_Condition`, `Data_Modality`, and `Metric` are kept when their similarity is at least `MIN_CONCEPT_SIMILARITY`. Stored edges (publication → concept) lead to the publications. It sets `hnsw.ef_search=100`.

Publications are ranked at the publication level and the best 10 are returned with all their matched concept edges. A publication related to more of the queries ranks first; ties are broken by the sum, over the queries, of the best concept similarity found for each. Publications that match only some of the queries still follow the ones that match all.

Results become visualization nodes and edges with node type, bibliographic properties, and relationship labels.

### 10.3 One-hop retrieval

`get_one_hop` loads incoming and outgoing stored edges incident to a specified paper, with both endpoints' names, labels, and properties. Nodes and edge triples are deduplicated in Python using sets.

An isolated publication has no edge rows and therefore is not returned as a standalone node by this function.

### 10.4 Bounded related-paper expansion

The current `get_two_hops` is **not an exhaustive, strictly topological two-hop traversal**. It combines exact shared-concept paths with embedding-based concept expansion:

1. Retrieve the selected paper's first-hop graph.
2. Treat non-publication, non-author, non-reference neighbors as concepts.
3. Include each concept as an exact match.
4. For concepts of selected research types, retrieve up to three nearby embedded nodes by default using negative inner product.
5. Follow paper-to-concept edges to candidate publications.
6. Count distinct original concepts matched exactly and through semantic expansion.
7. Rank lexicographically by exact count, then similar count, then ID.
8. Restrict preliminary candidates to 100, suppress papers already shown and exact-title duplicates, and keep up to five additional publications.
9. Load existing edges between selected related papers and the allowed nodes.

Semantic-only matches are added as publication nodes even when they have no stored edge to the displayed first-hop graph. No synthetic similarity relationship is written to the database.

Methodological qualifications:

- An exact match means the **same concept ID**, not a scientifically established "100% relevance" score.
- Exact counts always outrank semantic counts; the procedure is not a single calibrated similarity measure.
- Similarity search has no minimum similarity threshold and does not restrict every candidate to the original concept's label.
- One original concept may contribute to both counts if a candidate paper connects to it and a nearby concept.
- The 100-candidate cutoff occurs before final title filtering; fewer than five distinct papers can result even when additional eligible papers exist.
- Exact-title deduplication selects a representative record; it does not merge metadata, DOI values, or all relationships of duplicate records.
- Papers reached through semantically similar nodes may not be reachable by two stored edges from the selected paper.

### 10.5 Visualization and links

The **Explorer** page caches related-paper graph results for five minutes per paper. Reference nodes can be hidden along with their incident edges. Clicking a publication opens its relationship view with author names, publication date, abstract, and an available DOI or URL link.

The **Search** page performs publication-vector semantic search, optionally filters to records with abstracts, and displays selected-publication details alongside its graph. The **Home** page shows collection counts, the available date range, and a publication example that can be sent to Search. The **AI Assistant** page is currently a placeholder, not a working assistant feature.

DOI and URL are read from publication-node properties. A missing DOI is not repaired by graph traversal; link availability depends on ingested metadata. Large graphs can remain expensive to serialize and lay out even when the database query is fast.

## 11. Configuration and Operational Boundaries

| Configuration | Usage |
|---|---|
| Python | Project supports Python 3.12; Docker image specifies 3.12.10 |
| `NEON_DATABASE_URL` | PostgreSQL connection |
| `OPENAI_KEY` | Publication and concept embeddings; alternative hosted extraction |
| `OPENALEX_API_KEY`, `USER_EMAIL` | OpenAlex client configuration |
| `S2_API_KEY` | Semantic Scholar authenticated requests when supplied |
| Optional dependency group `extraction` | GLiNER local extraction dependencies |

The adapters load `prod.env` relative to the working directory. Database and embedding modules generally resolve it from the repository root relative to their file paths. Deployment environments may supply variables directly.

The repository includes [.env.example](../.env.example) with placeholder names; copy it to `prod.env` and fill in local credentials. The example is not a source of real keys.

Credentials must not be included in documentation, exported research datasets, screenshots, or version control. The local extractor processes abstracts locally, but publication embedding sends title/abstract text to OpenAI, and graph embedding sends concept names. This external processing should be disclosed in the research data-management methodology.

The container installs dependencies from `pyproject.toml`; its current installation command does not enforce the full `uv.lock` resolution. Reproducibility claims should distinguish pinned direct dependencies from an exact, frozen dependency environment.

## 12. Recovery, Auditability, and Data Quality

| Stage | Completion marker | Restart behavior | Important caveat |
|---|---|---|---|
| Retrieval | Successfully published JSONL batch | Skip saved source/ID pairs | Continuation tokens are printed, not durably recorded |
| Publication ingestion | Committed identity/DOI in `publications` | Skip before embedding | Existing metadata is not refreshed |
| Extraction | Complete graph JSONL line with paper ID | Skip completed papers | Torn lines require repair |
| Graph archive | Appended enriched JSONL line | Can replay archive | Archive may precede a failed database commit |
| Graph load | Publication node in committed graph batch | Skip existing paper IDs | Partial/manual loads can defeat paper-level completion assumptions |
| UI | Console logs and stage messages | Operator reruns selected steps | Success messages do not prove zero skipped or failed records |

The UI reports stage completion when called functions return. Several stages log individual failures and continue, so operators must inspect failure counts and logs rather than relying exclusively on green completion messages.

The implementation has no centralized run manifest, experiment identifier, immutable extraction-model revision, or stored per-edge extraction evidence. It is restartable in important local ways but is not an end-to-end exactly-once workflow.

## 13. Academic Review and Evaluation Requirements

### 13.1 Claims supported by the implementation

- Two-provider metadata collection with a shared normalized record structure.
- DOI-aware deduplication for publication-vector ingestion.
- Source-scoped graph identities and deterministic bibliographic edges.
- Local, constrained semantic extraction with span validation and confidence thresholds.
- Reuse of concept embeddings and independently committed graph batches.
- Combined document-vector and concept/graph-based exploration.

### 13.2 Claims that require independent evidence

The code alone does not establish exhaustive coverage, source equivalence, extraction accuracy, clinical correctness, calibrated confidence, optimal ranking, or superior retrieval effectiveness. Nor does it establish that the database reflects every downloaded or extracted record.

For an academic report, retain and report:

1. **Collection protocol:** exact source-specific query strings, dates, retrieval times, credentials/access tier where relevant, limits, and continuation settings.
2. **Corpus accounting:** fetched, accepted, duplicate, abstract-missing, failed, extracted, and loaded record counts by source.
3. **Version information:** repository commit, dependency environment, extraction model revision, embedding model/dimension, and schema/index state.
4. **Extraction evaluation:** a manually annotated sample with entity precision/recall, relation precision/recall, and analysis of background mentions versus study-specific roles.
5. **Ranking evaluation:** judged queries and seed papers; comparison of document search, exact shared-concept ranking, and semantic concept expansion.
6. **Performance evaluation:** connection time, SQL execution time, embedding latency, cold/warm runs, output size, and browser layout time measured separately.
7. **Sensitivity analysis:** entity/role thresholds, the seven-concept budget, nearest-concept count, candidate cutoff, and final publication limit.
8. **Bias and provenance analysis:** source coverage, missing abstracts, condition-first prioritization, duplicate editions, and absent citation resolution.

No unmeasured latency, accuracy, or recall guarantee is asserted in this document.

## 14. Design Decisions and Trade-offs

| Decision | Rationale | Trade-off |
|---|---|---|
| Shared dataclass and JSONL | Consistent adapters; inspectable, restartable artifacts | Repeated file scans and limited run provenance |
| Separate vector and graph branches | Complementary retrieval without coupling stage execution | Different identities, duplicates, and coverage across stores |
| 512-dimensional embeddings | Explicit common vector size for both retrieval paths | Model/dimension changes require migration or re-embedding |
| Local GLiNER extraction | Constrained span/role extraction without per-paper hosted generation | CPU throughput and model-dependent extraction quality |
| Seven semantic nodes, conditions first | Bound graph growth and emphasize clinical topics | Secondary methods/tasks can be omitted |
| `MENTIONS` fallback | Avoid overasserting a study-specific role | More weakly informative relationships |
| Source-scoped paper/author IDs | Preserve provider provenance | Cross-provider entities remain unresolved |
| Shared concept IDs by label and name | Reuse nodes and embeddings | Lexical variation produces distinct concepts |
| Exact-first semantic expansion | Preserve direct shared evidence while broadening discovery | Not a calibrated semantic relevance score |
| Batch commit and retry | Limit lost work and avoid repeat paid requests | Files, APIs, and database commits are not atomic together |

## 15. External Technical References

The following references describe the external services and mechanisms used; repository code remains authoritative for this implementation's actual settings.

- OpenAlex. [API documentation](https://docs.openalex.org/).
- de Bruin, J. [PyAlex: Python interface for OpenAlex](https://github.com/J535D165/pyalex).
- Semantic Scholar. [Academic Graph API documentation](https://api.semanticscholar.org/api-docs/graph).
- OpenAI. [Embeddings guide](https://platform.openai.com/docs/guides/embeddings).
- Fastino. [GLiNER2 implementation](https://github.com/fastino-ai/GLiNER2) and [configured model repository](https://huggingface.co/fastino/gliner2.5-small-v1).
- pgvector. [PostgreSQL vector similarity search](https://github.com/pgvector/pgvector).
- PostgreSQL. [TABLESAMPLE and SELECT](https://www.postgresql.org/docs/current/sql-select.html) and [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).
- Streamlit. [Caching overview](https://docs.streamlit.io/develop/concepts/architecture/caching).

### Related project documentation

- [Understanding the transformation and cleaning utilities](transform_clean_guide.md).
- [Knowledge Graph Approach](Knowledge%20Graph%20Approach.md).
- [GLiNER Extraction Pipeline](GLiNER%20Extraction%20Pipeline.md).
- [GLiNER Quick Start](GLiNER%20Quick%20Start.md).
