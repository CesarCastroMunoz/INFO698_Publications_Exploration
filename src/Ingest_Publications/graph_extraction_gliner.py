"""Extract publication graphs locally with GLiNER2.5 Small on CPU.
   Revision 1: Initial implementation. Cesar C. 10/25/2026

   This module uses GLiNER2.5 Small to extract semantic graphs from publication metadata, including entities and their relations.
   The extraction is performed locally on CPU and is suitable for smaller-scale processing due to computational constraints.

   Fastino AI. (n.d.). GLiNER2.5 span attributes tutorial.
   GitHub. https://github.com/fastino-ai/GLiNER2/blob/main/tutorial/13-span_attributes.md
"""

import json
from pathlib import Path
from time import perf_counter
from urllib.parse import quote

INPUT_DIR = Path(__file__).resolve().parents[1] / "publications"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "graph_extracted"

MODEL = "fastino/gliner2.5-small-v1"
ENTITY_THRESHOLD = 0.5 # Threshold for entity extraction confidence
RELATION_THRESHOLD = 0.75  # Threshold for relation extraction confidence
MAX_ENTITIES = 7 # Maximum number of entities to extract per publication

# Define entity types and allowed nodes/edges for the semantic graph.
ENTITY_TYPES = {
    "Method": "Machine learning algorithms, model architectures, statistical and analytical methods",
    "Task": "Research tasks such as image segmentation, diagnosis, prediction or classification",
    "Medical_Condition": "Disease, disorder or clinical condition studied in the publication, such as diabetes, cancer, COVID-19 or depression",
    "Data_Modality": "Types of data such as MRI, CT scans, images or electronic health records",
    "Metric": "Evaluation metrics such as AUROC, F1 score, accuracy or sensitivity",
    "Dataset": "Proper names of research datasets, such as MIMIC-III, UK Biobank or ImageNet; not books or generic data collections",
    "Chemical_or_Drug": "Named drugs, medications or chemical substances",
    "Institution": "Named hospitals, universities or research organizations",
    "Symptom": "Symptoms or clinical signs",
}
ALLOWED_NODES = list(ENTITY_TYPES)

# Define allowed edges for the semantic graph.
ALLOWED_EDGES = [
    "USES_METHOD", "ADDRESSES_TASK", "STUDIES_CONDITION", "EVALUATED_ON",
    "TRAINED_WITH", "MEASURED_BY", "MENTIONS",
]
PUBLICATION_ROLES = {
    "method or algorithm used in this study": ("USES_METHOD", ["Method"]),
    "research task performed or addressed in this study": ("ADDRESSES_TASK", ["Task"]),
    "disease or medical condition investigated in this study": ("STUDIES_CONDITION", ["Medical_Condition"]),
    "dataset or data used to evaluate the model in this study": ("EVALUATED_ON", ["Dataset", "Data_Modality"]),
    "dataset or data used to train the model in this study": ("TRAINED_WITH", ["Dataset", "Data_Modality"]),
    "metric used to evaluate performance in this study": ("MEASURED_BY", ["Metric"]),
}


def load_model():
    """Load the GLiNER model and create the schema for entity extraction."""
    from gliner2 import AutoExtractor, AttributeGroup

    print(f"Loading {MODEL} on CPU (first run downloads the model)...", flush=True)
    model = AutoExtractor.from_pretrained(MODEL, map_location="cpu")

    # Create the schema for entity extraction, including publication roles as attributes.
    schema = model.create_schema().entities(ENTITY_TYPES).entity_attributes({
        "publication_role": AttributeGroup(
            list(PUBLICATION_ROLES) + ["entity only mentioned, including background or prior work"],
            applies_to=["Method", "Task", "Medical_Condition", "Dataset", "Data_Modality", "Metric"],
            qualify_labels=True,
        ),
    })
    return model, schema


def publication_id(publication):
    """Construct a unique identifier for the publication based on its source and source_id."""
    return f"paper:{quote(publication['source'], safe='')}:{quote(publication['source_id'], safe='')}"


def extract_graph(model, publication, schema):
    """Keep metadata deterministic; predict entity spans and their publication roles for the given publication."""

    # Validate required publication fields and their types.
    for key in ("source", "source_id", "title"):
        if not isinstance(publication.get(key), str) or not publication[key].strip():
            raise ValueError(f"{key} must be nonempty text")
    
    # Validate optional list fields and their contents.
    for key in ("authors", "references"):
        values = publication.get(key)
        if values is not None and (
            not isinstance(values, list) or
            any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise ValueError(f"{key} must be a list of nonempty text values")
    if publication.get("author_ids") is not None and not isinstance(publication["author_ids"], list):
        raise ValueError("author_ids must be a list")
    
    # Construct the paper node and initialize nodes and edges for authors and references.
    paper_id = publication_id(publication)
    nodes = {
        paper_id: {
            "id": paper_id, "label": "Publication", "name": publication["title"],
            "properties": {key: publication.get(key) for key in
                           ("source", "source_id", "doi", "publication_date", "url", "abstract")},
        }
    }
    edges = []
    author_ids = publication.get("author_ids") or []

    # Process authors and create corresponding nodes and edges.
    for index, name in enumerate(publication.get("authors") or []):
        provider_id = author_ids[index] if index < len(author_ids) else None
        author_id = (
            f"author:provider:{quote(publication['source'], safe='')}:{quote(str(provider_id), safe='')}"
            if provider_id else f"{paper_id}:author:{index}"
        )
        nodes[author_id] = {"id": author_id, "label": "Author", "name": name, "properties": {}}
        edges.append({"source": author_id, "target": paper_id, "relation": "AUTHORED", "properties": {}})

    # Process references and create corresponding nodes and edges.
    for index, reference in enumerate(publication.get("references") or []):
        reference_id = f"{paper_id}:reference:{index}"
        nodes[reference_id] = {
            "id": reference_id, "label": "Reference", "name": reference, "properties": {},
        }
        edges.append({"source": paper_id, "target": reference_id, "relation": "CITES", "properties": {}})

    # If the publication has an abstract, extract entities using the model and schema.
    if publication.get("abstract"):
        text = f"{publication['title']}\n{publication['abstract']}"

        # Extract entities from the publication text using the provided model and schema.
        result = model.extract_long(
            text, schema, threshold=ENTITY_THRESHOLD,
            chunk_size=200, chunk_overlap=40, batch_size=1,
            include_confidence=True, include_spans=True,
        )

        # Flatten the extracted entities into a list of (label, entity) tuples for further processing.
        entities = [
            (label, entity)
            for label, matches in result["entities"].items()
            for entity in matches
        ]
        # Sort entities by label and confidence to prioritize more relevant entities.
        # Keep Medical_Condition entities at the top of the list for priority processing.
        entities.sort(key=lambda item: (
            item[0] != "Medical_Condition", -item[1]["confidence"],
        ))
        semantic_ids = set()

        # Iterate over the sorted entities and construct nodes and edges based on their labels and roles.
        for label, entity in entities:

            # Skip entities that are not allowed in the semantic graph.
            if label not in ALLOWED_NODES:
                raise ValueError(f"Unknown entity label: {label}")

            # Validate the entity text against the source span and ensure it is not empty.
            if text[entity["start"]:entity["end"]] != entity["text"] or not entity["text"].strip():
                raise ValueError(f"Entity is not a valid source span: {entity}")

            # Skip entities that do not meet the confidence threshold.
            if entity["confidence"] < ENTITY_THRESHOLD:
                continue
            name = " ".join(entity["text"].lower().split())
            node_id = f"{label.lower()}:{name}"

            # Skip adding new nodes if the maximum number of entities has been reached.
            if node_id not in semantic_ids and len(semantic_ids) >= MAX_ENTITIES:
                continue

            # Add the node ID to the set of semantic IDs to track processed entities.
            semantic_ids.add(node_id)
            nodes[node_id] = {"id": node_id, "label": label, "name": name, "properties": {}}
            role = entity.get("publication_role", {})

            # Determine the relation type and valid target labels based on the publication role.
            relation, valid_labels = PUBLICATION_ROLES.get(role.get("label"), ("MENTIONS", []))
            if role.get("confidence", 0) < RELATION_THRESHOLD or label not in valid_labels:
                relation = "MENTIONS"
            edges.append({
                "source": paper_id, "target": node_id, "relation": relation, "properties": {},
            })

    specific_targets = {
        edge["target"] for edge in edges
        if edge["source"] == paper_id and edge["relation"] != "MENTIONS"
    }

    # Remove "MENTIONS" edges if the target is already involved in a more specific relation.
    edges = [edge for edge in edges if edge["relation"] != "MENTIONS" or edge["target"] not in specific_targets]
    unique_edges = {(edge["source"], edge["target"], edge["relation"]): edge for edge in edges}
    return {
        "paper_id": paper_id, "source": publication["source"], "source_id": publication["source_id"],
        "doi": publication.get("doi"), "nodes": list(nodes.values()), "edges": list(unique_edges.values()),
    }


def read_completed(output_dir):
    """Scan successful output once on startup; refuse to append after a torn write."""

    # Iterate through all output files to collect completed publication IDs.
    completed = set()
    files = sorted(output_dir.glob("graph_publications-*.jsonl"))
    last_count = 0

    # Process each output file to identify completed publications.
    for path in files:
        last_count = 0
        with path.open("rb") as file:
            for line_number, line in enumerate(file, 1):
                if not line.endswith(b"\n"):
                    raise ValueError(f"Incomplete record: {path}:{line_number}; repair before restarting")
                completed.add(json.loads(line)["paper_id"])
                last_count += 1
    number = int(files[-1].stem.rsplit("-", 1)[1]) if files else 1
    return completed, number, last_count


def run(input_dir=INPUT_DIR, output_dir=OUTPUT_DIR):
    '''Run the graph extraction process on all JSONL files 
       in the input directory and save results to the output directory.'''

    # Gather all input files and ensure the output directory exists.
    input_files = sorted(input_dir.glob("*.jsonl"))
    if not input_files:
        raise FileNotFoundError(f"No publication JSONL files found in {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Read the set of already completed publications and determine the next file number to use.
    completed, number, count = read_completed(output_dir)
    started = perf_counter()
    saved = failed = skipped = scanned = 0
    print(f"Found {len(completed)} publications already saved in {output_dir}. "
          f"Scanning {len(input_files)} input files.", flush=True)

    # Define a helper function to print progress at various locations in the process.
    def print_progress(location):
        rate = saved / max(perf_counter() - started, 0.001) * 60
        print(f"{location}: scanned={scanned}, saved={saved}, skipped={skipped}, "
              f"failed={failed}, {rate:.1f} graphs/min", flush=True)

    # Initialize the model and schema to None before processing any files.
    model = schema = None
    for file_number, path in enumerate(input_files, 1):
        print(f"File {file_number}/{len(input_files)}: {path.name}", flush=True)

        # Print progress for the current file before starting line-by-line processing.
        with path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, 1):
                if not line.strip():
                    continue
                scanned += 1
                try:
                    publication = json.loads(line)
                    paper_id = publication_id(publication)
                    if not isinstance(publication["title"], str):
                        raise ValueError("title must be text")
                    if publication.get("abstract") is not None and not isinstance(publication["abstract"], str):
                        raise ValueError("abstract must be text or null")
                except (ValueError, KeyError, TypeError) as error:
                    failed += 1
                    print(f"ERROR: {path}:{line_number}: {error}. Continuing.", flush=True)
                    continue
                if paper_id in completed:
                    skipped += 1
                    if scanned % 1000 == 0:
                        print_progress(path.name)
                    continue
                if model is None and publication.get("abstract"):
                    model, schema = load_model()
                try:
                    # Attempt to extract the graph for the current publication.
                    graph = extract_graph(model, publication, schema)
                    line = json.dumps(graph, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                except (RuntimeError, ValueError, TypeError, KeyError, IndexError) as error:
                    failed += 1
                    print(f"ERROR: Extraction failed for {paper_id}: {error}. Continuing.", flush=True)
                    print_progress(path.name)
                    continue
                if count >= 1000:
                    number, count = number + 1, 0
                target = output_dir / f"graph_publications-{number:06d}.jsonl"
                # Close the complete record before marking the publication complete.
                with target.open("a", encoding="utf-8", newline="\n") as output:
                    output.write(line + "\n")
                # Mark the publication as completed to avoid reprocessing in future runs.
                completed.add(paper_id)
                saved += 1
                count += 1
                print_progress(path.name)
        print_progress(f"Completed {path.name}")
    print(f"Finished: {saved} saved, {skipped} skipped, {failed} failed. "
          "Restart to retry failures.", flush=True)


if __name__ == "__main__":
    run()
