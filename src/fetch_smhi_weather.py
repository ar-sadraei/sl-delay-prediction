import requests
import pandas as pd

station = "98230"
parameter = "1"
period = "corrected-archive"

url = (f"https://opendata-download-metobs.smhi.se/api/version/latest"
       f"/parameter/{parameter}/station/{station}/period/{period}/data.csv")

resp = requests.get(url)
resp.raise_for_status()

with open("data/raw/smhi_temp_raw.csv", "wb") as f:
    f.write(resp.content)

print(f"Downloaded {len(resp.content)} bytes")

# Step 1: find which line number is the real header, don't hardcode a guess
with open("data/raw/smhi_temp_raw.csv", encoding="utf-8") as f:
    lines = f.readlines()

header_line_idx = next(i for i, line in enumerate(lines) if line.startswith("Datum;"))
print(f"Header found at line {header_line_idx}")

# Step 2: read from there, keep only the 4 columns that matter
df = pd.read_csv(
    "data/raw/smhi_temp_raw.csv",
    sep=";",
    skiprows=header_line_idx,
    usecols=[0, 1, 2, 3],
    names=["date", "time", "temperature_c", "quality"],
    header=0,
)

print(df.head())
print(df.dtypes)
print(len(df), "rows")

# Date and time into one proper datetime column
df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"])
print(df[["datetime", "temperature_c", "quality"]].head())
print(df["datetime"].min(), "to", df["datetime"].max())

# Save the cleaned version
df.to_csv("data/processed/smhi_temp_clean.csv", index=False)