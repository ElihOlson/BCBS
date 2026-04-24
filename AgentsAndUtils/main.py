#from agents import sqlAgent, bucketingAgent
from AgentsAndUtils.supabaseUtils import supabaseInteractions
from AgentsAndUtils.codeAgents import *
import json
import csv
import re
from pathlib import Path
import traceback
from io import StringIO



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
    output_file = Path(__file__).resolve().parent / "bucket_output.csv"
    response = json_to_csv(myBuckets)

    print("\n\n\n"+response)
    output_file.write_text(response, encoding="utf-8", newline="")
    #print(f"\n\n{rows[:][4]}\n\n")

except Exception as e:
    print("Could not parse AI response into CSV")
    print(f"Error: {e}")

    print(traceback.format_exc())







