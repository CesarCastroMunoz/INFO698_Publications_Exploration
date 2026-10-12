'''
Utilities to search multiple sources for publications related to a specific topic
Input thru a CLI and option to store as a bundle of markdown documents.
Revision 1: Initial Rev. Cesar C. 10/12/2026

# Citing the OpenAlex Python interface library:
# de Bruin, J. (2025). pyalex: A Python library for OpenAlex. 
# URL: https://github.com/J535D165/pyalex
'''

import json
import os
import re
from dotenv import load_dotenv
from pathlib import Path

# Define Path to store publications
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

# Get secrets and other variables 
load_dotenv("prod.env")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY")
USER_EMAIL = os.getenv("USER_EMAIL")

# Use PYALEX library to extract publication data
import pyalex
from pyalex import Works, Work
pyalex.config.api_key = OPENALEX_API_KEY
pyalex.config.email = USER_EMAIL

def slugify(text):
    '''
    Remove special characters from Publication Title to be in filename
    '''
    text = text.lower()
    text = re.sub(replace := r"[^\w\s-]", "", text)  # Remove punctuation
    return re.sub(r"[-\s]+", "_", text).strip("_")[:50]  # Replace space with underscore, limit length

def save_results(results,output_dir, existing_ids):
    '''
    Save publication results as Markdown with YAML frontmatter.
    '''
    saved_in_batch = 0

    for idx, res in enumerate(results, start=1):

        work = Work(res)

        openalex_id = work.get("id", "").split("/")[-1]

        # Check if we already have it
        if openalex_id in existing_ids:
            continue        

        #Get Results
        title = work.get("title", "Untitled Work")
        doi = work.get("doi", "No DOI available")
        year = work.get("publication_year", "N/A")
        pdate = work.get("publication_date", "N/A")
        citations = work.get("cited_by_count", 0)
        type = work.get("type")

        #Extract Abstract from OpenAlex
        abstract = work["abstract"] if work.get("abstract_inverted_index") else None

        #FileName
        safe_title = slugify(title)
        filename = f"{openalex_id}_{safe_title}.md"
        file_path = os.path.join(output_dir, filename)
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        #Get list of Authors as a List
        author_list = [
            author.get("author", {}).get("display_name", "") 
            for author in work.get("authorships", [])
        ]
        authors = list(filter(None, author_list))

        #Save Results into a Markdown Document with a YAML frontmatter
        with open(file_path, "w", encoding="utf-8") as md_file:
            md_file.write("---\n")
            md_file.write(f"title: {json.dumps(title, ensure_ascii=False)}\n")
            md_file.write(f"openalex_id: {json.dumps(openalex_id)}\n")
            md_file.write(f"authors: {json.dumps(authors, ensure_ascii=False)}\n")
            md_file.write(f"publication_year: {json.dumps(year)}\n")
            md_file.write(f"publication_date: {json.dumps(pdate)}\n")
            md_file.write(f"publication_type: {json.dumps(type)}\n")
            md_file.write(f"citations: {json.dumps(citations)}\n")
            md_file.write(f"Link/DOI: {json.dumps(doi)}\n")
            md_file.write("---\n\n")
            md_file.write(f"# {title}\n\n")

            # --- New Abstract Section ---
            md_file.write("## Abstract\n\n")
            if abstract:
                md_file.write(f"{abstract}\n")
            else:
                md_file.write("*No abstract available.*\n")

        existing_ids.add(openalex_id)
        saved_in_batch += 1
    
    return saved_in_batch

def get_existing_ids(output_dir):
    '''
    Scans the output directory and returns a set of already downloaded OpenAlex IDs.
    '''
    existing_ids = set()
    if not os.path.exists(output_dir):
        return existing_ids
        
    for filename in os.listdir(output_dir):
        if filename.endswith(".md"):
            # Filename format is: {openalex_id}_{safe_title}.md
            openalex_id = filename.split("_")[0]
            existing_ids.add(openalex_id)
            
    return existing_ids

def openalex_search_topic(topic, from_date="2024-01-01", max_results=100000):
    '''
    Request to search by topic
    '''

    target_dir = project_root / "publications"

    # Pre-load existing IDs from scanning the directory with markdowns
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
    
    # .paginate() fetches results page-by-page.
    # per_page=200 is the maximum allowed by OpenAlex per API call.
    # n_max safely caps the download.
    try:
        for page_num, page_results in enumerate(query.paginate(per_page=200, n_max=max_results), start=1):
                        
            newly_saved = save_results(page_results, target_dir, existing_ids)
            total_saved += newly_saved
            
            print(f"Processed batch {page_num} | New files saved: {newly_saved} (Total for session: {total_saved})")
            
    except Exception as e:
        print(f"An error occurred during pagination: {e}")
        
    print(f"Finished! Total new documents saved for '{topic}': {total_saved}\n")

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
        'OR "large language models")'
    )

    application_terms = (
    '("disease diagnosis" OR "cancer detection" '
    'OR "patient outcomes" OR "clinical decision support" '
    'OR "medical image segmentation" OR "drug discovery" '
    'OR "disease prediction")'
    )

    openalex_search_topic(
        f'{health_terms} AND {method_terms}',
        from_date="2010-01-01",
    )

    openalex_search_topic(
        f'{application_terms} AND {method_terms}',
        from_date="2010-01-01",
    )    