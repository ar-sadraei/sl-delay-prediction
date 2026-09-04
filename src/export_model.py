import pandas as pd
import joblib
import json
import os
from sklearn.ensemble import HistGradientBoostingClassifier

PROCESSED_DIR = "data/processed"

final = pd.read_parquet(f"{PROCESSED_DIR}/modeling_table_route607.parquet")
final_clean = final.dropna(subset=["is_delayed"]).copy()

# recompute imputation on the FULL dataset now -- there's no held-out test
# set left to protect from leakage, since this is the final deployed model
precip_median = final_clean["precip_mm"].median()
final_clean["precip_missing"] = final_clean["precip_mm"].isna().astype(int)
final_clean["precip_mm"] = final_clean["precip_mm"].fillna(precip_median)
final_clean["stop_id"] = final_clean["stop_id"].astype(str)

cat_features = ["weekday", "stop_id"]
num_features = ["hour", "temperature_c", "precip_mm", "precip_missing",
                 "is_rush_hour", "is_snow_proxy", "is_rain_proxy"]
all_features = cat_features + num_features

X = final_clean[all_features].copy()
X["weekday"] = X["weekday"].astype("category")
X["stop_id"] = X["stop_id"].astype("category")
y = final_clean["is_delayed"]

gbm = HistGradientBoostingClassifier(
    categorical_features=cat_features,
    class_weight="balanced",
    random_state=42,
)
gbm.fit(X, y)
print(f"Final model trained on {len(final_clean)} rows (full dataset, train+test combined).")

os.makedirs("api/artifacts", exist_ok=True)
joblib.dump(gbm, "api/artifacts/model.joblib")

# metadata the API needs to validate inputs and avoid silent extrapolation
metadata = {
    "features": all_features,
    "categorical_features": cat_features,
    "numeric_features": num_features,
    "precip_median": float(precip_median),
    "valid_stop_ids": sorted(final_clean["stop_id"].unique().tolist()),
    "valid_weekdays": sorted(final_clean["weekday"].unique().tolist()),
    "temperature_range": [float(final_clean["temperature_c"].min()), float(final_clean["temperature_c"].max())],
    "hour_range": [int(final_clean["hour"].min()), int(final_clean["hour"].max())],
    "training_rows": len(final_clean),
    "training_dates_count": final_clean["service_date"].nunique(),
}
with open("api/artifacts/metadata.json", "w") as f:
    json.dump(metadata, f, indent=2)

print("Saved api/artifacts/model.joblib and api/artifacts/metadata.json")