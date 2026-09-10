# 🚌 Route 607 Delay Predictor

Will my bus be late? This started as a simple question and turned into a full data science project: live transit data, real weather history, a model that actually ships, and an honest record of every wrong turn along the way.

**[Live prediction app →](https://sl-delay-prediction-meygurtasjc6fsysanpkhk.streamlit.app)**
**[Live API docs →](https://sl-delay-prediction.onrender.com/docs)**
**[Live system-wide dashboard →](https://datastudio.google.com/reporting/f05ed167-1118-40f2-bc73-e9e64b44df23)**

---

## The short version

I take route 607 from Sollentuna to university most winter mornings, and most winters that bus is unreliable in ways that feel predictable if you ride it enough. So I built a model that predicts, for a given stop, time, and weather, how likely that trip is to run more than 3 minutes late. It's deployed as a real API and a web app, not just a notebook. Alongside it, I built a system-wide analytics dashboard, fed by a pipeline that collects fresh data every single day without me touching it.

The final model is a gradient boosting classifier with a ROC-AUC of 0.705 on 11 fully held-out winter dates, trained on 240,665 real trip-stop observations across 54 winter service days between 2021 and 2026.

The biggest finding in the whole project, and one that got corrected and strengthened partway through after I found a real data quality bug, is that mode of transport dominates everything else. Metro trips run late 1.70% of the time. Buses, 24.4%. Ferries, 26.8%. That gap is far larger than anything weather or time of day did in this dataset.

---

## The actual story, because it matters more than the numbers

This project changed shape more than once, and every pivot came from a real finding or a real bug, not from a plan I wrote in advance.

**It started broad.** I ran an exploratory analysis of system-wide SL delays across 23 winter dates and found that weather roughly doubles delay, though it's confounded with the season and I say so plainly rather than overselling it. Rush hour barely moves the median delay but meaningfully worsens the tail. And mode of transport dominated everything, though the early version of that finding put metro at 2.1% delayed against 23.7% for everything else, a number I'd later have to revisit.

**Then I made it personal.** Once the metro versus bus gap made a system wide model feel like the wrong question (I don't ride the metro, and averaging across hundreds of routes I never take wasn't useful to me) I rebuilt the pipeline around my own route and scoped it to winter, since that's when the delays actually bother me.

**The first real model barely worked, until one question fixed it.** Weather and time of day alone got me a ROC-AUC of about 0.605, basically a coin flip with extra steps. Then I asked myself whether the data tracked delay at every stop along a trip, not just the trip as a whole. It turned out it did, and once I checked, I found a 16x spread in delay rate across the route's 52 stops. Adding stop_id as a feature pushed the ROC-AUC to 0.705.

**I also tried something that didn't work, and I kept it in the writeup anyway.** Predicting exactly how many minutes late a trip would be, given that it was already delayed, just didn't hold up. The model's error didn't beat simply guessing the average. Rather than force a falsely precise number into the app, I documented the failure and left it out.

**Finally, building a proper data pipeline exposed a bug in my own headline finding.** I wanted to demonstrate a real ELT workflow, so I built an automated pipeline and a BigQuery backed dashboard. While digging into it, I noticed something strange: a "metro" route on my dashboard included archipelago place names like Kvarnholmen and Fjäderholmarna, which have nothing to do with the subway. It turned out that route number "11" was shared by two completely unrelated GTFS routes from two different agencies, SL's actual metro Blue Line and a ferry operated by Waxholmsbolaget. My original classification had been silently blending ferry trips into the metro numbers since the very first analysis. I fixed it properly, with a real dimension table joined against every trip rather than a hardcoded list of route numbers, and it corrected years of historical data without needing to re-collect anything. The corrected number for metro delay, 1.70%, is actually lower than what I'd originally reported, because the misclassified ferry trips had been dragging it up the whole time.

Every real decision, bug, and dead end along the way, including a corrupted archive I only found by cross-checking three separate tools, a silent bug where unknown delays were defaulting to "on time," a training and serving mismatch that turned out to be a false alarm, and the route 11 mixup above, is written up in **[DECISIONS.md](DECISIONS.md)**.

---

## Architecture

**Personal commute prediction (Phases 1 through 5):**
```
Trafiklab (GTFS static + realtime)
KoDa (historical archives, 2021 to 2026)         ─► build_dataset.py ─► modeling_table_route607.parquet
SMHI (temperature + precipitation)                         │
                                                             ▼
                                              03_route607_modeling.ipynb
                                                             │
                                                             ▼
                            api/main.py (FastAPI)  ◄──  track_experiments.py (MLflow)
                                                             │
                                                             ▼
                            dashboard/app.py (Streamlit, calls the API over HTTP)
```

**System-wide automated pipeline and dashboard (Phase 7):**
```
GitHub Actions, scheduled daily at 06:00 UTC
        │
        ├─► daily_ingest.py            ► BigQuery: daily_all_routes (live, growing every day)
        │
        └─► backfill_route_types.py    ► BigQuery: trip_route_lookup (route_type, direction_id)
                                                             │
        historical_backfill (a 93 date, ────────────────────┤
        balanced, year round sample)                        ▼
                                          combined_delay_data (a view that unions both tables
                                          and joins in route_type to derive transport_mode,
                                          is_metro, punctuality_status, and season)
                                                             │
                                                             ▼
                    route_delay_summary, temp_delay_summary, stop_delay_summary
                                                             │
                                                             ▼
                                     Looker Studio, the live public dashboard
```

`combined_delay_data` and everything downstream of it are views, not tables that need rebuilding. They recompute on every query, so the dashboard reflects new data the moment the daily pipeline adds it.

---

## Tech stack

| Layer | Tools |
|---|---|
| Data ingestion | `requests`, GTFS realtime protobuf decoding, 7-zip extraction |
| Data engineering | `pandas`, per-date checkpointing at scale |
| Modeling | `scikit-learn` (LogisticRegression, HistGradientBoostingClassifier and Regressor) |
| Experiment tracking | `MLflow` |
| Serving | `FastAPI`, `Pydantic` |
| Frontend | `Streamlit` |
| Deployment | `Docker`, Render, Streamlit Community Cloud |
| Warehouse and ELT | `BigQuery` (dimension table pattern, views, scheduled enrichment) |
| Automation | `GitHub Actions` (a scheduled, self healing daily pipeline) |
| BI and analytics | `Looker Studio` |
| Data sources | [Trafiklab](https://www.trafiklab.se/) (GTFS Regional and KoDa), [SMHI](https://www.smhi.se/data/oppna-data) |

---

## Key results

**Personal model, route 607:**

| Model | ROC-AUC | Notes |
|---|---|---|
| Majority class baseline | (77.1% accuracy) | Always predict "not delayed" |
| Gradient boosting, weather and time only | 0.6052 | Nearly tied with logistic regression |
| **Gradient boosting with stop_id, shipped** | **0.7047** | stop_id is the dominant feature |
| Delay severity regression, minutes | Not shipped | A genuine negative result, documented rather than hidden |

**System-wide, corrected, from the live dashboard:**

| Mode | Delay rate |
|---|---|
| Metro | 1.70% |
| Tram | 4.8% |
| Commuter Rail | 10.66% |
| Bus | 24.38% |
| Ferry | 26.8% |

The full experiment history, including the negative result, lives in MLflow (`src/track_experiments.py`) and in BigQuery through `combined_delay_data`.

**Known limitations**, with the full list in DECISIONS.md:
- The personal model's coldest training band, below negative 10 Celsius, rests on only 5 independent days.
- In the 93 date system-wide sample, the extreme temperature bands are thin, just 5 dates below negative 10 and only 1 above 25 Celsius. Findings in the common range, roughly negative 10 to 25 Celsius, rest on much stronger evidence.
- As live daily collection keeps growing, the system-wide sample will slowly shift from being deliberately balanced across temperature bands toward being naturally weighted by how often those temperatures actually occur. That's an expected, documented evolution, not a flaw.

---

## Running it locally

**1. Set environment variables** in a gitignored `.env` file:
```
TRAFIKLAB_STATIC_KEY=...
TRAFIKLAB_REALTIME_KEY=...
TRAFIKLAB_KODA_KEY=...
```

**2. Rebuild the personal model's dataset**, optional since the trained model is already committed under `api/artifacts/`:
```bash
python src/build_dataset.py
```

**3. Run the API:**
```bash
uvicorn api.main:app --reload
```

**4. Run the dashboard:**
```bash
streamlit run dashboard/app.py
```

**5. Or run the API in Docker:**
```bash
docker build -t route607-api .
docker run -p 8000:8000 route607-api
```

**6. Run the system-wide pipeline**, which needs a GCP project and BigQuery dataset (setup notes are in DECISIONS.md):
```bash
python src/daily_ingest.py
python src/backfill_route_types.py
```
Both of these already run automatically every day through `.github/workflows/daily_ingest.yml`.

**7. Browse the experiment history:**
```bash
mlflow ui
```

---

## Data attribution

Public transport data comes from [Trafiklab](https://www.trafiklab.se/) (GTFS Regional Static and Realtime, plus the KoDa historical archives), sourced from Storstockholms Lokaltrafik and Waxholmsbolaget. Weather data comes from [SMHI](https://www.smhi.se/data/oppna-data) open data, which is CC0 licensed.

---

## Project history

**[DECISIONS.md](DECISIONS.md)** has the complete, honest log of every real decision, bug, and dead end across all seven phases of this project. It covers things like choosing a temperature parameter out of nine nearly identical SMHI options, a route number collision between a metro line and a ferry that quietly corrupted the project's headline finding for months, and why a training and serving mismatch I was worried about turned out to be nothing.
