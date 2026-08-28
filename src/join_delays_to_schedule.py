import zipfile
import pandas as pd

with zipfile.ZipFile("data/raw/static_2024-08-01.zip") as z:
    with z.open("stop_times.txt") as f:
        stop_times = pd.read_csv(f)
    with z.open("trips.txt") as f:
        trips = pd.read_csv(f)
    with z.open("routes.txt") as f:
        routes = pd.read_csv(f)

""" print(stop_times.shape, trips.shape, routes.shape)
print(stop_times.columns.tolist()) """

final_delays = pd.read_parquet("data/processed/final_delays_2024-08-01.parquet")

final_delays["trip_id"] = final_delays["trip_id"].astype(str)
stop_times["trip_id"] = stop_times["trip_id"].astype(str)
trips["trip_id"] = trips["trip_id"].astype(str)
stop_times["stop_id"] = stop_times["stop_id"].astype(str)

merged = (
    final_delays
    .merge(stop_times[["trip_id", "stop_id", "arrival_time"]], on=["trip_id", "stop_id"])
    .merge(trips[["trip_id", "route_id"]], on="trip_id")
    .merge(routes[["route_id", "route_short_name", "route_long_name"]], on="route_id")
)

""" print(merged.shape)
print(merged.head())

print(merged["route_long_name"].isna().sum(), "of", len(merged), "rows have null route_long_name")
print(merged[merged["route_long_name"].notna()]["route_short_name"].unique()[:20])
 """

merged.to_parquet("data/processed/delays_with_schedule_2024-08-01.parquet", index=False)
print("Saved.")