import pandas as pd
final = pd.read_parquet("data/processed/modeling_table_route607.parquet")
print(final["stop_id"].astype(str).nunique(), "unique stops in training data")

with open("api/artifacts/stop_metadata.json") as f:
    import json
    exported = json.load(f)
print(len(exported), "stops in exported metadata")

exported_ids = {s["stop_id"] for s in exported}
missing = set(final["stop_id"].astype(str).unique()) - exported_ids
print(f"{len(missing)} stop_ids in the model but missing from metadata:")
print(sorted(missing)[:10])