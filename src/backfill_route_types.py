"""
src/backfill_route_types.py

Retroactively fills in route_type/route_id/agency_id for every service_date
already collected, using only the (cheap) static GTFS feed per date -- no
realtime protobuf re-decoding needed. Incremental: only processes dates not
already in the lookup table, so it's safe and cheap to rerun as
daily_all_routes keeps growing.
"""
import os
import sys
import zipfile
import pandas as pd
from google.cloud import bigquery

sys.path.insert(0, os.path.dirname(__file__))
from build_dataset import fetch_koda_static

client = bigquery.Client()
LOOKUP_TABLE = "regal-stone-429421-j0.sl_delays.trip_route_lookup"

missing_dates_query = """
SELECT service_date FROM (
  SELECT DISTINCT service_date FROM `regal-stone-429421-j0.sl_delays.historical_backfill`
  UNION DISTINCT
  SELECT DISTINCT service_date FROM `regal-stone-429421-j0.sl_delays.daily_all_routes`
)
WHERE service_date NOT IN (
  SELECT DISTINCT SAFE.PARSE_DATE('%Y-%m-%d', service_date)
  FROM `regal-stone-429421-j0.sl_delays.trip_route_lookup`
)
"""
dates_to_process = [r.service_date.isoformat() for r in client.query(missing_dates_query).result()]
print(f"{len(dates_to_process)} dates need route_type backfilled")

new_rows = []
for date in dates_to_process:
    try:
        static_zip = fetch_koda_static(date)
        with zipfile.ZipFile(static_zip) as z:
            trips = pd.read_csv(z.open("trips.txt"))
            routes = pd.read_csv(z.open("routes.txt"))
        merged = trips[["trip_id", "route_id"]].merge(
            routes[["route_id", "route_short_name", "route_type", "agency_id"]], on="route_id"
        )
        merged["trip_id"] = merged["trip_id"].astype(str)
        merged["service_date"] = date
        new_rows.append(merged[["service_date", "trip_id", "route_id", "route_type", "agency_id"]])
        print(f"  {date}: {len(merged)} trip->route_type mappings")
        os.remove(static_zip)
    except Exception as e:
        print(f"  FAILED for {date}: {e} -- skipping")

if new_rows:
    combined = pd.concat(new_rows, ignore_index=True)
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
    client.load_table_from_dataframe(combined, LOOKUP_TABLE, job_config=job_config, location="EU").result()
    print(f"\nAppended {len(combined)} rows to {LOOKUP_TABLE}")
else:
    print("Nothing new to add.")