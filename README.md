# ChurnGuard

ChurnGuard is an AI-powered Customer Behavior and Retention Prediction System. It helps businesses identify customers who are likely to churn, understand *why* they're at risk, and automatically take retention action — before it's too late.

## Problem Statement

Businesses often lose customers without knowing they were at risk until it's too late. ChurnGuard solves this by predicting churn in advance, explaining the reasoning behind each prediction, and triggering automated retention actions.

## Features

- **Secure Authentication** – JWT-based login system
- **Dataset Upload** – Upload customer data as CSV
- **Smart Column Mapping** – Auto-detects and lets users confirm column mapping to required fields (customer ID, recency, frequency, monetary value, etc.)
- **Data Preprocessing** – Handles missing values and engineers RFM (Recency, Frequency, Monetary) features
- **Churn Prediction** – ML models (Logistic Regression, Random Forest, Gradient Boosting, XGBoost) predict churn probability
- **Explainability** – SHAP values explain *why* a customer is predicted to churn
- **Dashboard & Reports** – Visual dashboard with churn insights + downloadable PDF reports
- **Automated Retention Actions** – SMS (Twilio) and email (Gmail SMTP) alerts sent to at-risk customers
- **AI Retention Advisor** – Gemini API (with local Ollama fallback) generates personalized retention recommendations

## Tech Stack

- **Backend:** FastAPI, Python
- **Frontend:** React (Vite)
- **Database:** SQLite
- **ML:** scikit-learn, XGBoost, SHAP
- **Notifications:** Twilio (SMS), Gmail SMTP (Email)
- **AI Advisor:** Gemini API / Ollama (local fallback)

## Workflow

1. **Login** – User logs in via JWT-secured authentication
2. **Upload Dataset** – User uploads a CSV file
3. **Column Mapping** – System detects columns; user confirms mapping to required fields
4. **Preprocessing** – Missing values handled; RFM features engineered
5. **Prediction** – ML model predicts churn probability per customer
6. **Explainability** – SHAP explains the reasoning behind each prediction
7. **Dashboard & Report** – Results visualized; PDF report generated
8. **Notification & Action** – At-risk customers get automated SMS/email alerts with AI-driven retention recommendations

## Getting Started

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## License

This project was built for academic/hackathon purposes.