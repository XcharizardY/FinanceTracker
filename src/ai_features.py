"""
AI Features Module

Supports OpenAI API integration with automatic fallback to a local statistical engine
when API keys are missing, invalid, or out of credits (429 Quota Exceeded).
"""

import os
import json
from functools import lru_cache
from typing import Any, List, Dict, Optional

import pandas as pd
from openai import OpenAI

# Dynamic Path Resolution
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "ai_config.json")

DEFAULT_MODEL = "gpt-4o-mini"
FALLBACK_MODELS = ["gpt-4o-mini", "gpt-3.5-turbo"]
REQUEST_TIMEOUT_SEC = 15
MAX_RETRIES = 0

# ---------------- Internal Config & API Helpers ----------------

def _load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _is_valid_key(api_key: str, base_url: Optional[str]) -> bool:
    key = str(api_key).strip()
    if not key or "REPLACE_ME" in key or "YOUR-" in key or "..." in key:
        return False
    if base_url:
        return True
    return key.startswith("sk-")

def _get_api_key() -> Optional[str]:
    config = _load_config()
    base_url = os.getenv("OPENAI_BASE_URL") or config.get("base_url")
    env_key = os.getenv("OPENAI_API_KEY")
    cfg_key = config.get("api_key")

    if env_key and _is_valid_key(env_key, base_url):
        return str(env_key).strip()
    if cfg_key and _is_valid_key(cfg_key, base_url):
        return str(cfg_key).strip()
    return None

def _get_model() -> str:
    config = _load_config()
    return os.getenv("OPENAI_MODEL") or config.get("model") or DEFAULT_MODEL

def _get_base_url() -> Optional[str]:
    config = _load_config()
    base_url = os.getenv("OPENAI_BASE_URL") or config.get("base_url")
    if base_url:
        base_url = str(base_url).strip()
    if base_url and not base_url.startswith(("http://", "https://")):
        return None
    return base_url

@lru_cache(maxsize=4)
def _get_client_cached(api_key: str, base_url: Optional[str]) -> OpenAI:
    kwargs = {"api_key": api_key, "timeout": REQUEST_TIMEOUT_SEC, "max_retries": MAX_RETRIES}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)

def _extract_text(response: Any) -> str:
    if hasattr(response, "choices"):
        try:
            return response.choices[0].message.content
        except Exception:
            pass
    return ""

def _create_response(prompt: str) -> Optional[str]:
    api_key = _get_api_key()
    if not api_key:
        return None  # Triggers offline mode

    try:
        client = _get_client_cached(api_key, _get_base_url())
        model = _get_model()
        messages = [{"role": "user", "content": prompt}]
        res = client.chat.completions.create(model=model, messages=messages)
        return _extract_text(res)
    except Exception as e:
        err_msg = str(e).lower()
        if "429" in err_msg or "quota" in err_msg or "insufficient_quota" in err_msg:
            return None  # Quietly fall back to offline engine on payment errors
        raise RuntimeError(f"AI API Error: {str(e)}") from e

# ---------------- Public Features (Offline Fallback Engine) ----------------

def suggest_category(description: str, categories: List[str]) -> Optional[str]:
    if not description or not categories: return None
    categories_clean = [str(c).strip() for c in categories if str(c).strip()]
    
    # Try online API first
    prompt = f"Choose best category from {categories_clean} for description: '{description}'. Return ONLY category name."
    try:
        online_res = _create_response(prompt)
        if online_res:
            online_res = online_res.strip()
            for cat in categories_clean:
                if cat.lower() in online_res.lower():
                    return cat
    except Exception:
        pass

    # Offline Rule Engine
    desc_lower = description.lower()
    keyword_map = {
        "Salary": ["pay", "salary", "payroll", "stipend", "bonus", "deposit"],
        "Food": ["groceries", "lunch", "dinner", "cafe", "coffee", "restaurant", "snack", "burger", "pizza", "subway"],
        "Transport": ["gas", "fuel", "uber", "taxi", "bus", "metro", "parking", "flight", "train"],
        "Entertainment": ["movie", "cinema", "netflix", "spotify", "steam", "game", "ticket", "concert"],
        "Bills": ["electric", "water", "internet", "wifi", "rent", "utility", "phone", "bill", "subscription"]
    }
    
    for cat, keywords in keyword_map.items():
        if cat in categories_clean and any(k in desc_lower for k in keywords):
            return cat
            
    return categories_clean[0] if categories_clean else "Other"

def analyze_spending(df: pd.DataFrame) -> str:
    if df is None or df.empty: return "No transaction data available for analysis."

    # Try online API first
    try:
        online_res = _create_response(f"Analyze financial data and give 3 key insights:\n{df.to_string()}")
        if online_res: return online_res.strip()
    except Exception:
        pass

    # Offline Analysis Engine
    expenses = df[df["Type"] == "Expense"]
    income = df[df["Type"] == "Income"]
    
    total_in = income["Amount"].sum() if not income.empty else 0
    total_out = expenses["Amount"].sum() if not expenses.empty else 0
    savings = total_in - total_out
    
    top_cat = expenses.groupby("Category")["Amount"].sum().idxmax() if not expenses.empty else "N/A"
    top_cat_amt = expenses.groupby("Category")["Amount"].sum().max() if not expenses.empty else 0

    return (
        "💡 [Offline Insights Mode]\n\n"
        f"• Net Cash Flow: You saved ${savings:,.2f} overall.\n"
        f"• Top Expense Area: High expenditure detected in '{top_cat}' (${top_cat_amt:,.2f}).\n"
        f"• Savings Ratio: Spending accounts for {(total_out/total_in*100 if total_in else 0):.1f}% of total reported income.\n\n"
        "Suggestion: Consider capping non-essential category spends to boost net savings."
    )

def budget_advice(df: pd.DataFrame, budgets: Dict[str, float]) -> str:
    if df is None or df.empty: return "No transaction data available."

    try:
        online_res = _create_response(f"Provide budget advice for data: {df.to_string()} and limits: {budgets}")
        if online_res: return online_res.strip()
    except Exception:
        pass

    # Offline Budget Engine
    expenses = df[df["Type"] == "Expense"]
    if expenses.empty: return "No expenses recorded to evaluate budgets."

    spent_by_cat = expenses.groupby("Category")["Amount"].sum().to_dict()
    lines = ["📈 [Offline Budget Analysis]\n"]
    
    for cat, budget in (budgets or {}).items():
        spent = spent_by_cat.get(cat, 0.0)
        status = "⚠️ OVER BUDGET" if spent > budget else "✅ On Track"
        lines.append(f"• {cat}: Spent ${spent:,.2f} / Target ${budget:,.2f} — {status}")
        
    return "\n".join(lines)

def chat_assistant(df: pd.DataFrame, question: str) -> str:
    if not question.strip(): return "Please ask a specific question."

    try:
        online_res = _create_response(f"User Question: '{question}'. Transaction summary: {df.describe().to_string()}")
        if online_res: return online_res.strip()
    except Exception:
        pass

    # Offline Query Engine
    q_lower = question.lower()
    expenses = df[df["Type"] == "Expense"]
    income = df[df["Type"] == "Income"]

    if "spent" in q_lower or "expense" in q_lower:
        val = expenses["Amount"].sum() if not expenses.empty else 0
        return f"💬 Total recorded expenses equal ${val:,.2f}."
    elif "earn" in q_lower or "income" in q_lower or "salary" in q_lower:
        val = income["Amount"].sum() if not income.empty else 0
        return f"💬 Total recorded income equals ${val:,.2f}."
    
    return f"💬 [Offline Assistant] Total transactions recorded: {len(df)}. Total balance impact: ${income['Amount'].sum() - expenses['Amount'].sum():,.2f}."

def detect_unusual_spending(df: pd.DataFrame) -> str:
    if df is None or df.empty: return "No transactions found."
    expenses = df[df["Type"] == "Expense"].copy()
    if expenses.empty: return "No expense records to analyze."

    stats = expenses.groupby("Category")["Amount"].agg(["count", "mean", "std"]).fillna(0)
    flagged = []

    for _, row in expenses.iterrows():
        cat, amount = row.get("Category"), float(row.get("Amount", 0))
        if cat in stats.index and stats.loc[cat, "count"] >= 3:
            threshold = stats.loc[cat, "mean"] + (2.0 * stats.loc[cat, "std"])
            if amount > threshold and threshold > 0:
                flagged.append(row)

    if not flagged: return "🛡️ No unusual transaction outliers detected."

    lines = ["🛡️ Fraud / Outlier Flagged Transactions:"]
    for row in flagged[:5]:
        lines.append(f"- {str(row.get('Date',''))[:10]} | {row.get('Category')} | ${float(row.get('Amount',0)):,.2f} | {row.get('Description')}")
    return "\n".join(lines)