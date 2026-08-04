import os
import json
from functools import lru_cache
from typing import Any

import pandas as pd
from openai import OpenAI

DEFAULT_MODEL = "gpt-4o-mini"
FALLBACK_MODELS = ["gpt-4o-mini", "gpt-4.1-mini"]
CONFIG_FILENAME = "ai_config.json"
REQUEST_TIMEOUT_SEC = 20
MAX_RETRIES = 0


def _load_config():
    path = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), CONFIG_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _is_valid_key(api_key: str, base_url: str | None) -> bool:
    key = str(api_key).strip()
    if not key:
        return False
    if "REPLACE_ME" in key or "..." in key:
        return False
    if base_url:
        return True
    return key.startswith("sk-")


def _get_api_key():
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
            "OPENAI_API_KEY in the environment looks invalid. "
            f"Update it or remove it to use {CONFIG_FILENAME}."
        )

    raise RuntimeError(
        "OPENAI_API_KEY is not set. Set it in your environment or create "
        f"{CONFIG_FILENAME} with an 'api_key' value."
    )


def _get_model():
    config = _load_config()
    return (
        os.getenv("OPENAI_MODEL")
        or config.get("model")
        or DEFAULT_MODEL
    )


def _get_base_url():
    config = _load_config()
    base_url = os.getenv("OPENAI_BASE_URL") or config.get("base_url")
    if base_url:
        base_url = str(base_url).strip()
    if base_url and not base_url.startswith(("http://", "https://")):
        return None
    return base_url


@lru_cache(maxsize=4)
def _get_client_cached(api_key: str, base_url: str | None):
    if base_url:
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=REQUEST_TIMEOUT_SEC,
            max_retries=MAX_RETRIES
        )
    return OpenAI(
        api_key=api_key,
        timeout=REQUEST_TIMEOUT_SEC,
        max_retries=MAX_RETRIES
    )


def _get_client():
    api_key = _get_api_key()
    base_url = _get_base_url()
    return _get_client_cached(api_key, base_url)


def _extract_text(response):
    if hasattr(response, "output_text"):
        return response.output_text
    if hasattr(response, "output"):
        try:
            content = response.output[0].content[0].text
            return content
        except Exception:
            return ""
    if hasattr(response, "choices"):
        try:
            return response.choices[0].message.content
        except Exception:
            return ""
    return ""


def _clean_number(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def _json_default(value: Any):
    if isinstance(value, (pd.Timestamp, pd.Period)):
        return str(value)
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, set):
        return list(value)
    return str(value)


def _dump_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=True, default=_json_default)


def _is_model_error(message: str) -> bool:
    msg = message.lower()
    return "model" in msg and (
        "not found" in msg
        or "does not exist" in msg
        or "is not available" in msg
        or "not supported" in msg
    )


def _client_info() -> str:
    config = _load_config()
    base_url = os.getenv("OPENAI_BASE_URL") or config.get("base_url") or "default"
    model = _get_model()
    key_source = "env" if os.getenv("OPENAI_API_KEY") else "config"
    return f"model={model}, base_url={base_url}, key_source={key_source}"


def _create_response(prompt: str):
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
                    return client.chat.completions.create(
                        model=fallback, messages=messages
                    )
                except Exception:
                    continue
        raise RuntimeError(
            f"AI call failed: {type(e).__name__}: {str(e)} "
            f"({ _client_info() })"
        ) from e


def _prepare_dataframe(df):
    if df is None or df.empty:
        return None
    data = df.copy()
    if "Date" in data.columns:
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    return data


def _summarize_transactions(df, months=6):
    data = _prepare_dataframe(df)
    if data is None:
        return None

    if "Type" not in data.columns or "Amount" not in data.columns:
        return None

    totals_by_type = {
        str(k): _clean_number(v)
        for k, v in data.groupby("Type")["Amount"].sum().to_dict().items()
    }

    totals_by_account = {}
    if "Account" in data.columns:
        totals_by_account = {
            str(k): _clean_number(v)
            for k, v in data.groupby("Account")["Amount"].sum().to_dict().items()
        }

    top_categories = {}
    if "Category" in data.columns:
        expenses = data[data["Type"] == "Expense"]
        if not expenses.empty:
            top_categories = {
                str(k): _clean_number(v)
                for k, v in (
                    expenses.groupby("Category")["Amount"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(8)
                    .to_dict()
                ).items()
            }

    monthly = {}
    if "Date" in data.columns and data["Date"].notna().any():
        monthly_raw = (
            data.groupby([data["Date"].dt.to_period("M"), "Type"])["Amount"]
            .sum()
            .unstack(fill_value=0)
            .tail(months)
            .to_dict(orient="index")
        )
        monthly = {
            str(period): {
                str(k): _clean_number(v) for k, v in values.items()
            }
            for period, values in monthly_raw.items()
        }

    return {
        "totals_by_type": totals_by_type,
        "totals_by_account": totals_by_account,
        "top_expense_categories": top_categories,
        "recent_months": monthly
    }


def suggest_category(description, categories):
    if not description or not categories:
        return None

    categories_clean = [
        str(c).strip() for c in categories if str(c).strip()
    ]
    if not categories_clean:
        return None

    prompt = (
        "You are a finance assistant. Choose the best category from the list "
        "and respond with ONLY the category name.\n\n"
        f"Categories: {categories_clean}\n\n"
        f"Description: {description}\n\n"
        "Category:"
    )

    response = _create_response(prompt)

    text = (_extract_text(response) or "").strip()
    if not text:
        return None

    for category in categories_clean:
        if text.lower() == category.lower():
            return category

    for category in categories_clean:
        if category.lower() in text.lower():
            return category

    return None


def analyze_spending(df):
    payload = _summarize_transactions(df, months=6)
    if not payload:
        return None

    prompt = (
        "You are a financial assistant. Provide 3-5 concise insights and "
        "2 practical suggestions based on the data. Use bullet points.\n\n"
        f"Data:\n{_dump_json(payload)}"
    )

    response = _create_response(prompt)

    return (_extract_text(response) or "").strip()


def budget_advice(df, budgets):
    data = _prepare_dataframe(df)
    if data is None:
        return None

    if (
        "Type" not in data.columns
        or "Amount" not in data.columns
        or "Category" not in data.columns
        or "Date" not in data.columns
    ):
        return None

    expenses = data[data["Type"] == "Expense"].copy()
    if expenses.empty:
        return None

    month_index = expenses["Date"].dt.to_period("M")
    monthly_by_category = (
        expenses.groupby([month_index, "Category"])["Amount"]
        .sum()
        .unstack(fill_value=0)
    )

    recent = monthly_by_category.tail(3)
    avg_monthly = {}
    if not recent.empty:
        avg_monthly = {
            str(k): _clean_number(v)
            for k, v in recent.mean().round(2).to_dict().items()
        }

    current_month = {}
    if not monthly_by_category.empty:
        current_month = {
            str(k): _clean_number(v)
            for k, v in (
                monthly_by_category.tail(1).iloc[0].round(2).to_dict()
            ).items()
        }

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

    response = _create_response(prompt)

    return (_extract_text(response) or "").strip()


def chat_assistant(df, question):
    if not question or not question.strip():
        return None

    summary = _summarize_transactions(df, months=6)
    if summary is None:
        summary = {"note": "No transaction data available."}

    prompt = (
        "You are a helpful finance assistant. Use the provided data summary "
        "to answer the user's question. If the data is insufficient, say so "
        "and ask a brief follow-up question.\n\n"
        f"Data Summary:\n{_dump_json(summary)}\n\n"
        f"Question: {question}\n\nAnswer:"
    )

    response = _create_response(prompt)

    return (_extract_text(response) or "").strip()


def detect_unusual_spending(df):
    data = _prepare_dataframe(df)
    if data is None:
        return None

    if (
        "Type" not in data.columns
        or "Amount" not in data.columns
        or "Category" not in data.columns
        or "Date" not in data.columns
    ):
        return None

    expenses = data[data["Type"] == "Expense"].copy()
    if expenses.empty:
        return None

    stats = (
        expenses.groupby("Category")["Amount"]
        .agg(["count", "mean", "std", "median"])
        .fillna(0)
    )

    flagged = []
    for _, row in expenses.iterrows():
        category = row.get("Category")
        amount = float(row.get("Amount", 0))
        if category not in stats.index or amount <= 0:
            continue

        stat = stats.loc[category]
        count = int(stat["count"])
        mean = float(stat["mean"])
        std = float(stat["std"])
        median = float(stat["median"])

        if count >= 5 and std > 0:
            threshold = mean + (2.5 * std)
        elif median > 0:
            threshold = median * 3
        else:
            threshold = mean * 3

        if amount >= threshold and amount > 0:
            flagged.append(row)

    if not flagged:
        return "No unusual spending detected."

    flagged = sorted(
        flagged,
        key=lambda r: float(r.get("Amount", 0)),
        reverse=True
    )[:10]

    lines = ["Unusual spending detected:"]
    for row in flagged:
        date = str(row.get("Date", ""))[:10]
        category = str(row.get("Category", ""))
        account = str(row.get("Account", ""))
        description = str(row.get("Description", ""))
        amount = float(row.get("Amount", 0))
        lines.append(
            f"- {date} | {category} | {account} | ${amount:,.2f} | {description}"
        )

    return "\n".join(lines)
