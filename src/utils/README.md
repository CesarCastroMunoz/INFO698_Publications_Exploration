# Publication Data Pipeline

## Purpose

Collect publication metadata and abstracts about AI and data science in
healthcare from three sources:

- [search_openalex.py](search_openalex.py): OpenAlex.
- [search_arxiv.py](search_arxiv.py): arXiv.
- [search_sem_scholar.py](search_sem_scholar.py): Semantic Scholar.

The scripts save results as local Markdown documents with YAML frontmatter.
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
                  Extract publication data
                              |
               Skip previously saved source IDs
                              |
             Format YAML metadata and Markdown body
                              |
               Save files in src/publications
                              |
              Report progress and review results
```

Each script runs independently. There is no central orchestrator, shared
database, or automatic relevance-screening stage.

## Logical Steps

### 1. Define the search

The calls under each script's `if __name__ == "__main__":` block define the
topics and filters used when the script runs.

For OpenAlex and arXiv, the current searches combine two groups:

- Healthcare or application terms, such as healthcare, clinical, disease
  diagnosis, and medical imaging.
- Method terms, such as artificial intelligence, machine learning, deep
  learning, and computer vision. OpenAlex also explicitly includes data science.

Use `OR` within a group and `AND` between groups. Search syntax is
source-specific: arXiv uses field prefixes such as `all:`, while the current
Semantic Scholar call uses a text query rather than the other scripts' Boolean
expression.

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

Each script scans existing Markdown filenames in
[src/publications](../publications) and extracts the ID before the first
underscore. This lets repeated searches skip records already saved locally.

### 3. Retrieve results in pages

Pagination keeps the scripts from loading the entire collection at once.

| Source | Retrieval design | Current ordering and filters |
|---|---|---|
| OpenAlex | `pyalex.Works`, pages of 200 records | Searches title and abstract; requires an abstract; filters by publication date; newest publication date first |
| arXiv | `arxiv.Client`, pages and processing batches of 100 | Searches the supplied field-based query; newest submission first; three-second delay between requests |
| Semantic Scholar | HTTP requests with a limit of 100 and an increasing offset | Supplies a text query and year range; does not set an explicit sort order |

The functions have different result-limit behavior:

- **OpenAlex:** `max_results` caps retrieved records through `n_max`.
- **arXiv:** `max_results` is the overall result-position limit.
  `start_offset` allows resuming at a later position.
- **Semantic Scholar:** the loop stops when newly saved records reach
  `max_results`. It can retrieve more records because duplicates do not count,
  and the final batch can save more than the requested limit.

These values are limits, not guarantees of how many matches exist.

### 4. Extract and normalize metadata

Each script extracts its source ID, title, authors, available publication
information, citation information, and link.

- OpenAlex reconstructs abstract text from its inverted-index representation
  through `pyalex.Work`.
- arXiv supplies abstract text directly. Its titles and abstracts have embedded
  newlines replaced with spaces. Version suffixes are removed from arXiv IDs.
- Semantic Scholar supplies abstract text directly and reads DOI information
  from `externalIds`.

If no abstract is available, the Markdown body contains
`*No abstract available.*`.

### 5. Skip already saved records

Before writing, each script checks the source ID against the existing-ID set.
After saving a record, it adds the ID to that set to avoid duplicates during
the same run.

Deduplication is **by source ID**, not by DOI or title across sources. The same
paper can therefore have separate OpenAlex, arXiv, and Semantic Scholar files.
Existing records are skipped, not refreshed with newer citations or metadata.
arXiv versions are treated as the same record.

### 6. Write YAML frontmatter and Markdown

All scripts write UTF-8 documents to [src/publications](../publications), using:

```text
{source_id}_{normalized_title}.md
```

Titles are normalized for filenames and truncated to 50 characters. The full
title remains inside the document.

Each document starts with YAML frontmatter, followed by a Markdown title and
an Abstract section. Metadata values are serialized with `json.dumps`, which
produces JSON-compatible YAML values and safely quotes strings.

Example OpenAlex document:

```markdown
---
title: "Machine Learning for Clinical Diagnosis"
openalex_id: "W123456789"
authors: ["Jane Smith", "John Doe"]
publication_year: 2025
publication_date: "2025-06-15"
publication_type: "article"
citations: 42
Link/DOI: "https://doi.org/10.1234/example"
---

# Machine Learning for Clinical Diagnosis

## Abstract

The study applies machine learning to a clinical diagnosis task.
```

Fields differ according to source availability:

| Field | OpenAlex | arXiv | Semantic Scholar |
|---|---|---|---|
| `title`, `authors` | Yes | Yes | Yes |
| Source ID | `openalex_id` | `arxiv_id` | `semantic_scholar_id` |
| `publication_year` | Yes | No | Yes |
| `publication_date` | Yes | Yes | No |
| `publication_type` | Yes | No | No |
| `citations` | Source count | `"N/A (arXiv)"` | Source count |
| `Link/DOI` | DOI value, or missing-value representation | DOI URL, otherwise PDF URL | DOI URL, otherwise source URL |

Missing values may be `null` or strings such as `"N/A"` depending on the source
response and the script's defaults. Citation values are not uniformly numeric
across the three sources.

### 7. Report progress and handle errors

- **OpenAlex** reports newly saved files per page. Caught exceptions are printed,
  but the script still prints its final `Finished` message.
- **arXiv** reports retrieved records, existing records skipped, and new files.
  On a handled API/network error, it stops the current topic without retries,
  reports an incomplete search and a resume offset, and returns `False`. A later
  topic call can still run. Local file errors are not suppressed.
- **Semantic Scholar** reports newly saved files. HTTP 429 responses wait five
  seconds and retry without a retry limit. Other non-200 responses stop the
  search. Without an API key, it waits three seconds after successful pages.
  Caught exceptions are printed, but it still prints its final `Finished` message.

Saved files remain available after a later request fails. Check error messages
as well as final summaries: not every script's `Finished` message proves the
entire search completed.

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
| `arxiv_search_topic(topic, max_results, start_offset=...)` | Overall limit: 1,000; starting offset: 0 |
| `semantic_scholar_search_topic(topic, year_range, max_results)` | Years: `2024-`; new-record target: 1,000 |

The main-block calls can override these defaults. In the current scripts,
OpenAlex searches from 2010, arXiv requests up to 100,000 records per topic, and
Semantic Scholar requests a target of 500 newly saved records.

## Review and Downstream Use

After collection:

1. Check errors and retrieval summaries for incomplete searches.
2. Read YAML metadata and abstracts for relevance screening.
3. Keep papers that actually use AI or data science for a healthcare task.
4. Separate application studies from reviews or general discussions as needed.
5. Deduplicate across sources by DOI or other bibliographic identifiers before
   reporting unique-paper counts.

These review steps are recommended downstream work; the search scripts do not
perform them automatically. Source coverage, missing abstracts, API limits,
and search wording mean that the collection is not guaranteed to be exhaustive
or exclusively peer-reviewed.
