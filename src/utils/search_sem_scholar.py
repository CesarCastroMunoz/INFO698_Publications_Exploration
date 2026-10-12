'''
Utilities to search Semantic Scholar for publications related to a specific topic
Input thru a CLI and option to store as a bundle of markdown documents.
Revision 1: Semantic Scholar Version. 10/12/2026
'''

import json
import os
import re
import time
import requests
from dotenv import load_dotenv
from pathlib import Path

# Define Path to store publications
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

# Get secrets and other variables 
load_dotenv("prod.env")
S2_API_KEY = os.getenv("S2_API_KEY") # Rrecommended for large batches

def slugify(text):
    '''
    Remove special characters from Publication Title to be in filename
    '''
    text = str(text).lower()
    text = re.sub(replace := r"[^\w\s-]", "", text)  # Remove punctuation
    return re.sub(r"[-\s]+", "_", text).strip("_")[:50]  # Replace space with underscore, limit length

def get_existing_ids(output_dir):
    '''
    Scans the output directory and returns a set of already downloaded Semantic Scholar IDs.
    '''
    existing_ids = set()
    if not os.path.exists(output_dir):
        return existing_ids
        
    for filename in os.listdir(output_dir):
        if filename.endswith(".md"):
            # Filename format is: {paperId}_{safe_title}.md
            paper_id = filename.split("_")[0]
            existing_ids.add(paper_id)
            
    return existing_ids

def save_results(results, output_dir, existing_ids):
    '''
    Save publication results as Markdown with YAML frontmatter.
    '''
    saved_in_batch = 0

    for res in results:
        paper_id = res.get("paperId")

        # 1. Check if we already have it
        if not paper_id or paper_id in existing_ids:
            continue        

        # 2. Extract Results from Semantic Scholar JSON
        title = res.get("title", "Untitled Work")
        year = res.get("year", "N/A")
        citations = res.get("citationCount", 0)
        abstract = res.get("abstract") # S2 provides plain text abstracts natively!
        url = res.get("url", "No URL available")
        
        # S2 stores DOI inside an 'externalIds' dictionary
        external_ids = res.get("externalIds", {})
        doi = external_ids.get("DOI")
        link_str = f"https://doi.org/{doi}" if doi else url

        # 3. FileName
        safe_title = slugify(title)
        filename = f"{paper_id}_{safe_title}.md"
        file_path = os.path.join(output_dir, filename)
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 4. Get list of Authors
        author_list = [author.get("name", "") for author in res.get("authors", [])]
        authors = list(filter(None, author_list))

        # 5. Save Results into a Markdown Document
        with open(file_path, "w", encoding="utf-8") as md_file:
            md_file.write("---\n")
            md_file.write(f"title: {json.dumps(title, ensure_ascii=False)}\n")
            md_file.write(f"semantic_scholar_id: {json.dumps(paper_id)}\n")
            md_file.write(f"authors: {json.dumps(authors, ensure_ascii=False)}\n")
            md_file.write(f"publication_year: {json.dumps(year)}\n")
            md_file.write(f"citations: {json.dumps(citations)}\n")
            md_file.write(f"Link/DOI: {json.dumps(link_str)}\n")
            md_file.write("---\n\n")
            md_file.write(f"# {title}\n\n")

            # --- Abstract Section ---
            md_file.write("## Abstract\n\n")
            if abstract:
                md_file.write(f"{abstract}\n")
            else:
                md_file.write("*No abstract available.*\n")

        existing_ids.add(paper_id)
        saved_in_batch += 1
    
    return saved_in_batch

def semantic_scholar_search_topic(topic, year_range="2024-", max_results=1000):
    '''
    Request to search Semantic Scholar by topic with batch pagination
    '''
    target_dir = project_root / "publications"
    existing_ids = get_existing_ids(target_dir)
    
    print(f"Starting batch download for: '{topic}' (Found {len(existing_ids)} existing files)")

    # API Configuration
    endpoint = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}
    
    # Semantic Scholar max limit per page is 100
    limit = 100 
    offset = 0
    total_saved = 0
    batch_num = 1

    try:
        while total_saved < max_results:
            # Semantic Scholar query parameters
            params = {
                "query": topic,
                "year": year_range,
                "limit": limit,
                "offset": offset,
                "fields": "paperId,title,abstract,year,authors,citationCount,externalIds,url"
            }

            response = requests.get(endpoint, headers=headers, params=params)

            # Handle Rate Limiting gracefully
            if response.status_code == 429:
                print("Rate limit reached. Sleeping for 5 seconds...")
                time.sleep(5)
                continue
                
            if response.status_code != 200:
                print(f"API Error {response.status_code}: {response.text}")
                break

            data = response.json()
            papers = data.get("data", [])

            if not papers:
                print("No more results found.")
                break # We reached the end of the search results

            newly_saved = save_results(papers, target_dir, existing_ids)
            total_saved += newly_saved
            
            print(f"Processed batch {batch_num} | New files saved: {newly_saved} (Total for session: {total_saved})")
            
            offset += limit # Increment the pagination cursor
            batch_num += 1
            
            # Be polite to the API if you don't have a premium key
            if not S2_API_KEY:
                time.sleep(3) 

    except Exception as e:
        print(f"An error occurred during pagination: {e}")
        
    print(f"Finished! Total new documents saved for '{topic}': {total_saved}\n")

if __name__=="__main__":
    semantic_scholar_search_topic('"health care" "Artificial Intelligence"', max_results=500)