"""Extract publication graphs with the selected model and save restartable JSONL.
   Revision 1: Initial implementation. 10/25/2026

   This module uses LLM calls to extract semantic graphs from publication metadata, including entities and their relations.
   For larger quantity of documents, this method can be slow due to the reliance on LLM calls for each publication.

   Dependencies for Gemma 4 include running local LM studio for model inference.
"""

import json
import os
from pathlib import Path
from time import perf_counter
from urllib.parse import quote
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field, ValidationError, field_validator

load_dotenv(Path(__file__).resolve().parents[2] / "prod.env")

INPUT_DIR = Path(__file__).resolve().parents[1] / "publications"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "graph_extracted"

USE_LOCAL = False  # True = local Gemma 4; False = OpenAI
MODEL = "google/gemma-4-12b-qat" if USE_LOCAL else "gpt-6-luna"

# Define allowed node and edge types for the semantic graph.
ALLOWED_NODES = [
    "Method", "Task", "Condition", "Data_Modality", "Metric",
    "Dataset", "Chemical_or_Drug",
    "Institution", "Symptom",
]
ALLOWED_EDGES = [
    "USES_METHOD", "TARGETS_TASK", "EVALUATED_ON", "TRAINED_WITH",
    "MEASURED_BY",
]


class ExtractedNode(BaseModel):
    """Represents a node in the extracted semantic graph."""
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    label: Literal[
        "Method", "Task", "Condition", "Data_Modality", "Metric",
        "Model_Architecture", "Dataset", "Algorithm", "Chemical_or_Drug",
        "Institution", "Symptom",
    ]
    name: str = Field(min_length=1)
    properties: dict = Field(default_factory=dict)
    publication_relation: Literal[
        "USES_METHOD", "TARGETS_TASK", "EVALUATED_ON", "TRAINED_WITH",
        "MEASURED_BY", "OUTPERFORMS", "STUDIES_CONDITION", "HAS_SYMPTOM",
        "TREATS", "CAUSES", "INHIBITS",
    ] = Field(description="Allowed relation FROM the publication TO this entity")

    @field_validator("properties", mode="before")
    @classmethod
    def normalize_properties(cls, value):
        if isinstance(value, list) and not value:
            print("Model returned properties=[]; converting to {}.")
            return {}
        return value


class GraphExtraction(BaseModel):
    """Represents the extracted semantic graph for a publication."""
    nodes: list[ExtractedNode] = Field(max_length=7)


def is_publication_edge(edge, paper_id, labels):
    source, target, relation = edge["source"], edge["target"], edge["relation"]
    if relation == "AUTHORED":
        return target == paper_id and labels.get(source) == "Author"
    if relation == "CITES":
        return source == paper_id and labels.get(target) == "Reference"
    return source == paper_id and labels.get(target) in ALLOWED_NODES and relation in ALLOWED_EDGES


def publication_id(publication):
    """Construct a unique identifier for the publication based on its source and source_id."""
    return f"paper:{quote(publication['source'], safe='')}:{quote(publication['source_id'], safe='')}"


def extract_graph(client, publication, *, model=MODEL, local=True):
    """Keep metadata deterministic and ask the model only for semantic entities."""
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
    for index, name in enumerate(publication.get("authors") or []):
        provider_id = author_ids[index] if index < len(author_ids) else None
        author_id = (
            f"author:provider:{quote(publication['source'], safe='')}:{quote(str(provider_id), safe='')}"
            if provider_id else f"{paper_id}:author:{index}"
        )
        nodes[author_id] = {"id": author_id, "label": "Author", "name": name, "properties": {}}
        edges.append({"source": author_id, "target": paper_id, "relation": "AUTHORED", "properties": {}})
    for index, reference in enumerate(publication.get("references") or []):
        reference_id = f"{paper_id}:reference:{index}"
        nodes[reference_id] = {
            "id": reference_id, "label": "Reference", "name": reference, "properties": {},
        }
        edges.append({"source": paper_id, "target": reference_id, "relation": "CITES", "properties": {}})

    if publication.get("abstract"):
        schema = GraphExtraction.model_json_schema()
        prompt = (
            "Extract only facts supported by this medical-AI publication's title and abstract. "
            f"Return up to 7 important entities. Allowed labels: {', '.join(ALLOWED_NODES)}. "
            f"Allowed relations: {', '.join(ALLOWED_EDGES)}. "
            "Use concise standardized lowercase names and unique snake_case IDs. "
            "IDs may start with a letter or digit, for example 3d_u_net. "
            "For example, the entity random forest has ID random_forest, not the publication ID. "
            "Do not extract authors, references, or the publication itself. "
            "Each node must include publication_relation: the most appropriate allowed relation "
            "FROM the publication TO that entity. The application creates those edges. "
            "Do not return an edges list or entity-to-entity relationships. "
            "Never invent facts. properties must be objects, using {} when empty. "
            "Return only the JSON graph, without markdown or explanation."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Title: {publication['title']}\nAbstract: {publication['abstract']}"},
        ]
        if local:
            response = client.chat.completions.create(
                model=model, messages=messages, temperature=0, reasoning_effort="none",
                max_tokens=4096,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "GraphExtraction", "schema": schema},
                },
            )
            choice = response.choices[0]
            if choice.finish_reason != "stop" or not choice.message.content:
                raise ValueError(f"Incomplete extraction: finish_reason={choice.finish_reason}")
            content = choice.message.content
        else:
            response = client.responses.create(
                model=model, input=messages,
                text={"format": {
                    "type": "json_schema", "name": "GraphExtraction", "schema": schema, "strict": False,
                }},
            )
            if response.status != "completed" or not response.output_text:
                raise ValueError(f"Incomplete extraction: status={response.status}")
            content = response.output_text
        graph = GraphExtraction.model_validate_json(content)
        for node in graph.nodes:
            if node.id in nodes or not node.id.strip() or not node.name.strip():
                raise ValueError(f"Duplicate, reserved, or empty entity: {node.id}")
            nodes[node.id] = node.model_dump(exclude={"publication_relation"})
            edges.append({
                "source": paper_id, "target": node.id,
                "relation": node.publication_relation, "properties": {},
            })

    unique_edges = {(edge["source"], edge["target"], edge["relation"]): edge for edge in edges}
    return {
        "paper_id": paper_id, "source": publication["source"], "source_id": publication["source_id"],
        "doi": publication.get("doi"), "nodes": list(nodes.values()), "edges": list(unique_edges.values()),
    }


def read_completed(output_dir):
    """Scan successful output once on startup; refuse to append after a torn write."""
    completed = set()
    files = sorted(output_dir.glob("graph_publications-*.jsonl"))
    last_count = 0
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


def run(input_dir=INPUT_DIR, output_dir=OUTPUT_DIR, *, model=MODEL,
        base_url="http://127.0.0.1:1234/v1", local=True):
    input_files = sorted(input_dir.glob("*.jsonl"))
    if not input_files:
        raise FileNotFoundError(f"No publication JSONL files found in {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    completed, number, count = read_completed(output_dir)
    started = perf_counter()
    saved = failed = skipped = scanned = 0
    print(f"Found {len(completed)} publications already saved in {output_dir}. "
          f"Scanning {len(input_files)} input files.", flush=True)

    def print_progress(location):
        rate = saved / max(perf_counter() - started, 0.001) * 60
        print(f"{location}: scanned={scanned}, saved={saved}, skipped={skipped}, "
              f"failed={failed}, {rate:.1f} graphs/min", flush=True)

    api_key = "lm-studio" if local else os.environ.get("OPENAI_KEY")
    if not api_key:
        raise ValueError("OPENAI_KEY must be configured")
    with OpenAI(base_url=base_url, api_key=api_key, timeout=180, max_retries=2) as client:
        for file_number, path in enumerate(input_files, 1):
            print(f"File {file_number}/{len(input_files)}: {path.name}", flush=True)
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
                    except (ValueError, KeyError, TypeError) as error:
                        failed += 1
                        print(f"ERROR: {path}:{line_number}: {error}. Continuing.")
                        continue
                    if paper_id in completed:
                        skipped += 1
                        if scanned % 1000 == 0:
                            print_progress(path.name)
                        continue
                    try:
                        graph = extract_graph(client, publication, model=model, local=local)
                    except (OpenAIError, ValidationError, ValueError, TypeError, KeyError, IndexError) as error:
                        failed += 1
                        print(f"ERROR: Extraction failed for {paper_id}: {error}. Continuing.")
                        print_progress(path.name)
                        continue
                    if count >= 1000:
                        number, count = number + 1, 0
                    target = output_dir / f"graph_publications-{number:06d}.jsonl"
                    line = json.dumps(graph, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                    # Close the complete record before marking the publication complete.
                    with target.open("a", encoding="utf-8", newline="\n") as output:
                        output.write(line + "\n")
                    completed.add(paper_id)
                    saved += 1
                    count += 1
                    print_progress(path.name)
            print_progress(f"Completed {path.name}")
    print(f"Finished: {saved} saved, {skipped} skipped, {failed} failed. "
          "Restart to retry failures.", flush=True)


if __name__ == "__main__":
    run(
        model=MODEL,
        local=USE_LOCAL,
        base_url="http://127.0.0.1:1234/v1" if USE_LOCAL else "https://api.openai.com/v1",
        output_dir=OUTPUT_DIR,
    )
