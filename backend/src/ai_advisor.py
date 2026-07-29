import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
try:
    import google.generativeai as genai
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
except ImportError:
    genai = None

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_URL = "http://localhost:11434/api/generate"


def _safe_num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _sanitize_for_streamlit_markdown(text: str) -> str:
    """
    Streamlit's st.markdown() treats a lone `$` as the start of a LaTeX math
    block. LLM answers often contain raw dollar figures like "$144,926.48",
    which then get mangled into garbled math rendering. Escaping `$` as `\\$`
    keeps the literal dollar sign without triggering LaTeX parsing.
    """
    if not text:
        return text
    return text.replace("$", "\\$")


def build_business_context(churn_df: pd.DataFrame) -> str:
    """
    Summarizes the scored dataset into compact text the LLM can reason over —
    risk distribution, revenue at risk, and the top spenders in each risk
    bucket. Kept short and numeric on purpose so it's cheap to send on every
    chat turn.
    """
    df = churn_df.copy()
    df["monetary"] = _safe_num(df.get("monetary", 0))
    df["churn_probability"] = _safe_num(df.get("churn_probability", 0))

    total_customers = len(df)
    risk_counts = df["risk_level"].value_counts().to_dict() if "risk_level" in df.columns else {}

    high_risk = df[df["risk_level"] == "High Risk"] if "risk_level" in df.columns else df.iloc[0:0]
    revenue_at_risk = round(high_risk["monetary"].sum(), 2)
    total_revenue = round(df["monetary"].sum(), 2)
    spender_cols = ["customer_id", "monetary", "churn_probability"]
    if "segment" in high_risk.columns:
        spender_cols.append("segment")
    if "risk_reason" in high_risk.columns:
        spender_cols.append("risk_reason")

    top_high_risk_spenders = (
        high_risk.sort_values("monetary", ascending=False).head(10)[spender_cols]
        if "customer_id" in high_risk.columns
        else pd.DataFrame()
    )
    segment_summary = (
        df.groupby("segment")["monetary"].agg(["count", "sum"]).round(2).to_dict("index")
        if "segment" in df.columns
        else {}
    )

    lines = [
        f"Total customers: {total_customers}",
        f"Risk level counts: {risk_counts}",
        f"Total revenue (monetary) across all customers: {total_revenue}",
        f"Revenue held by High Risk customers (revenue at risk): {revenue_at_risk}",
        f"Segment breakdown (count, total monetary): {segment_summary}",
    ]

    if not top_high_risk_spenders.empty:
        lines.append("Top 10 highest-spending High Risk customers:")
        for _, row in top_high_risk_spenders.iterrows():
            lines.append(
                f"  - {row['customer_id']}: spend={row['monetary']}, "
                f"churn_prob={round(float(row['churn_probability']), 2)}, "
                f"segment={row.get('segment', 'N/A')}, reason={str(row.get('risk_reason', ''))[:120]}"
            )

    return "\n".join(lines)


def _fallback_answer(question, churn_df, error_detail=None):
    """
    Rule-based answer used only if BOTH Claude and Ollama are unreachable —
    keeps the demo working even without any AI backend. error_detail (if
    given) is the actual exception from whichever call failed, surfaced so
    the failure can be diagnosed instead of silently hidden.
    """
    df = churn_df.copy()
    df["monetary"] = _safe_num(df.get("monetary", 0))

    if "risk_level" not in df.columns:
        return "I don't have risk-scored data yet — please train the churn model first."

    high_risk = df[df["risk_level"] == "High Risk"].sort_values("monetary", ascending=False)
    revenue_at_risk = round(high_risk["monetary"].sum(), 2)

    if high_risk.empty:
        return "No high-risk customers found in this dataset right now."

    top5 = high_risk.head(5)
    names = ", ".join(str(c) for c in top5["customer_id"])
    label = f"(Offline fallback — {error_detail})" if error_detail else "(Offline fallback — no AI backend reachable)"
    return (
        f"{label} "
        f"There are {len(high_risk)} high-risk customers holding ₹{revenue_at_risk} in revenue. "
        f"Top 5 highest-spending high-risk customers to prioritize: {names}. "
        f"Consider targeted discounts for these first."
    )


def _system_prompt(context):
    return f"""You are a retention strategy advisor for a business owner using a
customer churn prediction dashboard. You have the following live data snapshot
from their uploaded dataset:

{context}

Answer the business owner's question using ONLY this data. Give concrete,
actionable recommendations (who to target, what offer, rough revenue impact)
in plain language — no jargon like "SHAP" or "model". Keep answers under
150 words unless the question needs a list. If the data doesn't contain
something needed to answer precisely, say so plainly instead of guessing."""


def _ask_claude(question, context, chat_history):
    messages = list(chat_history) if chat_history else []
    messages.append({"role": "user", "content": question})

    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 500,
            "system": _system_prompt(context),
            "messages": messages,
        },
        timeout=20,
    )

    if not resp.ok:
        # Surface Anthropic's actual error body (not just "400 Bad Request") —
        # e.g. {"error": {"type": "invalid_request_error", "message": "..."}}
        try:
            body = resp.json()
            detail = body.get("error", {}).get("message", resp.text[:300])
        except Exception:
            detail = resp.text[:300]
        raise RuntimeError(f"{resp.status_code} {detail}")

    data = resp.json()
    text_parts = [block["text"] for block in data.get("content", []) if block.get("type") == "text"]
    return "\n".join(text_parts).strip()


def _ask_gemini(question, context, chat_history):
    if genai is None or not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY not set — check your .env file")

    history_text = ""
    if chat_history:
        for turn in chat_history[-6:]:  # keep the prompt short — last few turns only
            speaker = "Business owner" if turn["role"] == "user" else "Advisor"
            history_text += f"{speaker}: {turn['content']}\n"

    prompt = f"""{_system_prompt(context)}

Conversation so far:
{history_text}
Business owner: {question}
Advisor:"""

    model = genai.GenerativeModel("gemini-3.6-flash")
    response = model.generate_content(prompt)
    return response.text.strip()


def _ask_ollama(question, context, chat_history):
    """
    Ollama's /api/generate is single-turn (plain prompt string, no message
    array), so prior turns are folded into the prompt as plain text instead.
    """
    history_text = ""
    if chat_history:
        for turn in chat_history[-6:]:  # keep the prompt short — last few turns only
            speaker = "Business owner" if turn["role"] == "user" else "Advisor"
            history_text += f"{speaker}: {turn['content']}\n"

    prompt = f"""{_system_prompt(context)}

Conversation so far:
{history_text}
Business owner: {question}
Advisor:"""

    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def ask_strategy_ai(question: str, churn_df: pd.DataFrame, chat_history=None, use_local: bool = False):
    """
    Answers a free-form business strategy question (e.g. "who should we give
    offers to", "how much revenue can we save") using the churn predictions
    and segments as grounding context.

    Returns a tuple: (answer_text, backend_used) where backend_used is one
    of "gemini", "ollama", or "fallback" — so the caller can show exactly
    which AI backend actually produced the answer, instead of guessing.

    Priority order:
    - use_local=True: skips straight to the local Ollama model only.
    - use_local=False (default): tries Gemini first (same GEMINI_API_KEY
      already used for schema mapping — fast and free-tier friendly), and if
      that fails for any reason, automatically falls back to local Ollama as
      a safety net so the demo still works. Claude is available via
      _ask_claude if you want to wire it back in later (e.g. once billing is
      set up), but isn't part of the default chain right now.
    - If every backend fails, returns a rule-based answer with the actual
      error included, so failures are debuggable instead of silent.

    chat_history: optional list of {"role": "user"/"assistant", "content": str}
    from earlier turns, so follow-up questions carry context.
    """
    context = build_business_context(churn_df)

    if use_local:
        try:
            answer = _ask_ollama(question, context, chat_history)
            if answer:
                return _sanitize_for_streamlit_markdown(answer), "ollama"
            return _fallback_answer(question, churn_df, "Ollama returned empty response"), "fallback"
        except Exception as e:
            print(f"[ai_advisor] Ollama call failed: {e}")
            return _fallback_answer(question, churn_df, f"Ollama error: {e}"), "fallback"

    gemini_error = None
    try:
        answer = _ask_gemini(question, context, chat_history)
        if answer:
            return _sanitize_for_streamlit_markdown(answer), "gemini"
        gemini_error = "Gemini returned empty response"
    except Exception as e:
        gemini_error = str(e)
        print(f"[ai_advisor] Gemini call failed, falling back to Ollama: {e}")

    try:
        answer = _ask_ollama(question, context, chat_history)
        if answer:
            return _sanitize_for_streamlit_markdown(answer), "ollama"
        return (
            _fallback_answer(question, churn_df, f"Gemini error: {gemini_error}; Ollama returned empty response"),
            "fallback",
        )
    except Exception as e:
        print(f"[ai_advisor] Ollama call also failed: {e}")
        return (
            _fallback_answer(question, churn_df, f"Gemini error: {gemini_error}; Ollama error: {e}"),
            "fallback",
        )