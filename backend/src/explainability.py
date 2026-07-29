import os
import requests
import shap
import pandas as pd
import numpy as np

FEATURE_COLS = ["recency", "frequency", "monetary", "R_score", "F_score", "M_score", "RFM_score"]

FEATURE_LABELS = {
    "recency": "days since last activity",
    "frequency": "engagement frequency",
    "monetary": "value/spend",
    "R_score": "recency score",
    "F_score": "frequency score",
    "M_score": "monetary score",
    "RFM_score": "overall RFM score",
}

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TIMEOUT_SECONDS = 8  # fail fast instead of hanging the whole run


def get_shap_explainer(model):
    return shap.TreeExplainer(model)


def explain_customer(model, churn_df: pd.DataFrame, customer_id: str, top_n: int = 3):
    """
    Returns the top contributing factors (with direction) for a single
    customer's churn prediction, using SHAP values.
    """
    explainer = get_shap_explainer(model)

    row = churn_df[churn_df["customer_id"] == customer_id]
    if row.empty:
        raise ValueError(f"Customer {customer_id} not found.")

    X_row = row[FEATURE_COLS]
    shap_values = explainer.shap_values(X_row)

    values = shap_values[0]
    contributions = list(zip(FEATURE_COLS, values, X_row.iloc[0].values))
    contributions.sort(key=lambda x: abs(x[1]), reverse=True)
    top_factors = contributions[:top_n]

    reasons = []
    for feat, shap_val, actual_val in top_factors:
        direction = "increases" if shap_val > 0 else "decreases"
        reasons.append({
            "feature": FEATURE_LABELS.get(feat, feat),
            "value": round(float(actual_val), 2),
            "impact": direction,
            "shap_value": round(float(shap_val), 4),
        })

    return reasons


def _technical_reason(top_features):
    """Compact fallback string — used if Ollama is down, slow, or skipped by the cap."""
    parts = []
    for feat, shap_val, actual_val in top_features:
        direction = "↑ risk" if shap_val > 0 else "↓ risk"
        label = FEATURE_LABELS.get(feat, feat)
        parts.append(f"{label}={round(float(actual_val), 1)} ({direction})")
    return "; ".join(parts)


def _llm_reason(segment, top_features):
    """
    Turns the top SHAP features into one natural-language sentence via local
    Ollama. Falls back to the technical string on any failure OR if the call
    takes longer than OLLAMA_TIMEOUT_SECONDS — a slow local model should never
    stall the whole explanation run.
    """
    feature_desc = "\n".join(
        f"- {FEATURE_LABELS.get(feat, feat)}: value={round(float(actual_val), 2)}, "
        f"{'pushes risk UP' if shap_val > 0 else 'pushes risk DOWN'}"
        for feat, shap_val, actual_val in top_features
    )

    prompt = f"""You are explaining why a customer is at risk of churning from a business.

Customer segment: {segment}
Top contributing factors from the churn model (SHAP feature importance):
{feature_desc}

Write ONE short, clear sentence (under 25 words) in plain English explaining WHY this
customer is at risk, based only on the factors above. Do not mention "SHAP" or "model" —
speak like you're explaining it to a business owner. Respond with ONLY the sentence,
no quotes, no markdown, no extra explanation."""

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()

        if not text or len(text) > 300:
            return _technical_reason(top_features)
        return text
    except Exception:
        return _technical_reason(top_features)


def explain_all_customers(
    model,
    churn_df: pd.DataFrame,
    top_n: int = 2,
    use_llm: bool = True,
    llm_risk_levels=("High Risk",),
    max_llm_calls: int = 20,
    progress_callback=None,
):
    """
    Batch version — computes SHAP values for ALL customers in one explainer
    call (fast regardless of row count), then builds a `risk_reason` per
    customer.

    - use_llm=True (default): rows whose risk_level is in `llm_risk_levels`
      (High Risk only, by default) get a natural-language sentence via local
      Ollama. Every other row skips the LLM call and gets the compact
      technical string directly.
    - max_llm_calls: HARD CAP on how many Ollama calls happen in one run,
      even within the high-risk subset — the highest churn_probability rows
      get the LLM treatment first, the rest (still high-risk, just past the
      cap) get the technical string instead. This bounds worst-case runtime
      on large datasets (e.g. 300+ rows) regardless of how many are flagged
      high-risk.
    - progress_callback: optional function(done, total) called after each
      row is processed — wire this to a UI progress bar so a slow local
      model never looks like a frozen/stuck spinner.
    - use_llm=False: always returns the technical string for every row
      (fastest — no network calls at all).
    """
    explainer = get_shap_explainer(model)
    X = churn_df[FEATURE_COLS]
    shap_values = explainer.shap_values(X)

    has_risk_level = "risk_level" in churn_df.columns

    # Decide up front WHICH rows get an LLM call, capped at max_llm_calls,
    # prioritizing the highest churn probability first.
    llm_eligible_idx = set()
    if use_llm:
        if has_risk_level:
            eligible = churn_df[churn_df["risk_level"].isin(llm_risk_levels)]
        else:
            eligible = churn_df
        if "churn_probability" in eligible.columns:
            eligible = eligible.sort_values("churn_probability", ascending=False)
        llm_eligible_idx = set(eligible.head(max_llm_calls).index)

    total = len(churn_df)
    reason_strings = []
    for i, (idx, _) in enumerate(churn_df.iterrows()):
        row_values = shap_values[i]
        row_actual = X.iloc[i]
        contributions = list(zip(FEATURE_COLS, row_values, row_actual.values))
        contributions.sort(key=lambda x: abs(x[1]), reverse=True)
        top = contributions[:top_n]

        if idx in llm_eligible_idx:
            segment = churn_df.iloc[i].get("segment", "customer")
            reason = _llm_reason(segment, top)
        else:
            reason = _technical_reason(top)

        reason_strings.append(reason)

        if progress_callback:
            progress_callback(i + 1, total)

    churn_df = churn_df.copy()
    churn_df["risk_reason"] = reason_strings
    return churn_df