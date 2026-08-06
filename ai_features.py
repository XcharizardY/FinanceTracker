"""
AI Features Module

This module handles all external communication with the OpenAI API for the Finance Tracker.
It provides data summarization, natural language insights, budget recommendations, 
fraud detection, and category suggestions based on pandas DataFrame inputs.
"""

import os
import json
from functools import lru_cache
from typing import Any, List, Dict, Optional

import pandas as pd
from openai import OpenAI

# API Configuration
DEFAULT_MODEL = "gpt-4o-mini"
FALLBACK_MODELS = ["gpt-4o-mini", "gpt-3.5-turbo"]
CONFIG_FILENAME = "ai_config.json"
REQUEST_TIMEOUT_SEC = 20
MAX_RETRIES = 0

# ---------------- Internal API Helpers ----------------

def _load_config() -> dict:
    """Loads API keys and base URLs from a local JSON config if present."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _is_valid_key(api_key: str, base_url: Optional[str]) -> bool:
    """Validates that the provided OpenAI key isn't a placeholder."""
    key = str(api_key).strip()
    if not key or "REPLACE_ME" in key or "..." in key:
        return False
    if base_url:
        return True
    return key.startswith("sk-")

def _get_api_key() -> str:
    """Resolves the OpenAI API key from the environment or local config."""
    config = _load_config()
    base_url = os.getenv("OPENAI_BASE_URL") or config.get("base_url")
    env_key = os.getenv("OPENAI_API_KEY")
    cfg_key = config.get("api_key")

    if env_key and _is_valid_key(env_key, base_url):
        return str(env_key).strip()
    if cfg_key and _is_valid_key(cfg_key, base_url):
        return str(cfg_key).strip()

    if env_key and not _is_valid_key(env_key, base_url):
        raise RuntimeError(
            f"OPENAI_API_KEY in the environment looks invalid. Update or remove it to use {CONFIG_FILENAME}."
        )

    raise RuntimeError(
        f"OPENAI_API_KEY is not set. Set it in your environment or create {CONFIG_FILENAME}."
    )

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
    """Caches the OpenAI client to prevent re-instantiation on every request."""
    kwargs = {
        "api_key": api_key,
        "timeout": REQUEST_TIMEOUT_SEC,
        "max_retries": MAX_RETRIES
    }
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)

def _get_client() -> OpenAI:
    return _get_client_cached(_get_api_key(), _get_base_url())

def _extract_text(response: Any) -> str:
    """Safely extracts text from various OpenAI response object structures."""
    if hasattr(response, "choices"):
        try:
            return response.choices[0].message.content
        except Exception:
            pass
    return ""

def _is_model_error(message: str) -> bool:
    msg = message.lower()
    return "model" in msg and any(
        err in msg for err in ["not found", "does not exist", "not available", "not supported"]
    )

def _create_response(prompt: str) -> Any:
    """Handles the core network call to OpenAI, including automatic model fallbacks."""
    client = _get_client()
    model = _get_model()
    messages = [{"role": "user", "content": prompt}]
    
    try:
        return client.chat.completions.create(model=model, messages=messages)
    except Exception as e:
        if _is_model_error(str(e)):
            for fallback in FALLBACK_MODELS:
                if fallback == model:
                    continue
                try:
                    return client.chat.completions.create(model=fallback, messages=messages)
                except Exception:
                    continue
        raise RuntimeError(f"AI call failed: {type(e).__name__}: {str(e)}") from e

# ---------------- Data Processing Helpers ----------------

def _clean_number(value: Any) -> float:
    if pd.isna(value): return 0.0
    try: return float(value)
    except Exception: return 0.0

def _json_default(value: Any) -> Any:
    """Custom JSON serializer for pandas data types."""
    if isinstance(value, (pd.Timestamp, pd.Period)): return str(value)
    if hasattr(value, "tolist"):
        try: return value.tolist()
        except Exception: pass
    if hasattr(value, "item"):
        try: return value.item()
        except Exception: pass
    if isinstance(value, set): return list(value)
    return str(value)

def _dump_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=True, default=_json_default)

def _prepare_dataframe(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    data = df.copy()
    if "Date" in data.columns:
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    return data

def _summarize_transactions(df: pd.DataFrame, months: int = 6) -> Optional[dict]:
    """Aggregates raw DataFrame data into a structured JSON payload for the LLM context window."""
    data = _prepare_dataframe(df)
    if data is None or "Type" not in data.columns or "Amount" not in data.columns:
        return None

    totals_by_type = {str(k): _clean_number(v) for k, v in data.groupby("Type")["Amount"].sum().to_dict().items()}
    
    totals_by_account = {}
    if "Account" in data.columns:
        totals_by_account = {str(k): _clean_number(v) for k, v in data.groupby("Account")["Amount"].sum().to_dict().items()}

    top_categories = {}
    if "Category" in data.columns:
        expenses = data[data["Type"] == "Expense"]
        if not expenses.empty:
            top_categories = {
                str(k): _clean_number(v)
                for k, v in expenses.groupby("Category")["Amount"].sum().sort_values(ascending=False).head(8).to_dict().items()
            }

    monthly = {}
    if "Date" in data.columns and data["Date"].notna().any():
        monthly_raw = data.groupby([data["Date"].dt.to_period("M"), "Type"])["Amount"].sum().unstack(fill_value=0).tail(months).to_dict(orient="index")
        monthly = {str(period): {str(k): _clean_number(v) for k, v in values.items()} for period, values in monthly_raw.items()}

    return {
        "totals_by_type": totals_by_type,
        "totals_by_account": totals_by_account,
        "top_expense_categories": top_categories,
        "recent_months": monthly
    }

# ---------------- Public AI Actions (Exported to UI) ----------------

def suggest_category(description: str, categories: List[str]) -> Optional[str]:
    """
    Asks the AI to map a raw transaction description to the closest available category.
    """
    if not description or not categories: return None
    categories_clean = [str(c).strip() for c in categories if str(c).strip()]
    if not categories_clean: return None

    prompt = (
        "You are a finance assistant. Choose the best category from the list "
        "and respond with ONLY the category name.\n\n"
        f"Categories: {categories_clean}\n\n"
        f"Description: {description}\n\n"
        "Category:"
    )

    text = (_extract_text(_create_response(prompt)) or "").strip()
    if not text: return None

    # Strict string matching to prevent UI injection errors
    for category in categories_clean:
        if text.lower() == category.lower() or category.lower() in text.lower():
            return category
    return None

def analyze_spending(df: pd.DataFrame) -> Optional[str]:
    """
    Generates high-level financial insights based on historical transaction data.
    """
    payload = _summarize_transactions(df, months=6)
    if not payload: return None

    prompt = (
        "You are a financial assistant. Provide 3-5 concise insights and "
        "2 practical suggestions based on the data. Use bullet points.\n\n"
        f"Data:\n{_dump_json(payload)}"
    )
    return (_extract_text(_create_response(prompt)) or "").strip()

def budget_advice(df: pd.DataFrame, budgets: Dict[str, float]) -> Optional[str]:
    """
    Compares current spending velocity against predefined category budgets.
    """
    data = _prepare_dataframe(df)
    if data is None or not {"Type", "Amount", "Category", "Date"}.issubset(data.columns):
        return None

    expenses = data[data["Type"] == "Expense"].copy()
    if expenses.empty: return None

    month_index = expenses["Date"].dt.to_period("M")
    monthly_by_category = expenses.groupby([month_index, "Category"])["Amount"].sum().unstack(fill_value=0)

    recent = monthly_by_category.tail(3)
    avg_monthly = {str(k): _clean_number(v) for k, v in recent.mean().round(2).to_dict().items()} if not recent.empty else {}
    current_month = {str(k): _clean_number(v) for k, v in monthly_by_category.tail(1).iloc[0].round(2).to_dict().items()} if not monthly_by_category.empty else {}

    payload = {
        "budgets": {str(k): _clean_number(v) for k, v in (budgets or {}).items()},
        "avg_monthly_spend_last_3_months": avg_monthly,
        "current_month_spend": current_month
    }

    prompt = (
        "You are a financial assistant. Suggest monthly budget limits per "
        "category using the data. If a category exceeds current budgets, "
        "propose a new limit and a short reason. Use bullet points.\n\n"
        f"Data:\n{_dump_json(payload)}"
    )
    return (_extract_text(_create_response(prompt)) or "").strip()

def chat_assistant(df: pd.DataFrame, question: str) -> Optional[str]:
    """
    Allows the user to query their aggregated financial data using natural language.
    """
    if not question or not question.strip(): return None

    summary = _summarize_transactions(df, months=6) or {"note": "No transaction data available."}
    prompt = (
        "You are a helpful finance assistant. Use the provided data summary "
        "to answer the user's question. If the data is insufficient, say so "
        "and ask a brief follow-up question.\n\n"
        f"Data Summary:\n{_dump_json(summary)}\n\n"
        f"Question: {question}\n\nAnswer:"
    )
    return (_extract_text(_create_response(prompt)) or "").strip()

def detect_unusual_spending(df: pd.DataFrame) -> Optional[str]:
    """
    Statistically analyzes transaction history to flag outliers and unusual velocity, 
    bypassing the LLM for faster, deterministic execution.
    """
    data = _prepare_dataframe(df)
    if data is None or not {"Type", "Amount", "Category", "Date"}.issubset(data.columns):
        return None

    expenses = data[data["Type"] == "Expense"].copy()
    if expenses.empty: return None

    stats = expenses.groupby("Category")["Amount"].agg(["count", "mean", "std", "median"]).fillna(0)
    flagged = []

    for _, row in expenses.iterrows():
        category, amount = row.get("Category"), float(row.get("Amount", 0))
        if category not in stats.index or amount <= 0: continue

        stat = stats.loc[category]
        count, mean, std, median = int(stat["count"]), float(stat["mean"]), float(stat["std"]), float(stat["median"])

        if count >= 5 and std > 0:
            threshold = mean + (2.5 * std)
        elif median > 0:
            threshold = median * 3
        else:
            threshold = mean * 3

        if amount >= threshold and amount > 0:
            flagged.append(row)

    if not flagged: return "No unusual spending detected."

    flagged = sorted(flagged, key=lambda r: float(r.get("Amount", 0)), reverse=True)[:10]
    lines = ["Unusual spending detected:"]
    for row in flagged:
        lines.append(f"- {str(row.get('Date', ''))[:10]} | {row.get('Category', '')} | "
                     f"{row.get('Account', '')} | ${float(row.get('Amount', 0)):,.2f} | {row.get('Description', '')}")

    return "\n".join(lines)