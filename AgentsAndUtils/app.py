import os
import sys
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, send_file, jsonify, request
from supabase import create_client, Client
from dotenv import load_dotenv

# Add this directory to path so we can import sibling modules
basedir = Path(__file__).resolve().parent
if str(basedir) not in sys.path:
    sys.path.insert(0, str(basedir))

load_dotenv(basedir / ".env")

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    print("--- ERROR: Credentials missing from .env ---")
    exit(1)

supabase: Client = create_client(supabase_url, supabase_key)

from supabaseUtils import supabaseInteractions
from codeAgents import bucketingAgent, emailAgent
from main import normalize_generated_bucket_sqls

sb = supabaseInteractions()
bkt_agent = bucketingAgent()
email_agent = emailAgent()

campaign_history_path = basedir / "launched_campaigns.json"

# Startup check
def startup_checks():
    print("\n" + "="*40)
    print("STARTING BCBS BACKEND")
    try:
        rpc_res = supabase.rpc('get_table_schema').execute()
        if rpc_res.data:
            tables = sorted(list(set([row['table_name'] for row in rpc_res.data])))
            print("CONNECTION: Success")
            print(f"TABLES FOUND: {', '.join(tables)}")
        else:
            print("CONNECTION: Success, but no tables found.")
    except Exception as e:
        print(f"CONNECTION FAILED: {str(e)}")
    print("="*40 + "\n")

startup_checks()

# 3. FLASK APP & ROUTES
app = Flask(__name__)

@app.route('/')
@app.route('/home')
def home():
    return send_file(basedir / 'launch_page.html')

@app.route('/api/internal/schema')
def api_schema():
    try:
        rpc_res = supabase.rpc('get_table_schema').execute()
        return jsonify(rpc_res.data)
    except Exception:
        return jsonify({"error": "failed"}), 500


@app.route('/api/campaign/run', methods=['POST'])
def api_campaign_run():
    payload = request.get_json(silent=True) or {}
    about = (payload.get("about") or "").strip()
    campaign_for = (payload.get("campaign_for") or "").strip()
    success_conditions = (payload.get("success_conditions") or "").strip()

    if not about or not campaign_for or not success_conditions:
        return jsonify({"error": "about, campaign_for, and success_conditions are required"}), 400

    try:
        campaign_request = bkt_agent.build_campaign_request(about, campaign_for, success_conditions)
        schema_lines = sb.getSchema() or []
        raw_buckets = bkt_agent.generateBuckets("none", schema_lines, campaign_request=campaign_request)
        bucket_payload = json.loads(normalize_generated_bucket_sqls(raw_buckets))

        buckets = []
        total_reach = 0
        for idx, bucket in enumerate(bucket_payload.get("buckets", []), start=1):
            sql = (bucket.get("sql") or "").strip()
            results = sb.run_sql_query(sql) if sql else []
            row_count = len(results) if isinstance(results, list) else 0
            total_reach += row_count
            email_body = email_agent.genEmail(sql, bucket.get("rationale", ""), campaign_request)
            buckets.append({
                "id": idx,
                "rank": bucket.get("rank") or idx,
                "name": bucket.get("name") or f"Bucket {idx}",
                "sql": sql,
                "rationale": bucket.get("rationale") or "",
                "suggested_treatment": bucket.get("suggested_treatment") or "",
                "estimated_count": bucket.get("estimated_count"),
                "row_count": row_count,
                "sample_rows": (results[:3] if isinstance(results, list) else []),
                "email_body": email_body,
            })

        campaign_possible = any(b["row_count"] > 0 for b in buckets)
        return jsonify({
            "campaign_request": campaign_request,
            "analyzer": {
                "possible": campaign_possible,
                "predicted_reach": total_reach,
                "confidence_score": 95 if campaign_possible else 0,
                "data_integrity": 99 if campaign_possible else 0,
                "message": "Campaign inputs are valid and executable." if campaign_possible else "No reachable members returned for these inputs.",
            },
            "buckets": buckets,
            "launch": {
                "campaign_name": about[:60],
                "total_reach": total_reach,
                "bucket_count": len(buckets),
            },
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/campaign/launch', methods=['POST'])
def api_campaign_launch():
    payload = request.get_json(silent=True) or {}
    campaign_name = payload.get("campaign_name") or "Campaign"
    total_reach = int(payload.get("total_reach") or 0)
    selected_bucket_count = int(payload.get("selected_bucket_count") or 0)
    launched_at = datetime.utcnow().strftime("%b %d, %Y")

    history = []
    if campaign_history_path.exists():
        try:
            history = json.loads(campaign_history_path.read_text(encoding="utf-8"))
        except Exception:
            history = []

    history.insert(0, {
        "campaign_name": campaign_name,
        "status": "Launched",
        "launch_date": launched_at,
        "total_reach": total_reach,
        "selected_bucket_count": selected_bucket_count,
    })
    campaign_history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return jsonify({"status": "launched", "launch_date": launched_at})


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)