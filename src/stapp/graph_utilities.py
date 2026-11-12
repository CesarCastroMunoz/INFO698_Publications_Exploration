'''
Graph helpers shared by the Streamlit pages (Explorer and Publication Search).
Revision 1: Initial Rev. Cesar C. 11/05/2026
'''

from urllib.parse import quote
import copy

import streamlit as st
from rapidfuzz import fuzz, process
from streamlit_agraph import agraph, Config

import st_utilities

NODE_COLORS = {
    "Publication": "#4C78A8",
    "Method": "#F58518",
    "Task": "#54A24B",
    "Medical_Condition": "#E45756",
    "Data_Modality": "#B279A2",
    "Metric": "#FFCA3A",
    "Reference": "#B072B3",
    "Author": "#DAE7C1"
}

# Concept names scoring at least this (0-100, RapidFuzz token_set_ratio) are merged into one node.
# 100 is the strictest: only identical names, or names whose words all appear in the other name
# (e.g. "artificial intelligence (ai)" and "artificial intelligence (ai) for automated cancer").
# Lower it to merge more loosely similar names.
NAME_MERGE_THRESHOLD = 90


def kg_paper_id(source, source_id):
    '''Knowledge graph node id of a publication (same format used when the graph is loaded).

    Args:
        source (str): The source of the publication (e.g., journal name).
        source_id (str): The unique identifier of the publication within the source.

    Returns:
        str: The knowledge graph node id for the publication.
    '''
    return f"paper:{quote(source, safe='')}:{quote(source_id, safe='')}"


@st.cache_data(ttl=300)
def load_two_hops(target_paper_id: str):
    """Cache two-hop graph results for five minutes per paper.

    Args:
        target_paper_id (str): The knowledge graph node id of the target paper.

    Returns:
        tuple: A tuple containing the nodes and edges around the target paper.
    """
    return st_utilities.get_two_hops(target_paper_id)


def remove_references(nodes, edges):
    '''Drop Reference nodes and any edge that touches them.

    Args:
        nodes (list): The list of graph nodes.
        edges (list): The list of graph edges.

    Returns:
        tuple: A tuple containing the filtered nodes and edges.
    '''
    nodes = [node for node in nodes if node.type != "Reference"]
    node_ids = {node.id for node in nodes}
    edges = [edge for edge in edges if edge.source in node_ids and edge.to in node_ids]
    return nodes, edges


def load_paper_graph(target_paper_id: str, ref_filter=True):
    '''Return (nodes, edges) around a paper. Raises psycopg2.Error if the database fails.

    Args:
        target_paper_id (str): The knowledge graph node id of the target paper.
        ref_filter (bool): Whether to remove reference nodes and their edges.

    Returns:
        tuple: A tuple containing the nodes and edges around the target paper.
    '''
    nodes, edges = load_two_hops(target_paper_id)
    if ref_filter:
        nodes, edges = remove_references(nodes, edges)
    return nodes, edges


def merge_duplicates(nodes, edges, threshold=NAME_MERGE_THRESHOLD):
    '''Merge concept nodes with similar names into the first one (its name is kept) and redirect their edges.
    Publications are not fuzzy matched: they only merge when the titles are identical.

    Args:
        nodes (list): The list of graph nodes.
        edges (list): The list of graph edges.
        threshold (int): The fuzzy matching threshold for concept names.

    Returns:
        tuple: A tuple containing the merged nodes and edges.
    '''
    papers = {}
    concepts = {}
    new_id = {}
    for node in nodes:
        name = " ".join((node.label or node.id).lower().split())
        if node.type == "Publication":
            new_id[node.id] = papers.setdefault(name, node).id
            continue
        match = process.extractOne(name, list(concepts), scorer=fuzz.token_set_ratio, score_cutoff=threshold)
        first = concepts[match[0]] if match else concepts.setdefault(name, node)
        new_id[node.id] = first.id
    kept = [node for node in nodes if new_id[node.id] == node.id]

    merged_edges = {}
    for edge in edges:
        source, target = new_id.get(edge.source, edge.source), new_id.get(edge.to, edge.to)
        if source == target:
            continue
        merged = copy.copy(edge)
        merged.source, merged.to = source, target
        merged.__dict__["from"] = source  # agraph sends "from", not "source"
        merged_edges.setdefault((source, target, getattr(edge, "label", None)), merged)
    return kept, list(merged_edges.values())


def draw_graph(nodes, edges):
    '''Merge duplicate nodes, color the nodes by type, draw the graph and return the id of the clicked node.

    Args:
        nodes (list): The list of graph nodes.
        edges (list): The list of graph edges.

    Returns:
        str: The id of the clicked node in the graph.
    '''
    nodes, edges = merge_duplicates(nodes, edges)
    config = Config(
        width="100%",
        height=600,
        directed=True,
        hierarchical=False,
        physics={
            "enabled": True,
            "solver": "forceAtlas2Based",  # Better for separating distinct groups
            "forceAtlas2Based": {
                "gravitationalConstant": -30000,  # Pushes distinct groups apart
                "centralGravity": 0.01,  # Gentle pull to keep them on screen
                "springLength": 80,  # Short springs pull connected nodes close together
                "springConstant": 0.08,  # Stiff springs so groups don't stretch out
                "damping": 0.4,  # Higher damping stops the groups from endlessly spinning
                "avoidOverlap": 1,  # Prevents node bounding boxes from touching
            },
            "minVelocity": 0.75,
            "stabilization": {
                "enabled": True,
                "iterations": 1000,
                "fit": True,
            },
        },
        edges={
            "arrows": "to",
            "font": {"size": 11, "align": "middle"},
        },
    )
    for node in nodes:
        node.color = NODE_COLORS.get(node.type, "#AAAAAA")
    return agraph(nodes=nodes, edges=edges, config=config)
