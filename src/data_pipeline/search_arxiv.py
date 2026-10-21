'''
Utilities to search arXiv for publications related to a specific topic
Collect publication metadata and abstracts in JSONL batches.
Revision 1: arXiv Version. 10/12/2026
Revision 1.1: Implementing transform_clean.py to reduce code duplication Cesar C. 10/14/2026

# Citing the arXiv API documentation:
# arXiv. (2026). arXiv API User's Manual. 
# URL: https://info.arxiv.org/help/api/user-manual.html and https://info.arxiv.org/help/api/basics.html 
'''

import re
from datetime import date
import arxiv
from requests.exceptions import ConnectionError, Timeout

if __package__:
    from .transform_clean import OUTPUT_DIR, Publication, PublicationBuffer, chunked_iterable, get_existing_ids
else:
    from transform_clean import OUTPUT_DIR, Publication, PublicationBuffer, chunked_iterable, get_existing_ids

#converts results into a publication Object that will be use to save results
def to_publication(result: arxiv.Result) -> Publication:
    """Map arXiv fields; version updates share the same source ID."""
    return Publication(
        source="arxiv",
        source_id=re.sub(r"v\d+$", "", result.get_short_id()),
        title=result.title,
        authors=[author.name for author in result.authors],
        publication_date=result.published.strftime("%Y-%m-%d"),
        doi=result.doi,
        url=result.pdf_url or result.entry_id,
        abstract=result.summary,
    )

def arxiv_search_topic(
    topic, max_results=1000, *, start_offset=0, from_date=None, to_date=None
):
    '''
    Download articles in batches and count found, already saved, and new articles.
    Stop at max_results, even if more matches exist.
    Optional from_date/to_date use YYYY-MM-DD and include both days in UTC.
    On an API error, stop this topic and return False so the next topic can run.
    '''
    # Check for max results to be positive and start is also positive. 
    if max_results < 0 or not 0 <= start_offset <= max_results:
        raise ValueError("Require 0 <= start_offset <= max_results.")

    # Handle searches by Date
    if (from_date is None) != (to_date is None):
        raise ValueError("Provide both from_date and to_date, or neither.")
    if from_date is not None:
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        if start.isoformat() != from_date or end.isoformat() != to_date:
            raise ValueError("Dates must use YYYY-MM-DD.")
        if start > end:
            raise ValueError("from_date must not be after to_date.")
        topic = (
            f"({topic}) AND submittedDate:"
            f"[{start:%Y%m%d}0000 TO {end:%Y%m%d}2359]"
        )

    target_dir = OUTPUT_DIR
    existing_ids = get_existing_ids(target_dir)
    
    print(f"Starting batch download for: '{topic}' (Already saved locally: {len(existing_ids)} articles)")

    # arXiv client automatically handles the required 3-second delay between pages
    client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=0)
    
    search = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )

    total_saved = 0
    writer = PublicationBuffer(target_dir, existing_ids)
    total_retrieved = 0
    total_skipped = 0
    batch_size = 100
    completed = True
    results = client.results(search, offset=start_offset) # This creates a lazy iterator

    try:
        #break down results into smaller list for tracking and processing.
        #As chunked_iterable asks the iterator for items, the arXiv client fetches pages from the API
        for batch_num, batch in enumerate(chunked_iterable(results, batch_size), start=1):
            newly_saved = writer.add(
                to_publication(result) for result in batch
            )
            #Tracking Results
            skipped = len(batch) - newly_saved
            total_retrieved += len(batch)
            total_skipped += skipped
            total_saved += newly_saved

            print(
                f"Processed batch {batch_num} | Articles retrieved: {len(batch)} "
                f"| Already seen (skipped): {skipped} | New publications accepted: {newly_saved} "
                f"(Total retrieved: {total_retrieved}, saved: {writer.saved}, pending: {len(writer.records)})"
            )
    except (arxiv.HTTPError, arxiv.UnexpectedEmptyPageError, ConnectionError, Timeout) as e:
        #Handle request Fails
        completed = False
        print(f"API error for '{topic}': {e}")
        print(
            f"Stopping this topic without retrying. Saved files are preserved. "
            f"Next topic can proceed. Resume offset: {start_offset + total_retrieved}."
        )
    writer.flush()
    status = "Finished search" if completed else "Incomplete search"
    print(
        f"{status} for '{topic}' | Total articles retrieved: {total_retrieved} "
        f"| Already saved (skipped): {total_skipped} "
        f"| New publications saved: {total_saved} "
        f"(Retrieval limit: {max_results})\n"
    )
    return completed

if __name__=="__main__":
    # Note: arXiv requires specific field prefixes for exact matching. 
    # 'all:' searches title, abstract, and authors.
    # ti: – Searches only the Title (e.g., ti:"Artificial Intelligence")
    # au: – Searches only Authors (e.g., au:"Andrew Ng")
    # abs: – Searches only the Abstract (e.g., abs:"neural networks")
    # cat: – Searches only the Subject Category (e.g., cat:cs.AI for Computer Science - AI)

    #arxiv_search_topic('all:"health care" AND all:"Artificial Intelligence"', max_results=100000)
    #arxiv_search_topic('all:"health care" AND all:"Computer Vision"', max_results=100000)
    #arxiv_search_topic('all:"health care" AND all:"Neural Networks"', max_results=100000)
    health_terms = (
        '(all:healthcare OR all:"health care" OR all:medical '
        'OR all:clinical OR all:biomedical)'
    )

    application_terms = (
        '(all:"disease diagnosis" OR all:"cancer detection" OR all:"patient outcomes" '
        'OR all:"clinical decision support" OR all:"medical image segmentation" '
        'OR all:"drug discovery" OR all:"disease prediction")'
    )

    ai_terms = (
        '(all:"artificial intelligence" OR all:"machine learning" '
        'OR all:"deep learning" OR all:"neural network" '
        'OR all:"neural networks" OR all:"computer vision" '
        'OR all:"large language model" OR all:"large language models")'
    )

    for year in range(2010, 2025):
        arxiv_search_topic(
            f"{health_terms} AND {ai_terms}",
            max_results=1000,
            from_date=f"{year}-01-01",
            to_date=f"{year}-12-31",
        )

    # for year in range(2000, 2025):
    #     arxiv_search_topic(
    #         f"{application_terms} AND {ai_terms}",
    #         max_results=1000,
    #         from_date=f"{year}-01-01",
    #         to_date=f"{year}-12-31",
    #     )
