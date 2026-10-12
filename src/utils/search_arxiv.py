'''
Utilities to search arXiv for publications related to a specific topic
Input thru a CLI and option to store as a bundle of markdown documents.
Revision 1: arXiv Version. 10/12/2026

# Citing the arXiv API documentation:
# arXiv. (2026). arXiv API User's Manual. 
# URL: https://info.arxiv.org/help/api/user-manual.html and https://info.arxiv.org/help/api/basics.html 
'''

import json
import os
import re
import arxiv
from itertools import islice
from pathlib import Path
from requests.exceptions import ConnectionError, Timeout

# Define Path to store publications
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

def slugify(text):
    '''
    Remove special characters from Publication Title to be in filename
    '''
    text = str(text).lower()
    # ArXiv titles sometimes contain newlines, replace them with spaces first
    text = text.replace('\n', ' ') 
    text = re.sub(replace := r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text).strip("_")[:50]

def get_existing_ids(output_dir):
    '''
    Scans the output directory and returns a set of already downloaded arXiv IDs.
    '''
    existing_ids = set()
    if not os.path.exists(output_dir):
        return existing_ids
        
    for filename in os.listdir(output_dir):
        if filename.endswith(".md"):
            # Filename format is: {arxiv_id}_{safe_title}.md
            arxiv_id = filename.split("_")[0]
            existing_ids.add(arxiv_id)
            
    return existing_ids

def save_results(results, output_dir, existing_ids):
    '''
    Save publication results as Markdown with YAML frontmatter.
    '''
    saved_in_batch = 0

    for res in results:
        # arXiv IDs often include a version number (e.g., 2109.12345v1). 
        # Decided to strip the version so updates don't create duplicate files.
        arxiv_id = res.get_short_id().split('v')[0] 

        if arxiv_id in existing_ids:
            continue        

        # Extract Results from arXiv object
        title = res.title.replace('\n', ' ')
        date_published = res.published.strftime("%Y-%m-%d")
        abstract = res.summary.replace('\n', ' ')
        pdf_url = res.pdf_url
        doi = res.doi
        
        # arXiv does not track citation counts natively as openalex so default to N/A
        citations = "N/A (arXiv)" 
        link_str = f"https://doi.org/{doi}" if doi else pdf_url

        # FileName
        safe_title = slugify(title)
        filename = f"{arxiv_id}_{safe_title}.md"
        file_path = os.path.join(output_dir, filename)
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Get list of Authors
        author_list = [author.name for author in res.authors]

        # Save Results into a Markdown Document with a YAML frontmatter
        with open(file_path, "w", encoding="utf-8") as md_file:
            md_file.write("---\n")
            md_file.write(f"title: {json.dumps(title, ensure_ascii=False)}\n")
            md_file.write(f"arxiv_id: {json.dumps(arxiv_id)}\n")
            md_file.write(f"authors: {json.dumps(author_list, ensure_ascii=False)}\n")
            md_file.write(f"publication_date: {json.dumps(date_published)}\n")
            md_file.write(f"citations: {json.dumps(citations)}\n")
            md_file.write(f"Link/DOI: {json.dumps(link_str)}\n")
            md_file.write("---\n\n")
            md_file.write(f"# {title}\n\n")

            md_file.write("## Abstract\n\n")
            if abstract:
                md_file.write(f"{abstract}\n")
            else:
                md_file.write("*No abstract available.*\n")

        existing_ids.add(arxiv_id)
        saved_in_batch += 1
    
    return saved_in_batch

def chunked_iterable(iterable, size):
    '''Helper to chunk the arXiv generator into batches for logging'''
    it = iter(iterable)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            break
        yield chunk

def arxiv_search_topic(topic, max_results=1000, *, start_offset=0):
    '''
    Download articles in batches and count found, already saved, and new articles.
    Stop at max_results, even if more matches exist.
    On an API error, stop this topic and return False so the next topic can run.
    '''
    # Check for max results to be positive and start is also positive. 
    if max_results < 0 or not 0 <= start_offset <= max_results:
        raise ValueError("Require 0 <= start_offset <= max_results.")

    target_dir = project_root / "publications"
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
    total_retrieved = 0
    total_skipped = 0
    batch_size = 100
    completed = True
    results = client.results(search, offset=start_offset)

    try:
        for batch_num, batch in enumerate(chunked_iterable(results, batch_size), start=1):
            newly_saved = save_results(batch, target_dir, existing_ids)
            skipped = len(batch) - newly_saved
            total_retrieved += len(batch)
            total_skipped += skipped
            total_saved += newly_saved

            print(
                f"Processed batch {batch_num} | Articles retrieved: {len(batch)} "
                f"| Already saved (skipped): {skipped} | New files saved: {newly_saved} "
                f"(Total retrieved: {total_retrieved}, total saved: {total_saved})"
            )
    except (arxiv.HTTPError, arxiv.UnexpectedEmptyPageError, ConnectionError, Timeout) as e:
        completed = False
        print(f"API error for '{topic}': {e}")
        print(
            f"Stopping this topic without retrying. Saved files are preserved. "
            f"Next topic can proceed. Resume offset: {start_offset + total_retrieved}."
        )
        
    status = "Finished search" if completed else "Incomplete search"
    print(
        f"{status} for '{topic}' | Total articles retrieved: {total_retrieved} "
        f"| Already saved (skipped): {total_skipped} "
        f"| New documents saved: {total_saved} "
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

    completed = arxiv_search_topic(
        f'{health_terms} AND {ai_terms}',
        max_results=100000,
    )

    completed = arxiv_search_topic(
        f'{application_terms} AND {ai_terms}',
        max_results=100000,
    )    
