"""
Finance Tracker Pro
A modern, PyQT6-based desktop application for personal finance management.
Features a dashboard, interactive data visualization, CSV import/export, 
and background-threaded AI assistants for financial insights.
"""

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
    QComboBox, QDateEdit, QProgressBar, QInputDialog, QHeaderView
)
from PyQt6.QtCore import Qt, QDate, QTimer
from PyQt6.QtGui import QIcon, QPixmap
import qtawesome as qta
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

# Set dark theme for matplotlib charts to match the UI
plt.style.use("dark_background")

# Attempt to load optional AI features module gracefully
try:
    import ai_features as _ai_features
    AI_IMPORT_ERROR = None
except Exception as e:
    _ai_features = None
    AI_IMPORT_ERROR = str(e)

if _ai_features is None and AI_IMPORT_ERROR:
    print("AI module failed to load:", AI_IMPORT_ERROR)

# Define a structural protocol for the AI backend so the UI 
# knows exactly what methods to expect.
class AiFeatures(Protocol):
    def analyze_spending(self, df: pd.DataFrame) -> str | None: ...
    def suggest_category(self, description: str, categories: list[str]) -> str | None: ...
    def budget_advice(self, df: pd.DataFrame, budgets: dict) -> str | None: ...
    def chat_assistant(self, df: pd.DataFrame, question: str) -> str | None: ...
    def detect_unusual_spending(self, df: pd.DataFrame) -> str | None: ...

ai_features: AiFeatures | None = _ai_features

# Application Constants
APP_VERSION = "1.0.0"
UPDATE_URL = "https://raw.githubusercontent.com/XcharizardY/FinanceTracker/main/version.json"
UPDATE_TIMEOUT_SEC = 5
AUTOSAVE_FILENAME = "autosave.csv"
AI_UI_TIMEOUT_MS = 25000

# DataFrame Schema Definition
COLUMNS = ["Date", "Type", "Category", "Account", "Amount", "Description"]
DEFAULT_CATEGORY = "Other"

# Brand Identity Colors (Integrated with Logo)
BRAND_YELLOW = "#FFCC00"
BRAND_YELLOW_HOVER = "#E6B800"

# Chart Color Palettes
LINE_COLORS = ["#00c8ff", "#ff4d6d", "#7cff6b"]
PIE_COLORS = ["#00c8ff", "#ff4d6d", "#ffd166", "#7cff6b", "#b388ff", "#ff8fab"]

# Global Qt StyleSheet (QSS) for a modern, dark web-app aesthetic
UI_STYLE = f"""
QWidget {{
    background: #121212;
    color: #e0e0e0;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}}

/* Primary Action Buttons (Branded Yellow) */
QPushButton {{
    background: {BRAND_YELLOW};
    color: #000000;
    font-weight: bold;
    padding: 8px 14px;
    border-radius: 6px;
    border: none;
}}
QPushButton:hover {{
    background: {BRAND_YELLOW_HOVER};
}}
QPushButton:disabled {{
    background: #2a2a2a;
    color: #666666;
}}

/* Modern Inputs with Brand Focus Rings */
QLineEdit, QComboBox, QDateEdit {{
    background: #1a1a1a;
    padding: 7px 10px;
    border-radius: 5px;
    border: 1px solid #2a2a2a;
    color: white;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
    border: 1px solid {BRAND_YELLOW};
}}

/* Clean Data Table */
QTableWidget {{
    background: #161616;
    border: 1px solid #222;
    border-radius: 6px;
    gridline-color: transparent;
    selection-background-color: #252525;
}}
QTableWidget::item {{
    padding: 6px;
    border-bottom: 1px solid #1f1f1f;
}}
QHeaderView::section {{
    background-color: #1e1e1e;
    padding: 6px;
    border: none;
    border-bottom: 2px solid #333;
    font-weight: bold;
    color: #aaa;
}}

/* Slim Pill-Style Progress Bar */
QProgressBar {{
    background-color: #1a1a1a;
    border: none;
    border-radius: 5px;
    max-height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {BRAND_YELLOW};
    border-radius: 5px;
}}
"""

class FinanceApp(QWidget):
    """
    Main Application Window.
    Handles the UI layout, data state (pandas DataFrame), and user interactions.
    """
    def __init__(self):
        super().__init__()

        # Window Configuration
        self.setWindowTitle("Finance Tracker Pro")
        self.resize(1280, 800)
        self.setWindowIcon(QIcon("FinanceTracker.png"))

        # State Initialization
        self.df = pd.DataFrame(columns=COLUMNS)
        self._dirty = False # Tracks if there are unsaved changes

        # Default User Settings
        self.categories = ["Salary", "Food", "Transport", "Entertainment", "Bills", "Other"]
        self.accounts = ["Cash", "Bank", "Credit Card"]
        self.budgets = {"Food": 500, "Transport": 300, "Entertainment": 300, "Bills": 1000, "Other": 400}
        self.savings_goal = 5000

        # Boot Sequence
        self.init_ui()
        self.apply_style()
        self.load_autosave_if_present()
        
        # Non-blocking update check on boot
        QTimer.singleShot(0, self.check_for_updates_async)

    # ---------------- State Management ----------------

    def load_autosave_if_present(self):
        """Restores the user's previous session silently on startup."""
        autosave_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), AUTOSAVE_FILENAME)
        if not os.path.exists(autosave_path):
            return
        try:
            df = pd.read_csv(autosave_path)
            if df.empty: return
            self.df = self._normalize_dataframe(df)
            self._dirty = False
            self.sync_categories_accounts_from_data()
            self.refresh_all()
        except Exception:
            return # Fail gracefully if file is corrupted

    def autosave(self):
        """Saves current state to local disk to prevent data loss."""
        if not self._dirty: return
        try:
            self.df.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), AUTOSAVE_FILENAME), index=False)
            self._dirty = False
        except Exception: pass

    # ---------------- UI Architecture ----------------

    def init_ui(self):
        """Builds the main window layout: Sidebar + Main Content Area."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Sidebar Setup
        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar)

        # 2. Main Content Area Setup
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(25, 25, 25, 25)
        content_layout.setSpacing(18)

        # Build & Inject Components
        self.dashboard = self.create_dashboard()
        content_layout.addLayout(self.dashboard)

        # Savings Goal Section
        goal_container = QVBoxLayout()
        goal_container.setSpacing(6)
        
        goal_header_layout = QHBoxLayout()
        self.goal_label = QLabel(f"Savings Goal Progress (Goal: ${self.savings_goal:,.2f})")
        self.goal_label.setStyleSheet("font-weight: bold; color: #bbb; font-size: 12px;")
        
        set_goal_btn = QPushButton("Set Goal")
        set_goal_btn.setFixedWidth(90)
        # Style this button as an outlined secondary action
        set_goal_btn.setStyleSheet(f"background: #222; color: {BRAND_YELLOW}; border: 1px solid {BRAND_YELLOW}; font-weight: normal; padding: 4px;")
        set_goal_btn.clicked.connect(self.set_savings_goal)
        
        goal_header_layout.addWidget(self.goal_label)
        goal_header_layout.addStretch()
        goal_header_layout.addWidget(set_goal_btn)
        
        goal_container.addLayout(goal_header_layout)

        self.goal_bar = QProgressBar()
        goal_container.addWidget(self.goal_bar)
        content_layout.addLayout(goal_container)

        content_layout.addWidget(self.create_entry_form())

        # Data Views (Table & Chart split 55/45)
        data_layout = QHBoxLayout()
        data_layout.setSpacing(20)
        
        self.table = QTableWidget()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        data_layout.addWidget(self.table, stretch=12)

        self.canvas = FigureCanvas(plt.figure())
        data_layout.addWidget(self.canvas, stretch=10)
        
        content_layout.addLayout(data_layout)
        main_layout.addWidget(content_widget, stretch=1)

    def create_sidebar(self):
        """Constructs the navigation sidebar with QTAwesome icons."""
        sidebar = QFrame()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("""
            QFrame { background: #161616; border-right: 1px solid #222; }
            QPushButton { background: transparent; text-align: left; padding: 10px 12px; color: #bbb; font-weight: normal; border-radius: 4px; }
            QPushButton:hover { background: #202020; color: white; }
            QLabel { color: #666; font-size: 10px; font-weight: bold; letter-spacing: 1.2px; padding-left: 5px; margin-top: 15px; }
        """)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(15, 20, 15, 20)
        layout.setSpacing(4)

        # Branding Header (Logo + Title)
        header_layout = QHBoxLayout()
        logo = QLabel()
        if os.path.exists("FinanceTracker.png"):
            logo.setPixmap(QPixmap("FinanceTracker.png").scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        title = QLabel(f"Finance <span style='color:{BRAND_YELLOW}'>Pro</span>")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setStyleSheet("font-size: 16px; font-weight: bold; border: none; margin-top: 0px;")
        
        header_layout.addWidget(logo)
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        layout.addSpacing(15)

        # Navigation: Data Management
        layout.addWidget(QLabel("DATA MANAGEMENT"))
        
        load_btn = QPushButton(" Load CSV")
        load_btn.setIcon(qta.icon('fa5s.folder-open', color='#aaa'))
        load_btn.clicked.connect(self.load_csv)
        layout.addWidget(load_btn)

        save_btn = QPushButton(" Save CSV")
        save_btn.setIcon(qta.icon('fa5s.save', color='#aaa'))
        save_btn.clicked.connect(self.save_csv)
        layout.addWidget(save_btn)

        export_btn = QPushButton(" Export Chart")
        export_btn.setIcon(qta.icon('fa5s.chart-pie', color='#aaa'))
        export_btn.clicked.connect(self.export_chart)
        layout.addWidget(export_btn)

        # Navigation: Config
        layout.addWidget(QLabel("CONFIGURATION"))
        
        manage_cat_btn = QPushButton(" Manage Categories")
        manage_cat_btn.setIcon(qta.icon('fa5s.tags', color='#aaa'))
        manage_cat_btn.clicked.connect(self.manage_categories)
        layout.addWidget(manage_cat_btn)

        manage_acc_btn = QPushButton(" Manage Accounts")
        manage_acc_btn.setIcon(qta.icon('fa5s.wallet', color='#aaa'))
        manage_acc_btn.clicked.connect(self.manage_accounts)
        layout.addWidget(manage_acc_btn)

        # Navigation: AI Assistant Tools
        layout.addWidget(QLabel("AI ASSISTANT HUB"))
        
        self.ai_insights_btn = QPushButton(" Financial Insights")
        self.ai_insights_btn.setIcon(qta.icon('fa5s.lightbulb', color='#aaa'))
        self.ai_insights_btn.clicked.connect(self.run_ai_insights)
        layout.addWidget(self.ai_insights_btn)

        self.ai_budget_btn = QPushButton(" Budget Advisor")
        self.ai_budget_btn.setIcon(qta.icon('fa5s.chart-line', color='#aaa'))
        self.ai_budget_btn.clicked.connect(self.run_ai_budget_advisor)
        layout.addWidget(self.ai_budget_btn)

        self.ai_fraud_btn = QPushButton(" Fraud Check")
        self.ai_fraud_btn.setIcon(qta.icon('fa5s.shield-alt', color='#aaa'))
        self.ai_fraud_btn.clicked.connect(self.run_ai_fraud_check)
        layout.addWidget(self.ai_fraud_btn)

        self.ai_chat_btn = QPushButton(" AI Chat")
        self.ai_chat_btn.setIcon(qta.icon('fa5s.robot', color='#aaa'))
        self.ai_chat_btn.clicked.connect(self.run_ai_chat)
        layout.addWidget(self.ai_chat_btn)

        layout.addStretch()
        return sidebar

    def create_dashboard(self):
        """Builds the 4 primary metric cards at the top of the content area."""
        layout = QHBoxLayout()
        layout.setSpacing(15)

        self.income_card = self.create_card("Total Income", "#00c8ff")
        self.expense_card = self.create_card("Total Expenses", "#ff4d6d")
        self.savings_card = self.create_card("Net Savings", "#7cff6b")
        self.rate_card = self.create_card("Savings Rate", BRAND_YELLOW)

        layout.addWidget(self.income_card)
        layout.addWidget(self.expense_card)
        layout.addWidget(self.savings_card)
        layout.addWidget(self.rate_card)
        return layout

    def create_card(self, title, accent_color):
        """Helper to construct unified dashboard card components."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: #181818; 
                padding: 14px; 
                border-radius: 8px; 
                border: 1px solid #222;
                border-left: 4px solid {accent_color};
            }}
            QFrame:hover {{ background: #1d1d1d; }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        
        label_title = QLabel(title)
        label_title.setStyleSheet("font-size: 11px; color: #888; font-weight: bold; text-transform: uppercase; border: none;")
        
        label_value = QLabel("$0.00")
        label_value.setStyleSheet("font-size: 22px; font-weight: bold; color: white; border: none;")
        
        layout.addWidget(label_title)
        layout.addWidget(label_value)
        frame.value = label_value
        return frame

    def create_entry_form(self):
        """Builds the grid layout for adding new transactions."""
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #161616; border: 1px solid #222; border-radius: 8px; } QLabel { color: #aaa; border: none; }")
        layout = QGridLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Form Inputs
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())
        self.type_input = QComboBox()
        self.type_input.addItems(["Income", "Expense"])
        self.category_input = QComboBox()
        self.category_input.addItems(self.categories)
        self.account_input = QComboBox()
        self.account_input.addItems(self.accounts)
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("What was this for?")

        # Layout: Row 1
        layout.addWidget(QLabel("Date:"), 0, 0)
        layout.addWidget(self.date_input, 0, 1)
        layout.addWidget(QLabel("Type:"), 0, 2)
        layout.addWidget(self.type_input, 0, 3)
        layout.addWidget(QLabel("Category:"), 0, 4)
        layout.addWidget(self.category_input, 0, 5)

        # Layout: Row 2
        layout.addWidget(QLabel("Account:"), 1, 0)
        layout.addWidget(self.account_input, 1, 1)
        layout.addWidget(QLabel("Amount:"), 1, 2)
        layout.addWidget(self.amount_input, 1, 3)
        layout.addWidget(QLabel("Description:"), 1, 4)
        layout.addWidget(self.desc_input, 1, 5)

        # Layout: Row 3 (Action Buttons)
        btn_layout = QHBoxLayout()
        self.ai_category_btn = QPushButton(" Auto-Categorize")
        self.ai_category_btn.setIcon(qta.icon('fa5s.magic', color='#000'))
        # Maintain purple for "AI magic" distinctiveness
        self.ai_category_btn.setStyleSheet("background: #b388ff; color: black; font-weight: bold;")
        self.ai_category_btn.clicked.connect(self.run_ai_category)
        
        add_btn = QPushButton(" Add Transaction")
        add_btn.setIcon(qta.icon('fa5s.plus-circle', color='#000'))
        add_btn.clicked.connect(self.add_transaction)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.ai_category_btn)
        btn_layout.addWidget(add_btn)
        
        layout.addLayout(btn_layout, 2, 0, 1, 6)
        return frame

    # ---------------- Data Processing ----------------

    def _normalize_dataframe(self, df):
        """Ensures incoming CSV data conforms to the required application schema."""
        if "Type" not in df.columns or "Date" not in df.columns or "Amount" not in df.columns:
            raise ValueError("CSV must include Date, Type, and Amount columns.")
        data = df.copy()
        data["Amount"] = pd.to_numeric(data["Amount"], errors="coerce")
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
        if "Category" not in data.columns: data["Category"] = DEFAULT_CATEGORY
        if "Account" not in data.columns: data["Account"] = self.accounts[0] if self.accounts else "Default"
        if "Description" not in data.columns: data["Description"] = ""
        return data[COLUMNS]

    def _ensure_datetime(self):
        """Protects against pandas datatype drift during dataframe operations."""
        if not self.df.empty and "Date" in self.df.columns:
            if not pd.api.types.is_datetime64_any_dtype(self.df["Date"]):
                self.df["Date"] = pd.to_datetime(self.df["Date"], errors="coerce")

    def _compute_totals(self):
        """Aggregates raw data into high-level dashboard metrics."""
        income = self.df[self.df["Type"] == "Income"]["Amount"].sum()
        expense = self.df[self.df["Type"] == "Expense"]["Amount"].sum()
        savings = income - expense
        rate = (savings / income * 100) if income else 0
        return income, expense, savings, rate

    def _mark_dirty(self):
        """Flags the state as modified to trigger autosaves."""
        self._dirty = True

    # ---------------- Core Actions ----------------

    def load_csv(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open CSV", "", "CSV Files (*.csv)")
        if not file_paths: return
        try:
            dfs = [self._normalize_dataframe(pd.read_csv(f)) for f in file_paths]
            merged = pd.concat(dfs, ignore_index=True)
            self.df = merged if self.df.empty else pd.concat([self.df, merged], ignore_index=True)
            self._mark_dirty()
            self.sync_categories_accounts_from_data()
            self.refresh_all()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def save_csv(self):
        if self.df.empty:
            QMessageBox.information(self, "Nothing to Save", "There is no data to save yet.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
        if file_path:
            try:
                self.df.to_csv(file_path, index=False)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def add_transaction(self):
        """Validates input and appends a new transaction to the DataFrame."""
        amount_text = self.amount_input.text().strip()
        try:
            amount = float(amount_text)
            if amount <= 0: raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Error", "Amount must be a positive number.")
            return
        
        new_row = {
            "Date": pd.Timestamp(self.date_input.date().toPyDate()),
            "Type": self.type_input.currentText(),
            "Category": self.category_input.currentText(),
            "Account": self.account_input.currentText(),
            "Amount": amount,
            "Description": self.desc_input.text()
        }
        self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)
        self._mark_dirty()
        self.sync_categories_accounts_from_data()
        self.refresh_all()
        self.amount_input.clear()
        self.desc_input.clear()

    # ---------------- UI Render Pipeline ----------------

    def refresh_all(self):
        """Master render method to update all UI components when data changes."""
        if self.df.empty: return
        self._ensure_datetime()
        i, e, s, r = self._compute_totals()
        self.update_dashboard(i, e, s, r)
        self.update_table()
        self.update_chart()
        self.update_goal(s)
        self.autosave()

    def update_dashboard(self, income, expense, savings, rate):
        self.income_card.value.setText(f"${income:,.2f}")
        self.expense_card.value.setText(f"${expense:,.2f}")
        self.savings_card.value.setText(f"${savings:,.2f}")
        self.rate_card.value.setText(f"{rate:.1f}%")

    def set_savings_goal(self):
        value, ok = QInputDialog.getDouble(self, "Set Goal", "Target amount ($):", self.savings_goal, 1, 1e9, 2)
        if ok:
            self.savings_goal = value
            self.goal_label.setText(f"Savings Goal Progress (Goal: ${self.savings_goal:,.2f})")
            if not self.df.empty: self.update_goal(self._compute_totals()[2])

    def update_goal(self, savings):
        if not self.savings_goal:
            self.goal_bar.setValue(0)
            return
        percent = max(0, min(int((savings / self.savings_goal) * 100), 100))
        self.goal_bar.setValue(percent)

    def update_table(self):
        """Populates the QTableWidget with string-formatted pandas data."""
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self.df))
        self.table.setColumnCount(len(self.df.columns))
        self.table.setHorizontalHeaderLabels(self.df.columns)
        
        display_df = self.df.copy()
        if not display_df.empty and "Date" in display_df.columns:
            display_df['Date'] = display_df['Date'].dt.strftime('%Y-%m-%d')
        
        for i, row in enumerate(display_df.to_numpy()):
            for j, value in enumerate(row):
                self.table.setItem(i, j, QTableWidgetItem(str(value)))
        self.table.setUpdatesEnabled(True)

    def update_chart(self):
        """Renders matplotlib visualizations onto the embedded FigureCanvas."""
        plt.close("all")
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 5.5))
        fig.patch.set_facecolor("#121212")
        ax1.set_facecolor("#161616")
        ax2.set_facecolor("#161616")

        df = self.df
        if df.empty or "Date" not in df.columns:
            self.canvas.figure = fig
            self.canvas.draw()
            return

        # Prepare Cash Flow Line Chart Data
        month_index = df["Date"].dt.to_period("M")
        monthly = df.groupby([month_index, "Type"])["Amount"].sum().unstack(fill_value=0)
        monthly["Savings"] = monthly.get("Income", 0) - monthly.get("Expense", 0)
        monthly = monthly.reindex(columns=["Income", "Expense", "Savings"], fill_value=0)

        if not monthly.empty:
            monthly.plot(ax=ax1, color=LINE_COLORS, linewidth=2.0, marker="o", markersize=3)

        # Style Top Chart
        ax1.set_title("Cash Flow", color="white", fontsize=10, pad=8)
        ax1.tick_params(colors="gray", labelsize=8)
        ax1.grid(color="#222", alpha=0.8)
        
        legend = ax1.legend(fontsize=8)
        if legend:
            legend.get_frame().set_facecolor("#161616")
            legend.get_frame().set_edgecolor("#333")
            for text in legend.get_texts(): text.set_color("white")

        # Prepare Expenses Pie Chart Data
        category = df[df["Type"] == "Expense"].groupby("Category")["Amount"].sum()
        if not category.empty:
            ax2.pie(category.values, labels=category.index, autopct="%1.0f%%", 
                    textprops={"color": "white", "fontsize": 8}, colors=PIE_COLORS, 
                    wedgeprops={"edgecolor": "#121212", "linewidth": 1.5})
        ax2.set_title("Expenses by Category", color="white", fontsize=10, pad=8)

        # Prevent title/label overlaps with increased h_pad
        fig.tight_layout(pad=1.5, h_pad=2.5)
        self.canvas.figure = fig
        self.canvas.draw()

    def export_chart(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Chart", "", "PNG Files (*.png)")
        if path: self.canvas.figure.savefig(path)

    def apply_style(self):
        self.setStyleSheet(UI_STYLE)

    # ---------------- AI System & Threading ----------------

    def _check_ai_ready(self):
        """Verifies the OpenAI integration file is present before execution."""
        if ai_features is None:
            QMessageBox.warning(self, "AI Unavailable", "ai_features.py could not be imported.")
            return False
        if AI_IMPORT_ERROR:
            QMessageBox.warning(self, "AI Import Error", AI_IMPORT_ERROR)
            return False
        return True

    def _run_ai_task(self, button, worker, on_success):
        """
        Executes AI network calls on a background daemon thread.
        This prevents the PyQt UI from freezing while waiting for API responses.
        """
        button.setEnabled(False)
        done = threading.Event()

        def _finish_success(result):
            if done.is_set(): return
            done.set()
            on_success(result)

        def _finish_error(message):
            if done.is_set(): return
            done.set()
            self._show_ai_error(message)

        def _wrapped():
            try:
                result = worker()
                # Qt requires UI updates to happen on the main thread
                QTimer.singleShot(0, lambda: _finish_success(result))
            except Exception as e:
                QTimer.singleShot(0, lambda: _finish_error(str(e)))

        def _timeout():
            if done.is_set(): return
            done.set()
            self._show_ai_error("AI request timed out. Check your API key and network.")

        thread = threading.Thread(target=_wrapped, daemon=True)
        QTimer.singleShot(AI_UI_TIMEOUT_MS, _timeout)
        thread.start()

    # AI Feature Triggers
    def run_ai_insights(self):
        if not self._check_ai_ready() or self.df.empty: return
        self._run_ai_task(self.ai_insights_btn, lambda: ai_features.analyze_spending(self.df), self._show_ai_insights)

    def _show_ai_insights(self, result):
        self.ai_insights_btn.setEnabled(True)
        QMessageBox.information(self, "AI Insights", result or "No insights returned.")

    def run_ai_budget_advisor(self):
        if not self._check_ai_ready() or self.df.empty: return
        self._run_ai_task(self.ai_budget_btn, lambda: ai_features.budget_advice(self.df, self.budgets), self._show_ai_budget)

    def _show_ai_budget(self, result):
        self.ai_budget_btn.setEnabled(True)
        QMessageBox.information(self, "Budget Advisor", result or "No budget advice returned.")

    def run_ai_fraud_check(self):
        if not self._check_ai_ready() or self.df.empty: return
        self._run_ai_task(self.ai_fraud_btn, lambda: ai_features.detect_unusual_spending(self.df), self._show_ai_fraud)

    def _show_ai_fraud(self, result):
        self.ai_fraud_btn.setEnabled(True)
        QMessageBox.information(self, "Fraud Detection", result or "No fraud detected.")

    def run_ai_chat(self):
        if not self._check_ai_ready(): return
        q, ok = QInputDialog.getMultiLineText(self, "AI Chat", "Ask about your finances:")
        if ok and q.strip():
            self._run_ai_task(self.ai_chat_btn, lambda: ai_features.chat_assistant(self.df, q.strip()), self._show_ai_chat)

    def _show_ai_chat(self, result):
        self.ai_chat_btn.setEnabled(True)
        QMessageBox.information(self, "AI Chat", result or "No response.")

    def run_ai_category(self):
        if not self._check_ai_ready(): return
        desc = self.desc_input.text().strip()
        if not desc:
            QMessageBox.information(self, "Missing Description", "Enter a description first.")
            return
        self._run_ai_task(self.ai_category_btn, lambda: ai_features.suggest_category(desc, list(self.categories)), self._apply_ai_category)

    def _apply_ai_category(self, category):
        self.ai_category_btn.setEnabled(True)
        if category:
            idx = self.category_input.findText(category)
            if idx >= 0: self.category_input.setCurrentIndex(idx)

    def _show_ai_error(self, message):
        """Re-enables UI buttons upon network failure."""
        for btn in [self.ai_insights_btn, self.ai_category_btn, self.ai_budget_btn, self.ai_fraud_btn, self.ai_chat_btn]:
            btn.setEnabled(True)
        QMessageBox.warning(self, "AI Error", message)

    # ---------------- Application Settings ----------------

    def manage_categories(self):
        """Simple dialog flow to add/remove custom tracking categories."""
        action, ok = QInputDialog.getItem(self, "Manage Categories", "Action:", ["Add Category", "Remove Category"], 0, False)
        if not ok: return
        if action == "Add Category":
            name, ok = QInputDialog.getText(self, "Add", "Category name:")
            if ok and name.strip() and name.strip() not in self.categories:
                self.categories.append(name.strip())
                self.category_input.addItem(name.strip())
        elif self.categories:
            name, ok = QInputDialog.getItem(self, "Remove", "Select:", self.categories, 0, False)
            if ok and name in self.categories:
                self.categories.remove(name)
                idx = self.category_input.findText(name)
                if idx >= 0: self.category_input.removeItem(idx)

    def manage_accounts(self):
        """Simple dialog flow to add/remove financial accounts."""
        action, ok = QInputDialog.getItem(self, "Manage Accounts", "Action:", ["Add Account", "Remove Account"], 0, False)
        if not ok: return
        if action == "Add Account":
            name, ok = QInputDialog.getText(self, "Add", "Account name:")
            if ok and name.strip() and name.strip() not in self.accounts:
                self.accounts.append(name.strip())
                self.account_input.addItem(name.strip())
        elif len(self.accounts) > 1:
            name, ok = QInputDialog.getItem(self, "Remove", "Select:", self.accounts, 0, False)
            if ok and name in self.accounts:
                self.accounts.remove(name)
                idx = self.account_input.findText(name)
                if idx >= 0: self.account_input.removeItem(idx)

    def sync_categories_accounts_from_data(self):
        """Ensures lists contain historical categories/accounts when loading older CSV files."""
        if self.df.empty: return
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

    # ---------------- Utilities ----------------

    def check_for_updates_async(self):
        """Fires a background thread to check GitHub for newer releases."""
        threading.Thread(target=self._check_for_updates_worker, daemon=True).start()

    def _check_for_updates_worker(self):
        try:
            req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": f"FinanceTrackerPro/{APP_VERSION}"})
            with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT_SEC) as res:
                payload = json.loads(res.read().decode("utf-8"))
                latest = str(payload.get("version", "")).strip()
                if latest and self.normalize_version(latest) > self.normalize_version(APP_VERSION):
                    QTimer.singleShot(0, lambda: QMessageBox.information(self, "Update", f"New version {latest} available!"))
        except Exception: pass

    @staticmethod
    def normalize_version(v_text):
        """Parses semantic version strings for safe comparison."""
        return [int(''.join(c for c in p if c.isdigit()) or 0) for p in v_text.strip().split(".")]


# ---------------- Application Entry Point ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FinanceApp()
    window.show()
    sys.exit(app.exec())