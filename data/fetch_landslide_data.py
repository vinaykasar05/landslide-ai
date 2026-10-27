"""
fetch_landslide_data.py

Downloads REAL historical landslide records (NASA Global Landslide Catalog)
and enriches them with REAL historical rainfall data (NASA POWER API).

Run this on your own laptop / Google Colab (needs internet access).
Output: data/landslide_training_data.csv  -> used by model/train_model.py

Usage:
    python fetch_landslide_data.py
"""

import pandas as pd
import requests
import time
import random
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# STEP 1: Download the NASA Global Landslide Catalog (real data, ~11,000+
# rainfall-triggered landslide events worldwide, 2007-2016).
# Source: https://catalog.data.gov/dataset/global-landslide-catalog-export
#
# NOTE (2026-10-22): the old Socrata API URL (data.nasa.gov/api/views/...)
# started returning 404 - NASA restructured data.nasa.gov and moved this
# dataset's export to a static legacy path instead. Confirmed working by
# directly downloading it (8.1MB CSV) before updating this URL - not assumed.
# ---------------------------------------------------------------------------
GLC_URL = "https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv"

def download_glc():
    print("Downloading NASA Global Landslide Catalog...")
    df = pd.read_csv(GLC_URL)
    print(f"Downloaded {len(df)} total landslide records worldwide.")
    return df


def filter_india_ner(df):
    """Keep India records; flag North-Eastern Region states specifically."""
    ner_states = [
        "Assam", "Meghalaya", "Manipur", "Mizoram",
        "Nagaland", "Tripura", "Arunachal Pradesh", "Sikkim"
    ]
    india_df = df[df["country_name"].str.contains("India", na=False)].copy()
    print(f"India records: {len(india_df)}")

    def is_ner(row):
        text = f"{row.get('admin_division_name', '')} {row.get('location_description', '')}"
        return any(state.lower() in str(text).lower() for state in ner_states)

    india_df["is_ner"] = india_df.apply(is_ner, axis=1)
    print(f"Of which NER-tagged: {india_df['is_ner'].sum()}")
    return india_df


# ---------------------------------------------------------------------------
# STEP 2: For each event, pull REAL historical rainfall from NASA POWER API
# (free, no API key required, daily data since 1981, any lat/lon on Earth).
# Docs: https://power.larc.nasa.gov/docs/services/api/
# ---------------------------------------------------------------------------
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

def get_rainfall(lat, lon, event_date, days_back=7):
    """Return cumulative rainfall (mm) for the `days_back` days before event_date.

    event_date may be a plain "YYYY-MM-DD" string (used by the negative-example
    generator) OR a real-world date string straight out of the NASA GLC export,
    which can show up in several different formats (e.g. "3/15/2010 12:00:00 AM",
    with a time component, etc). pd.to_datetime() handles all of those; the old
    strict datetime.strptime(..., "%Y-%m-%d") silently failed on every single
    real GLC date, which is why the last run produced zero positive examples.
    """
    try:
        end = pd.to_datetime(event_date, errors="raise")
    except Exception as e:
        print(f"  date parse failed for event_date={event_date!r}: {e}")
        return None
    start = end - timedelta(days=days_back)

    params = {
        "parameters": "PRECTOTCORR",   # corrected precipitation, mm/day
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    try:
        r = requests.get(POWER_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        daily = data["properties"]["parameter"]["PRECTOTCORR"]
        values = [v for v in daily.values() if v not in (-999, None)]
        return {
            "rain_24h": values[-1] if values else 0,
            "rain_72h": sum(values[-3:]) if len(values) >= 3 else sum(values),
            "rain_7d": sum(values),
        }
    except Exception as e:
        print(f"  rainfall fetch failed for ({lat},{lon}) on {event_date}: {e}")
        return None


def build_positive_examples(india_df):
    """Landslide events = label 1."""
    rows = []
    for _, r in india_df.iterrows():
        lat, lon = r.get("latitude"), r.get("longitude")
        raw_date = r.get("event_date", "")
        date = str(raw_date) if pd.notna(raw_date) else ""
        if pd.isna(lat) or pd.isna(lon) or not date:
            print(f"  skipped row (missing lat/lon/date): lat={lat}, lon={lon}, event_date={raw_date!r}")
            continue
        rain = get_rainfall(lat, lon, date)
        time.sleep(0.3)  # be polite to the free API
        if rain is None:
            continue
        rows.append({
            "lat": lat, "lon": lon, "date": date,
            "rain_24h": rain["rain_24h"], "rain_72h": rain["rain_72h"], "rain_7d": rain["rain_7d"],
            "is_ner": r.get("is_ner", False),
            "label": 1,
        })
        print(f"  + positive example: {date} ({lat:.2f},{lon:.2f})")
    return rows


def build_negative_examples(india_df, n=None):
    """Same locations, random NON-landslide dates = label 0."""
    # NOTE: "n or len(india_df)" used to silently treat n=0 (e.g. zero positive
    # examples found) as "not given" and build negatives for the whole dataset
    # instead. Use "is None" so a real n=0 stays 0.
    n = len(india_df) if n is None else n
    rows = []
    locations = india_df[["latitude", "longitude", "is_ner"]].dropna().drop_duplicates()
    for _, loc in locations.sample(min(n, len(locations)), random_state=42).iterrows():
        random_date = datetime(2015, 1, 1) + timedelta(days=random.randint(0, 3000))
        date_str = random_date.strftime("%Y-%m-%d")
        rain = get_rainfall(loc["latitude"], loc["longitude"], date_str)
        time.sleep(0.3)
        if rain is None:
            continue
        rows.append({
            "lat": loc["latitude"], "lon": loc["longitude"], "date": date_str,
            "rain_24h": rain["rain_24h"], "rain_72h": rain["rain_72h"], "rain_7d": rain["rain_7d"],
            "is_ner": loc["is_ner"],
            "label": 0,
        })
        print(f"  - negative example: {date_str} ({loc['latitude']:.2f},{loc['longitude']:.2f})")
    return rows


if __name__ == "__main__":
    glc = download_glc()
    india = filter_india_ner(glc)

    if len(india) < 20:
        print("\nNOTE: NASA GLC has limited India-specific records (it's global and "
              "media-report-based). Consider ALSO checking GSI Bhukosh "
              "(https://bhukosh.gsi.gov.in) for a India-specific landslide inventory, "
              "and merging it in with the same lat/lon/date structure.\n")

    print("\nBuilding positive examples (real landslide events + real rainfall)...")
    pos = build_positive_examples(india)

    if len(pos) == 0:
        print("\nERROR: zero positive examples were built - stopping before writing a "
              "useless file. Check the 'date parse failed' / 'skipped row' messages "
              "above to see why every real landslide event was rejected.")
        raise SystemExit(1)

    print(f"\n{len(pos)} positive examples built.")
    print("\nBuilding negative examples (same regions, random non-landslide dates)...")
    neg = build_negative_examples(india, n=len(pos))

    final = pd.DataFrame(pos + neg)
    final.to_csv("landslide_training_data.csv", index=False)
    print(f"\nSaved {len(final)} rows to landslide_training_data.csv")
    print(final["label"].value_counts())