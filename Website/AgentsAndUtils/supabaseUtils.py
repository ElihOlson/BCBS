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
                    rows = [r for r in rpc_res.data if r['table_name'] == table]
                    col_parts = []
                    for r in rows:
                        label = r['column_name']
                        if r.get('is_primary_key'):
                            label += ' [PK]'
                        if r.get('foreign_table'):
                            label += f" [FK -> {r['foreign_table']}.{r['foreign_column']}]"
                        col_parts.append(label)
                    resultSchema.append(f"Table [{table}]: {', '.join(col_parts)}")
                    
                
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
                host="db.qnkrqseglxzveuvpipqb.supabase.co",
                database="postgres",
                user="postgres",
                password="Aiccorebcbs",
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
    sql = "SELECT DISTINCT m.member_id, m.first_name, m.last_name, m.email, m.phone_mobile FROM marketing_ai.members m JOIN marketing_ai.addresses a ON m.address_id = a.address_id JOIN marketing_ai.member_conditions mc ON m.member_id = mc.member_id WHERE LOWER(m.status) = 'active' AND m.date_of_birth BETWEEN (CURRENT_DATE - INTERVAL '40 years') AND (CURRENT_DATE - INTERVAL '25 years') AND LOWER(a.state) IN ('ne', 'ia') AND (LOWER(mc.icd10_code) LIKE 'e11%' OR LOWER(mc.icd10_code) LIKE 'i10%') AND EXISTS (SELECT 1 FROM marketing_ai.consent_preferences cp WHERE cp.member_id = m.member_id AND cp.sms_opt_in = TRUE) AND NOT EXISTS (SELECT 1 FROM marketing_ai.suppression_lists sl WHERE sl.member_id = m.member_id AND LOWER(sl.channel) = 'sms' AND (sl.expires_at IS NULL OR sl.expires_at > CURRENT_DATE)) AND EXISTS (SELECT 1 FROM marketing_ai.enrollments e WHERE e.member_id = m.member_id AND e.is_active = TRUE) AND EXISTS (SELECT 1 FROM marketing_ai.care_gaps cg WHERE cg.member_id = m.member_id AND LOWER(cg.status) = 'open' AND LOWER(cg.measure_category) = 'preventive')"
    result = DB.run_sql_query(sql)
    print(result)


    