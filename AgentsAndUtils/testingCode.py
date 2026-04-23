#from agents import sqlAgent, bucketingAgent
from getSchema import supabaseInteractions
from gptAgents import *
import json
import csv
import re
from pathlib import Path

def extract_bucket_payload(raw_text):
    text = raw_text.strip()

    # Prefer a fenced JSON block if present.
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        text = match.group(1).strip()

    # Fallback: parse the largest JSON object from mixed prose output.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    # Repair invalid JSON pattern sometimes emitted in estimated_count.
    text = re.sub(r'"estimated_count"\s*:\s*/\*.*?\*/', '"estimated_count": 0', text, flags=re.DOTALL)
    text = re.sub(r",\s*([}\]])", r"\1", text)

    data = json.loads(text)
    if isinstance(data, dict) and isinstance(data.get("buckets"), list):
        return data["buckets"]
    if isinstance(data, list):
        return data

    raise ValueError("AI output did not contain a recognized bucket list")


def to_int_or_zero(value):
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.findall(r"-?\d+", str(value))
    return int(digits[0]) if digits else 0


def write_bucket_csv(bucket_items, output_path):
    rows = []
    for bucket in bucket_items:
        rows.append([
            bucket.get("name", bucket.get("bucket_name", "")),
            to_int_or_zero(bucket.get("estimated_count", bucket.get("bucket_count", 0))),
            bucket.get("rationale", ""),
            bucket.get("suggested_treatment", ""),
            bucket.get("sql", ""),
        ])

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Name of bucket",
            "Count of bucket",
            "Rational of the bucket",
            "Suggested treatment",
            "SQL",
        ])
        writer.writerows(rows)

    return rows



sqlagent = sqlAgent()
bktagent = bucketingAgent()
sbInteract = supabaseInteractions()


schema = sbInteract.getSchema()


myBuckets = bktagent.generateBuckets("none", schema)

print("OUTPUT: \n\n", myBuckets)

try:
    buckets = extract_bucket_payload(myBuckets)
    output_file = Path(__file__).resolve().parent / "bucket_output.csv"
    rows = write_bucket_csv(buckets, output_file)

    print(f"CSV file returned: {output_file}")
    if rows and all(int(row[1]) == 0 for row in rows):
        print("If all counts are 0, then not possible")
except Exception as e:
    print("Could not parse AI response into CSV")
    print(f"Error: {e}")







