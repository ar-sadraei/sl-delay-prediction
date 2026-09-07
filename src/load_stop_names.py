"""
Loads the full system-wide stop_id -> stop_name mapping from SL's current
static GTFS feed into BigQuery, so stop_delay_summary can show human-
readable names instead of raw stop_ids. Same fetch pattern as
export_stop_metadata.py, but keeps every stop rather than filtering to
one route.
"""
from dotenv import load_dotenv
import os
import requests
import zipfile
import pandas as pd
from google.cloud import bigquery

load_dotenv()
API_KEY = os.getenv("TRAFIKLAB_STATIC_KEY")

url = f"https://opendata.samtrafiken.se/gtfs/sl/sl.zip?key={API_KEY}"
resp = requests.get(url)
resp.raise_for_status()
with open("data/raw/sl_static_for_stopnames.zip", "wb") as f:
    f.write(resp.content)

with zipfile.ZipFile("data/raw/sl_static_for_stopnames.zip") as z:
    stops = pd.read_csv(z.open("stops.txt"))

stops["stop_id"] = stops["stop_id"].astype(str)
# GTFS occasionally has duplicate stop_id rows (rare, but real) -- keep one
stops_clean = stops[["stop_id", "stop_name"]].drop_duplicates(subset="stop_id")
print(f"{len(stops_clean)} unique stops found system-wide")

client = bigquery.Client()
table_id = "regal-stone-429421-j0.sl_delays.stop_names"
job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
job = client.load_table_from_dataframe(stops_clean, table_id, job_config=job_config)
job.result()
print(f"Loaded {len(stops_clean)} stop names into {table_id}")