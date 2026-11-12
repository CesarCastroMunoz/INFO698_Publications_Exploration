'''
Graph explorer page for the academic literature exploration app.
Feature 3. Graph exploration for academic publications. 2. One-hop and semantic search capabilities.
Revision 1: Initial Rev. Cesar C. 11/02/2026
'''


import streamlit as st
from psycopg2 import Error
from streamlit_agraph import Node, Edge
import st_utilities
import graph_utilities
import math

# Load and explore publication graphs with one-hop and semantic search capabilities.
@st.cache_data(ttl=300)
def load_one_hop(target_paper_id: str):
    """Load graph nodes with their stored properties."""
    return st_utilities.get_one_hop(target_paper_id)


class GraphExplorer:
    '''Graph explorer class for the academic literature exploration app.'''
    def __init__(self):
        self.nodes = []
        self.edges = []

    def add_node(self, id, label):
        '''Add a node to the graph.
        Args:
            id (str): The unique identifier of the node.
            label (str): The label to display for the node.
        Returns:
            None
        '''
        self.nodes.append(Node(id=id, label=label))

    def add_edge(self, source, target):
        '''Add an edge to the graph.
        Args:
            source (str): The source node ID.
            target (str): The target node ID.
        Returns:
            None
        '''
        self.edges.append(Edge(source=source, target=target))

    def get_one_hop(self, target_paper_id: str):
        '''Load the one-hop graph for the target paper.
        Args:
            target_paper_id (str): The ID of the target paper.
        Returns:
            None
        '''
        self.nodes, self.edges = load_one_hop(target_paper_id)

    def semantic_search(self, condition: str, method: str):
        '''Perform a semantic search for papers related to the given condition and method.
        Args:
            condition (str): The condition to search for.
            method (str): The method to search for.
        Returns:
            None
        '''
        queries = [text for text in (condition, method) if text]
        self.nodes, self.edges = st_utilities.search_documents_via_graph(queries)

    def explore_one_paper(self, target_paper_id: str, ref_filter=True):
        ''' After user click a paper trigger another graph display for that paper
        Args:
            target_paper_id (str): The ID of the target paper.
            ref_filter (bool): Whether to apply reference filtering.
        Returns:
            None
        '''
        if target_paper_id:
            try:
                #self.get_one_hop(target_paper_id)
                self.nodes, self.edges = graph_utilities.load_paper_graph(target_paper_id, ref_filter)
            except Error:
                st.error("Unable to load the graph from the database. Please try again.")
                return

        # Check if the graph has any nodes or edges to display.
        if not self.nodes and not self.edges:
            if target_paper_id:
                st.info("No relationships found. The Paper ID may not exist or may have no connected nodes.")
            else:
                st.info("Enter a Paper ID to display its relationships.")
        else:        
            # Display the graph and abstract for the target paper.
            paper = next(
                (node for node in self.nodes if node.id == target_paper_id), None
            )
            abstract = (paper.properties or {}).get("abstract") if paper is not None else None
            if paper is not None:
                st.subheader(paper.label)
            # Display the paper title as a subheader if available.
            graph_column, abstract_column = st.columns([2, 1])
            with graph_column:
                with st.container(border=True):
                    clicked_paper = graph_utilities.draw_graph(self.nodes, self.edges)
                selected_paper = next(
                    (node for node in self.nodes if node.id == clicked_paper), None
                )
                if (
                    selected_paper is not None
                    and selected_paper.type == "Publication"
                    and clicked_paper != target_paper_id
                ):
                    st.session_state["explored_paper_id"] = clicked_paper
                    st.rerun()
            with abstract_column:
                with st.form("abstract_form"):
                    st.subheader("Abstract")
                    properties = (paper.properties or {}) if paper is not None else {}
                    author_ids = {
                        edge.source for edge in self.edges
                        if edge.label == "AUTHORED" and edge.to == target_paper_id
                    }
                    authors = [
                        node.label for node in self.nodes
                        if node.type == "Author" and node.id in author_ids
                    ]
                    st.markdown("**Authors:** " + ("; ".join(authors) or "Not available"))
                    st.markdown(f"**Publication date:** {properties.get('publication_date') or 'Not available'}")
                    doi = properties.get("doi")
                    url = properties.get("url")
                    if isinstance(doi, str) and doi.strip():
                        doi = doi.strip()
                        doi_url = doi if doi.startswith(("https://", "http://")) else f"https://doi.org/{doi}"
                        st.link_button("Open DOI", doi_url)
                    elif isinstance(url, str) and url.strip():
                        st.link_button("Open paper", url.strip())
                    if abstract and abstract.strip():
                        st.write(abstract)
                    else:
                        st.write("No abstract available.")
                        st.info("No abstract available for this paper.")

    def render(self, ref_filter=True):
        '''Render the publications explorer page.
        Args:
            ref_filter (bool): Whether to apply reference filtering when displaying the graph.
        Returns:
            None
        '''
        st.title("Publications Explorer")

        with st.form("graph_search"):
            condition_column, method_column, button_column = st.columns([3, 3, 1], vertical_alignment="bottom")
            condition = condition_column.text_input("Medical Condition or Topic:").strip()
            method = method_column.text_input("Method or Task:").strip()
            button_column.form_submit_button("Search", width="stretch")
        search_prompt = (condition, method)
        if st.session_state.get("graph_search_prompt") != search_prompt:
            st.session_state["graph_search_prompt"] = search_prompt
            st.session_state.pop("explored_paper_id", None)
            st.session_state.pop("graph_search_selection", None)
        if condition or method:
            try:
                self.semantic_search(condition, method)
                if ref_filter:
                    self.nodes, self.edges = graph_utilities.remove_references(self.nodes, self.edges)
            except Error:
                st.error("Unable to load the graph from the database. Please try again.")
                return

        if not self.nodes and not self.edges:
            if condition or method:
                st.info("No relationships found. The search may not match any documents.")
            else:
                st.info("Enter a medical condition, a method, or both to display their relationships.")
        else:        
            st.write("Click on a publication node to explore it")
            with st.container(border=True):
                clicked_node = graph_utilities.draw_graph(self.nodes, self.edges)

            if clicked_node:
                selected_node = next(
                    (node for node in self.nodes if node.id == clicked_node), None
                )
                if selected_node is not None and selected_node.type == "Publication":
                    if st.session_state.get("graph_search_selection") != clicked_node:
                        st.session_state["explored_paper_id"] = clicked_node
                else:
                    st.info("Click a publication node to explore its relationships.")
            st.session_state["graph_search_selection"] = clicked_node

            explored_paper_id = st.session_state.get("explored_paper_id")
            if explored_paper_id:
                GraphExplorer().explore_one_paper(explored_paper_id, ref_filter=ref_filter)

GraphExplorer().render()