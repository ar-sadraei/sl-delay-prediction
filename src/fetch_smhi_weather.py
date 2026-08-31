import requests
import pandas as pd

STATION = "98230"
PERIOD = "corrected-archive"


def fetch_smhi_parameter(parameter, label):
    """
    Download one SMHI parameter for STATION/PERIOD, find the real header row
    programmatically (SMHI's metadata header length isn't guaranteed stable),
    keep only the 4 real data columns, and return a clean datetime-indexed
    DataFrame with the value column named `label`.
    """
    url = (f"https://opendata-download-metobs.smhi.se/api/version/latest"
           f"/parameter/{parameter}/station/{STATION}/period/{PERIOD}/data.csv")

    resp = requests.get(url)
    resp.raise_for_status()

    raw_path = f"data/raw/smhi_{label}_raw.csv"
    with open(raw_path, "wb") as f:
        f.write(resp.content)
    print(f"Downloaded {label}: {len(resp.content)} bytes")

    with open(raw_path, encoding="utf-8") as f:
        lines = f.readlines()
    header_line_idx = next(i for i, line in enumerate(lines) if line.startswith("Datum;"))

    df = pd.read_csv(
        raw_path,
        sep=";",
        skiprows=header_line_idx,
        usecols=[0, 1, 2, 3],
        names=["date", "time", label, "quality"],
        header=0,
    )
    df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"])
    df = df[["datetime", label, "quality"]].rename(columns={"quality": f"{label}_quality"})

    print(f"  {len(df)} rows, {df['datetime'].min()} to {df['datetime'].max()}")
    return df


if __name__ == "__main__":
    # parameter 1: Lufttemperatur, momentanvärde, 1 gång/tim
    temp = fetch_smhi_parameter("1", "temperature_c")

    # parameter 7: Nederbördsmängd, summa 1 timme, 1 gång/tim
    precip = fetch_smhi_parameter("7", "precip_mm")

    # outer join: temperature and precipitation can have different gaps in
    # their hourly records (already confirmed real missing hours exist in
    # the temperature series) — an outer join keeps every hour either
    # source has data for, rather than silently dropping rows
    weather = temp.merge(precip, on="datetime", how="outer")

    # rain/snow proxy: SMHI's precipitation field is just an amount, it
    # doesn't distinguish rain from snow directly — this is a standard,
    # reasonable derived approximation (precip + temp <= 0C ~= snow),
    # not a directly-measured field, worth noting as such in DECISIONS.md
    weather["is_snow_proxy"] = ((weather["precip_mm"] > 0) & (weather["temperature_c"] <= 0)).astype(int)
    weather["is_rain_proxy"] = ((weather["precip_mm"] > 0) & (weather["temperature_c"] > 0)).astype(int)

    weather = weather.sort_values("datetime").reset_index(drop=True)
    print(f"\nCombined: {weather.shape}")
    print(weather.head())

    weather.to_csv("data/processed/smhi_weather_clean.csv", index=False)
    print("Saved data/processed/smhi_weather_clean.csv")