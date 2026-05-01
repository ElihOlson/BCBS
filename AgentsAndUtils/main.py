#from agents import sqlAgent, bucketingAgent
from supabaseUtils import supabaseInteractions
from codeAgents import *
import json
import csv
import re
from datetime import datetime
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


def ensure_unique_bucket_names(payload):
    """
    Inputs:
        payload (dict): Parsed bucket payload containing a `buckets` list.
    Purpose:
        Enforces unique bucket names for each generation run while preserving
        the model-provided naming intent.
    Returns:
        dict: Updated payload with unique `name` values.
    """
    seen = {}

    for bucket in payload.get("buckets", []):
        base_name = (bucket.get("name") or "").strip()
        if not base_name:
            rank_value = str(bucket.get("rank") or "").strip() or "Unknown"
            base_name = f"Bucket {rank_value}"

        count = seen.get(base_name, 0) + 1
        seen[base_name] = count

        if count == 1:
            bucket["name"] = base_name
        else:
            bucket["name"] = f"{base_name} ({count})"

    return payload


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

    payload = ensure_unique_bucket_names(payload)

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


class CampaignService:
    def __init__(self):
        self.basedir = Path(__file__).resolve().parent
        self.campaign_history_path = self.basedir / "launched_campaigns.json"

        self.sb_interact = None
        try:
            self.sb_interact = supabaseInteractions()
        except Exception:
            self.sb_interact = None

        self.bucket_agent = None
        self.email_agent = None
        try:
            self.bucket_agent = bucketingAgent()
            self.email_agent = emailAgent()
        except Exception:
            self.bucket_agent = None
            self.email_agent = None

    def startup_checks(self):
        print("\n" + "=" * 40)
        print("STARTING BCBS BACKEND")
        if self.sb_interact is None:
            print("CONNECTION FAILED: Supabase client unavailable")
            print("=" * 40 + "\n")
            return
        try:
            schema = self.sb_interact.getSchema()
            if not schema:
                print("CONNECTION: Success, but no tables found in public schema.")
        except Exception as exc:
            print(f"CONNECTION FAILED: {str(exc)}")
        print("=" * 40 + "\n")

    def get_schema_rows(self):
        if self.sb_interact is None:
            return []
        try:
            rpc_res = self.sb_interact.supabase.rpc("get_table_schema").execute()
            return rpc_res.data or []
        except Exception:
            return []

    def get_schema_api_payload(self):
        schema_rows = self.get_schema_rows()
        if not schema_rows:
            return None
        return schema_rows

    def safe_build_campaign_request(self, about_text, audience_text, success_text):
        if self.bucket_agent is None:
            return {
                "about": {
                    "campaign_type": about_text,
                    "channel": "sms",
                    "message_goal": about_text,
                },
                "for": {"description": audience_text},
                "success_conditions": {"primary_metric": success_text},
            }

        try:
            return self.bucket_agent.build_campaign_request(about_text, audience_text, success_text)
        except Exception:
            return {
                "about": {
                    "campaign_type": about_text,
                    "channel": "sms",
                    "message_goal": about_text,
                },
                "for": {"description": audience_text},
                "success_conditions": {"primary_metric": success_text},
            }

    def safe_generate_buckets(self, schema_lines, campaign_request):
        if self.bucket_agent is None:
            return {
                "universe_definition": "unavailable",
                "primary_slicing_axis": "unavailable",
                "coverage_note": "Bucketing agent is not configured.",
                "buckets": [],
            }

        raw = self.bucket_agent.generateBuckets("none", schema_lines, campaign_request=campaign_request)
        try:
            normalized = normalize_generated_bucket_sqls(raw)
            return json.loads(normalized)
        except Exception:
            cleaned = (raw or "").strip().replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned)

    def run_bucket_queries(self, bucket_rows):
        enriched = []
        total_reach = 0

        for idx, bucket in enumerate(bucket_rows, start=1):
            sql_query = (bucket.get("sql") or "").strip()
            row_count = 0
            sample_rows = []
            query_error = ""

            if sql_query and self.sb_interact is not None:
                try:
                    results = self.sb_interact.run_sql_query(sql_query)
                    if isinstance(results, list):
                        row_count = len(results)
                        sample_rows = results[:3]
                except Exception as exc:
                    query_error = str(exc)
            else:
                query_error = "SQL unavailable or DB connection unavailable"

            total_reach += row_count
            enriched.append(
                {
                    "id": idx,
                    "rank": bucket.get("rank") or idx,
                    "name": bucket.get("name") or f"Bucket {idx}",
                    "sql": sql_query,
                    "rationale": bucket.get("rationale") or "",
                    "suggested_treatment": bucket.get("suggested_treatment") or "",
                    "estimated_count": bucket.get("estimated_count"),
                    "row_count": row_count,
                    "sample_rows": sample_rows,
                    "query_error": query_error,
                }
            )

        return enriched, total_reach

    def generate_bucket_email(self, bucket, campaign_request):
        if self.email_agent is None:
            return {
                "subject": f"Action needed for {bucket['name']}",
                "body": f"This message targets {bucket['name']}. Edit this content before launch.",
            }

        try:
            raw_email = self.email_agent.genEmail(bucket["sql"], bucket["rationale"], campaign_request)
            text = (raw_email or "").strip().replace("```json", "").replace("```", "").strip()
            return {
                "subject": f"Campaign for {bucket['name']}",
                "body": text,
            }
        except Exception:
            return {
                "subject": f"Action needed for {bucket['name']}",
                "body": f"This message targets {bucket['name']}. Edit this content before launch.",
            }

    def build_campaign_response(self, about_text, audience_text, success_text):
        campaign_request = self.safe_build_campaign_request(about_text, audience_text, success_text)
        schema_rows = self.get_schema_rows()

        schema_lines = []
        if schema_rows:
            table_map = {}
            for row in schema_rows:
                table_map.setdefault(row["table_name"], []).append(row)
            for table, rows in table_map.items():
                labels = []
                for item in rows:
                    label = item["column_name"]
                    if item.get("is_primary_key"):
                        label += " [PK]"
                    if item.get("foreign_table"):
                        label += f" [FK -> {item['foreign_table']}.{item['foreign_column']}]"
                    labels.append(label)
                schema_lines.append(f"Table [{table}]: {', '.join(labels)}")

        bucket_payload = self.safe_generate_buckets(schema_lines, campaign_request)
        buckets, total_reach = self.run_bucket_queries(bucket_payload.get("buckets", []))

        for bucket in buckets:
            email_data = self.generate_bucket_email(bucket, campaign_request)
            bucket["email_subject"] = email_data["subject"]
            bucket["email_body"] = email_data["body"]

        campaign_possible = any(bucket["row_count"] > 0 for bucket in buckets)
        confidence = 95 if campaign_possible else 0
        data_integrity = 99 if campaign_possible else 0

        return {
            "campaign_request": campaign_request,
            "data_review": {
                "campaign_name": (about_text[:60] or "Campaign") + "",
                "source_database": "Supabase marketing_ai",
                "estimated_reach": total_reach,
                "target_summary": audience_text,
                "success_conditions": success_text,
                "schema_table_count": len({row.get("table_name") for row in schema_rows}),
            },
            "analyzer": {
                "possible": campaign_possible,
                "predicted_reach": total_reach,
                "confidence_score": confidence,
                "data_integrity": data_integrity,
                "message": "Campaign inputs are executable." if campaign_possible else "No reachable members were returned for the provided inputs.",
            },
            "buckets": buckets,
            "launch": {
                "total_reach": total_reach,
                "bucket_count": len(buckets),
                "quality_checks": [
                    {"label": "Audience segments generated", "passed": len(buckets) > 0},
                    {"label": "At least one reachable audience", "passed": campaign_possible},
                    {"label": "Creative drafts generated", "passed": len(buckets) > 0},
                ],
            },
        }

    def load_campaign_history(self):
        if not self.campaign_history_path.exists():
            return []

        try:
            data = json.loads(self.campaign_history_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    def save_campaign_history(self, history_rows):
        self.campaign_history_path.write_text(
            json.dumps(history_rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def launch_campaign(self, payload):
        selected_buckets = payload.get("selected_buckets") or []
        campaign_name = payload.get("campaign_name") or "Campaign"
        total_reach = int(payload.get("total_reach") or 0)
        selected_bucket_count = len(selected_buckets)
        launched_at = datetime.utcnow().strftime("%b %d, %Y")

        history_rows = self.load_campaign_history()
        history_rows.insert(
            0,
            {
                "campaign_name": campaign_name,
                "status": "Launched",
                "launch_date": launched_at,
                "total_reach": total_reach,
                "selected_bucket_count": selected_bucket_count,
            },
        )
        self.save_campaign_history(history_rows)

        return {
            "status": "launched",
            "campaign_name": campaign_name,
            "selected_bucket_count": selected_bucket_count,
            "total_reach": total_reach,
            "launch_date": launched_at,
            "message": "Campaign launch request accepted.",
        }



def run_cli_workflow():
    sqlagent = sqlAgent()
    bktagent = bucketingAgent()
    sbInteract = supabaseInteractions()

    schema = sbInteract.getSchema()
    campaign_request = bktagent.prompt_for_campaign_request()
    myBuckets = bktagent.generateBuckets("none", schema, campaign_request=campaign_request)
    myBuckets = normalize_generated_bucket_sqls(myBuckets)

    print("OUTPUT: \n\n", myBuckets)

    try:
        sqlList = []
        output_file = Path(__file__).resolve().parent / "bucket_output.csv"
        sql_results_file = Path(__file__).resolve().parent / "SQL_results.csv"
        response = json_to_csv(myBuckets)

        print("\n\n\n" + response)
        output_file.write_text(response, encoding="utf-8", newline="")

        bucket_rows = read_bucket_rows(output_file)
        for bucket in bucket_rows:
            sqlList.append([bucket["sql"], bucket["rationale"]])

        export_sql_results(bucket_rows, sql_results_file, sbInteract)

    except Exception as e:
        sqlList = []
        print("Could not parse AI response into CSV")
        print(f"Error: {e}")
        print(traceback.format_exc())

    agent = emailAgent()
    for x in sqlList:
        email = agent.genEmail(x[0], x[1], campaign_request)
        print(f"EMAILS:\n\n{email}\n")


if __name__ == "__main__":
    run_cli_workflow()


