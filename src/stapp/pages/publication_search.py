import csv

import streamlit as st
from psycopg2 import Error

import graph_utilities
import st_utilities


class PublicationSearchPage:
    def run(self):
        st.title("Publication Search")
        st.write("Explore academic literature through an interactive semantic interface.")

        # Check if the search was initiated from the home page with a pending publication concept.
        search_from_home = "pending_publication_concept" in st.session_state
        if search_from_home:
            st.session_state["publication_concept"] = st.session_state.pop("pending_publication_concept")

        # Display the search form for the publication concept.
        with st.form("publication_search"):
            search_input, search_button = st.columns([6, 1], vertical_alignment="bottom")
            with search_input:
                concept = st.text_input("Enter a concept to explore:", key="publication_concept")
            with search_button:
                submitted = st.form_submit_button("Search", width="stretch")
            only_abstract = st.checkbox("Only articles with an abstract", key="only_abstract")
        if submitted or search_from_home:
            self.process_input(concept, abstract=only_abstract)
        self.beautify_results()

    def process_input(self, concept, abstract=False):
        '''Process the input concept and perform a search for publications.'''
        if not concept.strip():
            st.warning("Enter a concept to search.")
            return
        with st.spinner("Searching publications..."):
            results = st_utilities.search_publications(concept.strip(), abstract=abstract)
        st.session_state["publications"] = results
        st.session_state.pop("search_paper_id", None)

    def beautify_results(self):
        '''Display the search results in a user-friendly format.'''
        publications = st.session_state.get("publications")
        if publications is None:
            return
        if publications.empty:
            st.info("No publications found.")
            return

        paper_ids = [
            graph_utilities.kg_paper_id(source, source_id)
            for source, source_id in zip(publications["source"], publications["source_id"])
        ]

        def select_publication(paper_id):
            st.session_state["search_paper_id"] = paper_id

        st.subheader("Select a Publication")
        selected_id = st.session_state.get("search_paper_id")
        selection_columns = st.columns(2, gap="small")
        midpoint = (len(publications) + 1) // 2
        for column, rows in zip(
            selection_columns,
            (range(midpoint), range(midpoint, len(publications))),
        ):
            with column, st.container(gap=None):
                for row in rows:
                    st.button(
                        publications.iloc[row]["title"],
                        key=f"select_publication_{row}",
                        type="primary" if selected_id == paper_ids[row] else "secondary",
                        width="stretch",
                        on_click=select_publication,
                        args=(paper_ids[row],),
                    )

        st.divider()
        if selected_id is None:
            st.info("Select a publication to view its details.")
            return

        try:
            nodes, edges = graph_utilities.load_paper_graph(selected_id)
        except Error:
            st.error("Unable to load the graph from the database. Please try again.")
            return

        result = self.get_result(publications, paper_ids, selected_id, nodes)
        if result is None:
            st.info("No information found for this publication.")
            return
        st.subheader(result["title"])
        graph_column, details_column = st.columns(2)
        with graph_column:
            if not nodes:
                st.info("No graph available for this publication.")
            else:
                clicked_id = graph_utilities.draw_graph(nodes, edges)
                clicked = next((node for node in nodes if node.id == clicked_id), None)
                if clicked is not None and clicked.type == "Publication" and clicked_id != selected_id:
                    st.session_state["search_paper_id"] = clicked_id
                    st.rerun()
        with details_column:
            self.show_details(result)

    def get_result(self, publications, paper_ids, paper_id, nodes):
        '''Return the publication details: the search result row, or the graph node if it is not in the results.'''
        if paper_id in paper_ids:
            return publications.iloc[paper_ids.index(paper_id)].dropna()
        paper = next((node for node in nodes if node.id == paper_id), None)
        if paper is None:
            return None
        return {**(paper.properties or {}), "title": paper.label}

    def show_details(self, result):
        '''Display the authors, links, abstract and references of the selected publication.'''
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
