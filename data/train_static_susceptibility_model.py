"""
train_static_susceptibility_model.py - Phase 5A

Run this on YOUR machine (same reason as every script before it - this
environment has no access to data/real_static_training_table.csv).

Trains and evaluates REAL models on the REAL static susceptibility table
produced in Phase 4C. Does not touch the frontend, backend, GIS API, or the
existing synthetic model - this is a standalone training/evaluation pass
that produces its own separate model file for later review.

=== Honesty notes, read before trusting the output ===

1. SPATIAL VALIDATION: the training table intentionally has NO geometry
   column (per Phase 4C's rule). This means a random stratified split is
   what's actually available here - it is NOT a geographic generalization
   test. Two slope units that happen to be geographic neighbours could end
   up in different splits, which can make performance look better than it
   would for a genuinely new, geographically distant region. This is
   reported explicitly in every output file, not glossed over.

2. CLASS IMBALANCE: y=1 is ~2.5% of the data. Accuracy is close to
   meaningless here (predicting all-zero would already score ~97.5%
   accuracy). Model selection below is driven by validation PR-AUC
   (precision-recall AUC), which is the standard, honest metric for this
   level of imbalance - not accuracy, and not ROC-AUC alone (which can look
   optimistic under heavy imbalance).

3. THIS IS A STATIC SUSCEPTIBILITY MODEL. It estimates where terrain is
   predisposed to landslides, not when one will happen. This is restated in
   every output file and in the saved model metadata, verbatim as required.

Output:
  data/phase5_model_comparison.md / .json
  data/phase5_training_report.md / .json
  model/real_static_susceptibility_model.joblib
  model/real_static_model_metadata.json

Install: pip install scikit-learn pandas joblib  (all already in backend/requirements.txt)
"""

import json
import sys
import platform
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import sklearn
import joblib
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    roc_auc_score, average_precision_score, precision_score, recall_score,
    f1_score, confusion_matrix, classification_report,
)
from sklearn.utils.class_weight import compute_sample_weight

HERE = Path(__file__).parent
MODEL_DIR = HERE.parent / "model"
CSV_PATH = HERE / "real_static_training_table.csv"

OUT_COMPARISON_MD = HERE / "phase5_model_comparison.md"
OUT_COMPARISON_JSON = HERE / "phase5_model_comparison.json"
OUT_REPORT_MD = HERE / "phase5_training_report.md"
OUT_REPORT_JSON = HERE / "phase5_training_report.json"
OUT_MODEL = MODEL_DIR / "real_static_susceptibility_model.joblib"
OUT_METADATA = MODEL_DIR / "real_static_model_metadata.json"

RANDOM_SEED = 42
LEAKAGE_FIELDS = {"id", "lsd", "si", "su", "y"}

REQUIRED_STATEMENT = (
    "This model is trained on real historical/static landslide susceptibility data. "
    "It estimates static landslide susceptibility from spatial predisposing factors. "
    "It is NOT a real-time landslide early-warning model and does NOT predict the "
    "timing of future landslides."
)


def log(msg):
    print(msg)


def metrics_for(y_true, y_proba, y_pred) -> dict:
    cm = confusion_matrix(y_true, y_pred).tolist()
    return {
        "roc_auc": float(roc_auc_score(y_true, y_proba)),
        "pr_auc": float(average_precision_score(y_true, y_proba)),
        "precision_class1": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall_class1": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1_class1": float(f1_score(y_true, y_pred, zero_division=0)),
        "confusion_matrix": cm,  # [[TN, FP], [FN, TP]]
        "confusion_matrix_labels": "[[TN, FP], [FN, TP]]",
        "class_distribution": {"0": int((y_true == 0).sum()), "1": int((y_true == 1).sum())},
    }


def main():
    if not CSV_PATH.exists():
        log(f"FATAL: {CSV_PATH} not found. Run build_static_training_table.py first (Phase 4C).")
        sys.exit(1)

    MODEL_DIR.mkdir(exist_ok=True)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "random_seed": RANDOM_SEED}

    # --- Load + leakage self-check (belt-and-suspenders on top of Phase 4C's own exclusion) ---
    df = pd.read_csv(CSV_PATH)
    if "y" not in df.columns:
        log("FATAL: 'y' column not found in the training table.")
        sys.exit(1)

    present_leakage = [c for c in df.columns if c.lower() in LEAKAGE_FIELDS and c.lower() != "y"]
    report["leakage_self_check"] = {"leakage_fields_found_among_predictors": present_leakage, "pass": len(present_leakage) == 0}
    if present_leakage:
        log(f"FATAL: leakage fields found among predictors: {present_leakage}. ABORTING - will not train on these.")
        with open(OUT_REPORT_JSON, "w") as f:
            json.dump(report, f, indent=2)
        sys.exit(1)

    feature_cols = [c for c in df.columns if c != "y"]
    X = df[feature_cols].copy()
    y = df["y"].astype(int)

    report["dataset"] = {
        "path": str(CSV_PATH), "total_rows": len(df), "feature_count": len(feature_cols),
        "feature_names": feature_cols,
        "class_distribution": {"y0": int((y == 0).sum()), "y1": int((y == 1).sum())},
        "positive_class_percent": round(100 * (y == 1).sum() / len(y), 3),
    }
    log(f"Loaded {len(df)} rows, {len(feature_cols)} features. y=1: {(y==1).sum()} ({report['dataset']['positive_class_percent']}%)")

    # --- Encode any non-numeric columns defensively (litho_*/lcover_* are expected to already
    #     be 0/1 dummy columns per the data dictionary, but handle raw categoricals if present) ---
    non_numeric = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
    if non_numeric:
        log(f"One-hot encoding non-numeric columns: {non_numeric}")
        X = pd.get_dummies(X, columns=non_numeric, dummy_na=True)
    report["encoding"] = {"non_numeric_columns_one_hot_encoded": non_numeric, "final_feature_count_after_encoding": X.shape[1]}

    # Missing values: report, do not silently impute beyond a simple, declared strategy
    missing_before = X.isna().sum()
    cols_with_missing = missing_before[missing_before > 0].to_dict()
    if cols_with_missing:
        log(f"Missing values found, median-imputing (declared, not silent): {cols_with_missing}")
        X = X.fillna(X.median(numeric_only=True))
    report["missing_value_handling"] = {
        "columns_with_missing_before_training": {k: int(v) for k, v in cols_with_missing.items()},
        "strategy": "median imputation" if cols_with_missing else "none needed - no missing values",
    }

    # --- Split: train / validation / test, STRATIFIED on y (random - see honesty note above) ---
    X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=0.30, stratify=y, random_state=RANDOM_SEED)
    X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.50, stratify=y_temp, random_state=RANDOM_SEED)

    report["split"] = {
        "strategy": "Random stratified split (70/15/15) - NOT a spatial/geographic holdout",
        "spatial_validation_note": (
            "Geometry was intentionally excluded from the training table (Phase 4C rule), so a true "
            "spatial block/geographic holdout is not performed here. This split tests whether the model "
            "generalizes across slope units drawn from the same overall distribution, not whether it "
            "generalizes to a new, geographically distant region. Treat validation/test metrics accordingly - "
            "they are a lower bound on how optimistic performance could look, not a geographic generalization proof."
        ),
        "train_size": len(X_train), "validation_size": len(X_val), "test_size": len(X_test),
        "train_class_dist": {"y0": int((y_train == 0).sum()), "y1": int((y_train == 1).sum())},
        "val_class_dist": {"y0": int((y_val == 0).sum()), "y1": int((y_val == 1).sum())},
        "test_class_dist": {"y0": int((y_test == 0).sum()), "y1": int((y_test == 1).sum())},
    }
    log(f"Split: train={len(X_train)} val={len(X_val)} test={len(X_test)}")

    # --- Models ---
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    sample_weight_train = compute_sample_weight(class_weight="balanced", y=y_train)

    models = {}

    log("Training Logistic Regression (class_weight=balanced)...")
    lr = LogisticRegression(class_weight="balanced", max_iter=2000, random_state=RANDOM_SEED)
    lr.fit(X_train_scaled, y_train)
    models["logistic_regression"] = {"model": lr, "needs_scaling": True, "params": lr.get_params()}

    log("Training Random Forest (class_weight=balanced)...")
    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1)
    rf.fit(X_train, y_train)
    models["random_forest"] = {"model": rf, "needs_scaling": False, "params": rf.get_params()}

    log("Training HistGradientBoostingClassifier (sample_weight-balanced; no extra dependency needed)...")
    gb = HistGradientBoostingClassifier(random_state=RANDOM_SEED)
    gb.fit(X_train, y_train, sample_weight=sample_weight_train)
    models["gradient_boosting"] = {"model": gb, "needs_scaling": False, "params": gb.get_params()}

    # Optional: xgboost only if already installed - never force-installed
    try:
        import xgboost as xgb
        pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
        xgb_model = xgb.XGBClassifier(random_state=RANDOM_SEED, scale_pos_weight=pos_weight, eval_metric="logloss")
        xgb_model.fit(X_train, y_train)
        models["xgboost"] = {"model": xgb_model, "needs_scaling": False, "params": xgb_model.get_params()}
        log("xgboost was available - included as an additional candidate.")
    except ImportError:
        log("xgboost not installed - skipped (not force-installed, per project convention). HistGradientBoostingClassifier covers the 'gradient boosting' requirement.")

    # --- Evaluate every model on train/val/test ---
    comparison = {}
    for name, m in models.items():
        model = m["model"]
        Xtr, Xv, Xte = (X_train_scaled, X_val_scaled, X_test_scaled) if m["needs_scaling"] else (X_train, X_val, X_test)

        def predict_both(Xsplit):
            proba = model.predict_proba(Xsplit)[:, 1]
            pred = (proba >= 0.5).astype(int)
            return proba, pred

        train_proba, train_pred = predict_both(Xtr)
        val_proba, val_pred = predict_both(Xv)
        test_proba, test_pred = predict_both(Xte)

        comparison[name] = {
            "train_metrics": metrics_for(y_train, train_proba, train_pred),
            "validation_metrics": metrics_for(y_val, val_proba, val_pred),
            "test_metrics": metrics_for(y_test, test_proba, test_pred),
            "overfitting_check": {
                "train_val_pr_auc_gap": round(
                    metrics_for(y_train, train_proba, train_pred)["pr_auc"] -
                    metrics_for(y_val, val_proba, val_pred)["pr_auc"], 4),
                "note": "A large gap (train much higher than validation) suggests overfitting.",
            },
        }
        log(f"{name}: val PR-AUC={comparison[name]['validation_metrics']['pr_auc']:.4f}, "
            f"val recall(y=1)={comparison[name]['validation_metrics']['recall_class1']:.4f}, "
            f"val ROC-AUC={comparison[name]['validation_metrics']['roc_auc']:.4f}")

    # --- Model selection: validation PR-AUC primary (justified - see module docstring), recall as tie-breaker ---
    ranked = sorted(comparison.items(), key=lambda kv: (kv[1]["validation_metrics"]["pr_auc"], kv[1]["validation_metrics"]["recall_class1"]), reverse=True)
    best_name = ranked[0][0]
    best_model_obj = models[best_name]["model"]
    best_needs_scaling = models[best_name]["needs_scaling"]

    selection_reasoning = (
        f"Selected '{best_name}' based on VALIDATION PR-AUC "
        f"({comparison[best_name]['validation_metrics']['pr_auc']:.4f}), the standard honest metric for ~2.5% "
        "positive-class imbalance (unlike accuracy, which would favour a trivial all-zero predictor at ~97.5%). "
        "Recall for the positive class was used as a tie-breaker, since missing real susceptible slope units "
        "(false negatives) is the costlier error for a susceptibility screening tool. Accuracy was NOT used as "
        "the selection criterion."
    )
    log(f"\nBEST MODEL: {best_name}\n{selection_reasoning}")

    # --- Write comparison report ---
    comp_report = {
        "generated_at": report["generated_at"], "random_seed": RANDOM_SEED,
        "models_trained": list(comparison.keys()), "comparison": comparison,
        "best_model": best_name, "selection_reasoning": selection_reasoning,
    }
    with open(OUT_COMPARISON_JSON, "w") as f:
        json.dump(comp_report, f, indent=2, default=str)
    _write_comparison_md(comp_report)

    # --- Save the best model + metadata ---
    joblib.dump({"model": best_model_obj, "scaler": scaler if best_needs_scaling else None,
                 "needs_scaling": best_needs_scaling, "feature_names": list(X.columns)}, OUT_MODEL)

    metadata = {
        "REQUIRED_STATEMENT": REQUIRED_STATEMENT,
        "model_type": best_name,
        "feature_names": list(X.columns),
        "feature_count": X.shape[1],
        "training_dataset": str(CSV_PATH),
        "dataset_provenance": "Real published dataset: 'Dataset of landslide susceptibility in north-east India' (Titti et al. 2022), Zenodo DOI 10.5281/zenodo.6575572",
        "target_definition": "y: 1 = slope unit contains real mapped landslide area (per original GSI-derived inventory), 0 = it does not",
        "class_distribution": report["dataset"]["class_distribution"],
        "train_size": len(X_train), "validation_size": len(X_val), "test_size": len(X_test),
        "random_seed": RANDOM_SEED,
        "evaluation_metrics": comparison[best_name],
        "model_parameters": models[best_name]["params"],
        "training_timestamp": report["generated_at"],
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "limitations": [
            "STATIC susceptibility only - does not predict WHEN a landslide will occur.",
            "Validation/test split is random-stratified, NOT a geographic holdout (geometry was excluded from the training table per Phase 4C) - metrics may be optimistic relative to true geographic generalization.",
            "Training data provenance is real, but the underlying landslide inventory's exact date range is not established (per Phase 3 audit).",
            "Not yet integrated into the application - this is a standalone candidate model pending review.",
            "Class imbalance (~2.5% positive) means even a well-performing model will have non-trivial false positive/negative rates - review the full confusion matrix before deployment, not a single summary metric.",
        ],
    }
    with open(OUT_METADATA, "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    # --- Final readiness decision ---
    best_val = comparison[best_name]["validation_metrics"]
    blocking = []
    if best_val["pr_auc"] <= (report["dataset"]["positive_class_percent"] / 100):
        blocking.append("Best model's validation PR-AUC does not clearly exceed the naive baseline (positive class prevalence) - model is not demonstrating real skill.")
    if present_leakage:
        blocking.append("Leakage fields detected among predictors.")
    train_val_gap = comparison[best_name]["overfitting_check"]["train_val_pr_auc_gap"]
    if train_val_gap > 0.30:
        blocking.append(f"Large train/validation PR-AUC gap ({train_val_gap}) suggests significant overfitting.")

    final_decision = "READY_FOR_REAL_STATIC_MODEL_REVIEW" if not blocking else "NOT_READY_FOR_REAL_STATIC_MODEL_REVIEW"

    report.update({
        "models_trained": list(comparison.keys()), "best_model": best_name,
        "selection_reasoning": selection_reasoning, "best_model_metrics": comparison[best_name],
        "leakage_detected": len(present_leakage) > 0, "synthetic_data_used": False,
        "model_file": str(OUT_MODEL), "metadata_file": str(OUT_METADATA),
        "limitations": metadata["limitations"], "final_decision": final_decision, "blocking_issues": blocking,
    })
    with open(OUT_REPORT_JSON, "w") as f:
        json.dump(report, f, indent=2, default=str)
    _write_training_report_md(report)

    log(f"\n{'='*60}\nFINAL DECISION: {final_decision}\n{'='*60}")
    if blocking:
        log(f"Blocking issues: {blocking}")


def _write_comparison_md(comp_report):
    md = [f"# Phase 5 Model Comparison\n\nGenerated: {comp_report['generated_at']}  \nRandom seed: {comp_report['random_seed']}\n"]
    md.append(f"Models trained: {comp_report['models_trained']}\n")
    for name, c in comp_report["comparison"].items():
        md.append(f"\n## {name}\n")
        for split in ["train_metrics", "validation_metrics", "test_metrics"]:
            m = c[split]
            md.append(f"**{split}**: ROC-AUC={m['roc_auc']:.4f} | PR-AUC={m['pr_auc']:.4f} | "
                       f"Precision(y=1)={m['precision_class1']:.4f} | Recall(y=1)={m['recall_class1']:.4f} | "
                       f"F1(y=1)={m['f1_class1']:.4f}  \nConfusion matrix {m['confusion_matrix_labels']}: {m['confusion_matrix']}\n")
        md.append(f"Overfitting check: {c['overfitting_check']}\n")
    md.append(f"\n## Best model: {comp_report['best_model']}\n\n{comp_report['selection_reasoning']}\n")
    with open(OUT_COMPARISON_MD, "w") as f:
        f.write("\n".join(md))


def _write_training_report_md(report):
    md = [f"# Phase 5A Training Report\n\nGenerated: {report['generated_at']}\n"]
    md.append(f"## Dataset\n{json.dumps(report['dataset'], indent=2)}\n")
    md.append(f"## Split\n{json.dumps(report['split'], indent=2)}\n")
    md.append(f"## Models trained\n{report['models_trained']}\n")
    md.append(f"## Best model: {report['best_model']}\n{report['selection_reasoning']}\n")
    md.append(f"## Best model metrics\n```json\n{json.dumps(report['best_model_metrics'], indent=2)}\n```\n")
    md.append(f"## Leakage detected: {report['leakage_detected']}\n## Synthetic data used: {report['synthetic_data_used']}\n")
    md.append(f"## Files\nModel: `{report['model_file']}`  \nMetadata: `{report['metadata_file']}`\n")
    md.append("## Limitations\n" + "\n".join(f"- {l}" for l in report["limitations"]) + "\n")
    md.append(
        "\n## REQUIRED STATEMENT\n\n> This model is trained on real historical/static landslide "
        "susceptibility data. It estimates static landslide susceptibility from spatial predisposing "
        "factors. It is NOT a real-time landslide early-warning model and does NOT predict the timing "
        "of future landslides.\n"
    )
    md.append(f"\n## FINAL DECISION: {report['final_decision']}\n")
    if report.get("blocking_issues"):
        md.append("Blocking issues:\n" + "\n".join(f"- {b}" for b in report["blocking_issues"]))
    with open(OUT_REPORT_MD, "w") as f:
        f.write("\n".join(md))


if __name__ == "__main__":
    main()
