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
from select_dates import select_dates

load_dotenv()
KODA_KEY = os.getenv("TRAFIKLAB_KODA_KEY")

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
DELAY_THRESHOLD_S = 180
RUSH_HOURS = [7, 8, 9, 16, 17, 18]


def fetch_koda_realtime(date, max_retries=10):
    archive_path = f"{RAW_DIR}/tripupdates_{date}.7z"
    extract_dir = f"{RAW_DIR}/tripupdates_{date}/"
    if os.path.exists(extract_dir):
        return extract_dir

    url = (f"https://api.koda.trafiklab.se/KoDa/api/v2/gtfs-rt/sl/TripUpdates"
           f"?date={date}&key={KODA_KEY}")
    resp = requests.get(url, timeout=60)
    retries = 0
    while resp.status_code == 202:
        if retries >= max_retries:
            raise TimeoutError(f"Archive for {date} still not ready after {max_retries} retries")
        print(f"  [{date}] archive generating, waiting 30s... (attempt {retries+1}/{max_retries})")
        time.sleep(30)
        resp = requests.get(url, timeout=60)
        retries += 1
    resp.raise_for_status()

    with open(archive_path, "wb") as f:
        f.write(resp.content)
    subprocess.run(["7zz", "x", archive_path, f"-o{extract_dir}", "-y"],
                    check=True, capture_output=True)
    return extract_dir


def fetch_koda_static(date):
    zip_path = f"{RAW_DIR}/static_{date}.zip"
    if os.path.exists(zip_path) and zipfile.is_zipfile(zip_path):
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
    Decode every snapshot for this service day, keep only the last-known
    delay per (trip_id, stop_id, stop_sequence). stop_sequence is required
    because a trip can legitimately visit the same stop_id more than once
    (loop routes) -- without it, one delay observation can match two rows
    in the schedule and get duplicated.
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

    delays_df["trip_id"] = delays_df["trip_id"].astype(str)
    delays_df["stop_id"] = delays_df["stop_id"].astype(str)
    stop_times["trip_id"] = stop_times["trip_id"].astype(str)
    stop_times["stop_id"] = stop_times["stop_id"].astype(str)
    trips["trip_id"] = trips["trip_id"].astype(str)

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
    """
    weather must already have an hourly `hour_bucket` column and carry
    temperature_c, precip_mm, is_snow_proxy, is_rain_proxy (see
    smhi_weather_clean.csv, built by fetch_smhi_weather.py).
    """
    df["scheduled_dt"] = df["arrival_time"].apply(
        lambda t: gtfs_time_to_datetime(service_date, t)
    )
    df["hour_bucket"] = df["scheduled_dt"].dt.floor("h")
    weather_cols = ["hour_bucket", "temperature_c", "precip_mm", "is_snow_proxy", "is_rain_proxy"]
    return df.merge(weather[weather_cols], on="hour_bucket", how="left")


def add_features(df):
    df["hour"] = df["scheduled_dt"].dt.hour
    df["weekday"] = df["scheduled_dt"].dt.day_name()
    df["is_rush_hour"] = df["hour"].isin(RUSH_HOURS).astype(int)

    # is_delayed must stay null where delay_seconds is null -- NaN > threshold
    # silently evaluates to False in pandas, which would mislabel "unknown"
    # delay as "on time" if not handled explicitly
    df["is_delayed"] = df["delay_seconds"].apply(
        lambda d: None if pd.isna(d) else int(d > DELAY_THRESHOLD_S)
    )
    df["delay_minutes"] = df["delay_seconds"] / 60
    return df


def build_for_date(date, weather, routes=None):
    """
    routes: list of route_short_name values to keep (e.g. ["607"]), or
    None to keep every route system-wide. Filtering happens after the
    schedule join, since route is only knowable at that point -- the
    realtime decode itself always covers the whole network regardless.
    """
    suffix = "_".join(routes) if routes else "all"
    daily_path = f"{PROCESSED_DIR}/daily/modeling_table_{date}_{suffix}.parquet"
    if os.path.exists(daily_path):
        print(f"--- {date} ({suffix}) already processed, skipping ---")
        return daily_path

    print(f"--- {date} ---")
    extract_dir = fetch_koda_realtime(date)
    static_zip = fetch_koda_static(date)
    delays = aggregate_delays(date, extract_dir)
    print(f"  {len(delays)} unique trip-stop-sequence records (all routes)")

    scheduled = join_schedule(delays, static_zip)
    if routes:
        scheduled = scheduled[scheduled["route_short_name"].isin(routes)].copy()
        print(f"  {len(scheduled)} records after filtering to {routes}")

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


if __name__ == "__main__":
    TARGET_ROUTES = ["607"]

    dates = select_dates()

    weather = pd.read_csv(f"{PROCESSED_DIR}/smhi_weather_clean.csv", parse_dates=["datetime"])
    weather["hour_bucket"] = weather["datetime"].dt.floor("h")

    for date in dates:
        try:
            build_for_date(date, weather, routes=TARGET_ROUTES)
        except Exception as e:
            print(f"  FAILED for {date}: {e} -- skipping this date")

    suffix = "_".join(TARGET_ROUTES)
    daily_files = glob.glob(f"{PROCESSED_DIR}/daily/*_{suffix}.parquet")
    final = pd.concat([pd.read_parquet(f) for f in daily_files], ignore_index=True)
    print(f"\nTotal: {len(final)} rows across {len(daily_files)} dates")

    dupes = final.duplicated(subset=["trip_id", "stop_id", "stop_sequence", "service_date"], keep=False)
    print(f"Duplicate check: {dupes.sum()} duplicate rows found")

    out_path = f"{PROCESSED_DIR}/modeling_table_route607.parquet"
    final.to_parquet(out_path, index=False)
    print(f"Saved {out_path}")