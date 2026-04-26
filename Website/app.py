import os
from pathlib import Path
from flask import Flask, send_file, jsonify, request
from supabase import create_client, Client
from dotenv import load_dotenv
from AgentsAndUtils import codeAgents, supabaseUtils



# 1. SETUP & AUTH
basedir = Path(__file__).resolve().parent
load_dotenv(basedir / ".env")

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    print("--- ERROR: Credentials missing from .env ---")
    exit(1)

supabase: Client = create_client(supabase_url, supabase_key)



# 3. FLASK APP & ROUTES
app = Flask(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return send_file('launch_page.html')

@app.route('/submit', methods=['POST'])
def submit():
    data = request.get_json()

    about = data.get('about')
    for_text = data.get('for')
    success = data.get('success')

    info = [
        f"{about}",
        f"{for_text} ",
        f"{success}"
    ]

    return jsonify({"info": info})

@app.route('/data_review')
def data_review():
    return send_file('data_review.html')

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
        rpc_res = supabase.rpc('get_table_schema').execute()
        return jsonify(rpc_res.data)
    except:
        return jsonify({"error": "failed"}), 500

if __name__ == '__main__':
    app.run(debug=True)