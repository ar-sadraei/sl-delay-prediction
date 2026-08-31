# src/build_dataset.py
from dotenv import load_dotenv
import os
import glob
import time
import subprocess
import zipfile
import shutil 
import requests
import pandas as pd
from google.transit import gtfs_realtime_pb2

load_dotenv()
KODA_KEY = os.getenv("TRAFIKLAB_KODA_KEY")

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
DELAY_THRESHOLD_S = 180
RUSH_HOURS = [7, 8, 9, 16, 17, 18]


def fetch_koda_realtime(date):
    archive_path = f"{RAW_DIR}/tripupdates_{date}.7z"
    extract_dir = f"{RAW_DIR}/tripupdates_{date}/"
    if os.path.exists(extract_dir):
        return extract_dir  # already fetched, skip

    url = (f"https://api.koda.trafiklab.se/KoDa/api/v2/gtfs-rt/sl/TripUpdates"
           f"?date={date}&key={KODA_KEY}")
    resp = requests.get(url, timeout=60)
    while resp.status_code == 202:
        print(f"  [{date}] archive generating, waiting 30s...")
        time.sleep(30)
        resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    with open(archive_path, "wb") as f:
        f.write(resp.content)
    subprocess.run(["7zz", "x", archive_path, f"-o{extract_dir}", "-y"],
                    check=True, capture_output=True)
    return extract_dir


def fetch_koda_static(date):
    zip_path = f"{RAW_DIR}/static_{date}.zip"
    if os.path.exists(zip_path):
        return zip_path

    url = (f"https://api.koda.trafiklab.se/KoDa/api/v2/gtfs-static/sl"
           f"?date={date}&key={KODA_KEY}")
    resp = requests.get(url, timeout=60, stream=True)
    while resp.status_code == 202:
        time.sleep(30)
        resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()

    with open(zip_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1_000_000):
            f.write(chunk)
    return zip_path


def aggregate_delays(date, extract_dir):
    """
    Decode every snapshot for this service day and keep only the last-known
    delay per (trip_id, stop_id, stop_sequence). stop_sequence is included
    because a single trip can legitimately visit the same stop_id more than
    once (loop routes, out-and-back patterns) — without it, one real delay
    observation can match two rows in the schedule and get duplicated.
    """
    pb_files = glob.glob(f"{extract_dir}sl/TripUpdates/**/*.pb", recursive=True)
    latest = {}
    for pb_file in pb_files:
        feed = gtfs_realtime_pb2.FeedMessage()
        with open(pb_file, "rb") as f:
            feed.ParseFromString(f.read())
        snapshot_time = feed.header.timestamp
        for entity in feed.entity:
            if entity.HasField("trip_update"):
                trip_id = entity.trip_update.trip.trip_id
                for stu in entity.trip_update.stop_time_update:
                    key = (trip_id, stu.stop_id, stu.stop_sequence)
                    delay_s = stu.arrival.delay if stu.HasField("arrival") else None
                    if key not in latest or snapshot_time > latest[key]["snapshot_time"]:
                        latest[key] = {"delay_seconds": delay_s, "snapshot_time": snapshot_time}

    rows = [
        {"trip_id": t, "stop_id": s, "stop_sequence": seq, **info}
        for (t, s, seq), info in latest.items()
    ]
    return pd.DataFrame(rows)


def join_schedule(delays_df, static_zip_path):
    with zipfile.ZipFile(static_zip_path) as z:
        with z.open("stop_times.txt") as f:
            stop_times = pd.read_csv(f)
        with z.open("trips.txt") as f:
            trips = pd.read_csv(f)
        with z.open("routes.txt") as f:
            routes = pd.read_csv(f)

    # trip_id/stop_id: cast to str on both sides (protobuf gives strings,
    # the static CSVs get auto-inferred as int64 — silent mismatch otherwise)
    delays_df["trip_id"] = delays_df["trip_id"].astype(str)
    delays_df["stop_id"] = delays_df["stop_id"].astype(str)
    stop_times["trip_id"] = stop_times["trip_id"].astype(str)
    stop_times["stop_id"] = stop_times["stop_id"].astype(str)
    trips["trip_id"] = trips["trip_id"].astype(str)

    # stop_sequence: cast to int on both sides to be safe, then join on all
    # three keys so a trip visiting the same stop twice no longer produces
    # a duplicate match
    delays_df["stop_sequence"] = delays_df["stop_sequence"].astype(int)
    stop_times["stop_sequence"] = stop_times["stop_sequence"].astype(int)

    return (
        delays_df
        .merge(
            stop_times[["trip_id", "stop_id", "stop_sequence", "arrival_time"]],
            on=["trip_id", "stop_id", "stop_sequence"],
        )
        .merge(trips[["trip_id", "route_id"]], on="trip_id")
        .merge(routes[["route_id", "route_short_name"]], on="route_id")
    )


def gtfs_time_to_datetime(service_date, time_str):
    h, m, s = map(int, time_str.split(":"))
    return pd.Timestamp(service_date) + pd.Timedelta(hours=h, minutes=m, seconds=s)


def join_weather(df, service_date, weather):
    df["scheduled_dt"] = df["arrival_time"].apply(
        lambda t: gtfs_time_to_datetime(service_date, t)
    )
    df["hour_bucket"] = df["scheduled_dt"].dt.floor("h")
    return df.merge(weather[["hour_bucket", "temperature_c"]], on="hour_bucket", how="left")


def add_features(df):
    df["hour"] = df["scheduled_dt"].dt.hour
    df["weekday"] = df["scheduled_dt"].dt.day_name()
    df["is_rush_hour"] = df["hour"].isin(RUSH_HOURS).astype(int)

    # is_delayed must stay null where delay_seconds is null — don't let a
    # NaN comparison silently resolve to False (and therefore 0/"on time")
    df["is_delayed"] = df["delay_seconds"].apply(
        lambda d: None if pd.isna(d) else int(d > DELAY_THRESHOLD_S)
    )
    df["delay_minutes"] = df["delay_seconds"] / 60
    return df


def build_for_date(date, weather):
    daily_path = f"{PROCESSED_DIR}/daily/modeling_table_{date}.parquet"
    if os.path.exists(daily_path):
        print(f"--- {date} already processed, skipping ---")
        return daily_path

    print(f"--- {date} ---")
    extract_dir = fetch_koda_realtime(date)
    static_zip = fetch_koda_static(date)
    delays = aggregate_delays(date, extract_dir)
    print(f"  {len(delays)} unique trip-stop-sequence records")
    scheduled = join_schedule(delays, static_zip)
    weathered = join_weather(scheduled, date, weather)
    featured = add_features(weathered)
    featured["service_date"] = date

    os.makedirs(f"{PROCESSED_DIR}/daily", exist_ok=True)
    featured.to_parquet(daily_path, index=False)
    print(f"  Saved {daily_path}")

    shutil.rmtree(extract_dir, ignore_errors=True)
    os.remove(f"{RAW_DIR}/tripupdates_{date}.7z")
    os.remove(static_zip)

    return daily_path

winter_dates = [
    # December 2023
    "2023-12-01", "2023-12-04", "2023-12-06", "2023-12-09",
    "2023-12-12", "2023-12-14", "2023-12-17", "2023-12-20",
    # January 2024 (skips New Year's/Epiphany period)
    "2024-01-08", "2024-01-10", "2024-01-13", "2024-01-16",
    "2024-01-18", "2024-01-21", "2024-01-24", "2024-01-26",
    # February 2024
    "2024-02-01", "2024-02-03", "2024-02-06", "2024-02-08",
    "2024-02-11", "2024-02-13", "2024-02-16", "2024-02-21",
]

if __name__ == "__main__":
    dates = winter_dates  # the list above

    weather = pd.read_csv(f"{PROCESSED_DIR}/smhi_temp_clean.csv", parse_dates=["datetime"])
    weather["hour_bucket"] = weather["datetime"].dt.floor("h")

    for date in dates:
        try:
            build_for_date(date, weather)
        except Exception as e:
            print(f"  FAILED for {date}: {e} — skipping this date")

    daily_files = glob.glob(f"{PROCESSED_DIR}/daily/*.parquet")
    final = pd.concat([pd.read_parquet(f) for f in daily_files], ignore_index=True)
    print(f"\nTotal: {len(final)} rows across {len(daily_files)} dates")

    dupes = final.duplicated(subset=["trip_id", "stop_id", "stop_sequence", "service_date"], keep=False)
    print(f"Duplicate check: {dupes.sum()} duplicate rows found")

    final.to_parquet(f"{PROCESSED_DIR}/modeling_table.parquet", index=False)
    print("Saved final combined modeling table.")