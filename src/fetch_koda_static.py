from dotenv import load_dotenv
import os
import requests
import time
import zipfile

load_dotenv()
API_KEY = os.getenv("TRAFIKLAB_KODA_KEY")

date = "2024-08-01"

static_url = (f"https://api.koda.trafiklab.se/KoDa/api/v2/gtfs-static/sl"
              f"?date={date}&key={API_KEY}")

resp = requests.get(static_url, timeout=60, stream=True)
while resp.status_code == 202:
    print("Archive still being generated, waiting 30s...")
    time.sleep(30)
    resp = requests.get(static_url, timeout=60, stream=True)

resp.raise_for_status()
total = int(resp.headers.get("Content-Length", 0))
print(f"Status: {resp.status_code} | Expected size: {total / 1_000_000:.1f} MB")

out_path = f"data/raw/static_{date}.bin"
downloaded = 0
with open(out_path, "wb") as f:
    for chunk in resp.iter_content(chunk_size=1_000_000):  # 1 MB at a time
        f.write(chunk)
        downloaded += len(chunk)
        print(f"  {downloaded / 1_000_000:.1f} / {total / 1_000_000:.1f} MB", end="\r")

print(f"\nDone. Downloaded {downloaded} bytes to {out_path}")


with zipfile.ZipFile("data/raw/static_2024-08-01.bin") as z:
    print(z.namelist())