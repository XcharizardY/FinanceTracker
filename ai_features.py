import os
import json
import pandas as pd
from openai import OpenAI

AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


def _get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


def _extract_text(response):
    if hasattr(response, "output_text"):
        return response.output_text
    if hasattr(response, "output"):
        try:
            content = response.output[0].content[0].text
            return content
        except Exception:
            return ""
    return ""


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

    response = _get_client().responses.create(
        model=AI_MODEL,
        input=prompt
    )

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
    if df is None or df.empty:
        return None

    data = df.copy()
    if "Date" in data.columns:
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")

    if (
        "Type" not in data.columns
        or "Amount" not in data.columns
        or "Category" not in data.columns
    ):
        return None

    totals_by_type = data.groupby("Type")["Amount"].sum().to_dict()
    expenses = data[data["Type"] == "Expense"]
    top_categories = (
        expenses.groupby("Category")["Amount"]
        .sum()
        .sort_values(ascending=False)
        .head(8)
        .to_dict()
        if not expenses.empty
        else {}
    )

    monthly = {}
    if "Date" in data.columns and data["Date"].notna().any():
        monthly = (
            data.groupby([data["Date"].dt.to_period("M"), "Type"])["Amount"]
            .sum()
            .unstack(fill_value=0)
            .tail(6)
            .astype(float)
            .to_dict(orient="index")
        )
        monthly = {str(k): v for k, v in monthly.items()}

    payload = {
        "totals_by_type": totals_by_type,
        "top_expense_categories": top_categories,
        "recent_months": monthly
    }

    prompt = (
        "You are a financial assistant. Provide 3-5 concise insights and "
        "2 practical suggestions based on the data. Use bullet points.\n\n"
        f"Data:\n{json.dumps(payload, ensure_ascii=True)}"
    )

    response = _get_client().responses.create(
        model=AI_MODEL,
        input=prompt
    )

    return (_extract_text(response) or "").strip()
