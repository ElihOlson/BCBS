import os
from pathlib import Path
from flask import Flask, send_file, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv


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
                cols = [r['column_name'] for r in rpc_res.data if r['table_name'] == table]
                print(f"Table [{table}]: {', '.join(cols)}")
        else:
            print("CONNECTION: Success, but no tables found in public schema.")
            
    except Exception as e:
        print(f"CONNECTION FAILED: {str(e)}")
    print("="*40 + "\n")

# Run the check immediately on launch
startup_checks()