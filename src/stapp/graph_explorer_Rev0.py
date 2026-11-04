import streamlit as st
from psycopg2 import Error
from streamlit_agraph import agraph, Node, Edge, Config
import st_utilities


@st.cache_data(ttl=300)
def load_one_hop(target_paper_id: str):
    return st_utilities.get_one_hop(target_paper_id)


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

    def render(self, ref_filter=True):
        st.title("Publications Explorer")

        target_paper_id = st.text_input("Enter Paper ID:").strip()
        if target_paper_id:
            try:
                self.get_one_hop(target_paper_id)
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
            config = Config(
                width=1200,
                height=600,
                directed=True,
                hierarchical=True,
                direction="UD",
                sortMethod="directed",
                levelSeparation=200,
                nodeSpacing=160,
                treeSpacing=200,
                physics=False,
                edges={
                    "arrows": "to",
                    "smooth": {
                        "enabled": True,
                        "type": "cubicBezier",
                        "forceDirection": "horizontal",
                    },
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

            clicked_node = agraph(nodes=self.nodes, edges=self.edges, config=config)

            if clicked_node:
                st.write(f"You clicked on: {clicked_node}")

GraphExplorer().render()