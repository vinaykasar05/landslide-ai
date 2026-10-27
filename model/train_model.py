"""
train_model.py

Trains a Random Forest classifier to predict landslide risk from rainfall
features (24h / 72h / 7-day cumulative rainfall).

Input:  ../data/landslide_training_data.csv
Output: landslide_model.pkl  (used by backend/main.py)
"""

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import joblib

DATA_PATH = "../data/landslide_training_data.csv"
MODEL_PATH = "landslide_model.pkl"
FEATURES = ["rain_24h", "rain_72h", "rain_7d"]

def main():
    df = pd.read_csv(DATA_PATH)
    print(f"Loaded {len(df)} rows")

    X = df[FEATURES]
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        class_weight="balanced",  # landslide events are rarer than non-events
        random_state=42,
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]

    print("\n--- Evaluation ---")
    print(classification_report(y_test, preds, target_names=["No landslide", "Landslide"]))
    print("Confusion matrix:")
    print(confusion_matrix(y_test, preds))
    print("\nFeature importances:")
    for feat, imp in zip(FEATURES, model.feature_importances_):
        print(f"  {feat}: {imp:.3f}")

    joblib.dump(model, MODEL_PATH)
    print(f"\nModel saved to {MODEL_PATH}")

if __name__ == "__main__":
    main()
