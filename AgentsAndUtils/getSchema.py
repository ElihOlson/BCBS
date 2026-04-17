import os
from pathlib import Path
from supabase import create_client, Client
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

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
                    #resultSchema.append(f"Table [{table}]: {', '.join(cols)}")
                    resultSchema.append(f"{table}({','.join(cols)})")
                    
                
                return resultSchema

            else:
                print("CONNECTION: Success, but no tables found in public schema.")
                
        except Exception as e:
            print(f"CONNECTION FAILED: {str(e)}")
        

    def run_sql_query(self,sql_query: str):
        """
        Executes a raw SQL query against a Supabase Postgres database
        and returns the results as a list of dictionaries.
        """

        try:
            conn = psycopg2.connect(
                host="YOUR_HOST",
                database="postgres",
                user="postgres",
                password="YOUR_PASSWORD",
                port=5432
            )

            # Return rows as dicts instead of tuples
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute(sql_query)

            # Try to fetch results (SELECT queries)
            try:
                results = cursor.fetchall()
            except psycopg2.ProgrammingError:
                results = None  # For INSERT/UPDATE/DELETE

            conn.commit()

            cursor.close()
            conn.close()

            return results

        except Exception as e:
            print(f"Error executing query: {e}")
            return None
            

    
if __name__ == "__main__":
    DB = supabaseInteractions()
    DB.getSchema()


    sql = "SELECT m.* FROM marketing_ai.members m JOIN marketing_ai.addresses a ON m.address_id = a.address_id WHERE a.state = 'CA';"
    result = DB.run_sql_query(sql)
    print(result)


    