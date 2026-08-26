from google.transit import gtfs_realtime_pb2
import glob

# grab any one file from the 03:00 hour folder to start
pb_files = glob.glob("data/raw/tripupdates_2024-08-01/sl/TripUpdates/2024/08/01/03/*.pb")
sample_file = pb_files[0]
print("Decoding:", sample_file)

feed = gtfs_realtime_pb2.FeedMessage()
with open(sample_file, "rb") as f:
    feed.ParseFromString(f.read())

count = 0
for entity in feed.entity:
    if entity.HasField("trip_update"):
        trip_id = entity.trip_update.trip.trip_id
        for stu in entity.trip_update.stop_time_update:
            stop_id = stu.stop_id
            delay_s = stu.arrival.delay if stu.HasField("arrival") else None
            print(trip_id, stop_id, delay_s)
            count += 1
            if count >= 10:  # just peek at the first 10 rows
                break
    if count >= 10:
        break