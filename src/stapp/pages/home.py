'''
Publication search page for the academic literature exploration app.
Feature 1. Home page and summary of publications.
Revision 1: Initial Rev. Cesar C. 11/01/2026
'''


import streamlit as st
import st_utilities as stu

# Cache the example publication for 60 seconds to avoid re-querying on clicks.
@st.cache_data(ttl=60)
def load_example():
    """Reuse the same random example for 60 seconds so clicks don't re-query."""
    return stu.get_example_kg_publication()


class PublicationHomePage:
    """Home page for the publication exploration app."""
    def __init__(self):
        self.render()

    def render(self):
        '''Render the home page for the publication exploration app.'''

        # Load the summary of publications and the date distribution.
        dfs = stu.publications_summary()
        total_publications = int(dfs["pub_count"].sum()) if not dfs.empty else 0

        # Load the date distribution of publications.
        df_date_dist = stu.publication_date_distribution()
        max_date = df_date_dist["max_date"].iloc[0] if not df_date_dist.empty else None
        min_date = df_date_dist["min_date"].iloc[0] if not df_date_dist.empty else None

        # Display the introductory caption for the home page.
        st.caption(
            "Discover hidden connections in research. An AI-powered platform to explore, "
            "visualize, and synthesize literature across AI, Data Science and healthcare."
        )

        # Set up the layout for the collection overview and the publications by source chart.
        details_column, chart_column = st.columns([1, 1], gap="large")
        with details_column:
            with st.container(border=True):
                st.markdown("### Collection Overview")
                st.metric("Available publications", f"{total_publications:,}")
                st.caption("PUBLICATION DATE RANGE")
                if min_date is not None and max_date is not None:
                    st.markdown(f"**{min_date}** to **{max_date}**")
                else:
                    st.caption("Date range unavailable.")

        # Display the collection overview in the details column.
        with chart_column:
            st.subheader("Publications by Source")
            if total_publications == 0:
                st.info("No publications available to display.")
            else:
                # Render the publications by source chart using Vega-Lite.
                st.vega_lite_chart(
                    dfs,
                    {
                        "height": 174,
                        "autosize": {"type": "fit-x", "contains": "padding"},
                        "padding": {"top": 12, "right": 12, "bottom": 12, "left": 12},
                        "transform": [
                            {
                                "joinaggregate": [
                                    {"op": "sum", "field": "pub_count", "as": "total"}
                                ]
                            },
                            {
                                "calculate": "datum.pub_count / datum.total",
                                "as": "percentage",
                            },
                        ],
                        "mark": {
                            "type": "arc",
                            "innerRadius": 40,
                            "outerRadius": 75,
                            "cornerRadius": 4,
                            "padAngle": 0.02,
                        },
                        "encoding": {
                            "theta": {"field": "pub_count", "type": "quantitative"},
                            "color": {
                                "field": "source",
                                "type": "nominal",
                                "title": "Source",
                                "scale": {"scheme": "tableau10"},
                                "legend": {"orient": "right", "direction": "vertical"},
                            },
                            "tooltip": [
                                {"field": "source", "type": "nominal", "title": "Source"},
                                {
                                    "field": "pub_count",
                                    "type": "quantitative",
                                    "title": "Publications",
                                    "format": ",",
                                },
                                {
                                    "field": "percentage",
                                    "type": "quantitative",
                                    "title": "Share",
                                    "format": ".1%",
                                },
                            ],
                        },
                        "config": {"view": {"stroke": None}},
                    },
                    width="stretch",
                )

        # Load an example publication for the "Feeling Curious?" section.
        df = load_example()
        if 'example_idx' not in st.session_state:
            st.session_state.example_idx = 0

        def select_example(title):
            '''Select an example publication and store it in the session state.'''
            st.session_state["pending_publication_concept"] = title

        row = df.iloc[st.session_state.example_idx]

        # Display the "Feeling Curious?" section with an example publication.
        st.subheader("Feeling Curious?")
        with st.container(border=True):
            st.caption("🔍 Literature Example")
            st.markdown(f"### {str(row['medical_condition']).title()}")
            st.markdown(f"Studied in **{str(row['paper_title']).title()}**")
            st.markdown(f"Using the method **{str(row['method']).title()}**")
            
            if st.button("Search", on_click=select_example, args=(str(row["paper_title"]).title(),)):
                st.switch_page("pages/LSearch.py")


PublicationHomePage()