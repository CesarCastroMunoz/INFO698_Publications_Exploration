# Understanding `transform_clean.py`

> **Citation:** This document was created with the assistance of GitHub Copilot
> (GitHub, 2026), an AI programming assistant. https://github.com/features/copilot

This guide explains [transform_clean.py](../src/data_pipeline/transform_clean.py), the shared utility
used by the three publication search scripts. It describes the current code,
not a proposed architecture.

## 1. What the module does

```text
API result
    |
Source-specific to_publication() adapter
    |
Publication object: validate and clean fields
    |
PublicationBuffer: skip duplicates and accumulate records
    |
JSONL file: normally 1,000 unique publications
    |
read_jsonl(): stream records for later use
    |
Optional batch_to_markdown(): export readable documents
```

The source-specific adapters live in the search scripts. This module does not
call any API, download PDFs, create embeddings, or build a knowledge graph.

## 2. Why each library is used

Every import in this module comes from Python's **standard library**. None
requires installing another package.

| Import | Purpose in this module |
|---|---|
| `json` | Convert dictionaries to JSON strings with `dumps()` and parse JSON strings with `loads()`. Used for JSONL and for safely quoting Markdown metadata values. |
| `re` | Regular expressions: remove punctuation from filename titles and remove known prefixes from DOI values. |
| `dataclasses.dataclass` | Generate an initializer, readable representation, and field-based equality for `Publication`. |
| `dataclasses.asdict` | Convert a `Publication` object into a dictionary of its fields for serialization. |
| `dataclasses.field` | Define special field behavior: an independent authors list for each object and a keyword-only `type` field. |
| `itertools.islice` | Take a limited number of items from an iterator without consuming the entire iterator. |
| `pathlib.Path` | Build paths, find files, create directories, and read/write/rename files. |
| `typing.Iterable` | Describe inputs that can be looped over, including lists and generators. |
| `typing.Iterator` | Describe outputs that produce items one at a time. |
| `typing.Literal` | Describe the supported source names for static type checking. |
| `typing.TypeVar` | Let `chunked_iterable()` preserve the input item type in its output type. |
| `urllib.parse.quote` | Percent-encode unsafe characters in publication IDs when creating Markdown filenames. |
| `uuid.uuid4` | Generate random identifiers for batch filenames. |

## 3. Constants and type aliases

### `Source`

```python
Source = Literal["arxiv", "openalex", "semantic_scholar"]
```

This tells type-checking tools which source strings are expected. It does
**not** enforce those values at runtime. The current code does not explicitly
validate the source against this list.

### `OUTPUT_DIR`

```python
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "publications"
```

- `__file__` identifies this Python file.
- `resolve()` obtains its resolved absolute path.
- The first `.parent` is the `utils` directory.
- The second `.parent` is the `src` directory.
- `/ "publications"` joins a path component using `Path`.

The result is the repository's `src/publications` directory, regardless of the
working directory from which the script runs. The `/` here is a Python path
joining operator, not division.

### `T`

```python
T = TypeVar("T")
```

`T` means "some item type." A batch of integers remains a list of integers;
a batch of publication objects remains a list of publication objects.

## 4. `clean_text()`

```python
def clean_text(text: str | None) -> str:
    return " ".join((text or "").split())
```

This converts missing text to an empty string and normalizes whitespace:

```python
clean_text("  Machine\n learning\t study  ")
# "Machine learning study"

clean_text(None)
# ""
```

`split()` with no separator splits on whitespace and removes empty pieces.
`" ".join(...)` puts the words back together with one space between them.

It does not remove punctuation or change letter case. It does remove original
paragraph breaks, so it is a normalization step rather than an exact copy of
the API text.

## 5. `slugify()`

Creates a short title suitable for use in a Markdown filename:

```python
slugify("A study: Machine Learning!")
# "a_study_machine_learning"
```

Its steps are:

1. Clean whitespace and lowercase the title.
2. Remove characters other than word characters, whitespace, and hyphens.
3. Replace runs of whitespace or hyphens with underscores.
4. Strip leading/trailing underscores.
5. Keep at most 50 characters.
6. Use `"untitled"` if nothing remains.

The regular expression `\w` includes Unicode word characters, not just ASCII
letters. Only the filename title is shortened; the publication's full title
remains in its stored record.

## 6. The `Publication` dataclass

`Publication` is the common record format used by all source adapters.

```python
publication = Publication(
    source="openalex",
    source_id="W123",
    title="A machine learning study",
    authors=["Jane Doe"],
    abstract="The study investigates...",
)
```

### Fields

| Field | Meaning |
|---|---|
| `source` | Provider that supplied this record. |
| `source_id` | Identifier passed by that provider's adapter. |
| `title` | Publication title. |
| `type` | Record label, defaulting to `"Publication"`; distinct from the publication's article/review type. |
| `authors` | List of author names. |
| `author_ids` | Provider author IDs in the same order as `authors`; `None` where unavailable (always for arXiv). |
| `references` | Provider IDs of works this publication cites. OpenAlex only; empty for arXiv and Semantic Scholar. |
| `publication_year` | Year, or `None` if unknown. |
| `publication_date` | Date string, or `None`. |
| `publication_type` | Provider-supplied article/review/etc. classification, or `None`. |
| `citations` | Citation count, not citation relationships. |
| `doi` | Normalized bare DOI identifier, or `None`. |
| `url` | Publication/source URL, or `None`. |
| `abstract` | Abstract text, or `None`. |

`str | None` means a value may be a string or `None`. Python serializes `None`
as JSON `null`. Type annotations guide editors and type checkers; they do not
automatically validate every runtime value.

### Why `field(default_factory=list)`?

Each new publication gets its own authors list. It avoids sharing one mutable
list between multiple objects.

### Why `kw_only=True` for `type`?

The optional record label must be passed by name:

```python
Publication("arxiv", "2401.12345", "Title", type="Publication")
```

It does not interfere with the existing positional order of the required
`source`, `source_id`, and `title` fields.

### `__post_init__()`

The dataclass-generated initializer assigns the fields and then automatically
calls this method.

It:

- Rejects an empty or whitespace-only ID.
- Preserves `source_id` unchanged; `strip()` is used only for the check.
- Cleans the title and substitutes `"Untitled Work"` for an empty title.
- Cleans author names and removes empty names, removing each matching author ID too so `authors` and `author_ids` stay aligned.
- Cleans reference IDs and removes empty ones.
- Cleans optional text fields and changes empty strings to `None`.
- Derives a year from the first four date characters if no year was supplied.
- Removes DOI prefixes such as `https://doi.org/`, `http://dx.doi.org/`, or `doi:`.
- Lowercases the DOI identifier.
- Cleans the URL without stripping its URL prefix.

The authors comprehension uses `:=` to assign the cleaned name once and keep
the name and its ID only if the name is nonempty. When no IDs are given, a list
of `None` values is used so both lists still have the same length.

This module preserves the ID **received from the adapter**. Some adapters
already transform IDs, such as removing arXiv version suffixes; that is separate
from this class.

The method is not a comprehensive schema validator. For example, deriving a
year can raise `ValueError` if the date does not begin with a valid integer.

## 7. `format_markdown()`

Returns a Markdown string; it does not write a file.

1. `asdict(publication)` creates a dictionary of the fields.
2. `pop("abstract")` removes the abstract from that dictionary, not from the object.
3. Each remaining value is serialized with `json.dumps()`.
4. Those key/value lines become YAML frontmatter between `---` markers.
5. The title and abstract become the Markdown body.

JSON-encoded values are valid YAML values, so strings, lists, `null`, and
numbers can be represented without adding a YAML library.

`ensure_ascii=False` preserves non-ASCII characters in the serialized text.
An absent abstract produces `*No abstract available.*` in the Markdown body.
JSONL instead retains an absent abstract as `null`.

## 8. `read_jsonl()`

Reads a batch one line at a time and yields `Publication` objects:

```python
for publication in read_jsonl(batch_path):
    print(publication.source_id, publication.title)
```

JSONL means **JSON Lines**: each physical line is one complete JSON object.
Embedded newlines in JSON strings are escaped, rather than becoming additional
records.

```python
Publication(**json.loads(line))
```

`json.loads()` parses the line into a dictionary. `**` unpacks its entries as
named constructor arguments, such as `source=...` and `title=...`.

`yield` makes this function a generator. Opening and parsing happen when the
caller iterates, not when it simply creates the generator.

Invalid JSON or constructor values raise an error with the batch path and
1-based line number. `raise ... from error` preserves the original cause.
Missing files and other filesystem errors propagate normally. Blank lines are
not silently ignored.

Reading reconstructs the dataclass, so its cleaning and validation run again.

## 9. `get_existing_ids()`

Streams every top-level `*.jsonl` file and builds a set of:

```python
("openalex", "W123")
("semantic_scholar", "abc123")
```

The tuple combines source and ID so identical ID strings from different
providers do not collide. Sets provide efficient membership checks and retain
each key only once.

Important boundaries:

- This prevents duplicate **provider records**, not duplicate papers by DOI.
- It ignores Markdown and temporary files.
- It does not search subdirectories.
- It parses all existing records at startup and retains all keys in memory.
- It does not record which topic originally matched a publication.

## 10. `PublicationBuffer`

This class keeps state between API pages. Without persistent state, each
100-record OpenAlex page would produce its own small JSONL file.

### `__init__()`: initialize the state

| Attribute | What it tracks |
|---|---|
| `directory` | Output directory as a `Path`. |
| `existing_ids` | The supplied set of IDs already saved; the same set is updated after successful writes. |
| `records` | Pending serialized JSON strings, not publication objects. |
| `pending_ids` | Keys of records buffered but not yet written. |
| `saved` | Number successfully published by this buffer, not the total collection size. |

### `add()`: accept a page or stream

For each publication:

1. Construct `(source, source_id)`.
2. Skip it if already saved or pending.
3. Serialize it and add it to the buffer.
4. Add its key to `pending_ids`.
5. Flush when the buffer reaches 1,000 records.

The returned count is the number **accepted** from this call. Some accepted
records may still be pending; they are not necessarily all saved to disk yet.

```text
API page: 100 new records
    → accepted = 100
    → saved = 0
    → pending = 100

Enough pages to reach 1,000 unique records
    → write one batch
    → saved = 1,000
    → pending = 0
```

Pending IDs must be checked because a duplicate can arrive before the first
copy has been written.

### `flush()`: publish the pending batch

If the buffer is empty, it does nothing. Otherwise:

1. Create the output directory if needed.
2. Generate a filename such as `batch-<random_identifier>.jsonl`.
3. Write records to the matching `.tmp` file, with a final newline.
4. Rename the temporary file to its final `.jsonl` path.
5. Clean up the temporary path in `finally`.
6. Only after success, update saved IDs and the saved count.
7. Clear pending records and keys.

`uuid4().hex` produces a random UUID as 32 hexadecimal characters. This makes
filename collisions extremely unlikely; it is not a sequential batch number
or a timestamp. There is no explicit collision check.

Writing a temporary file before renaming avoids exposing an incomplete final
JSONL file during a normal write failure. It is not a database transaction or
a guarantee against every power-loss/filesystem failure.

If writing or renaming fails, the exception propagates. Pending records remain
in the buffer and their IDs are not marked saved, allowing a caller that handles
the error to retry.

### Buffer lifetime

The search scripts create one buffer per search call. They flush at normal
completion and on their handled API errors. A final partial file is expected:

```text
2,350 unique publications → 1,000 + 1,000 + 350
```

Buffers do not carry across topics or process restarts. A forced termination
can lose up to 999 pending records; a rerun can retrieve those records again.
The buffer itself does not change query limits or enforce a collection-wide cap.

## 11. `save_results()`

A convenience function for immediate saving:

```python
count = save_results(publications, output_dir, existing_ids)
```

It creates a buffer, adds the supplied iterable, flushes the remainder, and
returns the count actually saved.

Unlike keeping a `PublicationBuffer` alive, separate calls to `save_results()`
do not combine small pages. The search scripts therefore use the buffer
directly.

## 12. `batch_to_markdown()`

Streams one JSONL batch and writes one Markdown file per publication:

```python
batch_to_markdown(batch_path, markdown_output_dir)
```

The layout is:

```text
markdown_output_dir\
    openalex\
        W123_example_title.md
    arxiv\
        hep-th%2F9901001_example_title.md
```

Source subfolders avoid cross-provider collisions without adding source names
to filenames.

`quote(..., safe="")` encodes characters such as `/`. Underscores are explicitly
encoded as `%5F`, because `quote()` otherwise leaves them unchanged. This
encoding affects only the filename, not the metadata ID.

The function uses `slugify()` for the title and `format_markdown()` for content.
It returns the number of files written. Re-exporting overwrites matching paths;
it does not merge records or delete older files whose titles changed. Filesystem
errors propagate.

## 13. `chunked_iterable()`

Groups any iterable into lists of at most `size` items:

```python
list(chunked_iterable([1, 2, 3, 4, 5], 2))
# [[1, 2], [3, 4], [5]]
```

- Rejects zero or negative sizes.
- `iter()` creates an iterator that remembers its current position.
- `islice(iterator, size)` takes the next items.
- `list()` collects those items into one batch.
- `:=` assigns that list to `chunk`.
- An empty list ends the `while` loop.
- `yield` produces each nonempty batch.

The annotation `Iterator[list[T]]` means "produce lists of the same item type
that the input contains."

This helper groups **input items**; it does not deduplicate them. In arXiv it
supports 100-record processing/progress batches. `PublicationBuffer` separately
groups unique records into 1,000-record output files.

## 14. Putting it together

```python
from pathlib import Path
from src.utils.transform_clean import (
    Publication,
    PublicationBuffer,
    batch_to_markdown,
    get_existing_ids,
    read_jsonl,
)

output = Path("example_publications")
existing = get_existing_ids(output)
writer = PublicationBuffer(output, existing)

writer.add([
    Publication("openalex", "W1", "First study", abstract="First abstract"),
])
writer.add([
    Publication("openalex", "W1", "First study"),  # Duplicate: skipped.
    Publication("openalex", "W2", "Second study"),
])
writer.flush()

print(writer.saved)  # 2 on the first run; 0 if both IDs already exist.

for batch in output.glob("*.jsonl"):
    for publication in read_jsonl(batch):
        print(publication.source_id)
    batch_to_markdown(batch, Path("example_markdown"))
```

The source search scripts already manage this lifecycle. This example
illustrates the utility without making network requests.

## 15. Practical limitations to remember

- Run sequential writers: duplicate checking is not coordinated between processes.
- Existing Markdown files are not included in JSONL duplicate detection.
- Startup duplicate lookup grows with the number of stored records.
- Citation edges (`references`) come only from OpenAlex; Semantic Scholar and arXiv records have none.
- Unknown metadata stays `null`; missing abstracts do not become embedding text.
- JSONL files contain normalized metadata and abstracts, not full papers.
- UUID batch names do not indicate source, topic, or retrieval order.
- The module stores no API continuation checkpoints.

For the full retrieval workflow, see [README.md](../README.md).
