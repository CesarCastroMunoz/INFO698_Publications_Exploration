'''
Utilities for publication cleaning, JSONL batches, and optional Markdown export.
Revision 1: Initial Rev. Cesar C. 10/14/2026
'''

import json
import re
from dataclasses import asdict, dataclass, field
from itertools import islice
from pathlib import Path
from typing import Iterable, Iterator, Literal, TypeVar
from urllib.parse import quote
from uuid import uuid4

Source = Literal["arxiv", "openalex", "semantic_scholar"]
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "publications"
T = TypeVar("T")


def clean_text(text: str | None) -> str:
    """Collapse embedded newlines and repeated whitespace."""
    return " ".join((text or "").split())


def slugify(text: str) -> str:
    '''Remove special characters and limit title to 50 characters for Filename'''
    text = re.sub(r"[^\w\s-]", "", clean_text(text).lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")[:50] or "untitled"


@dataclass
class Publication:
    """Source-neutral metadata; unknown values stay None, not placeholder text."""

    source: Source
    source_id: str
    title: str
    type: str = field(default="Publication", kw_only=True)
    authors: list[str] = field(default_factory=list)
    author_ids: list[str | None] = field(default_factory=list)  # aligned with authors
    references: list[str] = field(default_factory=list)  # IDs of works this one cites
    publication_year: int | None = None
    publication_date: str | None = None
    publication_type: str | None = None
    citations: int | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None

    def __post_init__(self) -> None:
        '''Calls after it creates and initializes a Publication object
           Cleans Text and formats to be appropiated for storage and Markdown export.'''
        if not self.source_id.strip():
            raise ValueError(f"Missing publication ID from {self.source}")
        self.title = clean_text(self.title) or "Untitled Work"
        # Keep each author ID paired with its name when empty names are dropped.
        ids = self.author_ids or [None] * len(self.authors)
        pairs = [
            (name, clean_text(author_id) or None)
            for author, author_id in zip(self.authors, ids)
            if (name := clean_text(author))
        ]
        self.authors = [name for name, _ in pairs]
        self.author_ids = [author_id for _, author_id in pairs]
        self.references = [ref for ref in map(clean_text, self.references) if ref]
        self.abstract = clean_text(self.abstract) or None
        self.publication_date = clean_text(self.publication_date) or None
        self.publication_type = clean_text(self.publication_type) or None
        if self.publication_year is None and self.publication_date:
            self.publication_year = int(self.publication_date[:4])
        doi = clean_text(self.doi)
        #Clean DOI to be use to find if same paper found in different sources
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
        self.doi = doi.lower() or None
        self.url = clean_text(self.url) or None

# Keep option for Markdown Output. 
def format_markdown(publication: Publication) -> str:
    """JSON-encoded metadata values are also valid YAML values."""
    metadata = asdict(publication)
    abstract = metadata.pop("abstract") #remove from metadata that will be use in FrontMatter
    frontmatter = "\n".join(
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in metadata.items()
    )
    return (
        f"---\n{frontmatter}\n---\n\n# {publication.title}\n\n"
        f"## Abstract\n\n{abstract or '*No abstract available.*'}\n"
    )


def read_jsonl(batch_path: str | Path) -> Iterator[Publication]:
    """Stream publications from a JSONL batch; reject malformed records.
    Read current JSON files to list already pulled publications to avoid duplication"""
    with Path(batch_path).open(encoding="utf-8") as batch:
        for line_number, line in enumerate(batch, start=1):
            try:
                yield Publication(**json.loads(line))
            except (ValueError, TypeError) as error:
                raise ValueError(f"Invalid publication in {batch_path}, line {line_number}") from error


def get_existing_ids(output_dir: str | Path) -> set[tuple[str, str]]:
    """Read source/ID pairs from saved JSONL batches."""
    existing_ids: set[tuple[str, str]] = set()
    for path in Path(output_dir).glob("*.jsonl"):
        for publication in read_jsonl(path):
            existing_ids.add((publication.source, publication.source_id))
    return existing_ids


def save_results(
    publications: Iterable[Publication],
    output_dir: str | Path,
    existing_ids: set[tuple[str, str]],
) -> int:
    """Save an iterable immediately, using the shared buffered writer."""
    writer = PublicationBuffer(output_dir, existing_ids)
    writer.add(publications)
    writer.flush()
    return writer.saved


class PublicationBuffer:
    """Accumulate unique publications across pages before publishing JSONL."""

    def __init__(self, output_dir: str | Path, existing_ids: set[tuple[str, str]]):
        self.directory = Path(output_dir)
        self.existing_ids = existing_ids
        self.records: list[str] = []
        self.pending_ids: set[tuple[str, str]] = set()
        self.saved = 0

    def add(self, publications: Iterable[Publication]) -> int:
        """Return newly accepted records, including those still pending."""
        accepted = 0
        for publication in publications:
            key = (publication.source, publication.source_id)
            if key in self.existing_ids or key in self.pending_ids:
                continue
            self.records.append(json.dumps(asdict(publication), ensure_ascii=False))
            self.pending_ids.add(key)
            accepted += 1
            if len(self.records) == 1000:
                self.flush()
        return accepted

    def flush(self) -> None:
        """Publish pending records and mark IDs saved only after a successful write."""
        if not self.records:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"batch-{uuid4().hex}.jsonl"
        #temp file writing to track if errors happen not to have an bad file
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_text("\n".join(self.records) + "\n", encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        self.existing_ids.update(self.pending_ids)
        self.saved += len(self.records)
        self.records.clear()
        self.pending_ids.clear()


def batch_to_markdown(batch_path: str | Path, output_dir: str | Path) -> int:
    """Export one JSONL batch as Markdown files grouped by source."""
    saved = 0
    for publication in read_jsonl(batch_path):
        directory = Path(output_dir) / publication.source
        directory.mkdir(parents=True, exist_ok=True)
        safe_id = quote(publication.source_id, safe="").replace("_", "%5F")
        path = directory / f"{safe_id}_{slugify(publication.title)}.md"
        path.write_text(format_markdown(publication), encoding="utf-8")
        saved += 1
    return saved


def chunked_iterable(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    '''Takes an iterable and splits it into smaller lists'''
    if size <= 0:
        raise ValueError("Batch size must be positive.")
    iterator = iter(iterable)
    while chunk := list(islice(iterator, size)):
        yield chunk
