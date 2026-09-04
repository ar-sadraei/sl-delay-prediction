"""
api/main.py

FastAPI service exposing the route-607 delay prediction model.

IMPORTANT: the feature-engineering logic here (RUSH_HOURS, the snow/rain proxy rules) must exactly match src/build_dataset.py's add_features().
This duplication is a known, documented risk, see DECISIONS.md.
If either copy changes without the other, predictions will silently diverge from what the model was actually trained on ("training/serving skew").
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import joblib
import json
import pandas as pd

# --- must match src/build_dataset.py exactly ---
RUSH_HOURS = [7, 8, 9, 16, 17, 18]

app = FastAPI(title="Route 607 Delay Predictor", version="1.0")

model = joblib.load("api/artifacts/model.joblib")

with open("api/artifacts/metadata.json") as f:
    metadata = json.load(f)

with open("api/artifacts/stop_metadata.json") as f:
    stop_metadata = json.load(f)

VALID_STOP_IDS = set(metadata["valid_stop_ids"])
VALID_WEEKDAYS = set(metadata["valid_weekdays"])
TEMP_MIN, TEMP_MAX = metadata["temperature_range"]
HOUR_MIN, HOUR_MAX = metadata["hour_range"]
PRECIP_MEDIAN = metadata["precip_median"]
FEATURE_ORDER = metadata["features"]


class PredictRequest(BaseModel):
    stop_id: str = Field(..., description="A stop_id from GET /stops")
    weekday: str = Field(..., description="e.g. 'Monday'")
    hour: int = Field(..., ge=0, le=23)
    temperature_c: float
    precip_mm: Optional[float] = Field(
        None, description="Leave unset if unknown -- the model handles this explicitly"
    )


class PredictResponse(BaseModel):
    delay_probability: float
    is_delayed_prediction: bool
    warnings: list[str] = []


@app.get("/health")
def health():
    return {"status": "ok", "training_rows": metadata["training_rows"],
            "training_dates": metadata["training_dates_count"]}


@app.get("/stops")
def get_stops():
    """Stop metadata (id, name, direction) for populating a UI -- single
    source of truth so the frontend never has to hardcode this list."""
    return stop_metadata


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    warnings = []

    # --- validate inputs, don't let sklearn error on garbage silently ---
    if req.stop_id not in VALID_STOP_IDS:
        raise HTTPException(status_code=400, detail=f"Unknown stop_id: {req.stop_id}")
    if req.weekday not in VALID_WEEKDAYS:
        raise HTTPException(status_code=400, detail=f"weekday must be one of {sorted(VALID_WEEKDAYS)}")

    # out-of-range inputs are allowed but flagged -- the model CAN still
    # produce a number, but it's extrapolating outside what it was
    # trained on, and that should be visible to whoever's reading the
    # response, not silently hidden
    if not (TEMP_MIN <= req.temperature_c <= TEMP_MAX):
        warnings.append(
            f"temperature_c={req.temperature_c} is outside the training range "
            f"[{TEMP_MIN}, {TEMP_MAX}] -- prediction may be unreliable."
        )

    # --- derive engineered features, using the SAME rules as training ---
    is_rush_hour = int(req.hour in RUSH_HOURS)

    if req.precip_mm is None:
        precip_missing = 1
        precip_mm = PRECIP_MEDIAN
    else:
        precip_missing = 0
        precip_mm = req.precip_mm

    is_snow_proxy = int(precip_mm > 0 and req.temperature_c <= 0)
    is_rain_proxy = int(precip_mm > 0 and req.temperature_c > 0)

    row = pd.DataFrame([{
        "weekday": req.weekday,
        "stop_id": req.stop_id,
        "hour": req.hour,
        "temperature_c": req.temperature_c,
        "precip_mm": precip_mm,
        "precip_missing": precip_missing,
        "is_rush_hour": is_rush_hour,
        "is_snow_proxy": is_snow_proxy,
        "is_rain_proxy": is_rain_proxy,
    }])
    row["weekday"] = row["weekday"].astype("category")
    row["stop_id"] = row["stop_id"].astype("category")
    row = row[FEATURE_ORDER]  # enforce exact training column order

    proba = model.predict_proba(row)[0, 1]

    return PredictResponse(
        delay_probability=round(float(proba), 4),
        is_delayed_prediction=bool(proba > 0.5),
        warnings=warnings,
    )