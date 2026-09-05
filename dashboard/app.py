"""
dashboard/app.py

Streamlit UI for the route-607 delay predictor. Deliberately does NOT
load the model directly -- it calls the FastAPI service over HTTP, the
same way any other consumer of the API would (a mobile app, another
team's tool, a script). This separation is what makes the model-serving
layer reusable rather than tied to one specific UI.
"""
import streamlit as st
import requests
import os

def get_api_url():
    try:
        return st.secrets["API_URL"]
    except (KeyError, FileNotFoundError):
        return os.getenv("API_URL", "http://127.0.0.1:8000")

API_URL = get_api_url()

st.set_page_config(page_title="Route 607 Delay Predictor", page_icon="🚌")
st.title("🚌 Will my 607 be delayed?")
st.caption("A model trained on 54 winter service days (2021-2026), route 607 Sollentuna.")
st.caption(
    "Note: the API runs on a free hosting tier and may take 20-30s to "
    "wake up on the first request after a period of inactivity."
)

# --- load stop list from the API, not a local copy -- single source of truth ---
@st.cache_data(ttl=3600)
def load_stops():
    resp = requests.get(f"{API_URL}/stops", timeout=10)
    resp.raise_for_status()
    return resp.json()

try:
    stops = load_stops()
except requests.exceptions.RequestException:
    st.error("Can't reach the prediction API. Is it running? (`uvicorn api.main:app`)")
    st.stop()

direction_labels = {0: "Direction A", 1: "Direction B"}
direction = st.radio("Direction", options=[0, 1], format_func=lambda d: direction_labels[d], horizontal=True)

stops_for_direction = [s for s in stops if s["direction_id"] == direction]
stop_names = [s["stop_name"] for s in stops_for_direction]
selected_name = st.selectbox("Stop", options=stop_names)
selected_stop = next(s for s in stops_for_direction if s["stop_name"] == selected_name)

col1, col2 = st.columns(2)
with col1:
    weekday = st.selectbox("Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
    hour = st.slider("Hour of day", 0, 23, 8)
with col2:
    temperature_c = st.slider("Temperature (°C)", -25, 30, 0)
    know_precip = st.checkbox("I know the precipitation amount", value=False)
    precip_mm = st.number_input("Precipitation (mm)", min_value=0.0, max_value=20.0, value=0.0, step=0.1) if know_precip else None

if st.button("Predict", type="primary"):
    payload = {
        "stop_id": selected_stop["stop_id"],
        "weekday": weekday,
        "hour": hour,
        "temperature_c": float(temperature_c),
        "precip_mm": precip_mm,
    }
    try:
        resp = requests.post(f"{API_URL}/predict", json=payload, timeout=10)
        if resp.status_code == 400:
            st.error(resp.json()["detail"])
        else:
            resp.raise_for_status()
            result = resp.json()

            proba = result["delay_probability"]
            st.metric("Estimated delay probability", f"{proba:.0%}")

            if result["is_delayed_prediction"]:
                st.warning("This trip is more likely delayed than not.")
            else:
                st.success("This trip is more likely on time.")

            for w in result["warnings"]:
                st.info(f"⚠️ {w}")
    except requests.exceptions.RequestException as e:
        st.error(f"Request to the API failed: {e}")

st.divider()
st.caption(
    "Model: gradient boosting classifier, ROC-AUC ~0.70 on held-out winter dates. "
    "stop_id is the strongest predictor, ahead of hour and day of week; weather "
    "contributes modestly. See the project's DECISIONS.md for full methodology."
)