import csv
import os
import pandas as pd

csv_path = os.path.join(os.path.dirname(__file__), "bucket_output.csv")

sql_list = []

df = pd.read_csv(csv_path, usecols=["sql"])

for sql in df["sql"].dropna():
    # print(sql)
    sql_list.append(sql)


for x in sql_list:
    print(f"\n\n{x}\n\n")


