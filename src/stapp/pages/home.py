import streamlit as st
import st_utilities as stu


class PublicationHomePage:
    def __init__(self):
        self.render()

    def render(self):

        dfs = stu.publications_summary()
        total_publications = int(dfs["pub_count"].sum()) if not dfs.empty else 0

        st.title("Interactive Semantic Exploration of Academic Literature")

        st.markdown(
            "Explore academic literature through an interactive semantic interface.<br>"
            f"Total Available publications: {total_publications}.<br>"
            "Publication Summary:",
            unsafe_allow_html=True,
        )

        dfs.columns = ["Source", "Publication Count"]
        st.dataframe(dfs, width="content")

        df = stu.get_example_kg_publication()        
        if 'example_idx' not in st.session_state:
            st.session_state.example_idx = 0

        def next_example():
            st.session_state.example_idx = (st.session_state.example_idx + 1) % len(df)

        row = df.iloc[st.session_state.example_idx]

        st.subheader("Feeling Curious?")
        with st.container(border=True):
            st.caption("🔍 Example Discovery")
            st.markdown(f"### {str(row['medical_condition']).title()}")
            st.markdown(f"Studied in **{str(row['paper_title']).title()}**")
            st.markdown(f"Using the method **{str(row['method']).title()}**")
            
            st.button("Shuffle Example 🎲", on_click=next_example)  


PublicationHomePage()