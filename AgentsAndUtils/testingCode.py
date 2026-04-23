#from agents import sqlAgent, bucketingAgent
from getSchema import supabaseInteractions
from gptAgents import *
import json

def printer(json_str):
    

    data = json.loads(json_str)

    for obj in data:
        for key, value in obj.items():
            print(f"{key}: {value}")
        print()  # blank line between objects



sqlagent = sqlAgent()
bktagent = bucketingAgent()
sbInteract = supabaseInteractions()




prompt = input("Enter a prompt: ")

schema = sbInteract.getSchema()

ans = bktagent.generateBuckets(prompt, schema)

print("OUTPUT", ans)







