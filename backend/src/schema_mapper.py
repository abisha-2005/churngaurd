import os
import json
import requests
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

try:
    import google.generativeai as genai
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
except ImportError:
    genai = None

STANDARD_FIELDS = ["customer_id", "phone_number", "email", "recency", "frequency", "monetary", "signup_date", "feedback_score", "other"]

def build_prompt(column_info):
    return f"""You are a data analyst. Below is column metadata from a customer dataset (any business type — e-commerce, food delivery, SaaS, etc).

Column metadata:
{json.dumps(column_info, indent=2, default=str)}

Map EACH column to exactly ONE of these standard fields: {STANDARD_FIELDS}
- customer_id: unique identifier for a customer
- phone_number: customer's mobile/phone number for SMS notifications
- email: customer's email address for email notifications
- recency: how recently the customer was active (last login/order/visit date)
- frequency: how often the customer engages (order count, visit count, transaction count)
- monetary: value the customer brings (total spend, revenue, amount)
- signup_date: when the customer joined
- feedback_score: rating, satisfaction, NPS, complaints etc.
- other: does not fit any category above

Respond ONLY with valid JSON, no markdown, no explanation, in this exact format:
{{"column_name_1": "standard_field", "column_name_2": "standard_field"}}
"""

def map_columns_gemini(column_info):
    model = genai.GenerativeModel("gemini-flash-latest")
    prompt = build_prompt(column_info)
    response = model.generate_content(prompt)
    text = response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(text)

def map_columns_ollama(column_info, model_name="llama3.1:8b"):
    prompt = build_prompt(column_info)
    resp = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model_name, "prompt": prompt, "stream": False},
    )
    text = resp.json()["response"].strip().replace("```json", "").replace("```", "")
    return json.loads(text)

def map_columns(df, use_local=False):
    column_info = {}
    for col in df.columns:
        sample = df[col].dropna().iloc[0] if df[col].dropna().shape[0] > 0 else None
        column_info[col] = {"dtype": str(df[col].dtype), "sample_value": sample}

    try:
        if use_local:
            return map_columns_ollama(column_info)
        return map_columns_gemini(column_info)
    except Exception as e:
        raise RuntimeError(f"Schema mapping failed: {e}")
