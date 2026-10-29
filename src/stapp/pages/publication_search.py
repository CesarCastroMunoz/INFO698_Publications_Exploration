import csv

import streamlit as st
import st_utilities


class PublicationSearchPage:
    def run(self):
        st.title("Publication Search")
        st.write("Explore academic literature through an interactive semantic interface.")

        with st.form("publication_search"):
            search_input, search_button = st.columns([6, 1], vertical_alignment="bottom")
            with search_input:
                concept = st.text_input("Enter a concept to explore:")
            with search_button:
                submitted = st.form_submit_button("Search", width="stretch")
        if submitted:
            self.process_input(concept)
        self.beautify_results()

    def process_input(self, concept):
        if not concept.strip():
            st.warning("Enter a concept to search.")
            return
        with st.spinner("Searching publications..."):
            results = st_utilities.search_publications(concept.strip())
        st.session_state["publications"] = results
        st.session_state.pop("publication_selection", None)

    def beautify_results(self):
        publications = st.session_state.get("publications")
        if publications is None:
            return
        if publications.empty:
            st.info("No publications found.")
            return

        left, right = st.columns([3, 3])
        with left:
            st.subheader("Publications")
            selection = st.radio(
                "Select a publication",
                options=range(len(publications)),
                format_func=lambda row: publications.iloc[row]["title"],
                index=None,
                label_visibility="collapsed",
                key="publication_selection",
            )
        with right:
            if selection is None:
                st.info("Select a publication to view its details.")
                return
            result = publications.iloc[selection].dropna()
            st.subheader(result["title"])
            authors = result.get("authors") or []

            if isinstance(authors, str):
                authors = authors.strip()
                if authors.startswith("{") and authors.endswith("}"):
                    authors = next(csv.reader([authors[1:-1]], escapechar="\\"))
                else:
                    authors = [authors]
            details = ["**Authors:** " + ("; ".join(authors) or "Not available")]
            for label, field in (
                ("Publication date", "publication_date"),
                ("Source", "source"),
                ("Source ID", "source_id"),
            ):
                details.append(f"**{label}:** {result.get(field) or 'Not available'}")
            doi = result.get("doi")
            if not isinstance(doi, str) or not doi.strip():
                details.append("**DOI:** Not available")
            st.markdown("  \n".join(details))
            if isinstance(doi, str) and doi.strip():
                doi_url = doi if doi.startswith(("https://", "http://")) else f"https://doi.org/{doi}"
                st.link_button("Open DOI", doi_url)
            url = result.get("url")
            if isinstance(url, str) and url.strip():
                st.link_button("Publication website", url)
            st.markdown("#### Abstract")
            st.write(result.get("abstract") or "No abstract available.")
            with st.expander("References"):
                st.write(result.get("references") or "No references available.")


PublicationSearchPage().run()
