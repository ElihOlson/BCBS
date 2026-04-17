import os
from pathlib import Path
from supabase import create_client, Client
from dotenv import load_dotenv

basedir = Path(__file__).resolve().parent
load_dotenv(basedir / ".env")

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

class supabaseInteractions:
    def __init__(self):

        if not supabase_url or not supabase_key:
            print("--- ERROR: Credentials missing from .env ---")
            exit(1)

        self.supabase:Client = create_client(supabase_url, supabase_key)

    # 2. BACKEND LOGIC (Terminal Output Only)
    def getSchema(self):

        resultSchema = []

        try:
            # Calls the SQL function in Supabase
            rpc_res = self.supabase.rpc('get_table_schema').execute()
            
            if rpc_res.data:
                # Get unique tables
                tables = sorted(list(set([row['table_name'] for row in rpc_res.data])))
                print("CONNECTION: Success")
                print(f"TABLES FOUND: {', '.join(tables)}")
                

                for table in tables:
                    cols = [r['column_name'] for r in rpc_res.data if r['table_name'] == table]
                    resultSchema.append(f"Table [{table}]: {', '.join(cols)}")
                
                return resultSchema

            else:
                print("CONNECTION: Success, but no tables found in public schema.")
                
        except Exception as e:
            print(f"CONNECTION FAILED: {str(e)}")
        

    
if __name__ == "__main__":
    DB = supabaseInteractions()
    DB.getSchema()