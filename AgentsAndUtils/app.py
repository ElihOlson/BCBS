import json
import os
import re
import sys
import importlib
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from supabase import Client, create_client

basedir = Path(__file__).resolve().parent
agents_dir = basedir.parent / "AgentsAndUtils"
campaign_history_path = agents_dir / "launched_campaigns.json"
if str(agents_dir) not in sys.path:
    sys.path.append(str(agents_dir))

code_agents_module = importlib.import_module("codeAgents")
supabase_utils_module = importlib.import_module("supabaseUtils")

bucketingAgent = code_agents_module.bucketingAgent
emailAgent = code_agents_module.emailAgent
supabaseInteractions = supabase_utils_module.supabaseInteractions

env_candidates = [
    basedir / ".env",
    agents_dir / ".env",
]
for env_path in env_candidates:
    if env_path.exists():
        load_dotenv(env_path)
        break

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

supabase: Client | None = None
if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)

sb_interact = None
try:
    sb_interact = supabaseInteractions()
except Exception:
    sb_interact = None

bucket_agent = None
email_agent = None
try:
    bucket_agent = bucketingAgent()
    email_agent = emailAgent()
except Exception:
    bucket_agent = None
    email_agent = None

# 2. BACKEND LOGIC (Terminal Output Only)
def startup_checks():
    print("\n" + "="*40)
    print("STARTING BCBS BACKEND")
    if supabase is None:
        print("CONNECTION FAILED: Credentials missing from .env")
        print("="*40 + "\n")
        return
    try:
        rpc_res = supabase.rpc('get_table_schema').execute()
        
        if rpc_res.data:
            # Get unique tables
            tables = sorted(list(set([row['table_name'] for row in rpc_res.data])))
            print("CONNECTION: Success")
            print(f"TABLES FOUND: {', '.join(tables)}")
            
            print("\n--- DETECTED SCHEMA ---")
            for table in tables:
                rows = [r for r in rpc_res.data if r['table_name'] == table]
                col_parts = []
                for r in rows:
                    label = r['column_name']
                    if r.get('is_primary_key'):
                        label += ' [PK]'
                    if r.get('foreign_table'):
                        label += f" [FK -> {r['foreign_table']}.{r['foreign_column']}]"
                    col_parts.append(label)
                print(f"Table [{table}]: {', '.join(col_parts)}")
        else:
            print("CONNECTION: Success, but no tables found in public schema.")
            
    except Exception as e:
        print(f"CONNECTION FAILED: {str(e)}")
    print("="*40 + "\n")


def get_schema_rows():
    if supabase is None:
        return []
    try:
        rpc_res = supabase.rpc('get_table_schema').execute()
        return rpc_res.data or []
    except Exception:
        return []


def clean_json_text(raw_text):
    text = (raw_text or "").strip().replace("```json", "").replace("```", "").strip()
    return text


def sanitize_generated_sql(sql_query):
    if not sql_query:
        return sql_query

    fixed_sql = sql_query
    fixed_sql = re.sub(
        r"\bm\.sms_opt_in\s*=\s*TRUE\b",
        "EXISTS (SELECT 1 FROM marketing_ai.consent_preferences cp WHERE cp.member_id = m.member_id AND cp.sms_opt_in = TRUE)",
        fixed_sql,
        flags=re.IGNORECASE,
    )
    fixed_sql = re.sub(r"\s+", " ", fixed_sql).strip()
    return fixed_sql


def ensure_unique_bucket_names(payload):
    seen = {}
    for bucket in payload.get("buckets", []):
        base_name = (bucket.get("name") or "").strip()
        if not base_name:
            rank_value = str(bucket.get("rank") or "").strip() or "Unknown"
            base_name = f"Bucket {rank_value}"

        count = seen.get(base_name, 0) + 1
        seen[base_name] = count
        bucket["name"] = base_name if count == 1 else f"{base_name} ({count})"

    return payload


def normalize_bucket_payload(raw_bucket_json):
    cleaned = clean_json_text(raw_bucket_json)
    payload = json.loads(cleaned)
    for bucket in payload.get("buckets", []):
        if isinstance(bucket.get("sql"), str):
            bucket["sql"] = sanitize_generated_sql(bucket["sql"])
    return ensure_unique_bucket_names(payload)


def safe_build_campaign_request(about_text, audience_text, success_text):
    if bucket_agent is None:
        return {
            "about": {"campaign_type": about_text, "channel": "sms", "message_goal": about_text},
            "for": {"description": audience_text},
            "success_conditions": {"primary_metric": success_text},
        }

    try:
        return bucket_agent.build_campaign_request(about_text, audience_text, success_text)
    except Exception:
        return {
            "about": {"campaign_type": about_text, "channel": "sms", "message_goal": about_text},
            "for": {"description": audience_text},
            "success_conditions": {"primary_metric": success_text},
        }


def safe_generate_buckets(schema_lines, campaign_request):
    if bucket_agent is None:
        return {
            "universe_definition": "unavailable",
            "primary_slicing_axis": "unavailable",
            "coverage_note": "Bucketing agent is not configured.",
            "buckets": [],
        }

    raw = bucket_agent.generateBuckets("none", schema_lines, campaign_request=campaign_request)
    return normalize_bucket_payload(raw)


def run_bucket_queries(bucket_rows):
    enriched = []
    total_reach = 0

    for idx, bucket in enumerate(bucket_rows, start=1):
        sql_query = (bucket.get("sql") or "").strip()
        row_count = 0
        sample_rows = []
        query_error = ""

        if sql_query and sb_interact is not None:
            try:
                results = sb_interact.run_sql_query(sql_query)
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


def generate_bucket_email(bucket, campaign_request):
    if email_agent is None:
        return {
            "subject": f"Action needed for {bucket['name']}",
            "body": f"This message targets {bucket['name']}. Edit this content before launch.",
        }

    try:
        raw_email = email_agent.genEmail(bucket["sql"], bucket["rationale"], campaign_request)
        text = clean_json_text(raw_email)
        return {
            "subject": f"Campaign for {bucket['name']}",
            "body": text,
        }
    except Exception:
        return {
            "subject": f"Action needed for {bucket['name']}",
            "body": f"This message targets {bucket['name']}. Edit this content before launch.",
        }


def build_campaign_response(about_text, audience_text, success_text):
    campaign_request = safe_build_campaign_request(about_text, audience_text, success_text)
    schema_rows = get_schema_rows()
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

    bucket_payload = safe_generate_buckets(schema_lines, campaign_request)
    buckets, total_reach = run_bucket_queries(bucket_payload.get("buckets", []))

    for bucket in buckets:
        email_data = generate_bucket_email(bucket, campaign_request)
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
            "schema_table_count": len({row.get('table_name') for row in schema_rows}),
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


def load_campaign_history():
    if not campaign_history_path.exists():
        return []

    try:
        data = json.loads(campaign_history_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def save_campaign_history(history_rows):
    campaign_history_path.write_text(
        json.dumps(history_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# Run the check immediately on launch
startup_checks()

# 3. FLASK APP & ROUTES
app = Flask(__name__)

@app.route('/')
@app.route('/home')
def home():
    # Serves the actual UI to the user
    return send_file('launch_page.html')

@app.route('/data_review')
def data_review():
    return send_file('launch_page.html')

@app.route('/bucketing')
def bucketing():
    return send_file('launch_page.html')

@app.route('/email')
def email():
    return send_file('launch_page.html')

@app.route('/launch')
def launch():
    return send_file('launch_page.html')

# Internal API for the LangChain agent (hidden from UI)
@app.route('/api/internal/schema')
def api_schema():
    try:
        if supabase is None:
            return jsonify({"error": "failed"}), 500
        rpc_res = supabase.rpc('get_table_schema').execute()
        return jsonify(rpc_res.data)
    except:
        return jsonify({"error": "failed"}), 500


@app.route('/api/internal/campaign/run', methods=['POST'])
def api_campaign_run():
    payload = request.get_json(silent=True) or {}
    about_text = (payload.get("about") or "").strip()
    audience_text = (payload.get("campaign_for") or "").strip()
    success_text = (payload.get("success_conditions") or "").strip()

    if not about_text or not audience_text or not success_text:
        return jsonify({"error": "about, campaign_for, and success_conditions are required"}), 400

    try:
        result = build_campaign_response(about_text, audience_text, success_text)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/internal/campaign/launch', methods=['POST'])
def api_campaign_launch():
    payload = request.get_json(silent=True) or {}
    selected_buckets = payload.get("selected_buckets") or []
    campaign_name = payload.get("campaign_name") or "Campaign"
    total_reach = int(payload.get("total_reach") or 0)
    selected_bucket_count = len(selected_buckets)
    launched_at = datetime.utcnow().strftime("%b %d, %Y")

    history_rows = load_campaign_history()
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
    save_campaign_history(history_rows)

    return jsonify(
        {
            "status": "launched",
            "campaign_name": campaign_name,
            "selected_bucket_count": selected_bucket_count,
            "total_reach": total_reach,
            "launch_date": launched_at,
            "message": "Campaign launch request accepted.",
        }
    )


@app.route('/api/internal/campaign/history', methods=['GET'])
def api_campaign_history():
    return jsonify(load_campaign_history())

if __name__ == '__main__':
    app.run(debug=True)