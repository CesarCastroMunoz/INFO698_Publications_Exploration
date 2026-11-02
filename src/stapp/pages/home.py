import streamlit as st
import st_utilities as stu


class PublicationHomePage:
    def __init__(self):
        self.render()

    def render(self):

        dfs = stu.publications_summary()
        total_publications = int(dfs["pub_count"].sum()) if not dfs.empty else 0

        df_date_dist = stu.publication_date_distribution()
        max_date = df_date_dist["max_date"].iloc[0] if not df_date_dist.empty else None
        min_date = df_date_dist["min_date"].iloc[0] if not df_date_dist.empty else None

        st.title("Interactive Semantic Exploration of Academic Literature")

        st.markdown(
            "Explore academic literature through an interactive semantic interface.<br>"
            f"Total Available publications: {total_publications}.<br>"
            f"Publication Date Range: {min_date} to {max_date}.<br>"
            "Publication Summary:",
            unsafe_allow_html=True,
        )

        dfs.columns = ["Source", "Publication Count"]
        st.dataframe(dfs, width="content")

        df = stu.get_example_kg_publication()        
        if 'example_idx' not in st.session_state:
            st.session_state.example_idx = 0

        def select_example(title):
            st.session_state["pending_publication_concept"] = title

        row = df.iloc[st.session_state.example_idx]

        st.subheader("Feeling Curious?")
        with st.container(border=True):
            st.caption("🔍 Literature Example")
            st.markdown(f"### {str(row['medical_condition']).title()}")
            st.markdown(f"Studied in **{str(row['paper_title']).title()}**")
            st.markdown(f"Using the method **{str(row['method']).title()}**")
            
            if st.button("Search", on_click=select_example, args=(str(row["paper_title"]).title(),)):
                st.switch_page("pages/publication_search.py")


PublicationHomePage()