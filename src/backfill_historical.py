"""
Processes the 114-date year-round sample (reports/backfill_dates.txt),
system-wide (all routes), and loads the result into a dedicated BigQuery
table, kept separate from daily_all_routes -- this is a deliberately
sampled historical backfill, not the continuously-collected live table.

Reuses build_for_date() from build_dataset.py, so each date gets the
same local checkpointing (small daily parquet + immediate raw cleanup)
already proven across the 61-date and 23-date batches.
"""
import os
import sys
import shutil
import pandas as pd
from google.cloud import bigquery

sys.path.insert(0, os.path.dirname(__file__))
from build_dataset import build_for_date, PROCESSED_DIR
from fetch_smhi_weather import fetch_smhi_parameter
from daily_ingest import SCHEMA  # reuse the same pinned schema, don't redefine it twice

BQ_TABLE = "regal-stone-429421-j0.sl_delays.historical_backfill"


def get_full_weather():
    """
    corrected-archive (quality-controlled) excludes roughly the last 3
    months; latest-months covers that gap. Combine both so dates across
    the whole selected range -- old and recent -- get real weather,
    preferring the quality-controlled value where both exist.
    """
    print("Fetching corrected-archive weather...")
    temp_archive = fetch_smhi_parameter("1", "temperature_c", period="corrected-archive")
    precip_archive = fetch_smhi_parameter("7", "precip_mm", period="corrected-archive")

    print("Fetching latest-months weather (covers recent gap)...")
    temp_recent = fetch_smhi_parameter("1", "temperature_c", period="latest-months")
    precip_recent = fetch_smhi_parameter("7", "precip_mm", period="latest-months")

    temp = (pd.concat([temp_archive, temp_recent])
            .drop_duplicates(subset="datetime", keep="first")
            .sort_values("datetime"))
    precip = (pd.concat([precip_archive, precip_recent])
              .drop_duplicates(subset="datetime", keep="first")
              .sort_values("datetime"))

    weather = temp.merge(precip, on="datetime", how="outer")
    weather["is_snow_proxy"] = ((weather["precip_mm"] > 0) & (weather["temperature_c"] <= 0)).astype(int)
    weather["is_rain_proxy"] = ((weather["precip_mm"] > 0) & (weather["temperature_c"] > 0)).astype(int)
    weather["hour_bucket"] = weather["datetime"].dt.floor("h")
    return weather


if __name__ == "__main__":
    with open("reports/backfill_dates.txt") as f:
        dates = [line.strip() for line in f if line.strip()]
    print(f"Backfilling {len(dates)} dates, system-wide (all routes)\n")

    weather = get_full_weather()

    for date in dates:
        try:
            build_for_date(date, weather, routes=None)
        except Exception as e:
            print(f"  FAILED for {date}: {e} -- skipping this date")

    schema_columns = [field.name for field in SCHEMA]
    daily_files = [f"{PROCESSED_DIR}/daily/modeling_table_{d}_all.parquet" for d in dates]
    daily_files = [f for f in daily_files if os.path.exists(f)]

    dfs = [pd.read_parquet(f)[schema_columns] for f in daily_files]
    combined = pd.concat(dfs, ignore_index=True)
    print(f"\nTotal: {len(combined)} rows across {len(dfs)}/{len(dates)} dates")

    dupes = combined.duplicated(subset=["trip_id", "stop_id", "stop_sequence", "service_date"], keep=False)
    print(f"Duplicate check: {dupes.sum()} duplicate rows found")

    # WRITE_TRUNCATE, not WRITE_APPEND -- this is a one-time backfill table,
    # not the continuously-appending daily table. Rerunning this script
    # should replace the table cleanly, not accumulate duplicate loads.
    client = bigquery.Client()
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", schema=SCHEMA)
    job = client.load_table_from_dataframe(combined, BQ_TABLE, job_config=job_config)
    job.result()
    print(f"Loaded {len(combined)} rows into {BQ_TABLE}")