from agents import sqlAgent, bucketingAgent
from getSchema import supabaseInteractions


sqlagent = sqlAgent()
bktagent = bucketingAgent()
sbInteract = supabaseInteractions()


prompt = input("Enter a prompt: ")

schema = sbInteract.getSchema()

sqlQuery = sqlagent.genSQL(prompt,schema)
print(sqlQuery)

prompt = input("Continue? ")

response = bktagent.generateBuckets(sqlQuery,schema)
print(response)







