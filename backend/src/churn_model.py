import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score
import joblib
import os

FEATURE_COLS = ["recency", "frequency", "monetary", "R_score", "F_score", "M_score", "RFM_score"]

def train_churn_model(rfm_df: pd.DataFrame):
    """
    Trains an XGBoost churn model using the RFM dataframe.
    Requires rfm_df to contain a 'churn_label' column (0/1).
    Returns the trained model, test accuracy/auc, and the dataframe
    with predicted churn probabilities added.
    """
    if "churn_label" not in rfm_df.columns:
        raise ValueError(
            "No churn label found in the uploaded data. "
            "This system needs a historical churn column (0 = active, 1 = churned) "
            "to train the model — please make sure the AI schema mapping correctly "
            "identifies your churn/target column."
        )

    df = rfm_df.copy()
    df["churn_label"] = pd.to_numeric(df["churn_label"], errors="coerce").fillna(0).astype(int)

    X = df[FEATURE_COLS]
    y = df["churn_label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if y.nunique() > 1 else None
    )

    model = XGBClassifier(
        n_estimators=150,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba_test = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": round(accuracy_score(y_test, y_pred), 3),
        "roc_auc": round(roc_auc_score(y_test, y_proba_test), 3) if y.nunique() > 1 else None,
        "train_size": len(X_train),
        "test_size": len(X_test),
    }

    # Predict churn probability for ALL customers (not just test set)
    df["churn_probability"] = model.predict_proba(X)[:, 1]
    df["risk_level"] = pd.cut(
        df["churn_probability"],
        bins=[-0.01, 0.3, 0.6, 1.0],
        labels=["Low Risk", "Medium Risk", "High Risk"],
    )

    os.makedirs("models", exist_ok=True)
    joblib.dump(model, "models/churn_model.pkl")

    return model, metrics, df
def predict_with_existing_model(model, rfm_df: pd.DataFrame) -> pd.DataFrame:
    """
    Uses an already-trained model to score NEW customers that have
    no churn_label — prediction only, no training happens here.
    """
    df = rfm_df.copy()

    missing_cols = [c for c in FEATURE_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required features for prediction: {missing_cols}")

    X = df[FEATURE_COLS]

    df["churn_probability"] = model.predict_proba(X)[:, 1]
    df["risk_level"] = pd.cut(
        df["churn_probability"],
        bins=[-0.01, 0.3, 0.6, 1.0],
        labels=["Low Risk", "Medium Risk", "High Risk"],
    )
    return df