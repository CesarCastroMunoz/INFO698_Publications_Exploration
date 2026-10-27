'''
Utilities to search multiple sources for publications related to a specific topic
Collect publication metadata and abstracts in JSONL batches.
Revision 1: Initial Rev. Cesar C. 10/12/2026
Revision 1.1: Implementing transform_clean.py to reduce code duplication Cesar C. 10/14/2026

# Citing the OpenAlex Python interface library:
# de Bruin, J. (2025). pyalex: A Python library for OpenAlex. 
# URL: https://github.com/J535D165/pyalex
'''

import os
from dotenv import load_dotenv
from requests.exceptions import RequestException

if __package__:
    from .transform_clean import OUTPUT_DIR, Publication, PublicationBuffer, get_existing_ids
else:
    from transform_clean import OUTPUT_DIR, Publication, PublicationBuffer, get_existing_ids

# Get secrets and other variables 
load_dotenv("prod.env")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY")
USER_EMAIL = os.getenv("USER_EMAIL")

# Use PYALEX library to extract publication data
import pyalex
from pyalex import Works, Work
pyalex.config.api_key = OPENALEX_API_KEY
pyalex.config.email = USER_EMAIL
pyalex.config.max_retries = 5
pyalex.config.retry_backoff_factor = 2
pyalex.config.retry_http_codes = [429, 500, 502, 503, 504]

#converts results into a publication Object that will be use to save results
def to_publication(result: dict) -> Publication:
    """Map OpenAlex fields and reconstruct its inverted-index abstract."""
    work = Work(result)
    location = work.get("primary_location") or {}
    authors = [authorship.get("author") or {} for authorship in work.get("authorships") or []]
    return Publication(
        source="openalex",
        source_id=(work.get("id") or "").rsplit("/", 1)[-1],
        title=work.get("title") or "",
        authors=[author.get("display_name") or "" for author in authors],
        author_ids=[(author.get("id") or "").rsplit("/", 1)[-1] for author in authors],
        references=[ref.rsplit("/", 1)[-1] for ref in work.get("referenced_works") or []],
        publication_year=work.get("publication_year"),
        publication_date=work.get("publication_date"),
        publication_type=work.get("type"),
        citations=work.get("cited_by_count"),
        doi=work.get("doi"),
        url=location.get("landing_page_url") or work.get("id"),
        abstract=work["abstract"] if work.get("abstract_inverted_index") else None,
    )

def openalex_search_topic(
    topic, from_date="2024-01-01", max_results=100000, *, cursor: str = "*", start_batch: int = 1
):
    """Search from a cursor, fetching at most max_results records in this run."""
    if not cursor.strip():
        raise ValueError("cursor must not be empty")
    if start_batch < 1:
        raise ValueError("start_batch must be at least 1")

    target_dir = OUTPUT_DIR

    # Pre-load existing IDs from JSONL batches.
    existing_ids = get_existing_ids(target_dir)

    # OpenAlex Request -> searches titles, abstracts, available full text, and keywords.
    query = (
        Works()
        .filter(
            title_and_abstract={"search": topic},
            from_publication_date=from_date,
            has_abstract=True,
        )
        .sort(publication_date="desc")
    )

    print(f"Starting batch download for: {topic}")
    total_saved = 0 # Track how many documents process
    writer = PublicationBuffer(target_dir, existing_ids)
    resume_cursor = cursor
    next_batch = start_batch
    
    # .paginate() fetches results page-by-page.
    # per_page=200 is the maximum allowed by OpenAlex per API call.
    # n_max safely caps the download.
    try:
        for page_num, page_results in enumerate(
            query.paginate(per_page=100, n_max=max_results, cursor=cursor), start=start_batch
        ):
                        
            newly_saved = writer.add(
                to_publication(result) for result in page_results
            )
            total_saved += newly_saved
            
            print(f"Processed batch {page_num} | New publications accepted: {newly_saved} "
                  f"| Saved: {writer.saved} | Pending: {len(writer.records)}")
            resume_cursor = page_results.meta["next_cursor"]
            next_batch = page_num + 1
            
    except RequestException as e:
        print(f"An error occurred during pagination: {e}")
        writer.flush()
        print(f"Resume this same query with cursor={resume_cursor!r}, start_batch={next_batch}. "
              "max_results limits records fetched in the resumed run.")
        raise
    writer.flush()
    print(f"Finished! Total new publications saved for '{topic}': {total_saved}\n")

if __name__=="__main__":
    #openalex_search_topic('"health care" AND "Artificial Intelligence"')
    #openalex_search_topic('"health care" AND "AI"')
    #openalex_search_topic('"health care" AND "Computer Vision"')
    health_terms = (
    '(healthcare OR "health care" OR medical OR clinical '
    'OR biomedical OR patient OR hospital '
    'OR "public health" OR "medical imaging" '
    'OR "electronic health records")'
    )

    method_terms = (
        '("artificial intelligence" OR "machine learning" '
        'OR "deep learning" OR "data science" '
        'OR "predictive analytics" OR "neural networks" '
        'OR "computer vision" OR "natural language processing" '
        'OR "large language models" OR "Machine Learning")'
    )

    application_terms = (
    '("disease diagnosis" OR "cancer detection" '
    'OR "patient outcomes" OR "clinical decision support" '
    'OR "medical image segmentation" OR "drug discovery" '
    'OR "disease prediction")'
    )

    openalex_search_topic(
        f'{application_terms} AND {method_terms}',
        from_date="2000-01-01",max_results=500000
    )   
    
    openalex_search_topic(
        f'{health_terms} AND {method_terms}',
        from_date="2000-01-01",max_results=500000
    )

 