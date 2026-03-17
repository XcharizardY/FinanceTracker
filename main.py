import sys
import json
import threading
import urllib.error
import urllib.request
import os
from typing import Protocol

import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QMessageBox, QLabel, QFrame,
    QGridLayout, QTableWidget, QTableWidgetItem, QLineEdit,
    QComboBox, QDateEdit, QProgressBar, QInputDialog
)
from PyQt6.QtCore import QDate, QTimer
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

plt.style.use("dark_background")

try:
    import ai_features as _ai_features
    AI_IMPORT_ERROR = None
except Exception as e:
    _ai_features = None
    AI_IMPORT_ERROR = str(e)

if _ai_features is None and AI_IMPORT_ERROR:
    print("AI module failed to load:", AI_IMPORT_ERROR)


class AiFeatures(Protocol):
    def analyze_spending(self, df: pd.DataFrame) -> str | None: ...

    def suggest_category(
        self, description: str, categories: list[str]
    ) -> str | None: ...

    def budget_advice(
        self, df: pd.DataFrame, budgets: dict
    ) -> str | None: ...

    def chat_assistant(
        self, df: pd.DataFrame, question: str
    ) -> str | None: ...
    def detect_unusual_spending(self, df: pd.DataFrame) -> str | None: ...


ai_features: AiFeatures | None = _ai_features

APP_VERSION = "1.0.0"
UPDATE_URL = (
    "https://raw.githubusercontent.com/XcharizardY/FinanceTracker/main/"
    "version.json"
)
UPDATE_TIMEOUT_SEC = 5
AUTOSAVE_FILENAME = "autosave.csv"
AI_UI_TIMEOUT_MS = 25000

COLUMNS = ["Date", "Type", "Category", "Account", "Amount", "Description"]
DEFAULT_CATEGORY = "Other"

LINE_COLORS = ["#00c8ff", "#ff4d6d", "#7cff6b"]
PIE_COLORS = ["#00c8ff", "#ff4d6d", "#ffd166",
              "#7cff6b", "#b388ff", "#ff8fab"]

UI_STYLE = """
QWidget {
    background:#121212;
    color:white;
    font-family:Segoe UI;
}

QPushButton {
    background:#2ecc71;
    padding:8px;
    border-radius:6px;
}

QPushButton:hover {
    background:#27ae60;
}

QLineEdit, QComboBox, QDateEdit {
    background:#1e1e1e;
    padding:6px;
}

QTableWidget {
    background:#1e1e1e;
}
"""


class FinanceApp(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Finance Tracker Pro")
        self.resize(1200, 800)

        self.df = pd.DataFrame(columns=COLUMNS)
        self._dirty = False

        self.categories = [
            "Salary", "Food", "Transport", "Entertainment", "Bills", "Other"
        ]
        self.accounts = ["Cash", "Bank", "Credit Card"]

        self.budgets = {
            "Food": 500,
            "Transport": 300,
            "Entertainment": 300,
            "Bills": 1000,
            "Other": 400
        }

        self.savings_goal = 5000

        self.init_ui()
        self.apply_style()
        QTimer.singleShot(0, self.check_for_updates_async)

    # ---------------- UI ----------------

    def init_ui(self):

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        load_btn = QPushButton("Load CSV")
        load_btn.clicked.connect(self.load_csv)

        save_btn = QPushButton("Save CSV")
        save_btn.clicked.connect(self.save_csv)

        export_btn = QPushButton("Export Chart")
        export_btn.clicked.connect(self.export_chart)

        self.ai_insights_btn = QPushButton("AI Insights")
        self.ai_insights_btn.clicked.connect(self.run_ai_insights)

        self.ai_budget_btn = QPushButton("AI Budget Advisor")
        self.ai_budget_btn.clicked.connect(self.run_ai_budget_advisor)

        self.ai_fraud_btn = QPushButton("AI Fraud Check")
        self.ai_fraud_btn.clicked.connect(self.run_ai_fraud_check)

        self.ai_chat_btn = QPushButton("AI Chat")
        self.ai_chat_btn.clicked.connect(self.run_ai_chat)

        manage_categories_btn = QPushButton("Manage Categories")
        manage_categories_btn.clicked.connect(self.manage_categories)

        manage_accounts_btn = QPushButton("Manage Accounts")
        manage_accounts_btn.clicked.connect(self.manage_accounts)

        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(self.ai_insights_btn)
        btn_layout.addWidget(self.ai_budget_btn)
        btn_layout.addWidget(self.ai_fraud_btn)
        btn_layout.addWidget(self.ai_chat_btn)
        btn_layout.addWidget(manage_categories_btn)
        btn_layout.addWidget(manage_accounts_btn)

        main_layout.addLayout(btn_layout)

        # Dashboard cards
        self.dashboard = self.create_dashboard()
        main_layout.addLayout(self.dashboard)

        # Savings goal progress
        self.goal_bar = QProgressBar()
        main_layout.addWidget(QLabel("Savings Goal Progress"))
        main_layout.addWidget(self.goal_bar)

        # Entry form
        form = self.create_entry_form()
        main_layout.addLayout(form)

        # Table
        self.table = QTableWidget()
        main_layout.addWidget(self.table)

        # Chart
        self.canvas = FigureCanvas(plt.figure())
        main_layout.addWidget(self.canvas)

    # ---------------- Dashboard ----------------

    def create_dashboard(self):

        layout = QGridLayout()

        self.income_card = self.create_card("Income")
        self.expense_card = self.create_card("Expenses")
        self.savings_card = self.create_card("Savings")
        self.rate_card = self.create_card("Savings Rate")

        layout.addWidget(self.income_card, 0, 0)
        layout.addWidget(self.expense_card, 0, 1)
        layout.addWidget(self.savings_card, 0, 2)
        layout.addWidget(self.rate_card, 0, 3)

        return layout

    def create_card(self, title):

        frame = QFrame()
        frame.setStyleSheet(
            "background:#1e1e1e; padding:15px; border-radius:10px;"
        )

        layout = QVBoxLayout()

        label_title = QLabel(title)
        label_value = QLabel("0")

        label_title.setStyleSheet("font-size:14px; color:gray;")
        label_value.setStyleSheet("font-size:22px;")

        layout.addWidget(label_title)
        layout.addWidget(label_value)

        frame.setLayout(layout)
        frame.value = label_value  # type: ignore

        return frame

    # ---------------- Entry Form ----------------

    def create_entry_form(self):

        layout = QHBoxLayout()

        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())

        self.type_input = QComboBox()
        self.type_input.addItems(["Income", "Expense"])

        self.category_input = QComboBox()
        self.category_input.addItems(self.categories)

        self.account_input = QComboBox()
        self.account_input.addItems(self.accounts)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("Amount")

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Description")

        self.ai_category_btn = QPushButton("AI Category")
        self.ai_category_btn.clicked.connect(self.run_ai_category)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_transaction)

        layout.addWidget(self.date_input)
        layout.addWidget(self.type_input)
        layout.addWidget(self.category_input)
        layout.addWidget(self.account_input)
        layout.addWidget(self.amount_input)
        layout.addWidget(self.desc_input)
        layout.addWidget(self.ai_category_btn)
        layout.addWidget(add_btn)

        return layout

    # ---------------- Data Normalization ----------------

    def _normalize_dataframe(self, df):

        if (
            "Type" not in df.columns
            or "Date" not in df.columns
            or "Amount" not in df.columns
        ):
            raise ValueError(
                "CSV must include Date, Type, and Amount columns."
            )

        data = df.copy()
        data["Amount"] = pd.to_numeric(data["Amount"], errors="coerce")
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")

        if "Category" not in data.columns:
            data["Category"] = DEFAULT_CATEGORY
        if "Account" not in data.columns:
            data["Account"] = self.accounts[0] if self.accounts else "Default"
        if "Description" not in data.columns:
            data["Description"] = ""

        return data[COLUMNS]

    def _ensure_datetime(self):

        if not self.df.empty and "Date" in self.df.columns:
            if not pd.api.types.is_datetime64_any_dtype(self.df["Date"]):
                self.df["Date"] = pd.to_datetime(
                    self.df["Date"], errors="coerce"
                )

    def _compute_totals(self):

        income = self.df[self.df["Type"] == "Income"]["Amount"].sum()
        expense = self.df[self.df["Type"] == "Expense"]["Amount"].sum()
        savings = income - expense
        rate = (savings / income * 100) if income else 0
        return income, expense, savings, rate

    def _mark_dirty(self):
        self._dirty = True

    # ---------------- Load CSV ----------------

    def load_csv(self):

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Open CSV Files", "", "CSV Files (*.csv)"
        )

        if not file_paths:
            return

        try:
            dataframes = []
            for file_path in file_paths:
                df = pd.read_csv(file_path)
                dataframes.append(self._normalize_dataframe(df))

            merged = pd.concat(dataframes, ignore_index=True)

            if self.df.empty:
                self.df = merged
            else:
                self.df = pd.concat([self.df, merged], ignore_index=True)

            self._mark_dirty()
            self.sync_categories_accounts_from_data()
            self.refresh_all()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ---------------- Save CSV ----------------

    def save_csv(self):

        if self.df.empty:
            QMessageBox.information(
                self,
                "Nothing to Save",
                "There is no data to save yet."
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", "", "CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            self.df.to_csv(file_path, index=False)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ---------------- Add Transaction ----------------

    def add_transaction(self):

        try:
            date = pd.Timestamp(self.date_input.date().toPyDate())
            ttype = self.type_input.currentText()
            category = self.category_input.currentText()
            account = self.account_input.currentText()
            amount = float(self.amount_input.text())
            desc = self.desc_input.text()

            new_row = {
                "Date": date,
                "Type": ttype,
                "Category": category,
                "Account": account,
                "Amount": amount,
                "Description": desc
            }

            self.df = pd.concat(
                [self.df, pd.DataFrame([new_row])],
                ignore_index=True
            )

            self._mark_dirty()
            self.sync_categories_accounts_from_data()
            self.refresh_all()

        except Exception:
            QMessageBox.warning(self, "Error", "Invalid input")

    # ---------------- Refresh ----------------

    def refresh_all(self):

        if self.df.empty:
            return

        self._ensure_datetime()
        income, expense, savings, rate = self._compute_totals()

        self.update_dashboard(income, expense, savings, rate)
        self.update_table()
        self.update_chart()
        self.update_goal(savings)
        self.autosave()

    # ---------------- Dashboard Update ----------------

    def update_dashboard(self, income, expense, savings, rate):

        self.income_card.value.setText(f"${income:,.2f}")    # type: ignore
        self.expense_card.value.setText(f"${expense:,.2f}")  # type: ignore
        self.savings_card.value.setText(f"${savings:,.2f}")  # type: ignore
        self.rate_card.value.setText(f"{rate:.1f}%")         # type: ignore

    # ---------------- Goal Progress ----------------

    def update_goal(self, savings):

        percent = int((savings / self.savings_goal) * 100)
        percent = max(0, min(percent, 100))

        self.goal_bar.setValue(percent)

    # ---------------- Table ----------------

    def update_table(self):

        df = self.df

        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))

        self.table.setHorizontalHeaderLabels(df.columns)

        data = df.to_numpy()
        for i, row in enumerate(data):
            for j, value in enumerate(row):
                self.table.setItem(i, j, QTableWidgetItem(str(value)))

        self.table.setUpdatesEnabled(True)

    # ---------------- Charts ----------------

    def update_chart(self):

        plt.close("all")

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
        fig.patch.set_facecolor("#121212")
        ax1.set_facecolor("#1e1e1e")
        ax2.set_facecolor("#1e1e1e")

        df = self.df
        if df.empty or "Date" not in df.columns:
            self.canvas.figure = fig
            self.canvas.draw()
            return

        month_index = df["Date"].dt.to_period("M")
        monthly = df.groupby([month_index, "Type"])[
            "Amount"
        ].sum().unstack(fill_value=0)
        monthly["Savings"] = monthly.get(
            "Income", 0
        ) - monthly.get("Expense", 0)
        monthly = monthly.reindex(
            columns=["Income", "Expense", "Savings"],
            fill_value=0
        )

        if not monthly.empty:
            monthly.plot(
                ax=ax1,
                color=LINE_COLORS,
                linewidth=3.0,
                marker="o",
                markersize=5
            )

        ax1.set_title("Income vs Expenses")
        ax1.tick_params(colors="white")
        ax1.xaxis.label.set_color("white")
        ax1.yaxis.label.set_color("white")
        ax1.title.set_color("white")
        ax1.grid(color="#888888", alpha=0.6)

        legend = ax1.legend()
        if legend:
            legend.get_frame().set_facecolor("#1e1e1e")
            legend.get_frame().set_edgecolor("#444")
            for text in legend.get_texts():
                text.set_color("white")

        category = df[df["Type"] == "Expense"].groupby("Category")[
            "Amount"
        ].sum()

        if not category.empty:
            ax2.pie(
                category.values,
                labels=category.index,
                autopct="%1.0f%%",
                textprops={"color": "white"},
                colors=PIE_COLORS,
                wedgeprops={"edgecolor": "#1e1e1e", "linewidth": 1.0}
            )

        ax2.set_title("Expense Distribution")
        ax2.title.set_color("white")

        fig.tight_layout()

        self.canvas.figure = fig
        self.canvas.draw()

    # ---------------- Export Chart ----------------

    def export_chart(self):

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Chart", "", "PNG Files (*.png)"
        )

        if path:
            self.canvas.figure.savefig(path)

    # ---------------- Style ----------------

    def apply_style(self):

        self.setStyleSheet(UI_STYLE)

    # ---------------- AI Features ----------------

    def _check_ai_ready(self):

        if ai_features is None:
            QMessageBox.warning(
                self,
                "AI Unavailable",
                "ai_features.py could not be imported."
            )
            return False

        if AI_IMPORT_ERROR:
            QMessageBox.warning(
                self,
                "AI Import Error",
                AI_IMPORT_ERROR
            )
            return False

        return True

    def _run_ai_task(self, button, worker, on_success):

        button.setEnabled(False)
        done = threading.Event()

        def _finish_success(result):
            if done.is_set():
                return
            done.set()
            on_success(result)

        def _finish_error(message):
            if done.is_set():
                return
            done.set()
            self._show_ai_error(message)

        def _wrapped():
            try:
                result = worker()
                QTimer.singleShot(0, lambda: _finish_success(result))
            except Exception as e:
                QTimer.singleShot(0, lambda: _finish_error(str(e)))

        def _timeout():
            if done.is_set():
                return
            done.set()
            self._show_ai_error(
                "AI request timed out. Check your API key and network, then try again."
            )

        thread = threading.Thread(target=_wrapped, daemon=True)
        QTimer.singleShot(AI_UI_TIMEOUT_MS, _timeout)
        thread.start()

    def run_ai_insights(self):

        if not self._check_ai_ready():
            return

        if self.df.empty:
            QMessageBox.information(
                self,
                "No Data",
                "Add or import transactions before requesting insights."
            )
            return

        module = ai_features
        if module is None:
            self._show_ai_error("AI module not loaded.")
            return

        self._run_ai_task(
            self.ai_insights_btn,
            lambda: module.analyze_spending(self.df),
            self._show_ai_insights
        )

    def _show_ai_insights(self, result):

        self.ai_insights_btn.setEnabled(True)

        if not result:
            QMessageBox.information(
                self,
                "AI Insights",
                "No insights returned."
            )
            return

        QMessageBox.information(self, "AI Insights", result)

    def run_ai_budget_advisor(self):

        if not self._check_ai_ready():
            return

        if self.df.empty:
            QMessageBox.information(
                self,
                "No Data",
                "Add or import transactions before requesting budget advice."
            )
            return

        module = ai_features
        if module is None:
            self._show_ai_error("AI module not loaded.")
            return

        self._run_ai_task(
            self.ai_budget_btn,
            lambda: module.budget_advice(self.df, self.budgets),
            self._show_ai_budget
        )

    def _show_ai_budget(self, result):

        self.ai_budget_btn.setEnabled(True)

        if not result:
            QMessageBox.information(
                self,
                "Budget Advisor",
                "No budget advice returned."
            )
            return

        QMessageBox.information(self, "Budget Advisor", result)

    def run_ai_fraud_check(self):

        if not self._check_ai_ready():
            return

        if self.df.empty:
            QMessageBox.information(
                self,
                "No Data",
                "Add or import transactions before running fraud detection."
            )
            return

        module = ai_features
        if module is None:
            self._show_ai_error("AI module not loaded.")
            return

        self._run_ai_task(
            self.ai_fraud_btn,
            lambda: module.detect_unusual_spending(self.df),
            self._show_ai_fraud
        )

    def _show_ai_fraud(self, result):

        self.ai_fraud_btn.setEnabled(True)

        if not result:
            QMessageBox.information(
                self,
                "Fraud Detection",
                "No fraud detection results returned."
            )
            return

        QMessageBox.information(self, "Fraud Detection", result)

    def run_ai_chat(self):

        if not self._check_ai_ready():
            return

        question, ok = QInputDialog.getMultiLineText(
            self,
            "AI Chat",
            "Ask a question about your finances:"
        )
        if not ok or not question.strip():
            return

        module = ai_features
        if module is None:
            self._show_ai_error("AI module not loaded.")
            return

        self._run_ai_task(
            self.ai_chat_btn,
            lambda: module.chat_assistant(self.df, question.strip()),
            self._show_ai_chat
        )

    def _show_ai_chat(self, result):

        self.ai_chat_btn.setEnabled(True)

        if not result:
            QMessageBox.information(
                self,
                "AI Chat",
                "No response returned."
            )
            return

        QMessageBox.information(self, "AI Chat", result)

    def run_ai_category(self):

        if not self._check_ai_ready():
            return

        description = self.desc_input.text().strip()
        if not description:
            QMessageBox.information(
                self,
                "Missing Description",
                "Enter a description to get an AI category suggestion."
            )
            return

        module = ai_features
        if module is None:
            self._show_ai_error("AI module not loaded.")
            return

        self._run_ai_task(
            self.ai_category_btn,
            lambda: module.suggest_category(
                description, list(self.categories)
            ),
            self._apply_ai_category
        )

    def _apply_ai_category(self, category):

        self.ai_category_btn.setEnabled(True)

        if not category:
            QMessageBox.information(
                self,
                "AI Category",
                "No category suggestion returned."
            )
            return

        index = self.category_input.findText(category)
        if index >= 0:
            self.category_input.setCurrentIndex(index)
        else:
            QMessageBox.information(
                self,
                "AI Category",
                f"Suggested category not in list: {category}"
            )

    def _show_ai_error(self, message):

        for btn in [
            getattr(self, "ai_insights_btn", None),
            getattr(self, "ai_category_btn", None),
            getattr(self, "ai_budget_btn", None),
            getattr(self, "ai_fraud_btn", None),
            getattr(self, "ai_chat_btn", None)
        ]:
            if btn:
                btn.setEnabled(True)
        QMessageBox.warning(self, "AI Error", message)

    # ---------------- Category & Account Management ----------------

    def manage_categories(self):

        action, ok = QInputDialog.getItem(
            self,
            "Manage Categories",
            "Choose action:",
            ["Add Category", "Remove Category"],
            0,
            False
        )
        if not ok:
            return

        if action == "Add Category":
            name, ok = QInputDialog.getText(
                self, "Add Category", "Category name:"
            )
            if ok and name.strip():
                name = name.strip()
                if name not in self.categories:
                    self.categories.append(name)
                    self.category_input.addItem(name)
        else:
            if not self.categories:
                QMessageBox.information(
                    self, "No Categories", "There are no categories to remove."
                )
                return
            name, ok = QInputDialog.getItem(
                self,
                "Remove Category",
                "Select category:",
                self.categories,
                0,
                False
            )
            if ok and name in self.categories:
                self.categories.remove(name)
                index = self.category_input.findText(name)
                if index >= 0:
                    self.category_input.removeItem(index)

    def manage_accounts(self):

        action, ok = QInputDialog.getItem(
            self,
            "Manage Accounts",
            "Choose action:",
            ["Add Account", "Remove Account"],
            0,
            False
        )
        if not ok:
            return

        if action == "Add Account":
            name, ok = QInputDialog.getText(
                self, "Add Account", "Account name:"
            )
            if ok and name.strip():
                name = name.strip()
                if name not in self.accounts:
                    self.accounts.append(name)
                    self.account_input.addItem(name)
        else:
            if len(self.accounts) <= 1:
                QMessageBox.information(
                    self,
                    "Cannot Remove",
                    "At least one account is required."
                )
                return
            name, ok = QInputDialog.getItem(
                self,
                "Remove Account",
                "Select account:",
                self.accounts,
                0,
                False
            )
            if ok and name in self.accounts:
                self.accounts.remove(name)
                index = self.account_input.findText(name)
                if index >= 0:
                    self.account_input.removeItem(index)

    def sync_categories_accounts_from_data(self):

        if self.df.empty:
            return

        if "Category" in self.df.columns:
            for name in sorted(set(self.df["Category"].dropna().astype(str))):
                if name and name not in self.categories:
                    self.categories.append(name)
                    self.category_input.addItem(name)

        if "Account" in self.df.columns:
            for name in sorted(set(self.df["Account"].dropna().astype(str))):
                if name and name not in self.accounts:
                    self.accounts.append(name)
                    self.account_input.addItem(name)

    # ---------------- Autosave ----------------

    def autosave(self):

        if not self._dirty:
            return

        try:
            autosave_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                AUTOSAVE_FILENAME
            )
            self.df.to_csv(autosave_path, index=False)
            self._dirty = False
        except Exception:
            # Autosave failure should not interrupt the user flow
            return

    # ---------------- Update Check ----------------

    def check_for_updates_async(self):

        thread = threading.Thread(
            target=self._check_for_updates_worker,
            daemon=True
        )
        thread.start()

    def _check_for_updates_worker(self):

        update_info = self.fetch_update_info()
        if not update_info:
            return

        latest_version, url, notes = update_info

        if self.is_newer_version(latest_version, APP_VERSION):
            QTimer.singleShot(
                0,
                lambda: self.notify_update(latest_version, url, notes)
            )

    def fetch_update_info(self):

        try:
            request = urllib.request.Request(
                UPDATE_URL,
                headers={"User-Agent": f"FinanceTrackerPro/{APP_VERSION}"}
            )

            with urllib.request.urlopen(
                request,
                timeout=UPDATE_TIMEOUT_SEC
            ) as response:
                data = response.read().decode("utf-8")

            try:
                payload = json.loads(data)
                version = str(payload.get("version", "")).strip()
                if not version:
                    return None
                url = str(payload.get("url", "")).strip() or None
                notes = str(payload.get("notes", "")).strip() or None
                return version, url, notes
            except json.JSONDecodeError:
                version = data.strip()
                if not version:
                    return None
                return version, None, None

        except (urllib.error.URLError, TimeoutError, ValueError):
            return None

    @staticmethod
    def normalize_version(version_text):

        parts = []
        for part in version_text.strip().split("."):
            digits = ""
            for ch in part:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            parts.append(int(digits) if digits else 0)
        return parts

    @staticmethod
    def is_newer_version(latest, current):

        latest_parts = FinanceApp.normalize_version(latest)
        current_parts = FinanceApp.normalize_version(current)

        max_len = max(len(latest_parts), len(current_parts))
        latest_parts += [0] * (max_len - len(latest_parts))
        current_parts += [0] * (max_len - len(current_parts))

        return latest_parts > current_parts

    def notify_update(self, latest_version, url, notes):

        message = (
            "A newer version of Finance Tracker Pro is available.\n\n"
            f"Current: {APP_VERSION}\n"
            f"Latest: {latest_version}"
        )

        if notes:
            message += f"\n\nNotes: {notes}"

        if url:
            message += f"\n\nDownload: {url}"

        QMessageBox.information(self, "Update Available", message)


# ---------------- Run ----------------

if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = FinanceApp()
    window.show()

    sys.exit(app.exec())
