#from agents import sqlAgent, bucketingAgent
from supabaseUtils import supabaseInteractions
from codeAgents import *
import json
import csv
import re
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


def sanitize_generated_sql(sql_query):
    """
    Inputs:
        sql_query (str): A generated SQL statement.
    Purpose:
        Auto-corrects known invalid SQL patterns produced by the model.
    Returns:
        str: Sanitized SQL statement.
    """
    if not sql_query:
        return sql_query

    fixed_sql = sql_query

    fixed_sql = re.sub(
        r"\bm\.sms_opt_in\s*=\s*TRUE\b",
        "EXISTS (SELECT 1 FROM marketing_ai.consent_preferences cp WHERE cp.member_id = m.member_id AND cp.sms_opt_in = TRUE)",
        fixed_sql,
        flags=re.IGNORECASE,
    )

    age_between_pattern = re.compile(
        r"\(?\s*CURRENT_DATE\s*-\s*m\.date_of_birth\s*\)?\s+BETWEEN\s+INTERVAL\s+'(\d+)\s+years?'\s+AND\s+INTERVAL\s+'(\d+)\s+years?'",
        flags=re.IGNORECASE,
    )

    def _replace_age_between(match):
        first_year = int(match.group(1))
        second_year = int(match.group(2))
        older = max(first_year, second_year)
        younger = min(first_year, second_year)
        return f"m.date_of_birth BETWEEN CURRENT_DATE - INTERVAL '{older} years' AND CURRENT_DATE - INTERVAL '{younger} years'"

    fixed_sql = age_between_pattern.sub(_replace_age_between, fixed_sql)

    return fixed_sql


def normalize_generated_bucket_sqls(raw_bucket_json):
    """
    Inputs:
        raw_bucket_json (str): Raw JSON text from the bucketing agent.
    Purpose:
        Parses generated bucket JSON and sanitizes each bucket SQL before downstream use.
    Returns:
        str: Normalized JSON string with corrected SQL statements.
    """
    cleaned = raw_bucket_json.strip().replace("```json", "").replace("```", "").strip()
    payload = json.loads(cleaned)

    for bucket in payload.get("buckets", []):
        bucket_sql = bucket.get("sql")
        if isinstance(bucket_sql, str):
            bucket["sql"] = sanitize_generated_sql(bucket_sql)

    return json.dumps(payload, ensure_ascii=False, indent=2)


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

campaign_request = bktagent.prompt_for_campaign_request()

myBuckets = bktagent.generateBuckets("none", schema, campaign_request=campaign_request)

myBuckets = normalize_generated_bucket_sqls(myBuckets)

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
agent = emailAgent()
for x in sqlList:
    email = agent.genEmail(x[0], x[1], campaign_request)
    print(f"EMAILS:\n\n{email}\n")


