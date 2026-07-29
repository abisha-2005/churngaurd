"""
Extends churn_model.py's single-XGBoost training with a multi-model
comparison (Logistic Regression, Random Forest, Gradient Boosting, XGBoost)
and a feature-importance breakdown, without changing churn_model.py itself.

Kept as a separate module so the original Streamlit app / churn_model.py
behavior is untouched — this is purely additive for the dashboard.
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from xgboost import XGBClassifier

FEATURE_COLS = ["recency", "frequency", "monetary", "R_score", "F_score", "M_score", "RFM_score"]

FEATURE_LABELS = {
    "recency": "Recency",
    "frequency": "Frequency",
    "monetary": "Monetary Value",
    "R_score": "Recency Score",
    "F_score": "Frequency Score",
    "M_score": "Monetary Score",
    "RFM_score": "Overall RFM Score",
}


def _eval_model(model, X_test, y_test, has_two_classes):
    y_pred = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else y_pred

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    auc = roc_auc_score(y_test, proba) if has_two_classes else None

    return {
        "accuracy": round(acc * 100, 2),
        "precision": round(prec * 100, 2),
        "recall": round(rec * 100, 2),
        "auc": round(auc * 100, 2) if auc is not None else None,
    }


def compare_models(rfm_df: pd.DataFrame):
    """
    Trains 4 classifiers on the same RFM features + churn_label and returns
    metrics for each, plus which one is "best" (highest AUC, falling back to
    accuracy if AUC is undefined for single-class data).

    Returns: dict like:
    {
      "logistic_regression": {...metrics..., "label": "Logistic Regression"},
      "random_forest": {...},
      "gradient_boosting": {...},
      "xgboost": {...},
      "best": "logistic_regression"
    }
    """
    if "churn_label" not in rfm_df.columns:
        raise ValueError("No churn label found — cannot compare models.")

    df = rfm_df.copy()
    df["churn_label"] = pd.to_numeric(df["churn_label"], errors="coerce").fillna(0).astype(int)

    X = df[FEATURE_COLS]
    y = df["churn_label"]
    has_two_classes = y.nunique() > 1

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if has_two_classes else None
    )

    models = {
        "logistic_regression": (LogisticRegression(max_iter=1000), "Logistic Regression"),
        "random_forest": (RandomForestClassifier(n_estimators=150, random_state=42), "Random Forest"),
        "gradient_boosting": (GradientBoostingClassifier(random_state=42), "Gradient Boosting"),
        "xgboost": (
            XGBClassifier(
                n_estimators=150, max_depth=4, learning_rate=0.08,
                subsample=0.9, colsample_bytree=0.9, eval_metric="logloss", random_state=42,
            ),
            "XGBoost",
        ),
    }

    results = {}
    for key, (model, label) in models.items():
        model.fit(X_train, y_train)
        metrics = _eval_model(model, X_test, y_test, has_two_classes)
        metrics["label"] = label
        results[key] = metrics

    def rank_key(item):
        m = item[1]
        return m["auc"] if m["auc"] is not None else m["accuracy"]

    best_key = max(results.items(), key=rank_key)[0]
    results["best"] = best_key
    return results


def top_churn_drivers(model, top_n: int = 8):
    """
    Returns normalized (sum to 100%) feature importances from a trained
    tree-based model (XGBoost/RandomForest/GradientBoosting), sorted
    descending — used for the "Top Churn Drivers" panel.
    """
    if not hasattr(model, "feature_importances_"):
        return []

    importances = model.feature_importances_
    total = importances.sum() or 1.0

    pairs = list(zip(FEATURE_COLS, importances))
    pairs.sort(key=lambda x: x[1], reverse=True)

    drivers = []
    for feat, imp in pairs[:top_n]:
        drivers.append({
            "feature": FEATURE_LABELS.get(feat, feat),
            "importance_pct": round(float(imp) / total * 100, 2),
        })
    return drivers
