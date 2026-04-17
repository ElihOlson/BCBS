from groq import Groq
import os
from supabase import *
import json
from dotenv import load_dotenv
from pathlib import Path

basedir = Path(__file__).resolve().parent
load_dotenv(basedir / ".env")


grokKey = os.getenv("GROK_API_KEY")
spbsKey = os.getenv("SUPABASE_KEY2")
spbsUrl = os.getenv("SUPABASE_URL2")


#get emails out
#fix sql execution


class sqlAgent:
    def __init__(self):
        
        

        self.client = Groq(api_key=grokKey)

        self.SUPABASE_URL = spbsUrl
        self.SUPABASE_KEY = spbsKey

        DBClient = create_client(self.SUPABASE_URL, self.SUPABASE_KEY)



    def genSQL(self, prompt, schema):
        # Single call: return SQL or "INVALID" — avoids sending schema twice
        sysPrompt = (
            f"Schema:{schema}\n"
            "Return a SQL query for the user request. Add (marketing_ai.) before all column names i.e. SELECT m.* FROM marketing_ai.members m"
            "If the request cannot be answered from the schema, reply only: INVALID"
        )
        result = self.sendMessage(prompt, sysPrompt)
        if result.strip().upper() == "INVALID":
            return "Bad Request"
        return result




    def sendMessage(self, prompt, systemPrompt):
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": systemPrompt},
                {"role": "user", "content": prompt},
            ],
            model="llama-3.1-8b-instant",
            max_tokens=500,
        )
        return chat_completion.choices[0].message.content


    def readDB(self,dbInfo):


        #format llm output into a dict
        colsList = self.formatter(dbInfo)
        #print(f"COL LIST: {colsList}")

        colString = ""

        for x in range(len(colsList)):
            if x == 0:
                colString = colsList[x]
            else:
                colString = colString + ", " + colsList[x]
        #print(f"COLSTRING: {colString}")

        response = self.DBClient.table("Test1").select(colString).execute()

        data = response.data
        #print(data)
        self.printer(data)

    #take llm json and turn it into usable struct
    def formatter(self,json_string):
        
        #check if string can be formatted

        # Convert string to a Python dictionary
        data = json.loads(json_string)

        return data['columns']

    def printer(self,data,limit = 20):
        
        
        if not data:
            print("No data")
            return

        total_rows = len(data)
        rows = data[:limit]

        # Use consistent column order (from first row)
        columns = list(data[0].keys())

        # Compute column widths (only from displayed rows)
        col_widths = {
            col: max(
                len(col),
                max(len(str(row.get(col, ""))) for row in rows)
            )
            for col in columns
        }

        # Header
        header = " | ".join(col.ljust(col_widths[col]) for col in columns)
        print(header)
        print("-" * len(header))

        # Rows
        for row in rows:
            print(" | ".join(str(row.get(col, "")).ljust(col_widths[col]) for col in columns))

        # Footer info
        if total_rows > limit:
            print(f"\nShowing {limit} of {total_rows} rows...")
        else:
            print(f"\nTotal rows: {total_rows}")
#=====================================================================================#
#==================================End of Functions===================================#
#=====================================================================================#


class bucketingAgent:
    def __init__(self,):

        self.client = Groq(api_key=grokKey)
        self.SUPABASE_URL = spbsUrl
        self.SUPABASE_KEY = spbsKey
        DBClient = create_client(self.SUPABASE_URL, self.SUPABASE_KEY)

        #self.schema = r"TABLE: users\nCOLUMNS: id,first_name,last_name,email,phone,city,state"

    def sendMessage(self, prompt='none', systemPrompt='none'):
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": systemPrompt},
                {"role": "user", "content": prompt},
            ],
            model="llama-3.1-8b-instant",
            max_tokens=500,
        )
        return chat_completion.choices[0].message.content
    
    def generateBuckets(self,sqlQuery,schema):
        
        #create bucket ideas given schema
        #return sql queries for each bucket
        #sqlQuery = "SELECT first_name, email FROM users WHERE LOWER(first_name) = 'joe';"
        #schema = "TABLE: users\nCOLUMNS: id,first_name,last_name,email,phone,city,state"

        systemPrompt = 'Given a SQL query and schema, list useful audience groups. Reply only in JSON: [{"desc":"","sql":""}]'
        prompt1 = f"query:{sqlQuery}\nschema:{schema}"


        return self.sendMessage(prompt1,systemPrompt)


    def userPromptedBuckets():
        pass
