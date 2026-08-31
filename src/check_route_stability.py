from build_dataset import fetch_koda_static
import zipfile
import pandas as pd

def check_route_607(date):
    with zipfile.ZipFile(f"data/raw/static_{date}.zip") as z:
        with z.open("routes.txt") as f:
            routes = pd.read_csv(f)
        with z.open("trips.txt") as f:
            trips = pd.read_csv(f)
        with z.open("stop_times.txt") as f:
            stop_times = pd.read_csv(f)

    route_row = routes[routes["route_short_name"] == "607"]
    print(f"\n--- {date} ---")
    print(route_row[["route_id", "route_long_name"]])

    route_id = route_row["route_id"].values[0]
    trip_ids = trips[trips["route_id"] == route_id]["trip_id"]
    n_stops = stop_times[stop_times["trip_id"].isin(trip_ids)]["stop_id"].nunique()
    n_trips = trip_ids.nunique()
    print(f"Trips: {n_trips}, unique stops served: {n_stops}")


if __name__ == "__main__":
    check_dates = ["2021-01-08", "2023-01-27", "2026-01-25"]

    for date in check_dates:
        fetch_koda_static(date)   # downloads if not already present
        check_route_607(date)