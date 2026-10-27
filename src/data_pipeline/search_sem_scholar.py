'''
Utilities to search Semantic Scholar for publications related to a specific topic
Collect publication metadata and abstracts in JSONL batches.
Revision 1: Semantic Scholar Version. 10/12/2026
Revision 1.1: Implementing transform_clean.py to reduce code duplication Cesar C. 10/14/2026

# Citing the Semantic Scholar API documentation:
Allen Institute for AI. (n.d.). Semantic Scholar Academic Graph API documentation. 
Retrieved October 14, 2026, from https://api.semanticscholar.org/api-docs/graph
'''

import os
import time
import requests
from dotenv import load_dotenv

if __package__:
    from .transform_clean import OUTPUT_DIR, Publication, PublicationBuffer, get_existing_ids
else:
    from transform_clean import OUTPUT_DIR, Publication, PublicationBuffer, get_existing_ids

# Get secrets and other variables 
load_dotenv("prod.env")
S2_API_KEY = os.getenv("S2_API_KEY") 

#converts results into a publication Object that will be use to save results
def to_publication(result: dict) -> Publication:
    """Map Semantic Scholar fields, including optional external identifiers."""
    external_ids = result.get("externalIds") or {}
    publication_types = result.get("publicationTypes") or []
    return Publication(
        source="semantic_scholar",
        source_id=result.get("paperId") or "",
        title=result.get("title") or "",
        authors=[author.get("name") or "" for author in result.get("authors") or []],
        author_ids=[author.get("authorId") for author in result.get("authors") or []],
        publication_year=result.get("year"),
        publication_date=result.get("publicationDate"),
        publication_type=", ".join(publication_types) or None,
        citations=result.get("citationCount"),
        doi=external_ids.get("DOI"),
        url=result.get("url"),
        abstract=result.get("abstract"),
    )

def semantic_scholar_search_topic(
    topic, year_range="2000-", max_results=1000, *, start_token: str | None = None, start_batch: int = 1
):
    """Search from a bulk pagination token; max_results targets new records in this run."""
    if start_token is not None and not start_token.strip():
        raise ValueError("start_token must not be empty")
    if start_batch < 1:
        raise ValueError("start_batch must be at least 1")
    target_dir = OUTPUT_DIR
    existing_ids = get_existing_ids(target_dir)
    
    print(f"Starting batch download for: '{topic}' (Found {len(existing_ids)} existing publications)")

    # API Configuration. Using Bulk Extraction API. https://api.semanticscholar.org/api-docs/graph
    endpoint = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
    headers = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}
    
    token = start_token
    total_saved = 0
    writer = PublicationBuffer(target_dir, existing_ids)
    batch_num = start_batch

    try:
        while total_saved < max_results:
            # Semantic Scholar query parameters
            params = {
                "query": topic,
                "year": year_range,
                "fields": (
                    "paperId,title,abstract,year,authors,citationCount,externalIds,url,"
                    "publicationDate,publicationTypes"
                )
            }
            if token is not None:
                params["token"] = token

            time.sleep(1)
            response = requests.get(endpoint, headers=headers, params=params)

            # Handle Rate Limiting gracefully
            if response.status_code == 429:
                print("Rate limit reached. Sleeping for 5 seconds...")
                time.sleep(5)
                continue
                
            if response.status_code != 200:
                print(f"API Error {response.status_code}: {response.text}")
                response.raise_for_status()

            data = response.json()
            papers = data.get("data", [])

            newly_saved = writer.add(
                to_publication(result) for result in papers
            )
            total_saved += newly_saved
            
            print(f"Processed batch {batch_num} | New publications accepted: {newly_saved} "
                  f"| Saved: {writer.saved} | Pending: {len(writer.records)}")
            
            token = data.get("token")
            if not token:
                print("No more results found.")
                break
            batch_num += 1
            
    except requests.RequestException as e:
        print(f"An error occurred during pagination: {e}")
        writer.flush()
        print(f"Resume this same query and year_range with start_token={token!r}, "
              f"start_batch={batch_num}. max_results targets new records in the resumed run.")
        raise
    writer.flush()
    print(f"Finished! Total new publications saved for '{topic}': {total_saved}\n")

if __name__=="__main__":
    # health_terms = (
    #     '(healthcare | "health care" | medical '
    #     '| clinical | biomedical)'
    # )

    health_terms = (
    '(EHR | EMR '
    '| telemedicine | telehealth | wearables '
    '| genomics | bioinformatics | "precision medicine" '
    '| "personalized medicine" | radiology | pathology '
    '| oncology | cardiology | epidemiology)'
    )

    application_terms = (
        '("disease diagnosis" | "cancer detection" | "patient outcomes" '
        '| "clinical decision support" | "medical image segmentation" '
        '| "drug discovery" | "disease prediction")'
    )

    ai_terms = (
        '("artificial intelligence" | "machine learning" '
        '| "deep learning" | "data science" '
        '| "predictive analytics" | "neural network" '
        '| "neural networks" | "computer vision" '
        '| "large language model" | "large language models")'
    )

    semantic_scholar_search_topic(
        f'{health_terms} + {ai_terms}',
        max_results=250000,
    )

    # semantic_scholar_search_topic(
    #     f'{application_terms} + {ai_terms}',
    #     max_results=250000,
    # )