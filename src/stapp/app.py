from pathlib import Path

import streamlit as st

pages_dir = Path(__file__).parent / "pages"

def render_banner(title):
    """Small banner that fades from blue (left) to white (right)."""
    st.markdown(
        f"""
        <div style="background: linear-gradient(90deg, #1F4E79 0%, #1F4E79 45%, #FFFFFF 100%);
                    color: #FFFFFF; padding: 0.6rem 1.2rem; border-radius: 6px;
                    font-size: 1.05rem; font-weight: 600; letter-spacing: 0.02em;
                    margin-bottom: 1rem;">
            {title}
        </div>
        """,
        unsafe_allow_html=True,
    )

st.set_page_config(
    render_banner("Interactive Semantic Exploration of Academic Literature"),
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
