"""
inspect_gpkg.py - Phase 2 inspection of data/raw/India_dataset.gpkg

Run this on YOUR machine (where the file actually lives) - this environment
has no access to your local filesystem or the ability to receive a 2.3GB
upload, so this script was written blind to the file's actual contents and
makes no assumptions about layer names, field names, or structure. Everything
it reports is discovered at runtime, not guessed in advance.

Strategy for a 2.3GB file (metadata-first, to avoid loading everything into
memory before we know what's in it):
  1. List every layer + geometry type + feature count + CRS + bounds via
     pyogrio.read_info() - this reads metadata only, not the actual features,
     so it stays fast and low-memory even for a huge file.
  2. Point/MultiPoint layers (most plausible home for discrete landslide
     events) get a FULL read + full inspection: missing values, duplicates,
     state detection, date detection, per-state counts.
  3. Polygon/Line/raster-derived layers (plausible "slope unit" conditioning-
     factor layers) get metadata only UNLESS a field name suggests a
     landslide presence/absence indicator (e.g. contains "LS", "landslide",
     "slide"), in which case a full read is also attempted.
  4. Every failure is caught and reported verbatim - this script never
     silently skips something that failed; it writes down exactly what broke
     and why, so nothing gets quietly treated as "fine" when it wasn't checked.

Output:
  data/ml_dataset_audit.json  (machine-readable)
  data/ml_dataset_report.md   (human-readable)

Install (if needed):
    pip install geopandas pyogrio

pyogrio is used specifically because, unlike the older fiona/GDAL-from-source
route, it ships prebuilt wheels for Windows - much less likely to hit the
kind of DLL/install problems seen earlier in this project with scipy/sklearn.
"""

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

GPKG_PATH = Path(__file__).parent / "raw" / "India_dataset.gpkg"
AUDIT_JSON_PATH = Path(__file__).parent / "ml_dataset_audit.json"
REPORT_MD_PATH = Path(__file__).parent / "ml_dataset_report.md"

NER_STATES = [
    "Arunachal Pradesh", "Assam", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Sikkim", "Tripura",
]

# Candidate field-name substrings (case-insensitive) used to DISCOVER likely
# fields, never to assume they exist. Every match found is reported.
STATE_FIELD_HINTS = ["state", "st_nm", "st_name", "province"]
DATE_FIELD_HINTS = ["date", "year", "yr", "event_date", "ls_date"]
LANDSLIDE_FIELD_HINTS = ["landslide", "ls_", "slide", "event", "hazard"]
ID_FIELD_HINTS = ["id", "fid", "objectid", "gid"]


def fail(section: str, exc: Exception) -> dict:
    return {
        "status": "FAILED",
        "section": section,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "traceback": traceback.format_exc(),
    }


def main():
    audit = {
        "inspected_at": datetime.now(timezone.utc).isoformat(),
        "file_path": str(GPKG_PATH),
        "file_exists": GPKG_PATH.exists(),
    }

    if not GPKG_PATH.exists():
        audit["fatal_error"] = f"File not found at {GPKG_PATH}. Confirm it was placed at data/raw/India_dataset.gpkg."
        _write_outputs(audit)
        print(f"FATAL: file not found at {GPKG_PATH}")
        sys.exit(1)

    audit["file_size_mb"] = round(GPKG_PATH.stat().st_size / (1024 * 1024), 1)

    try:
        import pyogrio
        import geopandas as gpd
    except ImportError as e:
        audit["fatal_error"] = (
            f"Required package not installed: {e}. Run: pip install geopandas pyogrio"
        )
        _write_outputs(audit)
        print(f"FATAL: {audit['fatal_error']}")
        sys.exit(1)

    # --- 1. List all layers (metadata only - safe for a 2.3GB file) ---
    try:
        layer_list = pyogrio.list_layers(str(GPKG_PATH))
        # pyogrio returns an array of [name, geometry_type] pairs
        layer_names = [row[0] for row in layer_list]
        audit["layers_found"] = len(layer_names)
    except Exception as e:
        audit["layer_listing"] = fail("list_layers", e)
        _write_outputs(audit)
        print("FATAL: could not even list layers - see ml_dataset_audit.json")
        sys.exit(1)

    audit["layers"] = {}

    for name in layer_names:
        layer_report = {"layer_name": name}
        try:
            info = pyogrio.read_info(str(GPKG_PATH), layer=name)
            layer_report["geometry_type"] = info.get("geometry_type")
            layer_report["feature_count"] = int(info["features"]) if info.get("features", -1) >= 0 else "unknown (not stored in header - would require a full scan)"
            layer_report["crs"] = str(info.get("crs"))
            layer_report["bounds_native_crs"] = list(info.get("total_bounds")) if info.get("total_bounds") is not None else None
            fields = list(info.get("fields", []))
            dtypes = list(info.get("dtypes", []))
            layer_report["fields"] = dict(zip(fields, dtypes))
        except Exception as e:
            layer_report["metadata_read"] = fail("read_info", e)
            audit["layers"][name] = layer_report
            continue

        geom_type = (layer_report.get("geometry_type") or "").lower()
        field_names_lower = [f.lower() for f in layer_report["fields"].keys()]
        has_landslide_hint = any(
            hint in fname for fname in field_names_lower for hint in LANDSLIDE_FIELD_HINTS
        )
        is_point_layer = "point" in geom_type

        layer_report["full_inspection_attempted"] = bool(is_point_layer or has_landslide_hint)
        layer_report["full_inspection_reason"] = (
            "point/multipoint geometry - most plausible discrete landslide-event layer" if is_point_layer
            else "field name suggests a landslide indicator column" if has_landslide_hint
            else "polygon/line layer with no landslide-indicator field name - metadata only, NOT fully scanned (avoiding an unnecessary full read of a potentially huge conditioning-factor layer)"
        )

        if layer_report["full_inspection_attempted"]:
            try:
                gdf = gpd.read_file(str(GPKG_PATH), layer=name, engine="pyogrio")
                layer_report["full_inspection"] = _inspect_dataframe(gdf, field_names_lower)
            except Exception as e:
                layer_report["full_inspection"] = fail("geopandas_read_file", e)

        audit["layers"][name] = layer_report

    # --- Overall verdict (only answered if we actually found something concrete) ---
    audit["overall_assessment"] = _assess(audit)

    _write_outputs(audit)
    print(f"Done. Wrote {AUDIT_JSON_PATH} and {REPORT_MD_PATH}")
    print(f"Layers found: {audit.get('layers_found')}")


def _inspect_dataframe(gdf, field_names_lower) -> dict:
    result = {"row_count": len(gdf)}

    # Missing values per column
    result["missing_value_counts"] = {col: int(gdf[col].isna().sum()) for col in gdf.columns}

    # Duplicates: by full attribute row (excluding geometry) and by geometry
    non_geom_cols = [c for c in gdf.columns if c != gdf.geometry.name]
    result["duplicate_rows_by_attributes"] = int(gdf.duplicated(subset=non_geom_cols).sum()) if non_geom_cols else None
    try:
        result["duplicate_rows_by_geometry"] = int(gdf.geometry.duplicated().sum())
    except Exception as e:
        result["duplicate_rows_by_geometry"] = f"could not check: {e}"

    # CRS and real lat/lon extraction
    result["crs"] = str(gdf.crs)
    try:
        gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs and gdf.crs.to_epsg() != 4326 else gdf
        result["reprojected_to_wgs84"] = gdf.crs and gdf.crs.to_epsg() != 4326
        centroids = gdf_wgs84.geometry.centroid
        result["geographic_extent_wgs84"] = {
            "min_lon": float(centroids.x.min()), "max_lon": float(centroids.x.max()),
            "min_lat": float(centroids.y.min()), "max_lat": float(centroids.y.max()),
        }
    except Exception as e:
        result["geographic_extent_wgs84"] = f"could not compute: {e}"
        gdf_wgs84 = None

    # Discover state field
    state_col = next((c for c in gdf.columns if any(h in c.lower() for h in STATE_FIELD_HINTS)), None)
    result["state_field_found"] = state_col
    if state_col:
        value_counts = gdf[state_col].value_counts(dropna=False).to_dict()
        result["all_unique_state_values"] = {str(k): int(v) for k, v in value_counts.items()}
        ner_counts = {}
        for ner_state in NER_STATES:
            matches = gdf[state_col].astype(str).str.strip().str.lower() == ner_state.lower()
            ner_counts[ner_state] = int(matches.sum())
        result["ner_state_record_counts"] = ner_counts
        result["ner_states_present"] = [s for s, c in ner_counts.items() if c > 0]
    else:
        result["ner_state_record_counts"] = "NOT COMPUTED - no column matched state-name hints; manual column inspection needed"

    # Discover date/year field
    date_col = next((c for c in gdf.columns if any(h in c.lower() for h in DATE_FIELD_HINTS)), None)
    result["date_field_found"] = date_col
    if date_col:
        result["date_field_sample_values"] = [str(v) for v in gdf[date_col].dropna().head(10).tolist()]
        result["date_field_dtype"] = str(gdf[date_col].dtype)

    # Discover ID field
    id_col = next((c for c in gdf.columns if any(h in c.lower() for h in ID_FIELD_HINTS)), None)
    result["id_field_found"] = id_col

    return result


def _assess(audit: dict) -> dict:
    point_layers_with_data = [
        name for name, rep in audit.get("layers", {}).items()
        if rep.get("full_inspection") and isinstance(rep["full_inspection"], dict) and rep["full_inspection"].get("row_count", 0) > 0
    ]
    return {
        "point_or_landslide_layers_found": point_layers_with_data,
        "note": (
            "This is a MECHANICAL summary of what was found, not a judgment call - "
            "read the full per-layer sections above/below before deciding whether "
            "this dataset can supply real positive labels and support the training "
            "pipeline. In particular: check whether any layer above has a usable "
            "state field, date field, and non-empty NER-state record counts."
        ),
    }


def _write_outputs(audit: dict):
    with open(AUDIT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, default=str)

    md = [f"# ML Dataset Audit Report\n\nGenerated: {audit.get('inspected_at')}\n"]
    md.append(f"**File:** `{audit.get('file_path')}`")
    md.append(f"**File exists:** {audit.get('file_exists')}")
    if "file_size_mb" in audit:
        md.append(f"**File size:** {audit['file_size_mb']} MB")
    if "fatal_error" in audit:
        md.append(f"\n## FATAL ERROR\n\n{audit['fatal_error']}\n")
    else:
        md.append(f"\n**Layers found:** {audit.get('layers_found')}\n")
        for name, rep in audit.get("layers", {}).items():
            md.append(f"\n## Layer: `{name}`\n")
            md.append(f"- Geometry type: `{rep.get('geometry_type')}`")
            md.append(f"- Feature count: {rep.get('feature_count')}")
            md.append(f"- CRS: {rep.get('crs')}")
            md.append(f"- Fields: {', '.join(rep.get('fields', {}).keys()) or 'N/A'}")
            md.append(f"- Full inspection attempted: {rep.get('full_inspection_attempted')}")
            md.append(f"  - Reason: {rep.get('full_inspection_reason')}")
            fi = rep.get("full_inspection")
            if isinstance(fi, dict):
                md.append(f"- Row count (full read): {fi.get('row_count')}")
                md.append(f"- State field found: {fi.get('state_field_found')}")
                if fi.get("ner_state_record_counts") and isinstance(fi["ner_state_record_counts"], dict):
                    md.append("  - NER state counts:")
                    for s, c in fi["ner_state_record_counts"].items():
                        md.append(f"    - {s}: {c}")
                md.append(f"- Date field found: {fi.get('date_field_found')}")
                md.append(f"- Duplicate rows (by attributes): {fi.get('duplicate_rows_by_attributes')}")
                md.append(f"- Duplicate rows (by geometry): {fi.get('duplicate_rows_by_geometry')}")
                md.append(f"- Geographic extent (WGS84): {fi.get('geographic_extent_wgs84')}")
            elif isinstance(fi, dict) and fi.get("status") == "FAILED":
                md.append(f"- **FULL INSPECTION FAILED:** {fi.get('error_type')}: {fi.get('error_message')}")
        md.append("\n## Overall assessment (mechanical, not a judgment)\n")
        md.append(json.dumps(audit.get("overall_assessment", {}), indent=2))

    with open(REPORT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md))


if __name__ == "__main__":
    main()
