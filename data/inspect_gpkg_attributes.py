"""
inspect_gpkg_attributes.py - Phase 2b: TARGETED ATTRIBUTE inspection of
data/raw/India_dataset.gpkg, geometry disabled.

Run this on YOUR machine (same reason as inspect_gpkg.py - this environment
has no access to your local file). This script makes NO assumptions about
what fields named y / SI / lsd / su / ID mean - it only reports what the
actual values show. Any interpretation of meaning happens afterward, by a
human (or by Claude) reading this script's OUTPUT, never inside the script.

Scope: only the 6 layers named below (not all 7 layers in the file) -
read as attribute tables only, geometry fully disabled via
pyogrio.read_dataframe(..., read_geometry=False), so the ~124,553 geometries
are never loaded into memory. Geographic extent still comes from
pyogrio.read_info() metadata (fast, no geometry load required for that).

Output:
  data/ml_attribute_audit.json  (machine-readable)
  data/ml_attribute_report.md   (human-readable)

Install (same as Phase 2):
    pip install -r requirements-geo.txt
"""

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

GPKG_PATH = Path(__file__).parent / "raw" / "India_dataset.gpkg"
AUDIT_JSON_PATH = Path(__file__).parent / "ml_attribute_audit.json"
REPORT_MD_PATH = Path(__file__).parent / "ml_attribute_report.md"

# Exactly the 6 layers requested. Matching is case/whitespace-insensitive
# against the GeoPackage's real layer names (which may differ slightly in
# casing or use underscores) - the script reports exactly which real layer
# name it matched to each requested name, or says "NOT FOUND" rather than
# guessing.
REQUESTED_LAYERS = [
    "fit lr",
    "fit woe",
    "lr crossvalidation",
    "SUcovariate3857lr_final",
    "SUcovariate3857woe_final",
    "woe crossvalidation",
]

# Fields requiring full statistical treatment (min/max/mean/unique/value_counts/missing%).
# Matched case-insensitively, EXACT name match only (not substring) - "y" must not
# accidentally match a column called "year" or "density", for example.
SPECIAL_FIELDS = ["y", "si", "lsd", "su", "id"]

# Substrings used only to FIND candidate location/date/id columns across ALL fields -
# never used to assume meaning, only to flag "this column name suggests X, verify its values".
CONTEXT_HINTS = {
    "state": ["state", "st_nm", "st_name"],
    "district": ["district", "dist", "distt"],
    "location": ["location", "place", "name"],
    "latitude": ["lat", "latitude", "y_coord", "ycoord"],
    "longitude": ["lon", "lng", "longitude", "x_coord", "xcoord"],
    "date": ["date"],
    "year": ["year", "yr"],
    "landslide_id": ["landslide", "ls_id", "event_id", "slide"],
}


def normalize(name: str) -> str:
    return name.strip().lower().replace("_", "").replace(" ", "")


def fail(section: str, exc: Exception) -> dict:
    return {
        "status": "FAILED", "section": section,
        "error_type": type(exc).__name__, "error_message": str(exc),
        "traceback": traceback.format_exc(),
    }


def main():
    audit = {
        "inspected_at": datetime.now(timezone.utc).isoformat(),
        "file_path": str(GPKG_PATH),
        "file_exists": GPKG_PATH.exists(),
        "scope_note": "Attribute-only inspection (geometry disabled) of the 6 requested layers only.",
    }

    if not GPKG_PATH.exists():
        audit["fatal_error"] = f"File not found at {GPKG_PATH}"
        _write_outputs(audit)
        print(f"FATAL: file not found at {GPKG_PATH}")
        sys.exit(1)

    try:
        import pyogrio
    except ImportError as e:
        audit["fatal_error"] = f"Required package not installed: {e}. Run: pip install -r requirements-geo.txt"
        _write_outputs(audit)
        print(f"FATAL: {audit['fatal_error']}")
        sys.exit(1)

    try:
        all_layers = [row[0] for row in pyogrio.list_layers(str(GPKG_PATH))]
    except Exception as e:
        audit["layer_listing"] = fail("list_layers", e)
        _write_outputs(audit)
        print("FATAL: could not list layers")
        sys.exit(1)

    audit["all_layers_in_file"] = all_layers
    audit["requested_layers"] = REQUESTED_LAYERS

    # Match requested names to real layer names (case/whitespace/underscore-insensitive)
    normalized_map = {normalize(name): name for name in all_layers}
    layer_matches = {}
    for requested in REQUESTED_LAYERS:
        real_name = normalized_map.get(normalize(requested))
        layer_matches[requested] = real_name if real_name else "NOT FOUND IN FILE"
    audit["layer_name_matches"] = layer_matches

    audit["layers"] = {}
    for requested_name, real_name in layer_matches.items():
        if real_name == "NOT FOUND IN FILE":
            audit["layers"][requested_name] = {"status": "NOT FOUND - no matching layer name in the file"}
            continue
        audit["layers"][requested_name] = _inspect_layer_attributes(str(GPKG_PATH), real_name)

    _write_outputs(audit)
    print(f"Done. Wrote {AUDIT_JSON_PATH} and {REPORT_MD_PATH}")


def _inspect_layer_attributes(path: str, layer_name: str) -> dict:
    import pyogrio
    result = {"real_layer_name": layer_name}

    # Geometry extent from metadata only - no geometry load required for this
    try:
        info = pyogrio.read_info(path, layer=layer_name)
        result["feature_count_from_metadata"] = int(info.get("features", -1))
        result["geometry_type"] = info.get("geometry_type")
        result["crs"] = str(info.get("crs"))
        result["geographic_extent_native_crs"] = list(info["total_bounds"]) if info.get("total_bounds") is not None else None
    except Exception as e:
        result["metadata_read"] = fail("read_info", e)

    # Attribute table ONLY - geometry explicitly disabled, never loaded
    try:
        df = pyogrio.read_dataframe(path, layer=layer_name, read_geometry=False)
    except Exception as e:
        result["attribute_read"] = fail("read_dataframe(read_geometry=False)", e)
        return result

    result["row_count"] = len(df)
    result["columns"] = {}

    for col in df.columns:
        series = df[col]
        col_report = {
            "dtype": str(series.dtype),
            "unique_value_count": int(series.nunique(dropna=True)),
            "missing_count": int(series.isna().sum()),
            "missing_percent": round(100 * series.isna().sum() / len(series), 2) if len(series) else None,
        }
        result["columns"][col] = col_report

    # Full statistical treatment for the 5 special fields - EXACT name match only (case-insensitive)
    result["special_fields"] = {}
    col_by_lower = {c.lower(): c for c in df.columns}
    for special in SPECIAL_FIELDS:
        actual_col = col_by_lower.get(special)
        if not actual_col:
            result["special_fields"][special] = "FIELD NOT PRESENT in this layer"
            continue
        series = df[actual_col]
        is_numeric = pd.api.types.is_numeric_dtype(series)
        entry = {
            "actual_column_name": actual_col,
            "dtype": str(series.dtype),
            "missing_percent": round(100 * series.isna().sum() / len(series), 2) if len(series) else None,
            "unique_value_count": int(series.nunique(dropna=True)),
        }
        if is_numeric:
            entry["min"] = float(series.min()) if series.notna().any() else None
            entry["max"] = float(series.max()) if series.notna().any() else None
            entry["mean"] = float(series.mean()) if series.notna().any() else None
        else:
            entry["min"] = entry["max"] = entry["mean"] = "not numeric"

        n_unique = series.nunique(dropna=True)
        if n_unique <= 20:
            vc = series.value_counts(dropna=False)
            entry["value_counts"] = {str(k): int(v) for k, v in vc.items()}
            entry["all_unique_values"] = [str(v) for v in sorted(series.dropna().unique().tolist())]
        else:
            entry["value_counts"] = f"{n_unique} unique values - too many to list; showing top 20 by frequency"
            entry["top_20_value_counts"] = {str(k): int(v) for k, v in series.value_counts(dropna=False).head(20).items()}

        # Specifically flag whether this field is binary (relevant for 'y' especially)
        non_null_values = set(series.dropna().unique().tolist())
        entry["appears_binary_0_1"] = non_null_values.issubset({0, 1, 0.0, 1.0})

        result["special_fields"][special] = entry

    # Search ALL columns for context hints (state/district/location/lat/lon/date/year/landslide-id)
    # Name-based hint only - does NOT assume the column's actual content matches its name.
    result["context_field_candidates"] = {}
    for context, hints in CONTEXT_HINTS.items():
        matches = [c for c in df.columns if any(h in c.lower() for h in hints)]
        if matches:
            result["context_field_candidates"][context] = matches

    return result


def _write_outputs(audit: dict):
    with open(AUDIT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, default=str)

    md = [f"# ML Attribute Audit Report (Phase 2b)\n\nGenerated: {audit.get('inspected_at')}\n"]
    md.append(f"**File:** `{audit.get('file_path')}`\n")
    if "fatal_error" in audit:
        md.append(f"## FATAL ERROR\n\n{audit['fatal_error']}\n")
        with open(REPORT_MD_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        return

    md.append("## Layer name matching\n")
    for req, real in audit.get("layer_name_matches", {}).items():
        md.append(f"- `{req}` -> `{real}`")

    for requested_name, rep in audit.get("layers", {}).items():
        md.append(f"\n---\n## Layer: `{requested_name}` (real name: `{rep.get('real_layer_name', 'N/A')}`)\n")
        if rep.get("status") == "NOT FOUND - no matching layer name in the file":
            md.append("**NOT FOUND in file.**")
            continue
        md.append(f"- Feature count (metadata): {rep.get('feature_count_from_metadata')}")
        md.append(f"- Row count (attribute read): {rep.get('row_count')}")
        md.append(f"- Geometry type: {rep.get('geometry_type')}")
        md.append(f"- CRS: {rep.get('crs')}")
        md.append(f"- Geographic extent (native CRS): {rep.get('geographic_extent_native_crs')}")

        md.append(f"\n### All columns ({len(rep.get('columns', {}))})\n")
        for col, c in rep.get("columns", {}).items():
            md.append(f"- `{col}`: dtype={c['dtype']}, unique={c['unique_value_count']}, missing={c['missing_percent']}%")

        md.append(f"\n### Special fields (y, SI, lsd, su, ID)\n")
        for field, entry in rep.get("special_fields", {}).items():
            md.append(f"\n**{field}**")
            if isinstance(entry, str):
                md.append(f"- {entry}")
                continue
            md.append(f"- actual column: `{entry['actual_column_name']}`")
            md.append(f"- dtype: {entry['dtype']}, missing: {entry['missing_percent']}%, unique count: {entry['unique_value_count']}")
            md.append(f"- min/max/mean: {entry['min']} / {entry['max']} / {entry['mean']}")
            md.append(f"- appears_binary_0_1: {entry['appears_binary_0_1']}")
            if "all_unique_values" in entry:
                md.append(f"- all unique values: {entry['all_unique_values']}")
                md.append(f"- value counts: {entry['value_counts']}")
            else:
                md.append(f"- top 20 value counts: {entry.get('top_20_value_counts')}")

        if rep.get("context_field_candidates"):
            md.append(f"\n### Context field candidates (name-based hints only, not verified content)\n")
            for context, cols in rep["context_field_candidates"].items():
                md.append(f"- {context}: {cols}")

    with open(REPORT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md))


if __name__ == "__main__":
    main()
