from dotenv import load_dotenv
import os
import requests
import zipfile
import pandas as pd

load_dotenv()
API_KEY = os.getenv("TRAFIKLAB_STATIC_KEY")

url = f"https://opendata.samtrafiken.se/gtfs/sl/sl.zip?key={API_KEY}"
resp = requests.get(url)
resp.raise_for_status()
with open("data/raw/sl_static_current.zip", "wb") as f:
    f.write(resp.content)

with zipfile.ZipFile("data/raw/sl_static_current.zip") as z:
    routes = pd.read_csv(z.open("routes.txt"))
    trips = pd.read_csv(z.open("trips.txt"))
    stop_times = pd.read_csv(z.open("stop_times.txt"))
    stops = pd.read_csv(z.open("stops.txt"))

route_id = routes[routes["route_short_name"] == "607"]["route_id"].values[0]

known_stop_ids = set(
    pd.read_parquet("data/processed/modeling_table_route607.parquet")["stop_id"].astype(str)
)

# a route runs in two directions, each with its own stop order -- export
# both, since the model was trained on stops from both directions
trips_with_dir = trips[trips["route_id"] == route_id][["trip_id", "direction_id"]]

all_stops = []
for direction in sorted(trips_with_dir["direction_id"].unique()):
    dir_trip_ids = trips_with_dir[trips_with_dir["direction_id"] == direction]["trip_id"]
    dir_stop_times = stop_times[stop_times["trip_id"].isin(dir_trip_ids)]
    longest_trip = dir_stop_times.groupby("trip_id").size().idxmax()

    ordered = (
        stop_times[stop_times["trip_id"] == longest_trip]
        .sort_values("stop_sequence")[["stop_id", "stop_sequence"]]
        .merge(stops[["stop_id", "stop_name"]], on="stop_id")
    )
    ordered["stop_id"] = ordered["stop_id"].astype(str)
    ordered["direction_id"] = int(direction)
    all_stops.append(ordered)

ordered_stops = pd.concat(all_stops, ignore_index=True)
ordered_stops = ordered_stops[ordered_stops["stop_id"].isin(known_stop_ids)]

ordered_stops.to_json("api/artifacts/stop_metadata.json", orient="records", indent=2)
print(f"Saved {len(ordered_stops)} stops across both directions to api/artifacts/stop_metadata.json")
print(ordered_stops.groupby("direction_id").size())