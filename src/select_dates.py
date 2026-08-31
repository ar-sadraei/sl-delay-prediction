import pandas as pd
import numpy as np


def is_holiday_period(date):
    month, day = date.month, date.day
    return (month == 12 and day >= 21) or (month == 1 and day <= 7)


def select_dates(weather_path="data/processed/smhi_weather_clean.csv", seed=42):
    weather = pd.read_csv(weather_path, parse_dates=["datetime"])
    daily_mean = weather.groupby(weather["datetime"].dt.date)["temperature_c"].mean()
    daily_mean.index = pd.to_datetime(daily_mean.index)

    candidates = daily_mean[
        (daily_mean.index >= "2021-01-01") &
        (daily_mean.index <= "2026-02-28") &
        (daily_mean.index.month.isin([11, 12, 1, 2, 3]))
    ]
    candidates = candidates[~candidates.index.map(is_holiday_period)]

    bands = {
        "(-15,-10]": (candidates[(candidates > -15) & (candidates <= -10)], 9),
        "(-10,-5]":  (candidates[(candidates > -10) & (candidates <= -5)], 15),
        "(-5,0]":    (candidates[(candidates > -5) & (candidates <= 0)], 15),
        "(0,5]":     (candidates[(candidates > 0) & (candidates <= 5)], 15),
        "(5,10]":    (candidates[(candidates > 5) & (candidates <= 10)], 10),
    }

    selected_dates = []
    for pool, target_n in bands.values():
        pool_sorted = pool.sort_index()
        n = min(target_n, len(pool_sorted))
        if n >= len(pool_sorted):
            picked = pool_sorted
        else:
            idx = np.linspace(0, len(pool_sorted) - 1, n).astype(int)
            picked = pool_sorted.iloc[idx]
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