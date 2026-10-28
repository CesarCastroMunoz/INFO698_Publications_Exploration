"""Embed, archive, and load publication graphs, including older extraction files."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
import psycopg2
from psycopg2.extras import Json, execute_values

from graph_extraction import ALLOWED_EDGES, ALLOWED_NODES, OUTPUT_DIR

LOADABLE_NODES = ALLOWED_NODES + ["Model_Architecture", "Algorithm", "Medical_Condition"]
LOADABLE_EDGES = ALLOWED_EDGES + [
    "OUTPERFORMS", "STUDIES_CONDITION", "HAS_SYMPTOM", "TREATS", "CAUSES", "INHIBITS", "MENTIONS",
    "ADDRESSES_TASK",
]

load_dotenv(Path(__file__).resolve().parents[2] / "prod.env")
READY_DIR = Path(__file__).resolve().parents[1] / "graph_output"
_archive_state = {}


def save_ready_graphs(graphs, output_dir):
    """Append ready graphs, rotating at 1,000 records independently of DB batches."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir not in _archive_state:
        numbers = [
            int(path.stem.removeprefix("graph_publications-"))
            for path in output_dir.glob("graph_publications-*.jsonl")
            if path.stem.removeprefix("graph_publications-").isdigit()
        ]
        number = max(numbers, default=1)
        target = output_dir / f"graph_publications-{number:06d}.jsonl"
        count = 0
        if target.exists():
            with target.open("rb") as file:
                for line in file:
                    if not line.endswith(b"\n"):
                        raise ValueError(f"Incomplete record in {target}; repair before appending")
                    count += 1
        _archive_state[output_dir] = number, count
    number, count = _archive_state[output_dir]
    try:
        for graph in graphs:
            line = json.dumps(graph, ensure_ascii=False, allow_nan=False) + "\n"
            if count >= 1000:
                number, count = number + 1, 0
            target = output_dir / f"graph_publications-{number:06d}.jsonl"
            with target.open("a", encoding="utf-8", newline="\n") as file:
                file.write(line)
            count += 1
            _archive_state[output_dir] = number, count
    except OSError:
        _archive_state.pop(output_dir, None)
        raise


def validate_graph(graph):
    """Reject malformed files before any paid embedding request."""
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise ValueError("Graph must be an object with nodes and edges lists")
    nodes = graph["nodes"]
    if any(not isinstance(node, dict) for node in nodes):
        raise ValueError("Nodes must be objects")
    if any(not isinstance(node.get("id"), str) or not node["id"] for node in nodes):
        raise ValueError("Node IDs must be nonempty strings")
    node_ids = {node["id"] for node in nodes}
    if len(node_ids) != len(nodes):
        raise ValueError("Duplicate node IDs")
    publications = [node for node in nodes if node["label"] == "Publication"]
    if len(publications) != 1 or publications[0]["id"] != graph["paper_id"]:
        raise ValueError("Graph must have one matching Publication node")
    for node in nodes:
        if node["label"] not in LOADABLE_NODES + ["Publication", "Author", "Reference"]:
            raise ValueError(f"Unknown node label: {node['label']}")
        if not isinstance(node["name"], str) or not isinstance(node.get("properties", {}), dict):
            raise ValueError("Node name must be text and properties must be an object")
    labels = {node["id"]: node["label"] for node in nodes}
    kept_edges = []
    for edge in graph["edges"]:
        if not isinstance(edge, dict) or edge.get("relation") not in LOADABLE_EDGES + ["AUTHORED", "CITES"]:
            raise ValueError("Invalid edge or relation")
        if edge["source"] not in node_ids or edge["target"] not in node_ids:
            raise ValueError("Edge references a missing node")
        if not isinstance(edge.get("properties", {}), dict):
            raise ValueError("Edge properties must be an object")
        source, target, relation = edge["source"], edge["target"], edge["relation"]
        if relation == "AUTHORED":
            valid = target == graph["paper_id"] and labels[source] == "Author"
        elif relation == "CITES":
            valid = source == graph["paper_id"] and labels[target] == "Reference"
        else:
            valid = source == graph["paper_id"] and labels[target] in LOADABLE_NODES
        if not valid:
            print(f"Skipping non-publication or invalid edge for {graph['paper_id']}: {edge}")
            continue
        kept_edges.append(edge)
    return {**graph, "edges": kept_edges}


def load_batch(conn, client, graphs, *, ready_dir=None):
    """Skip committed papers, reuse stored vectors, and commit one deduplicated group."""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM kg_nodes WHERE label = 'Publication' AND id = ANY(%s)",
            ([graph["paper_id"] for graph in graphs],),
        )
        existing = {row[0] for row in cursor.fetchall()}
    new_graphs = {}
    for graph in graphs:
        if graph["paper_id"] not in existing:
            new_graphs.setdefault(graph["paper_id"], graph)
    if not new_graphs:
        conn.commit()
        return 0
    nodes, edges = {}, {}
    for graph in new_graphs.values():
        for node in graph["nodes"]:
            previous = nodes.get(node["id"])
            if previous and (previous["name"], previous["label"]) != (node["name"], node["label"]):
                raise ValueError(f"Conflicting shared node: {node['id']}")
            nodes[node["id"]] = {
                **node, "properties": {**(previous or {}).get("properties", {}), **node.get("properties", {})},
            }
        for edge in graph["edges"]:
            key = (edge["source"], edge["target"], edge["relation"])
            edges[key] = {**edge, "properties": {
                **edges.get(key, {}).get("properties", {}), **edge.get("properties", {}),
            }}
    semantic = [node for node in nodes.values() if node["label"] in LOADABLE_NODES]
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, name, embedding::text FROM kg_nodes WHERE id = ANY(%s) AND embedding IS NOT NULL",
            ([node["id"] for node in semantic],),
        )
        stored = {node_id: (name, vector) for node_id, name, vector in cursor.fetchall()}
    if any(node["id"] in stored and stored[node["id"]][0] != node["name"] for node in semantic):
        raise ValueError("Stored node ID has a different name; refusing to replace its embedding")
    # Release the read transaction while the external embedding API is running.
    conn.commit()
    texts = list(dict.fromkeys(
        node["name"] for node in semantic
        if node["id"] not in stored or stored[node["id"]][0] != node["name"]
    ))
    vectors = {}
    for node in semantic:
        if node.get("embedding") is not None:
            vector = node["embedding"]
            vector = json.loads(vector) if isinstance(vector, str) else vector
            if not isinstance(vector, list) or len(vector) != 512:
                raise ValueError(f"Invalid saved embedding for {node['id']}")
            vectors[node["name"]] = json.dumps(vector, allow_nan=False)
    texts = [text for text in texts if text not in vectors]
    for start in range(0, len(texts), 256):
        inputs = texts[start:start + 256]
        response = client.embeddings.create(
            model="text-embedding-3-small", input=inputs, dimensions=512,
        )
        indexed = {item.index: item.embedding for item in response.data}
        if set(indexed) != set(range(len(inputs))) or any(len(vector) != 512 for vector in indexed.values()):
            raise ValueError("Embedding response has incorrect indexes or dimensions")
        vectors.update((text, json.dumps(indexed[index])) for index, text in enumerate(inputs))
    for node in semantic:
        stored_node = stored.get(node["id"])
        node["embedding"] = (
            stored_node[1] if stored_node and stored_node[0] == node["name"] else vectors[node["name"]]
        )
    if ready_dir is not None:
        ready_graphs = [
            {
                **graph,
                "nodes": [
                    {**node, "embedding": json.loads(nodes[node["id"]]["embedding"])}
                    if node["label"] in LOADABLE_NODES else node
                    for node in graph["nodes"]
                ],
            }
            for graph in new_graphs.values()
        ]
        save_ready_graphs(ready_graphs, ready_dir)
        print(f"Saved {len(ready_graphs)} ready graphs in {ready_dir}")
    with conn.cursor() as cursor:
        execute_values(cursor, """
            INSERT INTO kg_nodes (id, label, name, properties, embedding) VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                properties = kg_nodes.properties || EXCLUDED.properties,
                embedding = COALESCE(EXCLUDED.embedding, kg_nodes.embedding)
        """, [
            (node["id"], node["label"], node["name"], Json(node.get("properties", {})), node.get("embedding"))
            for node in nodes.values()
        ], template="(%s,%s,%s,%s,%s::vector)", page_size=1000)
        if edges:
            execute_values(cursor, """
                INSERT INTO kg_edges (source, target, relation, properties) VALUES %s
                ON CONFLICT (source, target, relation) DO UPDATE SET
                    properties = kg_edges.properties || EXCLUDED.properties
            """, [
                (edge["source"], edge["target"], edge["relation"], Json(edge.get("properties", {})))
                for edge in edges.values()
            ], page_size=1000)
    conn.commit()
    return len(new_graphs)


def run(input_dir=None, *, batch_size=100, ready_dir=READY_DIR):
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    input_dir = OUTPUT_DIR if input_dir is None else input_dir
    archive_dir = None if input_dir.resolve() == ready_dir.resolve() else ready_dir
    input_files = sorted(input_dir.glob("graph_publications-*.jsonl"))
    if not input_files:
        raise FileNotFoundError(f"No graph JSONL files found in {input_dir}")
    database_url = os.environ.get("NEON_DATABASE_URL")
    api_key = os.environ.get("OPENAI_KEY")
    if not database_url or not api_key:
        raise ValueError("NEON_DATABASE_URL and OPENAI_KEY must be configured")
    loaded = failed = 0
    graphs = []
    with OpenAI(api_key=api_key) as client:
        conn = psycopg2.connect(database_url)
        try:
            def flush():
                nonlocal loaded, failed, conn
                if not graphs:
                    return
                try:
                    if conn.closed:
                        conn = psycopg2.connect(database_url)
                    loaded += load_batch(conn, client, graphs, ready_dir=archive_dir)
                    print(f"Loaded {loaded} publication graphs so far.")
                except (psycopg2.Error, OpenAIError, OSError, ValueError, TypeError, KeyError) as error:
                    failed += len(graphs)
                    if not conn.closed:
                        try:
                            conn.rollback()
                        except psycopg2.Error as rollback_error:
                            print(f"ERROR: Rollback failed: {rollback_error}")
                            conn.close()
                    print(f"ERROR: Group failed ({[g['paper_id'] for g in graphs]}): {error}. "
                          "Continuing; restart to retry.")
                graphs.clear()

            for path in input_files:
                with path.open(encoding="utf-8") as file:
                    for line_number, line in enumerate(file, 1):
                        if not line.strip():
                            continue
                        try:
                            if not line.endswith("\n"):
                                raise ValueError("Incomplete JSONL record; repair before loading")
                            graphs.append(validate_graph(json.loads(line)))
                        except (ValueError, TypeError, KeyError) as error:
                            failed += 1
                            print(f"ERROR: {path}:{line_number}: {error}. Continuing.")
                            continue
                        if len(graphs) >= batch_size:
                            flush()
                flush()
        finally:
            conn.close()
    print(f"Finished: {loaded} loaded, {failed} failed/skipped. Source JSONL is unchanged.")


if __name__ == "__main__":
    run(batch_size=100)
