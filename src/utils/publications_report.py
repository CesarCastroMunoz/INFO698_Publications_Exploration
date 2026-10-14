'''
Search all JSONL files in publication folder and create a report of Quantity of Publications, DOIs, etc.
Revision 1: Initial Rev. Cesar C. 10/14/2026
'''

import sys
from pathlib import Path
current_file = Path(__file__).resolve()
src_dir = current_file.parent.parent  # publications_report.py -> utils -> src
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterator
import pandas as pd
from data_pipeline.transform_clean import Publication

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "publications"
TEMP_DIR = Path(__file__).resolve().parent.parent / "temp"


def read_jsonl(batch_path: str | Path) -> Iterator[Publication]:
    """Stream publications from a JSONL batch; reject malformed records.
    Read current JSON files to list already pulled publications to avoid duplication"""
    with Path(batch_path).open(encoding="utf-8") as batch:
        for line_number, line in enumerate(batch, start=1):
            try:
                yield Publication(**json.loads(line))
            except (ValueError, TypeError) as error:
                raise ValueError(f"Invalid publication in {batch_path}, line {line_number}") from error

def publications_summary():
    frames = [
        pd.read_json(path, lines=True, dtype=False)
        for path in Path(OUTPUT_DIR).glob("*.jsonl")
    ]
    df = pd.concat(frames, ignore_index=True)  # one concat, not one per record
    return df.drop(columns="abstract")            
        
def create_report(df):
    '''Create an HTML report with quantity of publications by source, Quantity of unique DOIs'''

    df_summary_by_source = df.groupby("source").agg(
        quantity_of_publications=pd.NamedAgg(column="source_id", aggfunc="count"),
        unique_dois=pd.NamedAgg(column="doi", aggfunc="nunique")
    ).reset_index()

    df_summary_total = pd.DataFrame([{
        "source": "Total",
        "quantity_of_publications": df["source_id"].count(),
        "unique_dois": df["doi"].nunique(),
    }])

    df_summary = pd.concat([df_summary_by_source, df_summary_total], ignore_index=True)
    
    report_path = TEMP_DIR / "publications_report.html"
    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(df_summary.to_html(index=False))


if __name__=="__main__":
    publications_df = publications_summary()
    publications_df.to_csv(TEMP_DIR / "publications_summary.csv", index=False)
    create_report(publications_df)
    

