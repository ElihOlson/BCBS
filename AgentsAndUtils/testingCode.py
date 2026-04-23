#from agents import sqlAgent, bucketingAgent
from getSchema import supabaseInteractions
from gptAgents import *
import json
import csv
import re
from pathlib import Path
import traceback
from io import StringIO


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


def json_to_csv(json_string):
    json_string = json_string.strip().replace("```json", "").replace("```", "").strip()
    data = json.loads(json_string)
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Define CSV headers
    headers = [
        "universe_definition",
        "primary_slicing_axis",
        "rank",
        "name",
        "sql",
        "estimated_count",
        "rationale",
        "suggested_treatment",
        "coverage_note"
    ]
    
    writer.writerow(headers)
    
    # Extract top-level fields
    universe_definition = data.get("universe_definition")
    primary_slicing_axis = data.get("primary_slicing_axis")
    coverage_note = data.get("coverage_note")
    
    # Iterate through buckets
    for bucket in data.get("buckets", []):
        writer.writerow([
            universe_definition,
            primary_slicing_axis,
            bucket.get("rank"),
            bucket.get("name"),
            bucket.get("sql"),
            bucket.get("estimated_count"),
            bucket.get("rationale"),
            bucket.get("suggested_treatment"),
            coverage_note
        ])
    
    return output.getvalue()



sqlagent = sqlAgent()
bktagent = bucketingAgent()
sbInteract = supabaseInteractions()


schema = sbInteract.getSchema()


myBuckets = bktagent.generateBuckets("none", schema)

print("OUTPUT: \n\n", myBuckets)

try:
    #buckets = extract_bucket_payload(myBuckets)
    output_file = Path(__file__).resolve().parent / "bucket_output.csv"
    response = json_to_csv(myBuckets)

    print("\n\n\n"+response)
    output_file.write_text(response, encoding="utf-8", newline="")
    #print(f"\n\n{rows[:][4]}\n\n")

except Exception as e:
    print("Could not parse AI response into CSV")
    print(f"Error: {e}")

    print(traceback.format_exc())







