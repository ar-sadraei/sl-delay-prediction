import pandas as pd
import numpy as np

weather = pd.read_csv("data/processed/smhi_weather_clean.csv", parse_dates=["datetime"])
daily_mean = weather.groupby(weather["datetime"].dt.date)["temperature_c"].mean()
daily_mean.index = pd.to_datetime(daily_mean.index)

candidates = daily_mean[
    (daily_mean.index >= "2021-01-01") &
    (daily_mean.index <= "2026-02-28") &
    (daily_mean.index.month.isin([11, 12, 1, 2, 3]))
]

def is_holiday_period(date):
    month, day = date.month, date.day
    return (month == 12 and day >= 21) or (month == 1 and day <= 7)

candidates = candidates[~candidates.index.map(is_holiday_period)]

bands = {
    "(-15,-10]": (candidates[(candidates > -15) & (candidates <= -10)], 9),   # take all available
    "(-10,-5]":  (candidates[(candidates > -10) & (candidates <= -5)], 15),
    "(-5,0]":    (candidates[(candidates > -5) & (candidates <= 0)], 15),
    "(0,5]":     (candidates[(candidates > 0) & (candidates <= 5)], 15),
    "(5,10]":    (candidates[(candidates > 5) & (candidates <= 10)], 10),
}

rng = np.random.default_rng(seed=42)  # fixed seed = reproducible selection, not re-random each run
selected_dates = []

for band_name, (pool, target_n) in bands.items():
    n = min(target_n, len(pool))
    # sample spread across different years by sorting and taking evenly-spaced picks
    # rather than pure random, which could accidentally cluster in one winter
    pool_sorted = pool.sort_index()
    if n >= len(pool_sorted):
        picked = pool_sorted
    else:
        idx = np.linspace(0, len(pool_sorted) - 1, n).astype(int)
        picked = pool_sorted.iloc[idx]
    selected_dates.extend(picked.index.strftime("%Y-%m-%d").tolist())
    print(f"{band_name}: picked {len(picked)} of {len(pool_sorted)} available")

selected_dates = sorted(set(selected_dates))
print(f"\nTotal selected: {len(selected_dates)} dates")
print(f"Candidates after excluding holiday period: {len(candidates)}")

# sanity check: weekday/weekend mix
selected_dt = pd.to_datetime(selected_dates)
print("\nWeekday distribution:")
print(selected_dt.day_name().value_counts())

print("\nYear distribution:")
print(selected_dt.year.value_counts().sort_index())

print("\nFull list:")
for d in selected_dates:
    print(d)