# GLiNER publication-graph extraction pipeline

This document explains what
[`graph_extraction_gliner.py`](../src/Ingest_Publications/graph_extraction_gliner.py)
does from startup through output. It describes the extraction stage only: the
script reads publication JSONL files and writes graph JSONL files. It does not
create embeddings, write to PostgreSQL, or modify the input files.

## Pipeline at a glance

```text
src/publications/*.jsonl
        |
        v
Validate each publication and build deterministic paper, author, and reference nodes
        |
        +--> If an abstract exists: GLiNER predicts entity spans and their study roles
        |                           -> validate, prioritize, cap, and link entities
        |
        v
Serialize one graph per publication to src/graph_extracted/*.jsonl
        |
        +--> On restart, skip paper IDs already present in output
```

## 1. Configuration and controlled vocabulary

At the top of the script:

- `INPUT_DIR` points to `src/publications`, relative to the script location.
- `OUTPUT_DIR` points to `src/graph_extracted`.
- `MODEL` selects `fastino/gliner2.5-small-v1`.
- `ENTITY_THRESHOLD = 0.5` is the minimum entity confidence accepted.
- `RELATION_THRESHOLD = 0.75` is the minimum role confidence required for a
  specific relationship.
- `MAX_ENTITIES = 7` limits distinct semantic entities per publication. It does
  not count the publication, author, or reference nodes.

`ENTITY_TYPES` defines the nine entity labels and natural-language descriptions
given to the extractor:

| Label | Meaning |
|---|---|
| `Method` | Algorithms, model architectures, statistical or analytical methods |
| `Task` | Research tasks such as diagnosis, prediction, classification, or segmentation |
| `Medical_Condition` | Diseases, disorders, or clinical conditions |
| `Data_Modality` | Data types such as MRI, CT, images, or electronic health records |
| `Metric` | Evaluation measures such as AUROC, F1, accuracy, or sensitivity |
| `Dataset` | Named research datasets |
| `Chemical_or_Drug` | Named drugs, medications, or chemicals |
| `Institution` | Named hospitals, universities, or research organizations |
| `Symptom` | Symptoms or clinical signs |

`ALLOWED_NODES` is derived from these labels and is checked when processing
predicted entities. `ALLOWED_EDGES` declares the relationship vocabulary, but
the current script does not use it to validate edges at runtime.
`PUBLICATION_ROLES` maps each role phrase predicted by GLiNER to a relationship
and the entity labels allowed to use it. For example, the role “method or
algorithm used in this study” maps to `USES_METHOD` for `Method` nodes. An
entity-role mismatch falls back to `MENTIONS`.

## 2. Loading the model and extraction schema

`load_model()` imports GLiNER only when needed, loads the configured model on
CPU, and constructs the extraction schema:

1. The schema asks for the entity types and descriptions in `ENTITY_TYPES`.
2. It also asks for a `publication_role` attribute on `Method`, `Task`,
   `Medical_Condition`, `Dataset`, `Data_Modality`, and `Metric`.
3. The possible role values are the phrases in `PUBLICATION_ROLES`, plus a
   general “entity only mentioned” role.
4. `qualify_labels=True` makes the role attribute specific to its entity label.

The model is loaded once per run, on the first new publication that has a
non-empty abstract. If there are no such publications, model loading is not
needed. A model download or initialization error is outside the per-publication
error handler and stops the run.

## 3. Stable publication identity

`publication_id(publication)` makes a stable paper ID from the source and its
source-specific record ID:

```text
paper:<URL-quoted source>:<URL-quoted source_id>
```

Quoting prevents special characters in those values from interfering with the
ID structure. The same source and source ID produce the same paper ID, which is
how restart logic recognizes previously saved records.

## 4. Building one publication graph

`extract_graph(model, publication, schema)` returns one graph dictionary.
Before building it, the function validates:

- `source`, `source_id`, and `title` are non-empty strings.
- If supplied, `authors` and `references` are lists containing only non-empty
  strings.
- If supplied, `author_ids` is a list.

Invalid required fields or list values raise an error; the run loop reports the
publication as failed instead of writing a partial graph.

### Publication node

The function always creates one `Publication` node. Its ID is the stable paper
ID, its name is the title, and its `properties` contain the available values
from `source`, `source_id`, `doi`, `publication_date`, `url`, and `abstract`.
Missing optional values remain `null` in the JSON.

### Author nodes and edges

For each author, it creates an `Author` node and an `AUTHORED` edge directed
from that author to the publication:

```text
Author --AUTHORED--> Publication
```

If a corresponding `author_ids` value is present and truthy, the ID uses the
provider source and provider ID. Otherwise the ID is based on the publication
ID and the author's position in its author list. Author nodes have empty
properties.

### Reference nodes and edges

For each reference string, it creates a `Reference` node with an ID based on
the publication ID and reference position. A `CITES` edge points from the
publication to that reference:

```text
Publication --CITES--> Reference
```

Reference nodes have empty properties. References are kept as provided; this
script does not resolve them to publication nodes.

## 5. Extracting semantic entities

Semantic extraction runs only when `abstract` is truthy. The input text is the
title, a newline, and the abstract. Thus the title can contribute extracted
entities as well as the abstract.

`model.extract_long()` is called with:

- `threshold=ENTITY_THRESHOLD` (0.5)
- `chunk_size=200` words
- `chunk_overlap=40` words
- `batch_size=1`
- confidence scores and source spans enabled

Long text is processed in overlapping chunks by the GLiNER library. The script
then flattens the model's label-to-matches result into individual
`(label, entity)` pairs.

Before creating nodes, it:

1. Sorts `Medical_Condition` entities ahead of other labels.
2. Sorts each priority group by descending entity confidence.
3. Rejects any label not in `ALLOWED_NODES`.
4. Checks that each predicted span points to exactly its reported entity text
   in the original title-plus-abstract text, and that the text is non-empty.
5. Rejects entities below the 0.5 confidence threshold.

For each remaining entity, its display name is lowercased and consecutive
whitespace is collapsed to a single space. Its semantic node ID is the
lowercased label, a colon, and that normalized name. For example:

```text
medical_condition:type 2 diabetes
```

The entity's `properties` are empty. Semantic IDs are shared across
publications when their normalized label and name match, so the ID represents
the semantic entity rather than a publication-specific mention.

The script retains at most seven distinct semantic IDs per publication.
Because conditions are sorted first, they get priority for those slots; within
that order, higher-confidence entities are considered first. Repeated
occurrences of the same semantic ID do not use additional slots. The cap does
not mean every publication will have seven entities.

## 6. Assigning relationships

Every semantic edge is directed from the publication to the entity. The role
attribute determines its relationship:

| Predicted role | Relationship | Allowed entity label(s) |
|---|---|---|
| Method or algorithm used in this study | `USES_METHOD` | `Method` |
| Research task performed or addressed | `ADDRESSES_TASK` | `Task` |
| Disease or condition investigated | `STUDIES_CONDITION` | `Medical_Condition` |
| Data used to evaluate the model | `EVALUATED_ON` | `Dataset`, `Data_Modality` |
| Data used to train the model | `TRAINED_WITH` | `Dataset`, `Data_Modality` |
| Metric used to evaluate performance | `MEASURED_BY` | `Metric` |

A specific relationship is used only if the role confidence is at least 0.75
and the entity label is allowed for that role. Otherwise the edge is `MENTIONS`.
Entity confidence and role confidence are separate thresholds: an entity must
first pass the 0.5 entity threshold, and its role must independently pass the
0.75 role threshold to receive a specific edge.

`Chemical_or_Drug`, `Institution`, and `Symptom` do not have specific roles in
`PUBLICATION_ROLES`, so they are linked using `MENTIONS`. More generally,
`MENTIONS` does not mean that a paper used, treated, evaluated, or caused the
entity; it only records an extracted mention.

If the same paper-to-entity target has both a specific relationship and
`MENTIONS`, the script removes the `MENTIONS` edge. It then deduplicates edges
by `(source, target, relation)`.

## 7. Graph output shape

`extract_graph()` returns the following top-level fields:

```json
{
  "paper_id": "paper:source:record-id",
  "source": "source",
  "source_id": "record-id",
  "doi": null,
  "nodes": [
    {
      "id": "paper:source:record-id",
      "label": "Publication",
      "name": "Paper title",
      "properties": {}
    }
  ],
  "edges": [
    {
      "source": "paper:source:record-id",
      "target": "medical_condition:example condition",
      "relation": "STUDIES_CONDITION",
      "properties": {}
    }
  ]
}
```

The example omits other node and edge fields for brevity. The actual graph
includes all nodes and edges created for that publication. No embeddings are
created in this script.

## 8. Restart handling and input validation

`read_completed(output_dir)` scans existing
`graph_publications-*.jsonl` files in sorted order. It reads each line as JSON,
collects its `paper_id`, and counts records in the last file. Every line must
end with a newline; if the last record is incomplete, the function raises an
error and requires repair before restarting. Malformed JSON also stops the
scan.

`run()` performs the batch workflow:

1. Finds sorted `*.jsonl` input files. If none exist, it raises
   `FileNotFoundError`.
2. Creates the output directory if needed and loads completed IDs and the
   current output-file position.
3. Reads each non-blank input line and parses it as JSON.
4. Creates its paper ID and checks that title is a string and abstract is
   either a string or `null`. The stricter non-empty and author/reference
   checks happen in `extract_graph()`.
5. Skips a publication whose ID already exists in the output.
6. Loads the model if this is the first unsaved publication with an abstract.
7. Builds and serializes the graph as compact UTF-8-friendly JSON. NaN and
   infinity are disallowed.
8. Appends one JSON object and newline to the current output file. The file is
   rotated after 1,000 successful records:
   `graph_publications-000001.jsonl`, `graph_publications-000002.jsonl`, etc.
9. Only after the write succeeds does it mark the ID complete in memory and
   increment the saved count.

Input parse/metadata errors and the listed per-publication extraction or
serialization errors are printed, counted as failures, and processing
continues. Failed publications are not marked complete and can be retried on a
later run. Output write errors are not swallowed and stop processing. Progress
messages report scanned, saved, skipped, failed, and the current successful
graphs-per-minute rate.

## 9. Running the pipeline and what comes next

From the repository root in PowerShell:

```powershell
uv sync --extra extraction
& .\.venv\Scripts\python.exe .\src\Ingest_Publications\graph_extraction_gliner.py
```

The first run may download model weights and requires internet access. This
script writes raw graph JSONL only. The separate
[`embed_load_graphs.py`](../src/Ingest_Publications/embed_load_graphs.py)
stage creates embeddings and loads graph data into PostgreSQL; it is not
called by `graph_extraction_gliner.py`.

For operational notes about accuracy, compatibility, and loading, see
[`GLiNER Quick Start.md`](./GLiNER%20Quick%20Start.md).
