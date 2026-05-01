import os
from pathlib import Path
from flask import Flask, send_file, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv

# 1. SETUP & AUTH
basedir = Path(__file__).resolve().parent
load_dotenv(basedir / ".env")

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    print("--- ERROR: Credentials missing from .env ---")
    exit(1)

supabase: Client = create_client(supabase_url, supabase_key)

# 2. BACKEND LOGIC (Terminal Output Only)
def startup_checks():
    print("\n" + "="*40)
    print("STARTING BCBS BACKEND")
    try:
        # Calls the SQL function in Supabase
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
        rpc_res = supabase.rpc('get_table_schema').execute()
        return jsonify(rpc_res.data)
    except:
        return jsonify({"error": "failed"}), 500

if __name__ == '__main__':
    app.run(debug=True)