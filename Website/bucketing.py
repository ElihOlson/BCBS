from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI

# Use your Supabase connection string
# postgresql://postgres.[project-id]:[password]@aws-0-us-east-1.pooler.supabase.com:5432/postgres
db = SQLDatabase.from_uri("your_supabase_connection_string")

# Define the LLM (e.g., GPT-4o for complex SQL logic)
llm = ChatOpenAI(model="gpt-4o", temperature=0)