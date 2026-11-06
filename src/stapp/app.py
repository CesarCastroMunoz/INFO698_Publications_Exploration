from datetime import date
from pathlib import Path

import streamlit as st

pages_dir = Path(__file__).parent / "pages"
assets_dir = Path(__file__).parent / "assets"

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
    st.Page(pages_dir / "graph_explorer.py", title="Explorer"),
    st.Page(pages_dir / "Deep_Dive.py", title="Deep Dive"),    
]

navigation = st.navigation(pages)

st.logo(str(assets_dir / "icon.svg"), size="large")

with st.sidebar:
    st.markdown(
        f"""
        <style>
        [data-testid="stMainBlockContainer"] {{
            padding-top: 4rem;
        }}
        [data-testid="stSidebarContent"] {{
            display: flex; flex-direction: column;
        }}
        [data-testid="stSidebarHeader"] {{
            position: relative; justify-content: center;
            height: auto; min-height: 96px; flex-shrink: 0;
            padding-top: 8px; padding-bottom: 8px; box-sizing: border-box;
        }}
        [data-testid="stSidebarHeader"] [data-testid="stLogoLink"] {{
            margin: 0 auto;
        }}
        [data-testid="stSidebarHeader"] img {{
            height: 80px; width: auto; max-width: 100%; object-fit: contain;
        }}
        [data-testid="stSidebarHeader"] [data-testid="stSidebarCollapseButton"] {{
            position: absolute; right: 0.5rem; top: 50%; transform: translateY(-50%);
        }}
        .sidebar-footer {{
            position: fixed; bottom: 0; left: 0; width: 21rem; max-width: 100%;
            padding: 0.8rem 1rem; font-size: 0.8rem; color: #5F6B7A;
            line-height: 1.5;
        }}
        </style>
        <div class="sidebar-footer">
            <strong>University of Arizona</strong><br>
            <strong>Developed by:</strong> C. Castro<br>
            <strong>Course:</strong> INFO 698 Capstone        
        </div>
        """,
        unsafe_allow_html=True,
    )

navigation.run()
