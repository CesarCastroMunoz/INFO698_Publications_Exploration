from pathlib import Path

import streamlit as st

pages_dir = Path(__file__).parent / "pages"

st.set_page_config(
    page_title="Interactive Semantic Exploration of Academic Literature",
    layout="wide",
)

pages = [
    st.Page(pages_dir / "home.py", title="Home", default=True),
    st.Page(pages_dir / "publication_search.py", title="Publication Search"),
    st.Page(pages_dir / "page_3.py", title="Page 3"),
    st.Page(pages_dir / "page_4.py", title="Page 4"),
    st.Page(pages_dir / "page_5.py", title="Page 5"),
]

navigation = st.navigation(pages)
navigation.run()
