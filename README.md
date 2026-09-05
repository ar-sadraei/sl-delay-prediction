# 🚌 Route 607 Delay Predictor

Will my bus be late? A real, end-to-end data science project that started as “predict SL delays” and ended up somewhere more specific, more personal, and more honest than that original framing — built on live transit data, real weather history, and a deliberately documented trail of the mistakes, dead ends, and rescopes along the way.

[**Live demo →**](https://sl-delay-prediction-meygurtasjc6fsysanpkhk.streamlit.app)
[**Full API docs →**](https://sl-delay-prediction.onrender.com/docs)

---

## The short version

I take route 607 (Sollentuna, Stockholm) to university most winter mornings. This project builds a model that predicts, for a given stop/time/weather, how likely that trip is to run more than 3 minutes late, and it’s wired into an actual API + web app, not just a notebook.

**Final model**: gradient boosting classifier, ROC-AUC **0.705** on 11 fully held-out winter dates, trained on 240,665 real trip-stop observations across 54 winter service days (2021–2026).

**The single strongest finding**: *where* the bus is matters far more than *when* or *what the weather’s doing*. Delay rate varies from 3% to 49% across route 607’s 52 stops, a bigger effect than weather, time of day, or day of week combined.

---

## The actual story

This project changed shape three times, and each pivot was driven by a real finding, not a plan made in advance:

1. **Started broad**: system-wide SL delay EDA across 23 winter dates. Found that weather roughly doubles delay (confounded with season, documented honestly), rush hour barely moves the *median* delay but meaningfully worsens the *tail* (25% severely delayed vs 18% off-peak), and, the big one → **mode of transport dominates everything**: metro trips run 2.1% delayed vs. 23.7% for buses, an ~11x gap.
2. **Pivoted to my own commute** (route 607) once that metro/bus finding made a system-wide model feel like the wrong question — I don’t ride the metro, and averaging across 561 routes I never take wasn’t actually useful to me. Rebuilt the pipeline to filter by route, rescoped to winter specifically (motivated by the weather finding), and pulled a fresh, deliberately balanced 54-date sample across the full Stockholm winter temperature range (-14.2°C to 14.6°C).
3. **A model that barely worked, until one question fixed it.** The first real model (weather + time-of-day features) landed at ROC-AUC ~0.605 — barely better than chance. Then I asked: *“don’t we follow delays between individual stops, not just the whole trip?”* Turned out yes, the data already tracked delay per stop and a quick check showed a **16x delay-rate spread across the route’s 52 stops**. Adding `stop_id` as a feature pushed ROC-AUC to 0.705 and made it the dominant predictor by a wide margin. That single question was worth more than any hyperparameter tuning would have been.
4. **A negative result, kept and reported.** I also tried predicting *how many minutes* late a trip would be, given that it’s already delayed. It didn’t work — the model’s error (1.82 min) didn’t beat just guessing the average (1.79 min). Rather than force a fake-precise number into the app, that experiment is documented and *not* shipped. It’s logged in MLflow alongside the models that did work.

Every real decision, bug, and dead end along the way, including a corrupted archive discovered by cross-checking three independent tools, a silent mislabeling bug where “unknown delay” was defaulting to “on time,” and a training/serving-skew investigation that turned out to be a false alarm is documented in [**DECISIONS.md**](DECISIONS.md).

---

## Architecture

```
Trafiklab (GTFS static + realtime)  ─┐
KoDa (historical archives, 2021-26) ─┼─► build_dataset.py ─► modeling_table_route607.parquet
SMHI (temperature + precipitation)  ─┘         │
                                                ▼
                                    03_route607_modeling.ipynb
                                    (EDA → baselines → LR → GBM →
                                     +stop_id → severity regression)
                                                │
                                                ▼
                                    export_model.py / export_stop_metadata.py
                                                │
                                                ▼
                              api/main.py (FastAPI)  ◄──  track_experiments.py (MLflow)
                                                │
                                                ▼
                              dashboard/app.py (Streamlit, calls the API over HTTP)
```

The API and UI are deliberately separate services the Streamlit app never loads the model directly, it calls the FastAPI service the same way any other client would. This is the actual pattern used in production ML systems: the model-serving layer is a reusable service, not glued to one specific frontend.

---

## Tech stack

| Layer | Tools |
| --- | --- |
| Data ingestion | `requests`, GTFS-realtime protobuf decoding, 7-zip extraction |
| Data engineering | `pandas`, per-date checkpointing to manage disk footprint at scale |
| Modeling | `scikit-learn` (LogisticRegression, HistGradientBoostingClassifier/Regressor) |
| Experiment tracking | `MLflow` |
| Serving | `FastAPI`, `Pydantic` for input validation |
| Frontend | `Streamlit` |
| Deployment | `Docker` |
| Data sources | [Trafiklab](https://www.trafiklab.se/) (GTFS Regional + KoDa), [SMHI](https://www.smhi.se/data/oppna-data) |

---

## Key results

| Model | ROC-AUC | Notes |
| --- | --- | --- |
| Majority-class baseline | (77.1% accuracy) | Always predict “not delayed” |
| Logistic regression (weather + time only) | 0.6065 |  |
| Gradient boosting (weather + time only) | 0.6052 | Near-tie with LR — added complexity didn’t help yet |
| **Gradient boosting + stop_id (shipped)** | **0.7047** | stop_id is the dominant feature (permutation importance 0.065, vs. 0.026 for hour) |
| Delay-severity regression (minutes, given delayed) | Not shipped | MAE 1.82 vs. 1.79 naive baseline — genuine negative result |

Full experiment history, including the negative result, is tracked in MLflow (`src/track_experiments.py`).

**Known limitations** (see DECISIONS.md for the complete list):

- Only 54 dates total; the coldest band (below -10°C) has just 5 independent days — extreme-cold predictions rest on thin evidence.
- Route 607’s stability across 2021–2026 was checked (route_id and stop count identical) but trip frequency has drifted slightly.
- The weather/delay association from the original 23-date EDA is confounded with season (winter vs. summer dates never overlap in temperature) a real association, not a proven causal weather effect.

---

## Running it locally

**1. Set up environment variables** (`.env`, gitignored):

```
TRAFIKLAB_STATIC_KEY=...
TRAFIKLAB_REALTIME_KEY=...
TRAFIKLAB_KODA_KEY=...
```

**2. Rebuild the dataset** (optional — the trained model is already committed under `api/artifacts/`):

```bash
python src/build_dataset.py
```

**3. Run the API:**

```bash
uvicorn api.main:app --reload
```

Interactive docs at `http://127.0.0.1:8000/docs`.

**4. Run the dashboard** (with the API already running):

```bash
streamlit run dashboard/app.py
```

**5. Or run the API in Docker:**

```bash
docker build -t route607-api .
docker run -p 8000:8000 route607-api
```

**6. Browse experiment history:**

```bash
mlflow ui
```

---

## Data attribution

Public transport data from [Trafiklab](https://www.trafiklab.se/) (GTFS Regional Static/Realtime, KoDa historical archives), sourced from Storstockholms Lokaltrafik (SL). Weather data from [SMHI](https://www.smhi.se/data/oppna-data) open data, CC0-licensed.

---

## Project history

See [**DECISIONS.md**](DECISIONS.md) for the complete, honest log of every real decision, bug, and dead end across all five phases from choosing a temperature parameter out of nine near-identical SMHI options, to a corrupted archive found by cross-checking three independent 7z implementations, to why a training/serving-skew investigation turned out to be a false alarm.