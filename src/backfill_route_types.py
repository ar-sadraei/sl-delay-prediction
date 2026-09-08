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

all_dates_query = """
SELECT DISTINCT service_date FROM `regal-stone-429421-j0.sl_delays.historical_backfill`
UNION DISTINCT
SELECT DISTINCT service_date FROM `regal-stone-429421-j0.sl_delays.daily_all_routes`
"""
all_dates = [r.service_date.isoformat() for r in client.query(all_dates_query).result()]

try:
    existing = {r.service_date.isoformat() for r in client.query(
        f"SELECT DISTINCT service_date FROM `{LOOKUP_TABLE}`"
    ).result()}
except Exception:
    existing = set()  # table doesn't exist yet on first run

dates_to_process = [d for d in all_dates if d not in existing]
print(f"{len(dates_to_process)} of {len(all_dates)} dates need route_type backfilled")

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
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND" if existing else "WRITE_TRUNCATE"
    )
    client.load_table_from_dataframe(combined, LOOKUP_TABLE, job_config=job_config).result()
    print(f"\nAppended {len(combined)} rows to {LOOKUP_TABLE}")
else:
    print("Nothing new to add.")