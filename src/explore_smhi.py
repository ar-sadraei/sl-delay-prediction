import requests

# uncomment to explore the keys
""" resp = requests.get("https://opendata-download-metobs.smhi.se/api.json")
resp.raise_for_status()
data = resp.json()

print(data.keys()) """

resp2 = requests.get("https://opendata-download-metobs.smhi.se/api/version/latest.json")
resp2.raise_for_status()
version_data = resp2.json()

""" for item in version_data["resource"]:
    if "temperatur" in item["title"].lower():
        print(item["key"], "-", item["title"], "-", item.get("summary", "")) """

""" # checking for key datatype
for item in version_data["resource"]:
    if "temperatur" in item["title"].lower():
        print(type(item["key"]), item["key"], "-", item.get("summary", "")) """

""" # Exploring the key value
for item in version_data["resource"]:
    if str(item["key"]) == "1" and "momentanvärde, 1 gång/tim" in item.get("summary", ""):
        print(item) """

param_url = "https://opendata-download-metobs.smhi.se/api/version/latest/parameter/1.json"

resp3 = requests.get(param_url)
resp3.raise_for_status()
param_data = resp3.json()

# print(param_data.keys())
""" # Finding the suitable station near the city center:
for s in param_data["station"]:
    if "stockholm" in s["name"].lower():
        print(s["key"], "-", s["name"]) """

""" # look for the differences between two stations
for station_key in ["98210", "98230"]:
    resp4 = requests.get(f"https://opendata-download-metobs.smhi.se/api/version/latest/parameter/1/station/{station_key}.json")
    resp4.raise_for_status()
    station_data = resp4.json()
    print(f"--- Station {station_key} ---")
    for p in station_data.get("period", []):
        print(" ", p["key"], "-", p.get("title", ""), "-", p.get("summary", "")) """