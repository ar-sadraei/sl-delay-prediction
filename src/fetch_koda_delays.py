from dotenv import load_dotenv
import os
import requests
import time
import py7zr

load_dotenv()
API_KEY = os.getenv("TRAFIKLAB_KODA_KEY")

date = "2024-08-01"

url = (f"https://api.koda.trafiklab.se/KoDa/api/v2/gtfs-rt/sl/TripUpdates"
       f"?date={date}&key={API_KEY}")

resp = requests.get(url)
while resp.status_code == 202:
    print("Archive still being generated, waiting 30s...")
    time.sleep(30)
    resp = requests.get(url)
resp.raise_for_status()

print("Content-Length header:", resp.headers.get("Content-Length"))
print("Actual bytes received:", len(resp.content))
print("Content-Type:", resp.headers.get("Content-Type"))

archive_path = f"data/raw/tripupdates_{date}.7z"
with open(archive_path, "wb") as f:
    f.write(resp.content)
print(f"Downloaded {len(resp.content)} bytes for {date}")

# extract it
extract_dir = f"data/raw/tripupdates_{date}/"
with py7zr.SevenZipFile(archive_path, mode="r") as z:
    z.extractall(path=extract_dir)
print(f"Extracted to {extract_dir}")