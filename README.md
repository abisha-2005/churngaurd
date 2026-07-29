# ChurnGuard — Full-Stack (FastAPI + React)

This wraps your existing `src/` pipeline (schema mapping, RFM features, XGBoost model,
SHAP explainability, SMS/Email alerts, AI Strategy Advisor, PDF report) behind a
FastAPI backend with authentication, and a React dashboard matching the ChurnGuard
UI you showed.

## What's new vs the Streamlit app

- **Authentication**: signup/login with JWT, SQLite `users` table (bcrypt-hashed passwords).
- **Multi-user history**: every upload becomes a saved "analysis" tied to your account,
  listed on the Dashboard (`analyses` table in SQLite).
- **Model Comparison**: `backend/src/model_comparison.py` is new — trains Logistic
  Regression, Random Forest, Gradient Boosting, and XGBoost side by side on the same
  RFM features and reports Accuracy/Precision/Recall/AUC for each, plus a
  "Top Churn Drivers" feature-importance panel. Your original `churn_model.py`
  (single XGBoost) is untouched and still used for the main risk scoring.
- Everything else (`schema_mapper.py`, `feature_engineering.py`, `explainability.py`,
  `notifier.py`, `ai_advisor.py`, `report_generator.py`) is your existing code, unmodified.

## 1. Backend setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
copy .env.example .env          # Windows: copy, macOS/Linux: cp
```

Edit `.env` and fill in `GEMINI_API_KEY`, Twilio, and Gmail credentials (same values
you were already using with Streamlit). Set `JWT_SECRET` to any random string.

Run the API:

```bash
uvicorn main:app --reload --port 8000
```

The first run creates `backend/storage/app.db` (SQLite) automatically — no manual
migration needed.

## 2. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`. The Vite dev server proxies `/api/*` to
`http://localhost:8000` (see `vite.config.js`), so no CORS setup needed locally.

## 3. Using it

1. Open `http://localhost:5173` → Create Account (business name, email, password).
2. Dashboard → **New Analysis** → drop a CSV → **Start Analysis**.
   This runs the full pipeline in one click: AI column mapping → RFM features →
   train + compare 4 models → SHAP risk explanations → lands on the Results page.
   (Tick "Review & override AI column mapping" first if you want to correct any
   column guess before it trains — same override the Streamlit app offered.)
3. Results page: stats, risk/segment charts, top churn drivers, model comparison,
   searchable customer table with per-customer **Send** (SMS/email), a **SMS Campaign**
   button to alert every High Risk customer at once, the **AI Strategy Advisor** chat,
   and **Download Report (PDF)**.
4. **SMS Logs** page: paste an analysis ID to see its notification history.

## Notes / known limits (carried over from the Streamlit version)

- Twilio trial accounts can only deliver real SMS to a verified number — enter yours
  in the "Twilio-verified test number" field on the Results page; the demo data's own
  phone numbers are kept for display/logging only.
- Training requires a churn/target column in your CSV (mapped to "other" and named
  something like `Churn`, `Churned`, `is_churn`, or `target`) — same requirement as before.
- The notification log (SMS Logs page) is currently global across all your analyses,
  same as the original Streamlit app's single SQLite log — not yet filtered per analysis_id.
- `GEMINI_API_KEY` issues (silent fallback to Ollama) are a `src/ai_advisor.py` /
  `src/schema_mapper.py` concern, unchanged from before — check the uvicorn terminal
  for the `[ai_advisor] Gemini call failed...` line if answers look off.
