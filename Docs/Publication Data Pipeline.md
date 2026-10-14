# Publication Data Pipeline

> **Citation:** This document was created with the assistance of GitHub Copilot
> (GitHub, 2026), an AI programming assistant. https://github.com/features/copilot

For an educational explanation of every shared utility import, class, and
function, see [Understanding transform_clean.py](transform_clean_guide.md).

## Purpose

Collect publication metadata and abstracts about AI and data science in
healthcare from three sources:

- [search_openalex.py](search_openalex.py): OpenAlex.
- [search_arxiv.py](search_arxiv.py): arXiv.
- [search_sem_scholar.py](search_sem_scholar.py): Semantic Scholar.

The scripts save results as local JSONL batches. Markdown export is optional.
They collect metadata and abstracts, not PDF files or full article text.
The collection provides candidates for literature review and later analysis;
matching search terms does not guarantee that a paper actually applies AI to
healthcare.

## High-Level Design

```text
Healthcare terms + AI/data-science terms + source-specific filters
                              |
                 Run a source search script
                              |
              Read IDs already saved locally
                              |
                 Fetch results page by page
                              |
             Map API fields to a Publication record
                              |
               Skip previously saved source IDs
                              |
             Serialize publication records as JSON
                              |
               Save files in src/publications
                              |
              Report progress and review results
```

Each search script owns its API queries, pagination, and `to_publication`
adapter. [transform_clean.py](transform_clean.py) owns the shared `Publication`
dataclass, whitespace and DOI cleaning, filename generation, duplicate
detection, JSONL batching, and optional Markdown export. It has no third-party
dependencies.

Each script runs independently. There is no central orchestrator, shared
database, or automatic relevance-screening stage. Adding a source requires an
API adapter returning `Publication` records; output formatting does not need
to be copied.

## Logical Steps

### 1. Define the search

The calls under each script's `if __name__ == "__main__":` block define the
topics and filters used when the script runs.

The current searches combine two groups:

- Healthcare or application terms, such as healthcare, clinical, disease
  diagnosis, and medical imaging.
- Method terms, such as artificial intelligence, machine learning, deep
  learning, and computer vision. OpenAlex also explicitly includes data science.

Use `OR` within a group and `AND` between groups. Search syntax is
source-specific: arXiv uses field prefixes such as `all:`. Semantic Scholar
bulk search uses `|` for OR and `+` for AND, with parentheses for groups and
quotes for phrases. It matches titles and abstracts without `all:` prefixes.
Its main query combines healthcare and AI terms; add `+ {application_terms}`
to the query to also require a specific application.

### 2. Load configuration and existing IDs

OpenAlex and Semantic Scholar load configuration from `prod.env`, relative to
the working directory:

| Variable | Used by |
|---|---|
| `OPENALEX_API_KEY` | OpenAlex client |
| `USER_EMAIL` | OpenAlex client |
| `S2_API_KEY` | Semantic Scholar request header, when provided |

arXiv does not use an API key in this implementation. Keep credentials out of
version control.

The shared helper streams records from JSONL batches in
[src/publications](../publications) and builds a set of `(source, source_id)`
pairs. All scripts write directly to this directory; subdirectories are not
scanned. Old Markdown files are not migrated or used for duplicate detection.
Recollect or separately migrate an old Markdown collection before resuming.

### 3. Retrieve results in pages

Pagination keeps the scripts from loading the entire collection at once.

| Source | Retrieval design | Current ordering and filters |
|---|---|---|
| OpenAlex | `pyalex.Works`, pages of 200 records | Searches title and abstract; requires an abstract; filters by publication date; newest publication date first |
| arXiv | `arxiv.Client`, pages and processing batches of 100 | Searches the supplied field-based query; newest submission first; three-second delay between requests |
| Semantic Scholar | Bulk HTTP search, up to 1,000 records per response, with continuation tokens | Supplies a Boolean title/abstract query and year range; does not set an explicit sort order |

The functions have different result-limit behavior:

- **OpenAlex:** `max_results` caps retrieved records through `n_max`.
- **arXiv:** `max_results` is the overall result-position limit.
  `start_offset` allows resuming at a later position.
  Optional `from_date` and `to_date` restrict submission dates, including both
  days in UTC. Supply both as `YYYY-MM-DD`, or omit both for an unrestricted
  search. Invalid or reversed ranges raise `ValueError` before retrieval.
- **Semantic Scholar:** the loop stops when newly saved records reach
  `max_results`. It can retrieve more records because duplicates do not count,
  and the final batch can save more than the requested limit.
  Each returned token requests the next batch; a missing token ends the search.

These values are limits, not guarantees of how many matches exist.

### 4. Extract and normalize metadata

Each API adapter maps its response to the same `Publication` dataclass. The
shared layer collapses whitespace in titles, author names, and abstracts;
normalizes DOI URLs or `doi:` prefixes to lowercase bare DOI identifiers;
and derives a year from the publication date when necessary.

- OpenAlex reconstructs abstract text from its inverted-index representation
  through `pyalex.Work`.
- arXiv supplies abstract text directly. Version suffixes are removed from
  arXiv IDs, including historical IDs containing a slash.
- Semantic Scholar supplies abstract text directly and reads DOI information
  from `externalIds`. It also requests publication dates and types; multiple
  publication types are joined into one comma-separated string.

Unknown metadata uses `None` in Python and `null` in JSON. Authors always use
a list; citation counts and years are integers or `null`. A missing title
becomes `Untitled Work`. Missing source IDs raise an error instead of producing
ambiguous files. `doi` and `url` are separate fields: the latter retains the
source's landing page or arXiv PDF link, even when a DOI is available.

If no abstract is available, JSONL stores `null`. Optional Markdown export
uses `*No abstract available.*` in the body.

### 5. Skip already saved records

Before writing, each script checks `(source, source_id)` against the existing-ID
set. After publishing a batch, it adds its keys to that set to avoid duplicates
during the same run.

Deduplication is **by source and publication ID**, not by DOI or title.
Identical IDs from different providers remain separate records. Existing
records are skipped, not refreshed with newer citations or metadata. arXiv
versions are treated as the same record.

### 6. Write JSONL batches

All scripts write UTF-8 batches to [src/publications](../publications), using:

```text
batch-{unique_id}.jsonl
```

Each line contains one complete publication object, including `abstract`.
Each search keeps a `PublicationBuffer` across API pages. Duplicates are removed
before buffering, including duplicates of records still pending. The writer
publishes a file when it reaches 1,000 unique records. Search completion or a
handled API error flushes the remainder, which may contain fewer than 1,000.
Buffers are not shared across topics or process restarts, and existing files
are not repacked. Empty or duplicate-only searches produce no file. Batch names
are generated with the standard-library `uuid` module and do not contain source
IDs or titles.

A batch is written to a temporary file and renamed only after writing succeeds.
Temporary files are ignored during duplicate lookup. Exceptions propagate and
failed batches do not mark their records saved. This assumes sequential writers;
there is no shared database, concurrent-writer coordination, or persisted API
checkpoint.

Progress reports distinguish accepted new records, records saved to disk, and
pending buffered records. Semantic Scholar counts saved plus pending records
toward its existing per-query target. A hard process termination can lose the
pending in-memory buffer (at most 999 records), which can be fetched on a rerun.
The `save_results` helper remains available for immediate saving and flushes
its final partial batch before returning.

Every source writes the same fields. Example record (pretty-printed here;
each actual record occupies one line):

```json
{
  "source": "openalex",
  "source_id": "W123456789",
  "title": "Machine Learning for Clinical Diagnosis",
  "type": "Publication",
  "authors": ["Jane Smith", "John Doe"],
  "author_ids": ["A5023888391", null],
  "references": ["W2741809807", "W1998765432"],
  "publication_year": 2025,
  "publication_date": "2025-06-15",
  "publication_type": "article",
  "citations": 42,
  "doi": "10.1234/example",
  "url": "https://openalex.org/W123456789",
  "abstract": "The study applies machine learning to a clinical diagnosis task."
}
```

`source` is `openalex`, `arxiv`, or `semantic_scholar`; `source_id` is the
provider's identifier. All other keys shown above appear for every source.
arXiv citations and publication type, for example, are `null`. The `type` field
defaults to the string `"Publication"`.

`author_ids` has the same length and order as `authors` (`null` when the
provider has no ID). IDs come from the provider: OpenAlex author IDs (`A...`) or
Semantic Scholar `authorId`. arXiv has no author IDs, so all values are `null`.
`references` lists IDs of the works this publication cites. Only OpenAlex
provides them (`W...` work IDs). They are empty for arXiv and for Semantic
Scholar, whose bulk search does not return references.

This is the only supported output schema. To open a DOI, prefix `doi` with
`https://doi.org/`; otherwise use `url`.

#### Optional Markdown export

Use `batch_to_markdown` for one batch, or loop over batch paths:

```python
from pathlib import Path
from src.utils.transform_clean import OUTPUT_DIR, batch_to_markdown, read_jsonl

for batch in OUTPUT_DIR.glob("*.jsonl"):
    batch_to_markdown(batch, Path("markdown"))
```

Exports use `{source}/{encoded_id}_{normalized_title}.md`, keeping source names
out of filenames while avoiding collisions between providers. IDs are encoded
only for filenames; the full ID remains in metadata. Re-exporting overwrites
matching paths. Each document has YAML frontmatter and an Abstract section.
For vector/graph ingestion, `read_jsonl(batch)` yields `Publication` objects
one at a time without loading a whole batch. Invalid records report their file
and line number.

### 7. Report progress and handle errors

- **OpenAlex** reports newly saved publications per page. API/network errors are
  printed and re-raised; data and local file errors propagate directly.
  A failed run does not print `Finished`.
- **arXiv** reports retrieved records, existing records skipped, and new publications.
  On a handled API/network error, it stops the current topic without retries,
  reports an incomplete search and a resume offset, and returns `False`. A later
  topic call can still run. Local file errors are not suppressed.
- **Semantic Scholar** reports newly saved publications. HTTP 429 responses wait five
  seconds and retry without a retry limit. Other non-200 responses stop the
  search by raising an HTTP error. The sequential script sleeps one second
  before every request, with or without an API key, including retries and new
  topic calls. Do not run concurrent searches or other clients using the same
  key without coordinating their requests across endpoints. Request errors
  are printed and re-raised; data and local file errors propagate directly.

Saved files remain available after a later request fails. Check error messages
as well as final summaries; a result limit can end a search before all matches
have been retrieved.

## Running the Pipeline

Use Python 3.10 or later and install the dependencies declared in
[pyproject.toml](../../pyproject.toml). With `uv`, run from the repository root:

```powershell
uv sync
uv run python .\src\utils\search_openalex.py
uv run python .\src\utils\search_arxiv.py
uv run python .\src\utils\search_sem_scholar.py
```

Alternatively, with the project's virtual environment already prepared:

```powershell
.\.venv\Scripts\python.exe .\src\utils\search_openalex.py
.\.venv\Scripts\python.exe .\src\utils\search_arxiv.py
.\.venv\Scripts\python.exe .\src\utils\search_sem_scholar.py
```

The scripts do not currently accept command-line search arguments. Edit their
main-block calls or call their search functions from Python:

| Function | Defaults |
|---|---|
| `openalex_search_topic(topic, from_date, max_results)` | Date: `2024-01-01`; retrieved limit: 100,000 |
| `arxiv_search_topic(topic, max_results, start_offset=..., from_date=..., to_date=...)` | Overall limit: 1,000; starting offset: 0; dates: unrestricted |
| `semantic_scholar_search_topic(topic, year_range, max_results)` | Years: `2024-`; new-record target: 1,000 |

The main-block calls can override these defaults. In the current scripts,
OpenAlex searches from 2010, arXiv requests up to 100,000 records per topic, and
Semantic Scholar requests a target of 100,000 newly saved records.

To split an arXiv query into separate years:

```python
from src.utils.search_arxiv import arxiv_search_topic

for year in range(2020, 2025):
    arxiv_search_topic(
        'all:healthcare AND all:"machine learning"',
        max_results=10000,
        from_date=f"{year}-01-01",
        to_date=f"{year}-12-31",
    )
```

Each call has its own retrieval limit. Use smaller date windows if a year has
too many matches. When resuming with `start_offset`, keep the same query and
date range.

## Offline Tests

Run from the repository root; no API calls or credentials are required:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover source adapters, identical output keys, missing metadata, cleaning,
source-specific duplicate detection, bounded JSONL batches, Markdown conversion,
write failures, and mocked search loops. The writer consumes iterables rather
than collecting all results in memory. Duplicate detection streams all saved
JSONL records and keeps their source/ID pairs in memory. A database index can
replace that scan later if startup time or memory becomes a bottleneck.

## Review and Downstream Use

After collection:

1. Check errors and retrieval summaries for incomplete searches.
2. Stream JSONL metadata and abstracts for relevance screening.
3. Keep papers that actually use AI or data science for a healthcare task.
4. Separate application studies from reviews or general discussions as needed.
5. Deduplicate across sources by DOI or other bibliographic identifiers before
   reporting unique-paper counts.

These review steps are recommended downstream work; the search scripts do not
perform them automatically. Source coverage, missing abstracts, API limits,
and search wording mean that the collection is not guaranteed to be exhaustive
or exclusively peer-reviewed.
