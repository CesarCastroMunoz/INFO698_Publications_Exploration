from pathlib import Path

import streamlit as st

pages_dir = Path(__file__).parent / "pages"

st.set_page_config(
    page_title="Interactive Semantic Exploration of Academic Literature",
    layout="wide",
)

pages = [
    st.Page(pages_dir / "home.py", title="Home", default=True),
    st.Page(pages_dir / "publication_search.py", title="Search"),
    st.Page(pages_dir / "graph_explorer.py", title="Graph Explorer"),
    st.Page(pages_dir / "Deep_Dive.py", title="Deep Dive"),    
]

navigation = st.navigation(pages)
navigation.run()
