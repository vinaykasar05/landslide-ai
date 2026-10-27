"""
services/ml_model.py - wraps the trained model so the rest of the app never
touches joblib/sklearn directly.

Two entry points:

* predict_with_model()  - STRICT. Runs the real trained model or raises
  ModelUnavailableError. Never substitutes a made-up formula. Used by the
  /api/prediction/risk and /api/gis/stations endpoints.

* predict_risk()        - LEGACY. Same model, but silently falls back to a
  simple rule-based formula if no model file exists. Kept unchanged so the
  older /predict, /locations and /alerts endpoints behave exactly as before.

Model facts (features, positive class, training-data provenance, verified
scikit-learn versions) live in model/model_metadata.json next to the .pkl.
"""

import os
import json
import logging
import warnings

import joblib
import pandas as pd

from app.config import settings

logger = logging.getLogger(__name__)

# classes_ == [0, 1]; label 1 = "landslide event" (see model_metadata.json)
POSITIVE_CLASS = 1

_METADATA_PATH = os.path.join(os.path.dirname(settings.MODEL_PATH), "model_metadata.json")


def _load_metadata() -> dict:
    try:
        with open(_METADATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read model metadata at {_METADATA_PATH}: {e}")
        return {}


_metadata = _load_metadata()
_model = None

if os.path.exists(settings.MODEL_PATH):
    try:
        # The pickle was saved by a different scikit-learn version. sklearn emits one
        # InconsistentVersionWarning PER TREE (~200 lines). Capture them and log ONE
        # explicit line instead - documented, not hidden, and the model is not modified.
        with warnings.catch_warnings(record=True) as _caught:
            warnings.simplefilter("always")
            _model = joblib.load(settings.MODEL_PATH)
        _version_warnings = [w for w in _caught if "InconsistentVersion" in w.category.__name__]
        if _version_warnings:
            w0 = _version_warnings[0].message
            saved = getattr(w0, "original_sklearn_version", "unknown")
            current = getattr(w0, "current_sklearn_version", "unknown")
            verified = current in _metadata.get("sklearn_compatibility_checks", {})
            logger.warning(
                f"Model was saved with scikit-learn {saved} but {current} is installed "
                f"({len(_version_warnings)} per-tree warnings condensed into this line). "
                + ("Predictions were verified identical for this version (see model/model_metadata.json). "
                   if verified else
                   "This version has NOT been verified against the saved model - re-check predictions. ")
                + "Model was not retrained or modified."
            )
        logger.info(f"Loaded model from {settings.MODEL_PATH}")
    except Exception as e:
        logger.error(f"Failed to load model at {settings.MODEL_PATH}: {e}")
        _model = None
else:
    logger.warning(f"No model file found at {settings.MODEL_PATH}")


class ModelUnavailableError(Exception):
    """Raised when the trained model is not loaded, so callers can return an honest error."""


def risk_level_from_score(score: float) -> str:
    """Maps model P(landslide) to a display level. Thresholds are settings, not calibrated cut-offs."""
    if score < settings.RISK_LOW_MAX:
        return "Low"
    if score < settings.RISK_MODERATE_MAX:
        return "Moderate"
    if score < settings.RISK_HIGH_MAX:
        return "High"
    return "Critical"


def model_feature_names() -> list:
    """Feature names/order taken from the model itself (not assumed)."""
    if _model is None:
        return []
    return list(getattr(_model, "feature_names_in_", ["rain_24h", "rain_72h", "rain_7d"]))


def get_model_info() -> dict:
    """Describes the loaded model, its features and its provenance/caveats."""
    training = _metadata.get("training_data", {})
    provenance = training.get("provenance", "unknown")
    info = {
        "loaded": _model is not None,
        "model_type": type(_model).__name__ if _model is not None else None,
        "features": model_feature_names(),
        "classes": [int(c) for c in getattr(_model, "classes_", [])],
        "positive_class": POSITIVE_CLASS,
        "risk_score_definition": _metadata.get("risk_score_definition"),
        "training_data_provenance": provenance,
        "training_data_caveat": training.get("caveat"),
        "level_rule": (f"Low < {settings.RISK_LOW_MAX:.0%} <= Moderate < {settings.RISK_MODERATE_MAX:.0%} "
                       f"<= High < {settings.RISK_HIGH_MAX:.0%} <= Critical (of model P(landslide))"),
        "model_used": (f"{type(_model).__name__} (rainfall-only features; trained on {provenance.upper()} data)"
                       if _model is not None else None),
    }
    return info


def predict_with_model(features: dict) -> dict:
    """STRICT prediction. `features` maps feature name -> numeric value.
    Raises ModelUnavailableError if no model is loaded, ValueError if a required
    feature is missing. Never invents a value."""
    if _model is None:
        raise ModelUnavailableError("Trained model is not loaded")
    names = model_feature_names()
    missing = [n for n in names if features.get(n) is None]
    if missing:
        raise ValueError(f"Missing required model features: {missing}")

    X = pd.DataFrame([[float(features[n]) for n in names]], columns=names)
    proba = _model.predict_proba(X)[0]
    pos_idx = list(_model.classes_).index(POSITIVE_CLASS)
    score = round(float(proba[pos_idx]), 3)
    return {
        "risk_score": score,
        "risk_percent": round(score * 100),
        "risk_level": risk_level_from_score(score),
        "positive_class": POSITIVE_CLASS,
        "positive_class_column_index": pos_idx,
        "feature_order": names,
        "model_used": get_model_info()["model_used"],
    }


def predict_risk(rain_24h: float, rain_72h: float, rain_7d: float):
    """LEGACY: returns (score 0-1, level). Falls back to a rule-based formula if no model."""
    if _model is None:
        score = min(1.0, (rain_24h / 150 + rain_72h / 300 + rain_7d / 400) / 3)
    else:
        X = pd.DataFrame([{"rain_24h": rain_24h, "rain_72h": rain_72h, "rain_7d": rain_7d}])
        score = float(_model.predict_proba(X)[0][1])
    return round(score, 3), risk_level_from_score(score)


def model_is_loaded() -> bool:
    return _model is not None
