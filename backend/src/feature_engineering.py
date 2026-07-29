import pandas as pd
import numpy as np

def build_rfm_features(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """
    Takes the raw dataframe + AI-confirmed column mapping,
    and returns a standardized RFM feature dataframe usable
    by any business/domain.
    """
    reverse_map = {}
    for orig_col, std_field in mapping.items():
        if std_field != "other":
            reverse_map.setdefault(std_field, orig_col)

    result = pd.DataFrame()

    # Customer ID (mandatory)
    if "customer_id" in reverse_map:
        result["customer_id"] = df[reverse_map["customer_id"]]
    else:
        result["customer_id"] = df.index.astype(str)

    # Phone number — optional, used for SMS notifications
    if "phone_number" in reverse_map:
        result["phone_number"] = df[reverse_map["phone_number"]].astype(str)
    else:
        result["phone_number"] = "N/A"

    # Email — optional, used for email notifications
    if "email" in reverse_map:
        result["email"] = df[reverse_map["email"]].astype(str)
    else:
        result["email"] = "N/A"

    # Recency (mandatory) — lower is better (more recent)
    if "recency" in reverse_map:
        result["recency"] = pd.to_numeric(df[reverse_map["recency"]], errors="coerce")
    else:
        result["recency"] = np.nan

    # Frequency — higher is better
    if "frequency" in reverse_map:
        result["frequency"] = pd.to_numeric(df[reverse_map["frequency"]], errors="coerce")
    else:
        result["frequency"] = np.nan

    # Monetary — higher is better
    if "monetary" in reverse_map:
        result["monetary"] = pd.to_numeric(df[reverse_map["monetary"]], errors="coerce")
    else:
        result["monetary"] = np.nan

    # Feedback score — optional
    if "feedback_score" in reverse_map:
        result["feedback_score"] = pd.to_numeric(df[reverse_map["feedback_score"]], errors="coerce")

    # Signup date / tenure — optional
    if "signup_date" in reverse_map:
        signup = pd.to_datetime(df[reverse_map["signup_date"]], errors="coerce")
        result["tenure_days"] = (pd.Timestamp.now() - signup).dt.days

    # Fill missing numeric values with median (keeps model training stable)
    for col in ["recency", "frequency", "monetary"]:
        if result[col].isnull().all():
            result[col] = 0
        else:
            result[col] = result[col].fillna(result[col].median())

    # ---- RFM Score (1-5 scale, 5 = best) ----
    result["R_score"] = pd.qcut(result["recency"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    result["F_score"] = pd.qcut(result["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    result["M_score"] = pd.qcut(result["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)

    result["RFM_score"] = result["R_score"] + result["F_score"] + result["M_score"]

    # ---- Customer Segment (business-friendly labels) ----
    def segment(row):
        if row["RFM_score"] >= 12:
            return "Loyal / High Value"
        elif row["RFM_score"] >= 9:
            return "Steady Customer"
        elif row["RFM_score"] >= 6:
            return "At Risk"
        else:
            return "High Risk / Likely Churn"

    result["segment"] = result.apply(segment, axis=1)

    # keep original churn label if it exists in raw data, for model training later
    if "other" in mapping.values():
        for orig_col, std_field in mapping.items():
            if std_field == "other" and orig_col.lower() in ["churn", "churned", "is_churn", "target"]:
                raw = df[orig_col]
                # Handles "Yes"/"No", True/False, or already-numeric 0/1 —
                # pd.to_numeric alone turns "Yes"/"No" into NaN -> all zeros.
                mapped = raw.astype(str).str.strip().str.lower().map({
                    "yes": 1, "no": 0, "true": 1, "false": 0, "1": 1, "0": 0
                })
                result["churn_label"] = mapped.fillna(pd.to_numeric(raw, errors="coerce")).fillna(0).astype(int)

    return result