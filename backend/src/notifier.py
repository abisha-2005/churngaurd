import os
import sqlite3
import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = os.getenv("TWILIO_PHONE_NUMBER")

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

DB_PATH = "models/notification_log.db"


def init_log_db():
    os.makedirs("models", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER,
            customer_id TEXT,
            channel TEXT,
            message TEXT,
            status TEXT,
            sent_at TEXT
        )
    """)
    # Migration for DBs created before analysis_id existed — without this,
    # every business's notification history stays mixed together forever
    # even after this fix ships, because the old rows never get scoped.
    existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(notifications)").fetchall()]
    if "analysis_id" not in existing_cols:
        conn.execute("ALTER TABLE notifications ADD COLUMN analysis_id INTEGER")
    conn.commit()
    conn.close()


def log_notification(analysis_id, customer_id, channel, message, status):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO notifications (analysis_id, customer_id, channel, message, status, sent_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (analysis_id, customer_id, channel, message, status, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_notification_log(analysis_id):
    """
    Returns notifications for ONE analysis only. Each analysis belongs to one
    logged-in user (enforced in main.py before this is ever called), so this
    is what keeps one business's customer contact history from showing up
    for another business.
    """
    import pandas as pd
    init_log_db()   # ensure table + analysis_id column exist before querying
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM notifications WHERE analysis_id = ? ORDER BY id DESC",
            conn, params=(analysis_id,),
        )
    except Exception:
        df = pd.DataFrame(columns=["id", "analysis_id", "customer_id", "channel", "message", "status", "sent_at"])
    conn.close()
    return df


def send_sms(analysis_id, customer_id, to_phone, message, verified_test_number=None):
    """
    Sends a real SMS via Twilio, scoped to a specific analysis_id so the log
    only ever appears under the business/dataset that sent it.

    Trial Twilio accounts can ONLY deliver to a verified number — so when
    verified_test_number is provided, that's where the SMS actually goes
    (the customer's own to_phone is kept only for log/display purposes).
    Falls back to a simulated log entry if credentials are missing or the
    Twilio call fails (e.g. unverified number, network issue).
    """
    init_log_db()

    destination = verified_test_number or to_phone

    if not (TWILIO_SID and TWILIO_TOKEN and TWILIO_PHONE and destination):
        log_notification(analysis_id, customer_id, "SMS", message, "simulated_demo_sent")
        return {"status": "simulated_demo_sent"}

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        msg = client.messages.create(body=message, from_=TWILIO_PHONE, to=destination)
        log_notification(analysis_id, customer_id, "SMS", message, f"sent_real:{msg.sid}")
        return {"status": "sent_real", "sid": msg.sid}
    except Exception as e:
        # Log the real reason instead of silently hiding it — helps you debug
        # during the demo (unverified number, bad E.164 format, etc.)
        log_notification(analysis_id, customer_id, "SMS", message, f"failed:{str(e)[:150]}")
        return {"status": f"failed: {str(e)}"}


def send_email(analysis_id, customer_id, to_email, subject, message):
    """
    Sends a real email via Gmail SMTP, scoped to a specific analysis_id.
    Falls back to a simulated log entry if Gmail credentials are missing
    or the send fails.
    """
    init_log_db()

    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD):
        log_notification(analysis_id, customer_id, "Email", f"{subject}: {message}", "simulated_demo_sent")
        return {"status": "simulated_demo_sent"}

    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=8) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())

        log_notification(analysis_id, customer_id, "Email", f"{subject}: {message}", "sent_real")
        return {"status": "sent_real"}
    except Exception as e:
        log_notification(analysis_id, customer_id, "Email", f"{subject}: {message}", f"failed:{str(e)[:150]}")
        return {"status": f"failed: {str(e)}"}


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_URL = "http://localhost:11434/api/generate"

_FALLBACK_MESSAGE = "Hi! We miss you. Here's a special offer just for you — come back and save today!"

DISCOUNT_BY_RISK = {
    "High Risk": 20,
    "Medium Risk": 10,
    "Low Risk": 0,
}


def _static_retention_message(risk_level=None):
    """Used when Ollama is unreachable or returns something unusable."""
    discount = DISCOUNT_BY_RISK.get(risk_level, 0)
    if discount:
        return f"We miss you! Here's {discount}% off your next order — come back and see what's new."
    return _FALLBACK_MESSAGE


def generate_retention_message(customer_id, segment, top_reason, risk_level=None):
    """
    Generates a short, personalized retention message using a local Ollama
    model, based on the customer's segment, top SHAP risk reason, and a
    discount tier derived from risk_level (High Risk = bigger discount).
    Falls back to a static template if Ollama is not running or errors out —
    so the demo never breaks even if the local model isn't up.
    """
    discount = DISCOUNT_BY_RISK.get(risk_level, 0)
    discount_line = (
        f"Offer them a {discount}% discount on their next purchase as an incentive to return."
        if discount else
        "Do not mention any discount — just a warm, low-pressure nudge to come back."
    )

    prompt = f"""You are writing a short SMS/email retention message for a customer
who is at risk of churning from a business.

Customer segment: {segment}
Top reason they're at risk: {top_reason}
{discount_line}

Write ONE short, warm, personalized message (max 2 sentences, under 200 characters)
encouraging them to come back, referencing their situation naturally without
sounding robotic. Do not include a greeting like "Dear customer" — keep it casual.
Respond with ONLY the message text, no quotes, no explanation, no markdown."""

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()

        # Basic sanity checks — reject empty or absurdly long responses
        if not text or len(text) > 400:
            return _static_retention_message(risk_level)

        return text
    except Exception:
        return _static_retention_message(risk_level)