#from agents import sqlAgent, bucketingAgent
from supabaseUtils import supabaseInteractions
from codeAgents import *
import json
import csv
from pathlib import Path
import traceback
from io import StringIO




def json_to_csv(json_string):
    """
    Inputs:
        json_string (str): JSON text containing universe metadata and bucket rows.
    Purpose:
        Converts the generated bucket JSON payload into CSV text for bucket_output.csv.
    Returns:
        str: CSV-formatted string with one row per bucket.
    """
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


def read_bucket_rows(bucket_csv_path):
    """
    Inputs:
        bucket_csv_path (Path): File path to bucket_output.csv.
    Purpose:
        Reads bucket rows from CSV and normalizes the fields needed by downstream steps.
    Returns:
        list[dict]: List of bucket dictionaries containing rank, name, sql, and rationale.
    """
    bucket_rows = []

    with bucket_csv_path.open("r", encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            bucket_rows.append({
                "rank": row.get("rank"),
                "name": row.get("name"),
                "sql": (row.get("sql") or "").strip(),
                "rationale": row.get("rationale"),
            })

    return bucket_rows


def export_sql_results(bucket_rows, output_csv_path, supabase_client):
    """
    Inputs:
        bucket_rows (list[dict]): Bucket records containing SQL and metadata.
        output_csv_path (Path): Destination path for SQL_results.csv.
        supabase_client (supabaseInteractions): Supabase helper used to run SQL queries.
    Purpose:
        Executes each bucket SQL query and writes query outcomes/results into SQL_results.csv.
    Returns:
        None: Writes output to disk and prints the destination path.
    """
    results_to_write = []

    for bucket in bucket_rows:
        sql_query = bucket.get("sql")
        rank = bucket.get("rank")
        bucket_name = bucket.get("name")

        if not sql_query:
            results_to_write.append({
                "rank": rank,
                "bucket_name": bucket_name,
                "sql": "",
                "status": "skipped",
                "row_count": 0,
                "result_row_index": "",
                "result_json": "",
                "error": "Missing SQL in bucket_output.csv"
            })
            continue

        query_results = supabase_client.run_sql_query(sql_query)

        if query_results is None:
            results_to_write.append({
                "rank": rank,
                "bucket_name": bucket_name,
                "sql": sql_query,
                "status": "failed",
                "row_count": 0,
                "result_row_index": "",
                "result_json": "",
                "error": "Query execution failed"
            })
            continue

        if len(query_results) == 0:
            results_to_write.append({
                "rank": rank,
                "bucket_name": bucket_name,
                "sql": sql_query,
                "status": "success",
                "row_count": 0,
                "result_row_index": "",
                "result_json": "",
                "error": ""
            })
            continue

        row_count = len(query_results)
        for row_index, row in enumerate(query_results, start=1):
            results_to_write.append({
                "rank": rank,
                "bucket_name": bucket_name,
                "sql": sql_query,
                "status": "success",
                "row_count": row_count,
                "result_row_index": row_index,
                "result_json": json.dumps(dict(row), ensure_ascii=False),
                "error": ""
            })

    headers = [
        "rank",
        "bucket_name",
        "sql",
        "status",
        "row_count",
        "result_row_index",
        "result_json",
        "error",
    ]

    with output_csv_path.open("w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=headers)
        writer.writeheader()
        writer.writerows(results_to_write)

    print(f"Wrote SQL execution results to: {output_csv_path}")



sqlagent = sqlAgent()
bktagent = bucketingAgent()
sbInteract = supabaseInteractions()


schema = sbInteract.getSchema()

myBuckets = bktagent.generateBuckets("none", schema)

print("OUTPUT: \n\n", myBuckets)

#write content to csv
try:
    sqlList = []
    output_file = Path(__file__).resolve().parent / "bucket_output.csv"
    sql_results_file = Path(__file__).resolve().parent / "SQL_results.csv"
    response = json_to_csv(myBuckets)

    print("\n\n\n"+response)
    output_file.write_text(response, encoding="utf-8", newline="")

    # Reuse original flow: pull SQL + rationale pairs into sqlList.
    bucket_rows = read_bucket_rows(output_file)
    for bucket in bucket_rows:
        sqlList.append([bucket["sql"], bucket["rationale"]])

    export_sql_results(bucket_rows, sql_results_file, sbInteract)
    #print(f"\n\n{rows[:][4]}\n\n")

except Exception as e:
    sqlList = []
    print("Could not parse AI response into CSV")
    print(f"Error: {e}")

    print(traceback.format_exc())


#query, desc\
desc = r'{ "about": { "age_range": [25, 40], "location": ["NE", "IA"], "conditions": ["diabetes", "hypertension"], "engagement_level": "medium" }, "for": { "campaign_type": "preventive_care", "channel": "sms", "message_goal": "schedule_appointment" }, "success_conditions": { "primary_metric": "conversion_rate", "secondary_metrics": ["open_rate", "click_rate"], "weights": { "conversion_rate": 0.6, "open_rate": 0.25, "click_rate": 0.15 } } }'
agent = emailAgent()
for x in sqlList:
    email = agent.genEmail(x[0], x[1])
    print(f"EMAILS:\n\n{email}\n")


