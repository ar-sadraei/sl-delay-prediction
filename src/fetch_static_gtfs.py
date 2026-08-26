from dotenv import load_dotenv
import os
import requests
import zipfile
import pandas as pd

load_dotenv()
API_KEY = os.getenv("TRAFIKLAB_STATIC_KEY")

# --- download the static feed ---
url = f"https://opendata.samtrafiken.se/gtfs/sl/sl.zip?key={API_KEY}"
resp = requests.get(url)
resp.raise_for_status()

with open("data/raw/sl_static.zip", "wb") as f:
    f.write(resp.content)

# --- inspect what's inside ---

with zipfile.ZipFile("data/raw/sl_static.zip") as z:

    with z.open("trips.txt") as f:
        df = pd.read_csv(f)
        print(df.head())
        print(df.columns.tolist())
    