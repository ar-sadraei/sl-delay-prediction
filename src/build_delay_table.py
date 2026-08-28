from google.transit import gtfs_realtime_pb2
import glob
import pandas as pd

pb_files = glob.glob(
    "data/raw/tripupdates_2024-08-01/sl/TripUpdates/2024/08/01/**/*.pb",
    recursive=True
)
print(f"Found {len(pb_files)} snapshot files")

latest = {}  # (trip_id, stop_id) -> {"delay_seconds": ..., "snapshot_time": ...}

for i, pb_file in enumerate(pb_files):
    feed = gtfs_realtime_pb2.FeedMessage()
    with open(pb_file, "rb") as f:
        feed.ParseFromString(f.read())

    snapshot_time = feed.header.timestamp

    for entity in feed.entity:
        if entity.HasField("trip_update"):
            trip_id = entity.trip_update.trip.trip_id
            for stu in entity.trip_update.stop_time_update:
                stop_id = stu.stop_id
                delay_s = stu.arrival.delay if stu.HasField("arrival") else None
                key = (trip_id, stop_id)

                if key not in latest or snapshot_time > latest[key]["snapshot_time"]:
                    latest[key] = {"delay_seconds": delay_s, "snapshot_time": snapshot_time}

    if i % 500 == 0:
        print(f"Processed {i}/{len(pb_files)} files, {len(latest)} unique trip-stops so far")

print(f"Done. {len(latest)} unique (trip_id, stop_id) pairs")



rows = [
    {"trip_id": trip_id, "stop_id": stop_id, **info}
    for (trip_id, stop_id), info in latest.items()
]
final_delays = pd.DataFrame(rows)
print(final_delays.head())
print(len(final_delays), "rows")

final_delays.to_parquet("data/processed/final_delays_2024-08-01.parquet", index=False)
print("Saved checkpoint.")