# Finance Tracker Pro

Finance Tracker Pro is a desktop personal finance manager built with PyQt6, pandas, and matplotlib. Track income, expenses, savings, accounts, and categories with a clean dashboard and charts. Optional AI features provide insights, budget advice, fraud checks, chat, and smart category suggestions.

---

## Features

- Import one or multiple CSV files at once
- Manual transaction entry
- Multi-account support
- Category management
- Financial dashboard cards (income, expenses, savings, rate)
- Income vs expense trend chart
- Expense distribution pie chart
- Savings goal progress tracking
- Transaction table view
- Export charts as images
- Autosave to `autosave.csv`
- Optional AI insights, budget advice, fraud check, chat, and category suggestion
- Automatic update check (version.json)

---

## Quick Start

### 1. Install dependencies

```bash
pip install PyQt6 pandas matplotlib openai
```

### 2. Run the app

```bash
python main.py
```

---

## CSV Format

The app accepts CSV files with these columns:

```csv
Date,Type,Category,Account,Amount,Description
2025-01-01,Income,Salary,Bank,3000,Monthly salary
2025-01-02,Expense,Food,Cash,50,Groceries
2025-01-03,Expense,Transport,Credit Card,20,Taxi
```

Required fields:

- `Date` (YYYY-MM-DD)
- `Type` (`Income` or `Expense`)
- `Amount` (numeric)

Optional fields:

- `Category` (defaults to `Other`)
- `Account` (defaults to the first account)
- `Description` (optional)

---

## AI Setup (Optional)

Create `ai_config.json` next to `main.py`:

```json
{
  "api_key": "YOUR_OPENAI_API_KEY",
  "model": "gpt-4o-mini"
}
```

Or set environment variables:

```bash
setx OPENAI_API_KEY "your-key"
setx OPENAI_MODEL "gpt-4o-mini"
```

Optional for custom endpoints:

```bash
setx OPENAI_BASE_URL "https://your-endpoint"
```

Notes:

- Keep `ai_config.json` out of source control (already in `.gitignore`).
- AI calls time out after ~20s and show an error if network or key is invalid.

---

## Usage

- **Load CSV**: Import one or multiple files
- **Save CSV**: Export all transactions
- **Add**: Manually add a transaction
- **Manage Categories / Accounts**: Add or remove list items
- **AI buttons**: Get insights, budget advice, fraud checks, chat answers, or category suggestions
- **Export Chart**: Save charts as PNG

---

## Requirements

- Python 3.9+
- PyQt6
- pandas
- matplotlib
- openai (optional for AI features)

---
