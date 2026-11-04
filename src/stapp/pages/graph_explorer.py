import streamlit as st
from psycopg2 import Error
from streamlit_agraph import agraph, Node, Edge, Config
import st_utilities
import math

@st.cache_data(ttl=300)
def load_one_hop(target_paper_id: str):
    """Load graph nodes with their stored properties."""
    return st_utilities.get_one_hop(target_paper_id)


@st.cache_data(ttl=300)
def load_two_hops(target_paper_id: str):
    """Cache two-hop graph results for five minutes per paper."""
    return st_utilities.get_two_hops(target_paper_id)


class GraphExplorer:
    def __init__(self):
        self.nodes = []
        self.edges = []

    def add_node(self, id, label):
        self.nodes.append(Node(id=id, label=label))

    def add_edge(self, source, target):
        self.edges.append(Edge(source=source, target=target))

    def get_one_hop(self, target_paper_id: str):
        self.nodes, self.edges = load_one_hop(target_paper_id)

    def get_two_hops(self, target_paper_id: str):
        self.nodes, self.edges = load_two_hops(target_paper_id)

    def semantic_search(self, query: str):
        self.nodes, self.edges = st_utilities.search_documents_via_graph(query)

    def explore_one_paper(self, target_paper_id: str, ref_filter=True):
        ''' After user click a paper trigger another graph display for that paper '''
        if target_paper_id:
            try:
                #self.get_one_hop(target_paper_id)
                self.get_two_hops(target_paper_id)
                
                if ref_filter:
                    self.nodes = [node for node in self.nodes if node.type != "Reference"]
                    node_ids = {node.id for node in self.nodes}
                    self.edges = [
                        edge for edge in self.edges
                        if edge.source in node_ids and edge.to in node_ids
                    ]
            except Error:
                st.error("Unable to load the graph from the database. Please try again.")
                return

        if not self.nodes and not self.edges:
            if target_paper_id:
                st.info("No relationships found. The Paper ID may not exist or may have no connected nodes.")
            else:
                st.info("Enter a Paper ID to display its relationships.")
        else:        
            # config = Config(
            #     width=700,
            #     height=800,
            #     directed=True,
            #     hierarchical=False,
            #     direction="LR",
            #     sortMethod="directed",
            #     levelSeparation=200,
            #     nodeSpacing=160,
            #     treeSpacing=200,
            #     physics=True,
            #     edges={
            #         "arrows": "to",
            #         "smooth": {
            #             "enabled": True,
            #             "type": "cubicBezier",
            #             "forceDirection": "horizontal",
            #         },
            #         "font": {"size": 11, "align": "middle"},
            #     },
            # )

            config = Config(
                width="100%",
                height=600,
                directed=True,
                hierarchical=False, 
                # Note: levelSeparation and nodeSpacing were removed because they only do something if hierarchical=True
                physics={
                    "enabled": True,
                    "solver": "forceAtlas2Based", # Better for separating distinct groups
                    "forceAtlas2Based": {
                        "gravitationalConstant": -30000, # Pushes distinct groups apart
                        "centralGravity": 0.01,        # Gentle pull to keep them on screen
                        "springLength": 80,            # SHORT springs to pull connected nodes close together
                        "springConstant": 0.08,        # STIFF springs so groups don't stretch out
                        "damping": 0.4,                # Higher damping to stop the groups from endlessly spinning
                        "avoidOverlap": 1,             # Strictly prevents node bounding boxes from touching
                    },
                    "minVelocity": 0.75,
                    "stabilization": {
                        "enabled": True,
                        "iterations": 1000,
                        "fit": True,
                    }
                },
                edges={
                    "arrows": "to",
                    "font": {"size": 11, "align": "middle"},
                },
            )

            colors = {
                "Publication": "#4C78A8",
                "Method": "#F58518",
                "Task": "#54A24B",
                "Medical_Condition": "#E45756",
                "Data_Modality": "#B279A2",
                "Metric": "#FFCA3A",
            }

            for node in self.nodes:
                node.color = colors.get(node.type, "#AAAAAA")   

            paper = next(
                (node for node in self.nodes if node.id == target_paper_id), None
            )
            abstract = (paper.properties or {}).get("abstract") if paper is not None else None
            if paper is not None:
                st.subheader(paper.label)
            graph_column, abstract_column = st.columns([2, 1])
            config.width = "100%"
            with graph_column:
                clicked_paper = agraph(nodes=self.nodes, edges=self.edges, config=config)
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
                st.subheader("Abstract")
                properties = (paper.properties or {}) if paper is not None else {}
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
                    st.info("No abstract available for this paper.")

    def render(self, ref_filter=True):
        st.title("Publications Explorer")

        search_prompt = st.text_input("Search:").strip()
        if st.session_state.get("graph_search_prompt") != search_prompt:
            st.session_state["graph_search_prompt"] = search_prompt
            st.session_state.pop("explored_paper_id", None)
            st.session_state.pop("graph_search_selection", None)
        if search_prompt:
            try:
                self.semantic_search(search_prompt)
                if ref_filter:
                    self.nodes = [node for node in self.nodes if node.type != "Reference"]
                    node_ids = {node.id for node in self.nodes}
                    self.edges = [
                        edge for edge in self.edges
                        if edge.source in node_ids and edge.to in node_ids
                    ]
            except Error:
                st.error("Unable to load the graph from the database. Please try again.")
                return

        if not self.nodes and not self.edges:
            if search_prompt:
                st.info("No relationships found. The search query may not match any documents.")
            else:
                st.info("Enter a search query to display its relationships.")
        else:        
            config = Config(
                width="100%",
                height=600,
                directed=True,
                hierarchical=False, 
                # Note: levelSeparation and nodeSpacing were removed because they only do something if hierarchical=True
                physics={
                    "enabled": True,
                    "solver": "forceAtlas2Based", # Better for separating distinct groups
                    "forceAtlas2Based": {
                        "gravitationalConstant": -30000, # Pushes distinct groups apart
                        "centralGravity": 0.01,        # Gentle pull to keep them on screen
                        "springLength": 80,            # SHORT springs to pull connected nodes close together
                        "springConstant": 0.08,        # STIFF springs so groups don't stretch out
                        "damping": 0.4,                # Higher damping to stop the groups from endlessly spinning
                        "avoidOverlap": 1,             # Strictly prevents node bounding boxes from touching
                    },
                    "minVelocity": 0.75,
                    "stabilization": {
                        "enabled": True,
                        "iterations": 1000,
                        "fit": True,
                    }
                },
                edges={
                    "arrows": "to",
                    "font": {"size": 11, "align": "middle"},
                },
            )

            colors = {
                "Publication": "#4C78A8",
                "Method": "#F58518",
                "Task": "#54A24B",
                "Medical_Condition": "#E45756",
                "Data_Modality": "#B279A2",
                "Metric": "#FFCA3A",
            }

            for node in self.nodes:
                node.color = colors.get(node.type, "#AAAAAA")   

            st.write("Click on a publication node to explore it")
            clicked_node = agraph(nodes=self.nodes, edges=self.edges, config=config)

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