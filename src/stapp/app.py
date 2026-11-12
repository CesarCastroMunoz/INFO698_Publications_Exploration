from datetime import date
from pathlib import Path

import streamlit as st

pages_dir = Path(__file__).parent / "pages"
assets_dir = Path(__file__).parent / "assets"

def render_banner(title):
    """Small banner that fades from blue (left) to white (right).

    Args:
        title (str): The title to display in the banner.
    """
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

# Set up the Streamlit page and render the banner at the top.
st.set_page_config(
    page_title="Interactive Semantic Exploration of Academic Literature",
    layout="wide",
)
render_banner("Interactive Semantic Exploration of Academic Literature")

# Define the pages for the Streamlit app and set up navigation.
pages = [
    st.Page(pages_dir / "home.py", title="Home", default=True),
    st.Page(pages_dir / "LSearch.py", title="Search"),
    st.Page(pages_dir / "Explorer.py", title="Explorer"),
    st.Page(pages_dir / "AI_explorer.py", title="AI Assistant"),    
]

# Set up the navigation for the Streamlit app.
navigation = st.navigation(pages)

# Display the app logo at the top of the sidebar.
st.logo(str(assets_dir / "icon.svg"), size="large")

# Customize the sidebar appearance and add a footer with app information.
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
            <strong>Developed by:</strong> Cesar Castro<br>
            <strong>Course:</strong> INFO 698 Capstone<br>
            <strong>Revision:</strong> Nov. 2026
        </div>
        """,
        unsafe_allow_html=True,
    )

navigation.run()
