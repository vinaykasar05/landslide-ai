"""
audit_feature_compatibility.py - Phase 5B

Run this on YOUR machine (reads model/real_static_model_metadata.json, which
only exists there).

This script is RULE-BASED, not a guess-as-you-go script: every assessment
below was worked out by directly inspecting this project's actual backend
code (services/terrain.py, services/weather.py, routes/gis.py, etc.) - not
assumed from feature names. The central finding driving almost every
assessment:

    THE TRAINING DATA IS PER-SLOPE-UNIT (zonal statistics over polygons -
    mean/std of a variable across the whole polygon's area).
    THE BACKEND IS PER-STATION (a single point coordinate, 8 fixed stations,
    no polygon/slope-unit concept at all).

This means even where the backend has a REAL data source for a concept
(elevation, slope, rainfall), the VALUE it produces is a different
statistical quantity than what the model was trained on - a point/grid-local
estimate, not a zonal mean/std over a delineated polygon. Per the task's
explicit instruction, this is NOT treated as compatible just because the
names are similar.

Output ONLY:
  data/phase5b_feature_compatibility_audit.md
  data/phase5b_feature_compatibility_audit.json

No model touched, no training, no frontend/backend changes.
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent
METADATA_PATH = HERE.parent / "model" / "real_static_model_metadata.json"
OUT_MD = HERE / "phase5b_feature_compatibility_audit.md"
OUT_JSON = HERE / "phase5b_feature_compatibility_audit.json"

STATUSES = {
    "COMPATIBLE", "COMPATIBLE_BUT_STATIC", "SOURCE_REQUIRED",
    "DEFINITION_MISMATCH", "NOT_FEASIBLE", "UNKNOWN_REQUIRES_SOURCE_VERIFICATION",
}

# ===========================================================================
# Rule table. Each rule is (regex pattern, assessment-builder function).
# Patterns are checked in order; first match wins. Every assessment below
# reflects what this project's ACTUAL backend code does right now, verified
# by reading services/terrain.py, services/weather.py, and routes/gis.py
# directly before writing this - not assumed from naming similarity.
# ===========================================================================

def _elev(name):
    is_std = name.lower().endswith("_std")
    return {
        "training_definition": f"Elevation {'standard deviation' if is_std else 'mean'} within a slope-unit polygon (zonal statistic over the real DEM, per the original SZ-plugin methodology)",
        "training_source": "ASTER/SRTM-class DEM, zonal-aggregated per slope unit (Titti et al. 2022 methodology)",
        "dynamic_or_static": "static",
        "current_backend_available": "PARTIAL" if not is_std else "NO",
        "current_backend_source": "services/terrain.py get_terrain_batch() -> elevation_m, via ASTER GDEM v3 (real)" if not is_std else "None - a single point has no standard deviation",
        "real_data_verified": True if not is_std else None,
        "definition_match": "NO",
        "legitimate_source_if_missing": "Same ASTER GDEM source, but would require delineating the actual slope-unit polygon (e.g. r.slopeunits/GRASS) and computing zonal mean/std over it - not a point/grid query",
        "integration_status": "DEFINITION_MISMATCH" if not is_std else "NOT_FEASIBLE",
        "notes": "Backend produces a single-point elevation value (real, ASTER GDEM), not a zonal mean over a slope-unit polygon. Using the point value as a substitute for Elev_mean would silently change what the feature represents." if not is_std else "No within-unit variability can exist for a single point - this requires slope-unit delineation first, which the backend does not do.",
    }

def _aspect(name):
    is_std = name.lower().endswith("_std")
    return {
        "training_definition": f"Aspect (slope direction, degrees) {'standard deviation' if is_std else 'mean'} within a slope-unit polygon",
        "training_source": "DEM-derived, zonal-aggregated per slope unit",
        "dynamic_or_static": "static",
        "current_backend_available": "PARTIAL" if not is_std else "NO",
        "current_backend_source": "services/terrain.py -> aspect_deg, Horn's method on a 3x3 real DEM grid (~30m) centered on the station point" if not is_std else "None",
        "real_data_verified": True if not is_std else None,
        "definition_match": "NO",
        "legitimate_source_if_missing": "Same DEM source, with slope-unit delineation + zonal aggregation. Note: aspect is CIRCULAR data (0-360 deg) - a naive arithmetic mean across a polygon would itself be WRONG; the original dataset's exact aggregation method (circular mean vs. another convention) is not confirmed from available sources.",
        "integration_status": "DEFINITION_MISMATCH" if not is_std else "NOT_FEASIBLE",
        "notes": "Backend's aspect is a single ~30m-grid-local estimate at one point, not a zonal statistic over a polygon - and even the correct way to average aspect across a polygon (circular mean) has not been confirmed from the original methodology.",
    }

def _slope(name):
    is_std = name.lower().endswith("_std")
    return {
        "training_definition": f"Slope angle (degrees) {'standard deviation' if is_std else 'mean'} within a slope-unit polygon",
        "training_source": "DEM-derived, zonal-aggregated per slope unit",
        "dynamic_or_static": "static",
        "current_backend_available": "PARTIAL" if not is_std else "NO",
        "current_backend_source": "services/terrain.py -> slope_deg, Horn's method (GDAL/QGIS/ArcGIS-standard) on a 3x3 real DEM grid at the station point" if not is_std else "None",
        "real_data_verified": True if not is_std else None,
        "definition_match": "NO",
        "legitimate_source_if_missing": "Same DEM + Horn's method, but applied over a delineated slope-unit polygon with zonal mean/std, not a single point",
        "integration_status": "DEFINITION_MISMATCH" if not is_std else "NOT_FEASIBLE",
        "notes": "The underlying method (Horn's) matches the likely original methodology, but the spatial support does not - point/grid-local vs. zonal-over-polygon.",
    }

def _rnsum(name):
    is_std = name.lower().endswith("_std")
    return {
        "training_definition": f"Rainfall sum {'standard deviation' if is_std else 'mean'} within a slope-unit polygon - almost certainly a LONG-TERM CLIMATOLOGICAL annual/seasonal rainfall statistic (static predisposing factor), not recent/current rainfall",
        "training_source": "Likely a climatological precipitation product (e.g. CHIRPS, WorldClim, or IMD gridded normals), zonal-aggregated - not confirmed from available sources",
        "dynamic_or_static": "static (training feature) - this is the critical distinction from the backend's rainfall",
        "current_backend_available": "NO (wrong kind of rainfall data exists)",
        "current_backend_source": "services/weather.py get_recent_rainfall() -> rain_24h/72h/7d via NASA POWER - this is REAL but DYNAMIC recent rainfall, not a static climatological normal",
        "real_data_verified": False,
        "definition_match": "NO",
        "legitimate_source_if_missing": "A long-term rainfall climatology dataset (CHIRPS, WorldClim BIO12, or IMD gridded rainfall normals), zonal-averaged per slope unit over many years",
        "integration_status": "DEFINITION_MISMATCH",
        "notes": "This is the most severe mismatch in the whole audit: the backend's rainfall is REAL but answers a completely different question (how much rain fell in the last week) than what the training feature represents (long-term average rainfall as a static predisposing factor). Substituting one for the other would not just be a scale issue - it would change the feature's meaning entirely.",
    }

def _relief(name):
    is_std = name.lower().endswith("_std")
    return {
        "training_definition": f"Relief (elevation range) {'standard deviation' if is_std else 'mean'} within a slope-unit polygon",
        "training_source": "DEM-derived, zonal-aggregated per slope unit",
        "dynamic_or_static": "static",
        "current_backend_available": "PARTIAL" if not is_std else "NO",
        "current_backend_source": "services/terrain.py -> relief_m, max-min elevation across a 3x3 real DEM grid (~60m extent) at the station point" if not is_std else "None",
        "real_data_verified": True if not is_std else None,
        "definition_match": "NO",
        "legitimate_source_if_missing": "Same DEM, but computed over the actual (likely much larger and irregularly shaped) slope-unit polygon, not a fixed ~60m grid window",
        "integration_status": "DEFINITION_MISMATCH" if not is_std else "NOT_FEASIBLE",
        "notes": "Backend's relief is computed over a small, fixed-size grid window; a slope unit's true extent and shape is unrelated to this and could be much larger.",
    }

def _curvature(name):
    kind = "vertical/profile" if name.lower().startswith("vcv") else "horizontal/plan"
    return {
        "training_definition": f"{kind.capitalize()} curvature mean/std within a slope-unit polygon",
        "training_source": "DEM-derived, zonal-aggregated per slope unit",
        "dynamic_or_static": "static",
        "current_backend_available": "NO",
        "current_backend_source": "None - the backend computes slope/aspect/ruggedness/relief from the DEM grid, but no curvature formula is implemented",
        "real_data_verified": None,
        "definition_match": "N/A - not currently produced",
        "legitimate_source_if_missing": "Same ASTER GDEM source already integrated; profile/plan curvature can be computed from the same 3x3 (or larger) grid using standard finite-difference formulas - technically straightforward to add, similar effort to the existing slope/aspect code",
        "integration_status": "SOURCE_REQUIRED",
        "notes": "Not a hard data-access problem (the DEM is already connected) - this is an engineering gap: curvature formulas were not implemented in this round. Even once added, the same point-vs-zonal mismatch as elevation/slope would apply.",
    }

def _ndvi(name):
    is_std = name.lower().endswith("_std")
    return {
        "training_definition": f"NDVI (vegetation index) {'standard deviation' if is_std else 'mean'} within a slope-unit polygon",
        "training_source": "Satellite imagery (likely Landsat/MODIS/Sentinel-2), zonal-aggregated",
        "dynamic_or_static": "static (as used here - a representative/seasonal value, not a live feed)",
        "current_backend_available": "NO",
        "current_backend_source": "None - no NDVI/vegetation integration exists anywhere in this project",
        "real_data_verified": None,
        "definition_match": "N/A - not currently produced",
        "legitimate_source_if_missing": "Sentinel-2 or MODIS NDVI via Google Earth Engine or Copernicus Open Access Hub, zonal-averaged per slope unit",
        "integration_status": "SOURCE_REQUIRED",
        "notes": "Genuinely not integrated yet - flagged in the project's own Real-Data Audit as a known gap.",
    }

def _litho(name):
    return {
        "training_definition": f"Lithology class indicator ({name}) - one dummy/one-hot column per rock-type category in the original study's classification scheme",
        "training_source": "Geological survey data (per the paper, GSI-derived), zonal-assigned per slope unit",
        "dynamic_or_static": "static",
        "current_backend_available": "NO (only an unverified placeholder exists)",
        "current_backend_source": "locations_data.py 'geology' field - HAND-WRITTEN PLACEHOLDER TEXT, explicitly flagged 'unverified_hardcoded' in prior audits, not a real geological survey source and not encoded in any categorical scheme",
        "real_data_verified": False,
        "definition_match": "NO",
        "legitimate_source_if_missing": "GSI Bhukosh (authoritative, but no stable public point-query API was found in Phase 1's research) for the raw lithology; critically, even with real lithology data, the EXACT category-to-integer mapping this specific dummy column encodes is not documented anywhere available to this project",
        "integration_status": "SOURCE_REQUIRED",
        "notes": "Two separate problems stacked: (1) no real lithology source is connected at all, and (2) even a real source would need to be re-coded into the training data's specific, undocumented classification scheme to be a true match - using a different lithology classification WOULD change this feature's definition.",
    }

def _lcover(name):
    return {
        "training_definition": f"Land cover class indicator ({name}) - one dummy/one-hot column per land-cover category in the original study's classification scheme (the numeric codes suggest a specific LULC standard, not confirmed which one)",
        "training_source": "Satellite-derived land-cover product, zonal-assigned per slope unit",
        "dynamic_or_static": "static (as used here)",
        "current_backend_available": "NO",
        "current_backend_source": "None",
        "real_data_verified": None,
        "definition_match": "N/A - not currently produced",
        "legitimate_source_if_missing": "ESA WorldCover (free, keyless, but needs rasterio/GDAL - flagged as risky on this machine in the Real-Data Audit) or NRSC's Annual LULC Atlas (official Indian source, class-code numbering style plausibly matches this dataset's lcover_* codes, but not confirmed)",
        "integration_status": "SOURCE_REQUIRED",
        "notes": "Even once a real source is connected, its classification codes would need to be verified against this exact training column's scheme (e.g. ESA WorldCover's 11 classes use different codes than NRSC's LULC hierarchy) - using the wrong one would silently change the feature's meaning.",
    }

def _pga(name):
    return {
        "training_definition": "Peak Ground Acceleration (seismic hazard) mean within a slope-unit polygon",
        "training_source": "Seismic hazard model/map, zonal-aggregated",
        "dynamic_or_static": "static (PGA is inherently a static hazard parameter, not something that changes day to day)",
        "current_backend_available": "NO",
        "current_backend_source": "None - no seismic hazard integration exists in this project",
        "real_data_verified": None,
        "definition_match": "N/A - not currently produced",
        "legitimate_source_if_missing": "National Seismic Hazard Map (BIS/NDMA) or a global model (USGS/GEM), zonal- or point-sampled",
        "integration_status": "SOURCE_REQUIRED",
        "notes": "Worth noting separately from most other features: PGA hazard maps are typically published as already-smoothed zone/grid values, so once a real source is connected, a point sample may be a MUCH closer match to the training definition than for terrain variables - this one could plausibly become COMPATIBLE_BUT_STATIC after integration, unlike most other missing features.",
    }

def _area(name):
    return {
        "training_definition": "Slope-unit polygon area (the spatial extent of the mapping unit itself)",
        "training_source": "Derived directly from the slope-unit delineation geometry",
        "dynamic_or_static": "static",
        "current_backend_available": "NO",
        "current_backend_source": "None - the backend has no slope-unit/polygon concept at all; it only has 8 fixed point coordinates",
        "real_data_verified": None,
        "definition_match": "N/A - fundamentally inapplicable to a point",
        "legitimate_source_if_missing": "Would require first solving slope-unit delineation for any new location (e.g. via r.slopeunits/GRASS or an equivalent algorithm) - a substantial, separate GIS engineering task, not a simple data-source swap",
        "integration_status": "NOT_FEASIBLE",
        "notes": "This feature has no meaning for a point location at all - it is specifically a property of the slope-unit polygon, which the backend's architecture does not have.",
    }


RULES = [
    (re.compile(r"^elev", re.I), _elev),
    (re.compile(r"^asp", re.I), _aspect),
    (re.compile(r"^slope", re.I), _slope),
    (re.compile(r"^rnsum", re.I), _rnsum),
    (re.compile(r"^rlf", re.I), _relief),
    (re.compile(r"^(vcv|hcv)", re.I), _curvature),
    (re.compile(r"^ndvi", re.I), _ndvi),
    (re.compile(r"^litho", re.I), _litho),
    (re.compile(r"^lcover", re.I), _lcover),
    (re.compile(r"^pga", re.I), _pga),
    (re.compile(r"^area$", re.I), _area),
]


def classify(feature_name: str) -> dict:
    for pattern, builder in RULES:
        if pattern.match(feature_name):
            result = builder(feature_name)
            result["feature"] = feature_name
            return result
    return {
        "feature": feature_name,
        "training_definition": "NOT ESTABLISHED - feature name did not match any known pattern from this project's prior research",
        "training_source": "NOT ESTABLISHED",
        "dynamic_or_static": "NOT ESTABLISHED",
        "current_backend_available": "UNKNOWN",
        "current_backend_source": "UNKNOWN",
        "real_data_verified": None,
        "definition_match": "UNKNOWN",
        "legitimate_source_if_missing": "Requires manual investigation of this specific feature name against the original dataset/paper",
        "integration_status": "UNKNOWN_REQUIRES_SOURCE_VERIFICATION",
        "notes": "This feature name was not recognized by any rule - do not assume it is safe or unsafe without manual verification.",
    }


def main():
    if not METADATA_PATH.exists():
        print(f"FATAL: {METADATA_PATH} not found. Run Phase 5A training first.")
        return

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    feature_names = metadata.get("feature_names", [])
    if not feature_names:
        print("FATAL: metadata.json has no 'feature_names' list.")
        return

    print(f"Auditing {len(feature_names)} real model features...")
    rows = [classify(f) for f in feature_names]

    counts = {status: sum(1 for r in rows if r["integration_status"] == status) for status in STATUSES}
    ready_statuses = {"COMPATIBLE", "COMPATIBLE_BUT_STATIC"}
    all_ready = all(r["integration_status"] in ready_statuses for r in rows)
    final_decision = "READY_FOR_MODEL_INTEGRATION" if all_ready else "NOT_READY_FOR_MODEL_INTEGRATION"

    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_metadata_source": str(METADATA_PATH),
        "total_features_audited": len(feature_names),
        "rows": rows,
        "counts": counts,
        "final_decision": final_decision,
        "central_finding": (
            "The training data is per-slope-unit (zonal statistics over polygons). "
            "The backend is per-station (point coordinates, 8 fixed stations, no polygon "
            "concept). This single architectural mismatch is the root cause of most "
            "DEFINITION_MISMATCH results below, even for features with a real underlying "
            "data source."
        ),
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, default=str)

    md = [f"# Phase 5B - Feature Compatibility Audit\n\nGenerated: {audit['generated_at']}\n"]
    md.append(f"**Central finding:** {audit['central_finding']}\n")
    md.append(f"Total features audited: {audit['total_features_audited']}\n")
    md.append("| feature | training_definition | training_source | current_backend_available | current_backend_source | definition_match | real_data_verified | dynamic_or_static | legitimate_source_if_missing | integration_status | notes |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        md.append("| " + " | ".join(str(r.get(k, "")).replace("\n", " ").replace("|", "/") for k in [
            "feature", "training_definition", "training_source", "current_backend_available",
            "current_backend_source", "definition_match", "real_data_verified", "dynamic_or_static",
            "legitimate_source_if_missing", "integration_status", "notes"]) + " |")

    md.append(f"\n## Summary counts\n")
    for status in sorted(STATUSES):
        md.append(f"- {status}: {counts[status]}")
    md.append(f"\n## FINAL DECISION: {final_decision}\n")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"\nFINAL DECISION: {final_decision}")
    print(f"Counts: {counts}")
    print(f"Wrote: {OUT_MD}, {OUT_JSON}")


if __name__ == "__main__":
    main()
