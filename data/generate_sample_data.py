"""
generate_sample_data.py

IMPORTANT: This creates a SYNTHETIC starter dataset, NOT real data.
It exists only so you can test the full pipeline (train -> API -> frontend)
immediately, without waiting on internet-dependent API calls.

Before you submit/demo your project, replace this with the REAL dataset
produced by fetch_landslide_data.py (run on a machine with internet access).

The values here are grounded in realistic ranges (rainfall thresholds that
typically trigger landslides in NER India are well documented, roughly
100mm+/24h or 200mm+/72h in steep terrain), but the individual event dates
are made up.
"""

import pandas as pd
import numpy as np

np.random.seed(42)

# Real locations in NER India (same places shown in the reference dashboard)
NER_LOCATIONS = [
    {"name": "Sohra (Cherrapunji), Meghalaya", "lat": 25.28, "lon": 91.72},
    {"name": "Aizawl, Mizoram", "lat": 23.73, "lon": 92.72},
    {"name": "Tupul, Manipur", "lat": 24.68, "lon": 93.83},
    {"name": "Khowai-Dhalai, Tripura", "lat": 24.06, "lon": 91.63},
    {"name": "Kohima, Nagaland", "lat": 25.67, "lon": 94.11},
    {"name": "Itanagar, Arunachal Pradesh", "lat": 27.10, "lon": 93.62},
    {"name": "Gangtok, Sikkim", "lat": 27.33, "lon": 88.61},
    {"name": "Guwahati, Assam", "lat": 26.14, "lon": 91.74},
]

rows = []
for loc in NER_LOCATIONS:
    for _ in range(40):  # 40 samples per location
        is_landslide = np.random.rand() < 0.35
        if is_landslide:
            rain_24h = np.random.normal(140, 30)
            rain_72h = rain_24h + np.random.normal(150, 40)
            rain_7d = rain_72h + np.random.normal(100, 50)
        else:
            rain_24h = np.random.normal(40, 25)
            rain_72h = rain_24h + np.random.normal(50, 30)
            rain_7d = rain_72h + np.random.normal(60, 40)

        rows.append({
            "lat": loc["lat"] + np.random.normal(0, 0.05),
            "lon": loc["lon"] + np.random.normal(0, 0.05),
            "location_name": loc["name"],
            "date": pd.Timestamp("2015-01-01") + pd.Timedelta(days=int(np.random.rand() * 3600)),
            "rain_24h": max(0, rain_24h),
            "rain_72h": max(0, rain_72h),
            "rain_7d": max(0, rain_7d),
            "is_ner": True,
            "label": int(is_landslide),
        })

df = pd.DataFrame(rows)
df.to_csv("landslide_training_data.csv", index=False)
print(f"Generated {len(df)} SYNTHETIC sample rows -> landslide_training_data.csv")
print(df["label"].value_counts())
print("\nReminder: replace this with real data from fetch_landslide_data.py before your final submission.")
