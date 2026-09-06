"""
src/daily_ingest.py

Pulls system-wide SL delay data for one day (default: yesterday) and
appends it to BigQuery. Designed to run unattended via a scheduled
GitHub Actions workflow -- no manual intervention once set up.
"""
import sys
import os
from datetime import date, timedelta
from google.cloud import bigquery

sys.path.insert(0, os.path.dirname(__file__))
from build_dataset import (
    fetch_koda_realtime, fetch_koda_static, aggregate_delays,
    join_schedule, join_weather, add_features,
)
from fetch_smhi_weather import fetch_smhi_parameter

BQ_TABLE = os.getenv("BQ_TABLE", "regal-stone-429421-j0.sl_delays.daily_all_routes")

# Schema is pinned explicitly rather than using autodetect=True, so the
# table's structure is a deliberate, versioned decision (visible in git)
# instead of being silently re-guessed from whatever a given day's
# DataFrame happens to contain.
SCHEMA = [
    bigquery.SchemaField("trip_id", "STRING"),
    bigquery.SchemaField("stop_id", "STRING"),
    bigquery.SchemaField("stop_sequence", "INTEGER"),
    bigquery.SchemaField("delay_seconds", "FLOAT"),
    bigquery.SchemaField("route_short_name", "STRING"),
    bigquery.SchemaField("scheduled_dt", "TIMESTAMP"),
    bigquery.SchemaField("temperature_c", "FLOAT"),
    bigquery.SchemaField("precip_mm", "FLOAT"),
    bigquery.SchemaField("is_snow_proxy", "FLOAT"),
    bigquery.SchemaField("is_rain_proxy", "FLOAT"),
    bigquery.SchemaField("hour", "INTEGER"),
    bigquery.SchemaField("weekday", "STRING"),
    bigquery.SchemaField("is_rush_hour", "INTEGER"),
    bigquery.SchemaField("is_delayed", "FLOAT"),
    bigquery.SchemaField("delay_minutes", "FLOAT"),
    bigquery.SchemaField("service_date", "DATE"),
]


def get_recent_weather():
    # corrected-archive excludes the last ~3 months -- use latest-months
    # for anything recent, or this silently returns nothing for "yesterday"
    temp = fetch_smhi_parameter("1", "temperature_c", period="latest-months")
    precip = fetch_smhi_parameter("7", "precip_mm", period="latest-months")
    weather = temp.merge(precip, on="datetime", how="outer")
    weather["is_snow_proxy"] = ((weather["precip_mm"] > 0) & (weather["temperature_c"] <= 0)).astype(int)
    weather["is_rain_proxy"] = ((weather["precip_mm"] > 0) & (weather["temperature_c"] > 0)).astype(int)
    weather["hour_bucket"] = weather["datetime"].dt.floor("h")
    return weather


def run(target_date):
    print(f"Ingesting {target_date} (system-wide, all routes)")
    weather = get_recent_weather()

    extract_dir = fetch_koda_realtime(target_date)
    static_zip = fetch_koda_static(target_date)
    delays = aggregate_delays(target_date, extract_dir)
    scheduled = join_schedule(delays, static_zip)
    weathered = join_weather(scheduled, target_date, weather)
    featured = add_features(weathered)
    featured["service_date"] = target_date
    print(f"  {len(featured)} rows (all pipeline columns)")

    # keep only the columns the pinned schema actually declares -- the
    # pipeline carries some intermediate/bookkeeping columns (snapshot_time,
    # arrival_time, route_id, hour_bucket) that were needed mid-pipeline but
    # were never meant to land in the permanent table
    schema_columns = [f.name for f in SCHEMA]
    featured = featured[schema_columns]

    client = bigquery.Client()
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND", schema=SCHEMA)
    job = client.load_table_from_dataframe(featured, BQ_TABLE, job_config=job_config)
    job.result()
    print(f"  Appended to {BQ_TABLE}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else (date.today() - timedelta(days=1)).isoformat()
    run(target)