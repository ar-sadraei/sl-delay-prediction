import pandas as pd
import numpy as np


def is_holiday_period(date):
    month, day = date.month, date.day
    return (month == 12 and day >= 21) or (month == 1 and day <= 7)


def select_dates(weather_path="data/processed/smhi_weather_clean.csv", seed=42,
                  bands=None, month_filter=None, date_range=("2021-01-01", "2026-08-31")):
    weather = pd.read_csv(weather_path, parse_dates=["datetime"])
    daily_mean = weather.groupby(weather["datetime"].dt.date)["temperature_c"].mean()
    daily_mean.index = pd.to_datetime(daily_mean.index)

    candidates = daily_mean[
        (daily_mean.index >= date_range[0]) &
        (daily_mean.index <= date_range[1])
    ]
    if month_filter:
        candidates = candidates[candidates.index.month.isin(month_filter)]
    candidates = candidates[~candidates.index.map(is_holiday_period)]

    if bands is None:
        # original winter-only default, unchanged behavior for existing callers
        bands = {
            "(-15,-10]": (-15, -10, 9),
            "(-10,-5]": (-10, -5, 15),
            "(-5,0]": (-5, 0, 15),
            "(0,5]": (0, 5, 15),
            "(5,10]": (5, 10, 10),
        }

    selected_dates = []
    for low, high, target_n in bands.values():
        pool = candidates[(candidates > low) & (candidates <= high)].sort_index()
        n = min(target_n, len(pool))
        if n >= len(pool):
            picked = pool
        else:
            idx = np.linspace(0, len(pool) - 1, n).astype(int)
            picked = pool.iloc[idx]
        selected_dates.extend(picked.index.strftime("%Y-%m-%d").tolist())

    return sorted(set(selected_dates))


if __name__ == "__main__":
    dates = select_dates()
    dt = pd.to_datetime(dates)
    print(f"Total selected: {len(dates)} dates")
    print("\nWeekday distribution:")
    print(dt.day_name().value_counts())
    print("\nYear distribution:")
    print(dt.year.value_counts().sort_index())
    print("\nFull list:")
    for d in dates:
        print(d)