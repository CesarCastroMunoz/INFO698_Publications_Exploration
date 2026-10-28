# GLiNER extraction on CPU

The separate [graph_extraction_gliner.py](../src/Ingest_Publications/graph_extraction_gliner.py)
uses `fastino/gliner2.5-small-v1` locally on CPU. The existing
[graph_extraction.py](../src/Ingest_Publications/graph_extraction.py) remains the
OpenAI/LM Studio extractor.

## Install and run

From the repository root in PowerShell:

```powershell
uv sync --extra extraction
& .\.venv\Scripts\python.exe .\src\Ingest_Publications\graph_extraction_gliner.py
```

Internet access is needed for the initial Hugging Face model download. No GPU,
NPU integration, LM Studio server, or API key is required for extraction.
By default, weights are cached outside this repository under
`%USERPROFILE%\.cache\huggingface\hub`. `HF_HOME` or `HF_HUB_CACHE` can override
that location. The repository ignores common model-weight files as a safeguard.
The dependency entries in `pyproject.toml` and `uv.lock` are metadata, not weights.
The model loads once, when the first unsaved paper with an abstract is found.
Model download or initialization errors stop the script rather than failing every paper.

## Files and restart

- Input: all sorted JSONL files in `src/publications`.
- Raw output: `src/graph_extracted/graph_publications-000001.jsonl`, rotating at
  1,000 successful publications. No embeddings or database writes.
- Same top-level fields as the original: `paper_id`, `source`, `source_id`,
  `doi`, `nodes`, and `edges`.
- Each line is a complete JSON object, with object-valued node/edge properties
  and no embeddings. Invalid metadata or non-JSON values are reported and that
  paper is not marked complete. File-write errors stop processing.
- Already saved paper IDs are skipped before inference, including papers saved
  by the original extractor. Existing output is not re-extracted or migrated.
- One paper at a time; each successful result is saved immediately.
- Progress includes scanned, saved, skipped, failed, and successful graphs/minute.
- Per-paper extraction errors print and continue. Failed papers can be retried
  by restarting. Repair incomplete JSONL lines before restarting.
- Run only one extractor against the shared output folder at a time.

## Entities and edges

The nine types are Method, Task, Medical_Condition, Data_Modality, Metric, Dataset,
Chemical_or_Drug, Institution, and Symptom. Algorithms and architectures are
included in Method. At most seven distinct semantic entities are retained,
with detected medical conditions prioritized before other types. Within each
priority group, entities are ranked by extraction confidence. Medical_Condition
means a disease, disorder or clinical condition studied by the paper, not a broad
discipline such as public health. No condition is invented when none is detected.

Python builds Publication, Author, Reference, AUTHORED, and CITES deterministically.
All semantic edges start at the publication:

- USES_METHOD, ADDRESSES_TASK, STUDIES_CONDITION, EVALUATED_ON, TRAINED_WITH,
  MEASURED_BY are assigned
  from predicted span attributes describing the entity's role in this study.
- Specific roles require confidence >= 0.75 and a compatible entity type.
- Otherwise MENTIONS is used, as agreed. A drug or disease mention does not
  imply treatment or causation.

ADDRESSES_TASK means the research task performed or addressed by the paper.
STUDIES_CONDITION means the disease or clinical condition investigated by the
paper, not a condition mentioned only in background or prior work. The model
receives natural-language role descriptions; Python maps them to these edge
names. Existing TARGETS_TASK edges remain supported by the loader and are not
renamed in saved files.

These are model predictions, not verified claims. Review a representative sample,
especially prior-work mentions and training versus evaluation datasets. Confidence
scores are not calibrated accuracy probabilities. Thresholds and the seven-entity
cap are constants near the top of the script.

The CPU smoke test confirmed execution and long-input coverage, not production
accuracy. It also exposed incorrect Method/Dataset labels on a synthetic example.
Review extraction quality before processing the entire collection; do not treat
passing pipeline tests as evidence of medically accurate extraction.

Long inputs use the library's overlapping word chunks (200 words, overlap 40),
without intentionally truncating the abstract. Predicted spans are checked against
the source text. Overlapping mentions are deduplicated.

Entity names are lowercase source spans with whitespace normalized, not
LLM-standardized terminology. New semantic IDs are label-prefixed readable names,
such as `medical_condition:type 2 diabetes`; spaces do not need `%20` in JSON or
PostgreSQL. Publication and author identity formats are unchanged.
Synonyms and abbreviations can remain separate; existing LLM node IDs are not
automatically merged with these IDs.
Existing output files (including URL-quoted IDs and Condition nodes) are unchanged
and still loadable. Restart skips their paper IDs, so these changes apply only to
new extractions. Existing papers need an explicit re-extraction/migration to change
their saved nodes and matching edge endpoints; do not edit IDs on their own.

## Embedding and loading

Use the existing shared loader:

```powershell
& .\.venv\Scripts\python.exe .\src\Ingest_Publications\embed_load_graphs.py
```

It accepts MENTIONS and older graph labels/relations, saves embedded ready files
in `src/graph_output` at 1,000 publications per file, and loads PostgreSQL.
This stage still needs `OPENAI_KEY` for embeddings and `NEON_DATABASE_URL`.
Existing database publications are skipped. Extraction speed does not include
embedding or database loading time.

Official model documentation:
<https://huggingface.co/fastino/gliner2.5-small-v1>
