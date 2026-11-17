import csv
import json
import random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = REPO_ROOT / "src" / "publications"
OUTPUT_CSV = Path(__file__).resolve().parent / "doi_audit_sample.csv"
SAMPLE_SIZE = 30
AUDIT_FIELDS = [
    "Title_Match (1/0)",
    "Author_Match (1/0)",
    "Abstract_Complete (1/0)",
    "Notes",
]


def sample_publications(input_dir, sample_size, rng=random):
    jsonl_files = sorted(input_dir.rglob("*.jsonl"))
    if not jsonl_files:
        raise FileNotFoundError(f"No publication JSONL files found in {input_dir}")

    sampled = []
    total = 0
    for file_path in jsonl_files:
        with file_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {file_path} at line {line_number}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"Expected a JSON object in {file_path} at line {line_number}")

                total += 1
                if len(sampled) < sample_size:
                    sampled.append(record)
                else:
                    index = rng.randrange(total)
                    if index < sample_size:
                        sampled[index] = record

    if not total:
        raise ValueError(f"No publication records found in {input_dir}")
    return sampled, total


def write_audit_csv(sampled, output_csv):
    publication_fields = list(dict.fromkeys(key for record in sampled for key in record))
    fieldnames = (
        ["Sample_ID"]
        + [f"publication.{key}" for key in publication_fields]
        + ["Publication_JSON"]
        + AUDIT_FIELDS
    )
    with output_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for index, record in enumerate(sampled, start=1):
            row = {
                f"publication.{key}": (
                    value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                )
                for key, value in record.items()
            }
            row["Sample_ID"] = index
            row["Publication_JSON"] = json.dumps(record, ensure_ascii=False)
            writer.writerow(row)


def main():
    sampled, total = sample_publications(INPUT_DIR, SAMPLE_SIZE)
    print(f"Total records found: {total}")
    write_audit_csv(sampled, OUTPUT_CSV)
    print(f"Random sample of {len(sampled)} records saved to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
