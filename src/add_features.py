import pandas as pd

final = pd.read_parquet("data/processed/full_modeling_table_2024-08-01.parquet")

# time-based features
final["hour"] = final["scheduled_dt"].dt.hour
final["weekday"] = final["scheduled_dt"].dt.day_name()
final["is_rush_hour"] = final["hour"].isin([7, 8, 9, 16, 17, 18]).astype(int)

# target variables
DELAY_THRESHOLD_S = 180 # 3 min Delay
final["is_delayed"] = (final["delay_seconds"] > DELAY_THRESHOLD_S).astype(int)
final["delay_minutes"] = final["delay_seconds"] / 60

print(final[["scheduled_dt", "hour", "weekday", "is_rush_hour", "delay_seconds", "is_delayed", "delay_minutes"]].head(10))
print()
print("Share delayed:", final["is_delayed"].mean())
print("Rows by weekday:")
print(final["weekday"].value_counts())

final.to_parquet("data/processed/full_modeling_table_2024-08-01.parquet", index=False)
print("Saved.")