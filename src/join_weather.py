import pandas as pd

# Load Step 2.3 inputs
merged = pd.read_parquet("data/processed/delays_with_schedule_2024-08-01.parquet")
weather = pd.read_csv("data/processed/smhi_temp_clean.csv", parse_dates=["datetime"])

# Convert GTFS arrival_time (a string, possibly past 24:00:00) into a real timestamp
def gtfs_time_to_datetime(service_date, time_str):
    h, m, s = map(int, time_str.split(":"))
    base = pd.Timestamp(service_date)
    return base + pd.Timedelta(hours=h, minutes=m, seconds=s)

SERVICE_DATE = "2024-08-01"
merged["scheduled_dt"] = merged["arrival_time"].apply(
    lambda t: gtfs_time_to_datetime(SERVICE_DATE, t)
)

# Step 2: floor both sides to the hour so they can be joined
merged["hour_bucket"] = merged["scheduled_dt"].dt.floor("h")
weather["hour_bucket"] = weather["datetime"].dt.floor("h")

# Step 3: join
final = merged.merge(
    weather[["hour_bucket", "temperature_c", "quality"]],
    on="hour_bucket",
    how="left"  # keep every trip even if that hour has no weather reading
)

print(final.shape)
print(final["temperature_c"].isna().sum(), "rows with no matching weather")
print(final[["trip_id", "route_short_name", "scheduled_dt", "temperature_c"]].head())

final.to_parquet("data/processed/full_modeling_table_2024-08-01.parquet", index=False)
print("Saved.")