import streamlit as st

# Data pipeline for ingesting publications into the system.
# Import local modules for searching publications
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_pipeline.search_openalex import openalex_search_topic
from data_pipeline.search_sem_scholar import semantic_scholar_search_topic

import ingest_vectorDB as ivdb
import graph_extraction_gliner as geg
import embed_load_graphs as elg

# Defaults

health_terms = ['EHR','telemedicine','telehealth','wearables',
    'genomics','bioinformatics','precision medicine',
    'personalized medicine','radiology','pathology',
    'oncology','cardiology','epidemiology'
    ]

ai_terms = ['artificial intelligence','machine learning',
    'deep learning','data science',
    'predictive analytics','neural network',
    'neural networks','computer vision',
    'large language model','large language models'
    ]

# Local streamlit app to ingest publications into the system

class IngestPublicationsApp:
    """Streamlit app for ingesting publications into the system."""

    def run(self):
        """Run the Streamlit app."""

        st.title("Ingest Publications")
        st.write("Ingest academic publications into the system.")

        # Display the ingestion form for user input.
        with st.form("ingest_form"):
            health_input = st.text_area("Health terms (one per line)", value="\n".join(health_terms))
            ai_input = st.text_area("AI terms (one per line)", value="\n".join(ai_terms))
            max_results = st.number_input("Publication search limit per source", min_value=1, value=1000, step=1)
            from_date = st.date_input("From publication date", value=date(2024, 1, 1), min_value=date(1800, 1, 1), max_value=date.today())
            to_date = st.date_input("To publication date", value=date.today(), min_value=date(1800, 1, 1), max_value=date.today())
            st.caption("OpenAlex uses the start date only. Semantic Scholar uses the selected start and end years.")
            st.markdown("**Pipeline steps to run**")
            run_openalex = st.checkbox("Search OpenAlex", value=True)
            run_semantic = st.checkbox("Search Semantic Scholar", value=True)
            run_ingest = st.checkbox("Ingest to VectorDB", value=True)
            run_extract = st.checkbox("Extract Graphs", value=True)
            run_embed = st.checkbox("Embed and Load Graphs", value=True)
            submitted = st.form_submit_button("Run Selected Steps")

        # Handle form submission and execute selected pipeline steps.
        if submitted:
            if not any([run_openalex, run_semantic, run_ingest, run_extract, run_embed]):
                st.warning("Select at least one pipeline step.")
                return
            if run_openalex or run_semantic:
                if from_date > to_date:
                    st.warning("The start date must be on or before the end date.")
                    return
                if not self.process_topic(health_input, ai_input, max_results, from_date, to_date,
                                          search_openalex=run_openalex, search_semantic=run_semantic):
                    return
            if run_ingest:
                self.ingest_to_vectorDB()
            if run_extract:
                self.extract_graphs()
            if run_embed:
                self.embed_and_load_graphs()

    def process_topic(self, health_input, ai_input, max_results=1000, from_date=None, to_date=None,
                      search_openalex=True, search_semantic=True):
        '''Run the selected searches. Returns False when the input is invalid.

        Args:
            health_input (str): Multiline string of health-related search terms.
            ai_input (str): Multiline string of AI-related search terms.
            max_results (int, optional): Maximum number of search results to retrieve. Defaults to 1000.
            from_date (datetime.date, optional): Start date for the search range. Defaults to None.
            to_date (datetime.date, optional): End date for the search range. Defaults to None.
            search_openalex (bool, optional): Whether to search OpenAlex. Defaults to True.
            search_semantic (bool, optional): Whether to search Semantic Scholar. Defaults to True.

        Returns:
            bool: True if the search was executed successfully, False if input was invalid.
        '''
        health = list(dict.fromkeys(term.strip() for term in health_input.splitlines() if term.strip()))
        ai = list(dict.fromkeys(term.strip() for term in ai_input.splitlines() if term.strip()))
        if not health or not ai:
            st.warning("Enter at least one health term and one AI term.")
            return False
        if any('"' in term for term in health + ai):
            st.warning("Enter terms without double quotes; phrase quotes are added automatically.")
            return False
        health = [f'"{term}"' for term in health]
        ai = [f'"{term}"' for term in ai]
        openalex_topic = f"({' OR '.join(health)}) AND ({' OR '.join(ai)})"
        semantic_topic = f"({' | '.join(health)}) + ({' | '.join(ai)})"
        with st.spinner("Searching publications..."):
            if search_openalex:
                openalex_search_topic(
                    openalex_topic, max_results=max_results,
                    from_date=from_date.isoformat() if from_date else "2024-01-01",
                )
            if search_semantic:
                semantic_scholar_search_topic(
                    semantic_topic, max_results=max_results,
                    year_range=f"{from_date.year}-{to_date.year}" if from_date and to_date else "2000-",
                )

        st.success("Search completed. Publications saved to local JSONL files.")
        return True

    def ingest_to_vectorDB(self):
        """Ingest publications into the vector database."""
        with st.spinner("Ingesting publications to vector DB..."):
            ivdb.ingest_files()
        st.success("Ingestion to vector DB completed.")

    def extract_graphs(self):
        """Extract graphs from the ingested publications."""
        with st.spinner("Extracting graphs from publications..."):
            geg.run()
        st.success("Graph extraction completed.")

    def embed_and_load_graphs(self):
        """Embed and load the extracted graphs into the database."""
        with st.spinner("Embedding and loading graphs..."):
            elg.run(batch_size=100)
        st.success("Embedding and loading of graphs completed.")

IngestPublicationsApp().run()