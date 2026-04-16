import os
from pathlib import Path
from flask import Flask, send_file, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv

# 1. SETUP & AUTH
basedir = Path(__file__).resolve().parent

# Check multiple possible naming variations to find your credentials
env_options = [basedir / ".env", basedir / "supabase.env", basedir / ".env.txt"]
env_found = False

for p in env_options:
    if p.exists():
        load_dotenv(p)
        print(f"File Found: {p.name}")
        env_found = True
        break

if not env_found:
    print(f"ALERT: No .env file found in {basedir}")
    # If you get stuck here, manually paste your URL/KEY below temporarily:
    # os.environ["SUPABASE_URL"] = "https://your-url.supabase.co"
    # os.environ["SUPABASE_KEY"] = "your-key"

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Credentials missing from environment. Please check your .env file.")

supabase: Client = create_client(supabase_url, supabase_key)

app = Flask(__name__)

# 2. DYNAMIC SCHEMA ROUTES
@app.route('/')
def check_connection():
    try:
        # This calls the SQL function you created in Supabase
        rpc_res = supabase.rpc('get_table_schema').execute()
        
        if not rpc_res.data:
            return "Connected! But no tables found. (Is your database empty or is the RPC missing?)"

        # Get unique list of tables
        tables = sorted(list(set([row['table_name'] for row in rpc_res.data])))
        return (f"<h1>Connection Successful!</h1>"
                f"<p><b>Tables Discovered:</b> {', '.join(tables)}</p>"
                f"<p>Check <a href='/api/schema'>/api/schema</a> for the full map.</p>")
    except Exception as e:
        return f"<h1>Connection Error</h1><p>{str(e)}</p>"

@app.route('/api/schema')
def get_full_schema():
    """Returns the database structure as JSON for your AI Agent."""
    try:
        rpc_res = supabase.rpc('get_table_schema').execute()
        schema_map = {}
        for row in rpc_res.data:
            t_name = row['table_name']
            if t_name not in schema_map:
                schema_map[t_name] = []
            schema_map[t_name].append({
                "column": row['column_name'],
                "type": row['data_type']
            })
        return jsonify(schema_map)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 3. PAGE ROUTES
@app.route('/home')
def home(): return send_file('launch_page.html')

@app.route('/data_review')
def data_review(): return send_file('launch_page.html')

@app.route('/bucketing')
def bucketing(): return send_file('launch_page.html')

@app.route('/email')
def email(): return send_file('launch_page.html')

@app.route('/launch')
def launch(): return send_file('launch_page.html')

if __name__ == '__main__':
    app.run(debug=True)