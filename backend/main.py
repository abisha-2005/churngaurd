import os
import sys
import io
import json
import joblib
import pandas as pd
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

sys.path.append(os.path.dirname(__file__))

from database import get_conn, init_db
from auth import hash_password, verify_password, create_access_token, get_current_user
from encryption import encrypt_value, decrypt_value

from src.schema_mapper import map_columns, STANDARD_FIELDS
from src.feature_engineering import build_rfm_features
from src.churn_model import train_churn_model
from src.model_comparison import compare_models, top_churn_drivers
from src.explainability import explain_all_customers
from src.notifier import send_sms, send_email, generate_retention_message, get_notification_log, init_log_db
from src.ai_advisor import ask_strategy_ai
from src.report_generator import generate_pdf_report

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage")
ANALYSES_DIR = os.path.join(STORAGE_DIR, "analyses")
os.makedirs(ANALYSES_DIR, exist_ok=True)

app = FastAPI(title="ChurnGuard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
init_log_db()

# In-memory cache of heavy objects (dataframes, trained models) per analysis_id,
# backed by a joblib file on disk so state survives a server restart.
_analysis_cache = {}


def _data_path(analysis_id: int) -> str:
    return os.path.join(ANALYSES_DIR, str(analysis_id), "data.pkl")


def _load_analysis(analysis_id: int) -> dict:
    if analysis_id in _analysis_cache:
        return _analysis_cache[analysis_id]
    path = _data_path(analysis_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Analysis not found or not processed yet")
    data = joblib.load(path)
    _analysis_cache[analysis_id] = data
    return data


def _save_analysis(analysis_id: int, data: dict):
    _analysis_cache[analysis_id] = data
    folder = os.path.join(ANALYSES_DIR, str(analysis_id))
    os.makedirs(folder, exist_ok=True)
    joblib.dump(data, os.path.join(folder, "data.pkl"))


def _get_owned_analysis_row(analysis_id: int, user_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM analyses WHERE id = ? AND user_id = ?", (analysis_id, user_id)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return dict(row)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    business_name: str
    website: Optional[str] = None
    phone: Optional[str] = None
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@app.post("/auth/signup")
def signup(payload: SignupRequest):
    conn = get_conn()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (payload.email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    cur = conn.execute(
        "INSERT INTO users (business_name, website, phone, email, password_hash) VALUES (?, ?, ?, ?, ?)",
        (payload.business_name, payload.website, payload.phone, payload.email, hash_password(payload.password)),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()

    token = create_access_token(user_id, payload.email)
    return {"access_token": token, "token_type": "bearer", "business_name": payload.business_name}


@app.post("/auth/login")
def login(payload: LoginRequest):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (payload.email,)).fetchone()
    conn.close()

    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token(row["id"], row["email"])
    return {"access_token": token, "token_type": "bearer", "business_name": row["business_name"]}


@app.get("/auth/me")
def me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "business_name": user["business_name"],
        "email": user["email"],
        "website": user["website"],
        "phone": user["phone"],
    }


# ---------------------------------------------------------------------------
# Dashboard — list analyses
# ---------------------------------------------------------------------------

@app.get("/analyses")
def list_analyses(user=Depends(get_current_user)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM analyses WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Step 1: Upload CSV
# ---------------------------------------------------------------------------

@app.post("/analyses/upload")
async def upload_csv(file: UploadFile = File(...), user=Depends(get_current_user)):
    raw_bytes = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {e}")

    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO analyses (user_id, filename, status) VALUES (?, ?, 'uploaded')",
        (user["id"], file.filename),
    )
    conn.commit()
    analysis_id = cur.lastrowid
    conn.close()

    folder = os.path.join(ANALYSES_DIR, str(analysis_id))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "raw.csv"), "wb") as f:
        f.write(raw_bytes)

    col_info = []
    for col in df.columns:
        sample = df[col].dropna().iloc[0] if df[col].dropna().shape[0] > 0 else None
        col_info.append({
            "column": col,
            "dtype": str(df[col].dtype),
            "sample_value": None if sample is None else str(sample),
            "missing_values": int(df[col].isnull().sum()),
        })

    data = {"raw_df": df, "filename": file.filename}
    _save_analysis(analysis_id, data)

    return {
        "analysis_id": analysis_id,
        "rows": df.shape[0],
        "columns": df.shape[1],
        "column_info": col_info,
        "preview": json.loads(df.head(10).to_json(orient="records")),
    }


# ---------------------------------------------------------------------------
# Step 2: AI schema mapping
# ---------------------------------------------------------------------------

class MappingDetectRequest(BaseModel):
    use_local: bool = False


@app.post("/analyses/{analysis_id}/detect-mapping")
def detect_mapping(analysis_id: int, payload: MappingDetectRequest, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    try:
        mapping = map_columns(data["raw_df"], use_local=payload.use_local)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    data["suggested_mapping"] = mapping
    _save_analysis(analysis_id, data)

    return {"mapping": mapping, "standard_fields": STANDARD_FIELDS}


class ConfirmMappingRequest(BaseModel):
    mapping: dict


@app.post("/analyses/{analysis_id}/confirm-mapping")
def confirm_mapping(analysis_id: int, payload: ConfirmMappingRequest, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    rfm_df = build_rfm_features(data["raw_df"], payload.mapping)

    # Encrypt PII columns before anything gets written to disk (pickle file).
    if "phone_number" in rfm_df.columns:
        rfm_df["phone_number"] = rfm_df["phone_number"].apply(encrypt_value)
    if "email" in rfm_df.columns:
        rfm_df["email"] = rfm_df["email"].apply(encrypt_value)

    data["final_mapping"] = payload.mapping
    data["rfm_df"] = rfm_df
    _save_analysis(analysis_id, data)

    conn = get_conn()
    conn.execute("UPDATE analyses SET status = 'mapped' WHERE id = ?", (analysis_id,))
    conn.commit()
    conn.close()

    preview_df = rfm_df.head(20).copy()
    if "phone_number" in preview_df.columns:
        preview_df["phone_number"] = preview_df["phone_number"].apply(decrypt_value)
    if "email" in preview_df.columns:
        preview_df["email"] = preview_df["email"].apply(decrypt_value)

    segment_counts = rfm_df["segment"].value_counts().to_dict()
    return {
        "segment_counts": segment_counts,
        "rfm_preview": json.loads(preview_df.to_json(orient="records")),
    }


# ---------------------------------------------------------------------------
# Step 3: Train + compare models
# ---------------------------------------------------------------------------

@app.post("/analyses/{analysis_id}/train")
def train(analysis_id: int, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    if "rfm_df" not in data:
        raise HTTPException(status_code=400, detail="Confirm column mapping before training")

    try:
        model, metrics, churn_df = train_churn_model(data["rfm_df"])
        comparison = compare_models(data["rfm_df"])
        drivers = top_churn_drivers(model)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    data["trained_model"] = model
    data["model_metrics"] = metrics
    data["churn_df"] = churn_df
    data["model_comparison"] = comparison
    data["top_drivers"] = drivers
    _save_analysis(analysis_id, data)

    # Auto-run Explain right after training so risk_reason is available
    # immediately — user doesn't need to click a separate Explain button.
    try:
        explained_df = explain_all_customers(model, churn_df, max_llm_calls=20)
        explained_df["customer_id"] = explained_df["customer_id"].astype(str)

        for stale_col in ["phone_number", "email"]:
            if stale_col in explained_df.columns:
                explained_df = explained_df.drop(columns=[stale_col])

        contact_cols = ["customer_id"]
        rfm_df = data["rfm_df"]
        if "phone_number" in rfm_df.columns:
            contact_cols.append("phone_number")
        if "email" in rfm_df.columns:
            contact_cols.append("email")

        contact_lookup = rfm_df[contact_cols].drop_duplicates(subset="customer_id").copy()
        contact_lookup["customer_id"] = contact_lookup["customer_id"].astype(str)
        explained_df = explained_df.merge(contact_lookup, on="customer_id", how="left")

        data["explained_df"] = explained_df
        _save_analysis(analysis_id, data)
    except Exception as e:
        print(f"[train] auto-explain failed, user can retry via /explain: {e}")

    total = len(churn_df)
    churn_rate = round(float((churn_df["churn_probability"] >= 0.5).mean() * 100), 1)
    high_risk = int((churn_df["risk_level"] == "High Risk").sum())

    conn = get_conn()
    conn.execute(
        "UPDATE analyses SET status='explained', total_customers=?, churn_rate=?, "
        "high_risk_count=?, model_accuracy=?, best_model=? WHERE id=?",
        (total, churn_rate, high_risk, metrics["accuracy"] * 100, comparison["best"], analysis_id),
    )
    conn.commit()
    conn.close()

    return {
        "metrics": metrics,
        "total_customers": total,
        "churn_rate": churn_rate,
        "high_risk_count": high_risk,
        "model_comparison": comparison,
        "top_drivers": drivers,
    }


class PredictRequest(BaseModel):
    source_analysis_id: int  # the analysis_id whose trained model you want to reuse


@app.post("/analyses/{analysis_id}/predict")
def predict(analysis_id: int, payload: PredictRequest, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    if "rfm_df" not in data:
        raise HTTPException(status_code=400, detail="Confirm column mapping before predicting")

    _get_owned_analysis_row(payload.source_analysis_id, user["id"])
    source_data = _load_analysis(payload.source_analysis_id)

    if "trained_model" not in source_data:
        raise HTTPException(status_code=400, detail="Source analysis has no trained model")

    from src.churn_model import predict_with_existing_model

    try:
        churn_df = predict_with_existing_model(source_data["trained_model"], data["rfm_df"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    data["churn_df"] = churn_df
    data["trained_model"] = source_data["trained_model"]
    data["model_metrics"] = source_data.get("model_metrics")
    data["model_comparison"] = source_data.get("model_comparison")
    data["top_drivers"] = source_data.get("top_drivers")

    # FIX: predict() never generated explanations, so explained_df was
    # missing and /alert always failed with "Generate explanations before
    # sending alerts", even though a model had already been applied.
    try:
        explained_df = explain_all_customers(data["trained_model"], churn_df, max_llm_calls=20)
        explained_df["customer_id"] = explained_df["customer_id"].astype(str)

        for stale_col in ["phone_number", "email"]:
            if stale_col in explained_df.columns:
                explained_df = explained_df.drop(columns=[stale_col])

        contact_cols = ["customer_id"]
        rfm_df = data["rfm_df"]
        if "phone_number" in rfm_df.columns:
            contact_cols.append("phone_number")
        if "email" in rfm_df.columns:
            contact_cols.append("email")

        contact_lookup = rfm_df[contact_cols].drop_duplicates(subset="customer_id").copy()
        contact_lookup["customer_id"] = contact_lookup["customer_id"].astype(str)
        explained_df = explained_df.merge(contact_lookup, on="customer_id", how="left")

        data["explained_df"] = explained_df
    except Exception as e:
        print(f"[predict] auto-explain failed, user can retry via /explain: {e}")

    _save_analysis(analysis_id, data)

    total = len(churn_df)
    high_risk = int((churn_df["risk_level"] == "High Risk").sum())
    churn_rate = round(float((churn_df["churn_probability"] >= 0.5).mean() * 100), 1)
    source_metrics = source_data.get("model_metrics") or {}
    model_accuracy = source_metrics.get("accuracy", 0) * 100

    conn = get_conn()
    conn.execute(
        "UPDATE analyses SET status='trained', total_customers=?, high_risk_count=?, "
        "churn_rate=?, model_accuracy=? WHERE id=?",
        (total, high_risk, churn_rate, model_accuracy, analysis_id),
    )
    conn.commit()
    conn.close()

    return {
        "total_customers": total,
        "high_risk_count": high_risk,
        "churn_rate": churn_rate,
        "model_accuracy": model_accuracy,
        "used_model_from_analysis": payload.source_analysis_id,
    }

# ---------------------------------------------------------------------------
# Step 4: Explainability (SHAP)
# ---------------------------------------------------------------------------

@app.post("/analyses/{analysis_id}/explain")
def explain(analysis_id: int, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    if "churn_df" not in data:
        raise HTTPException(status_code=400, detail="Train the model before generating explanations")

    try:
        explained_df = explain_all_customers(
            data["trained_model"], data["churn_df"], max_llm_calls=20,
        )
        explained_df["customer_id"] = explained_df["customer_id"].astype(str)

        for stale_col in ["phone_number", "email"]:
            if stale_col in explained_df.columns:
                explained_df = explained_df.drop(columns=[stale_col])

        contact_cols = ["customer_id"]
        rfm_df = data["rfm_df"]
        if "phone_number" in rfm_df.columns:
            contact_cols.append("phone_number")
        if "email" in rfm_df.columns:
            contact_cols.append("email")

        contact_lookup = rfm_df[contact_cols].drop_duplicates(subset="customer_id").copy()
        contact_lookup["customer_id"] = contact_lookup["customer_id"].astype(str)
        explained_df = explained_df.merge(contact_lookup, on="customer_id", how="left")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    data["explained_df"] = explained_df
    _save_analysis(analysis_id, data)

    conn = get_conn()
    conn.execute("UPDATE analyses SET status='explained' WHERE id=?", (analysis_id,))
    conn.commit()
    conn.close()

    return {"status": "done", "rows_explained": len(explained_df)}


# ---------------------------------------------------------------------------
# Results — full dashboard payload
# ---------------------------------------------------------------------------

@app.get("/analyses/{analysis_id}/results")
def results(analysis_id: int, user=Depends(get_current_user)):
    row = _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    if "churn_df" not in data:
        raise HTTPException(status_code=400, detail="Train the model first")

    df = data.get("explained_df", data["churn_df"]).copy()
    df["monetary"] = pd.to_numeric(df.get("monetary", 0), errors="coerce").fillna(0)

    if "phone_number" in df.columns:
        df["phone_number"] = df["phone_number"].apply(decrypt_value)
    if "email" in df.columns:
        df["email"] = df["email"].apply(decrypt_value)

    risk_counts = df["risk_level"].value_counts().to_dict()
    segment_counts = df["segment"].value_counts().to_dict() if "segment" in df.columns else {}
    revenue_by_risk = df.groupby("risk_level")["monetary"].sum().round(2).to_dict()

    display_cols = ["customer_id", "segment", "risk_level", "churn_probability",
                     "recency", "monetary", "phone_number", "email"]
    if "risk_reason" in df.columns:
        display_cols.append("risk_reason")
    display_cols = [c for c in display_cols if c in df.columns]

    customers = df[display_cols].sort_values("churn_probability", ascending=False)
    customers_json = json.loads(customers.to_json(orient="records"))

    return {
        "analysis": row,
        "total_customers": len(df),
        "churn_rate": round(float((df["churn_probability"] >= 0.5).mean() * 100), 1) if "churn_probability" in df.columns else None,
        "risk_distribution": risk_counts,
        "segment_distribution": segment_counts,
        "revenue_by_risk": revenue_by_risk,
        "model_metrics": data.get("model_metrics"),
        "model_comparison": data.get("model_comparison"),
        "top_drivers": data.get("top_drivers"),
        "customers": customers_json,
        "explained": "explained_df" in data,
    }


# ---------------------------------------------------------------------------
# Step 6: Alerts (SMS / Email)
# ---------------------------------------------------------------------------

class AlertRequest(BaseModel):
    verified_test_number: Optional[str] = None


def _is_valid_contact(value):
    if value is None:
        return False
    text = str(value).strip()
    return text != "" and text.upper() != "N/A" and text.lower() != "nan"


@app.post("/analyses/{analysis_id}/alert/{customer_id}")
def send_alert(analysis_id: int, customer_id: str, payload: AlertRequest, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    df = data.get("explained_df")
    if df is None:
        raise HTTPException(status_code=400, detail="Generate explanations before sending alerts")

    row = df[df["customer_id"] == customer_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Customer not found")
    row = row.iloc[0]

    message = generate_retention_message(
        customer_id, row.get("segment"), row.get("risk_reason"), row.get("risk_level")
    )

    # Decrypt right here, at the point of use — never stored in plaintext.
    phone_plain = decrypt_value(row.get("phone_number"))
    email_plain = decrypt_value(row.get("email"))

    results_out = {}
    has_phone = _is_valid_contact(phone_plain)
    has_email = _is_valid_contact(email_plain)

    if has_phone:
        branded_message = f"{user['business_name']}: {message}"
        results_out["sms"] = send_sms(
            analysis_id, customer_id, phone_plain, branded_message,
            verified_test_number=payload.verified_test_number,
        )
    if has_email:
        results_out["email"] = send_email(analysis_id, customer_id, email_plain, f"A Message from {user['business_name']}", message)
    if not results_out:
        raise HTTPException(status_code=400, detail="No phone number or email found for this customer")

    return {"message": message, "results": results_out}


@app.post("/analyses/{analysis_id}/alerts/campaign")
def send_campaign(analysis_id: int, payload: AlertRequest, user=Depends(get_current_user)):
    """Sends alerts to every High Risk customer in one call — the 'SMS Campaign' button."""
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    df = data.get("explained_df")
    if df is None:
        raise HTTPException(status_code=400, detail="Generate explanations before sending alerts")

    high_risk = df[df["risk_level"] == "High Risk"]
    sent, skipped = [], []

    for _, row in high_risk.iterrows():
        message = generate_retention_message(
            row["customer_id"], row.get("segment"), row.get("risk_reason"), row.get("risk_level")
        )

        # Decrypt right here, at the point of use — never stored in plaintext.
        phone_plain = decrypt_value(row.get("phone_number"))
        email_plain = decrypt_value(row.get("email"))

        has_phone = _is_valid_contact(phone_plain)
        has_email = _is_valid_contact(email_plain)

        if not (has_phone or has_email):
            skipped.append(row["customer_id"])
            continue

        channel_results = {}
        if has_phone:
            branded_message = f"{user['business_name']}: {message}"
            channel_results["sms"] = send_sms(
                analysis_id, row["customer_id"], phone_plain, branded_message,
                verified_test_number=payload.verified_test_number,
            )
        if has_email:
            channel_results["email"] = send_email(
                analysis_id, row["customer_id"], email_plain, f"A Message from {user['business_name']}", message
            )
        sent.append({"customer_id": row["customer_id"], "results": channel_results})

    return {"sent_count": len(sent), "skipped_count": len(skipped), "sent": sent, "skipped": skipped}


@app.get("/analyses/{analysis_id}/notifications")
def notifications(analysis_id: int, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    log_df = get_notification_log(analysis_id)
    return json.loads(log_df.to_json(orient="records"))


# ---------------------------------------------------------------------------
# Step 7: AI Strategy Advisor chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str
    use_local: bool = False


@app.post("/analyses/{analysis_id}/advisor/chat")
def advisor_chat(analysis_id: int, payload: ChatRequest, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    df = data.get("explained_df", data.get("churn_df"))
    if df is None:
        raise HTTPException(status_code=400, detail="Train the model before asking the advisor")

    history = data.setdefault("advisor_chat_history", [])
    history_for_call = [{"role": m["role"], "content": m["content"]} for m in history]

    try:
        answer, backend_used = ask_strategy_ai(
            payload.question, df, chat_history=history_for_call, use_local=payload.use_local,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advisor failed: {e}")

    history.append({"role": "user", "content": payload.question})
    history.append({"role": "assistant", "content": answer, "backend": backend_used})
    _save_analysis(analysis_id, data)

    return {"answer": answer, "backend": backend_used}


@app.get("/analyses/{analysis_id}/advisor/history")
def advisor_history(analysis_id: int, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)
    return data.get("advisor_chat_history", [])


# ---------------------------------------------------------------------------
# Step 8: PDF report
# ---------------------------------------------------------------------------

@app.get("/analyses/{analysis_id}/report")
def download_report(analysis_id: int, user=Depends(get_current_user)):
    _get_owned_analysis_row(analysis_id, user["id"])
    data = _load_analysis(analysis_id)

    if "churn_df" not in data:
        raise HTTPException(status_code=400, detail="Train the model first")

    folder = os.path.join(ANALYSES_DIR, str(analysis_id))
    output_path = os.path.join(folder, "retention_report.pdf")

    try:
        generate_pdf_report(
            churn_df=data["churn_df"],
            explained_df=data.get("explained_df"),
            notification_log_df=get_notification_log(analysis_id),
            model_metrics=data.get("model_metrics"),
            output_path=output_path,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not generate report: {e}")

    return FileResponse(output_path, media_type="application/pdf", filename="retention_report.pdf")


@app.get("/")
def root():
    return {"status": "ChurnGuard API running"}