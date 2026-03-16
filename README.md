# Finance Tracker Pro

Finance Tracker Pro is a desktop personal finance management application built with PyQt6, pandas, and matplotlib. It helps users track income, expenses, savings, and financial trends through an interactive dashboard and charts.

---

## Features

- CSV import for transaction data  
- Manual transaction entry  
- Financial dashboard with summary cards  
- Income vs expense trend chart  
- Expense distribution pie chart  
- Savings goal progress tracking  
- Transaction table view  
- Export charts as image files  
- Modern dark theme interface  

---


## Installation

### 1. Clone the repository

```bash
git clone https://github.com/XcharizardY/finance-tracker-pro.git
cd finance-tracker-pro
````

### 2. Install dependencies

```bash
pip install PyQt6 pandas matplotlib
```

### 3. Run the application

```bash
python main.py
```

---

## CSV Format

Your CSV file must include the following columns:

```csv
Date,Type,Category,Amount,Description
2025-01-01,Income,Salary,3000,Monthly salary
2025-01-02,Expense,Food,50,Groceries
2025-01-03,Expense,Transport,20,Taxi
```

Fields:

* Date: YYYY-MM-DD
* Type: Income or Expense
* Category: Any category name
* Amount: Numeric value
* Description: Optional text

---

## Usage

* Click **Load CSV** to import transactions
* Use the entry form to manually add transactions
* View financial summaries in dashboard cards
* Analyze charts for trends and spending distribution
* Export charts using the Export button

---

## Requirements

* Python 3.9+
* PyQt6
* pandas
* matplotlib

---
