import sys
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QTextEdit, QMessageBox, QLabel, QFrame,
    QGridLayout, QTableWidget, QTableWidgetItem, QLineEdit,
    QComboBox, QDateEdit, QProgressBar
)
from PyQt6.QtCore import QDate
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt


class FinanceApp(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Finance Tracker Pro")
        self.resize(1200, 800)

        self.df = pd.DataFrame(columns=[
            "Date", "Type", "Category", "Amount", "Description"
        ])

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

    # ---------------- UI ----------------

    def init_ui(self):

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        load_btn = QPushButton("Load CSV")
        load_btn.clicked.connect(self.load_csv)

        export_btn = QPushButton("Export Chart")
        export_btn.clicked.connect(self.export_chart)

        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(export_btn)

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
        frame.setStyleSheet("background:#1e1e1e; padding:15px; border-radius:10px;")

        layout = QVBoxLayout()

        label_title = QLabel(title)
        label_value = QLabel("0")

        label_title.setStyleSheet("font-size:14px; color:gray;")
        label_value.setStyleSheet("font-size:22px;")

        layout.addWidget(label_title)
        layout.addWidget(label_value)

        frame.setLayout(layout)
        frame.value = label_value

        return frame

    # ---------------- Entry Form ----------------

    def create_entry_form(self):

        layout = QHBoxLayout()

        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())

        self.type_input = QComboBox()
        self.type_input.addItems(["Income", "Expense"])

        self.category_input = QComboBox()
        self.category_input.addItems(
            ["Salary", "Food", "Transport", "Entertainment", "Bills", "Other"]
        )

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("Amount")

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Description")

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_transaction)

        layout.addWidget(self.date_input)
        layout.addWidget(self.type_input)
        layout.addWidget(self.category_input)
        layout.addWidget(self.amount_input)
        layout.addWidget(self.desc_input)
        layout.addWidget(add_btn)

        return layout

    # ---------------- Load CSV ----------------

    def load_csv(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open CSV", "", "CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            df = pd.read_csv(file_path)

            df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
            df["Date"] = pd.to_datetime(df["Date"])

            self.df = df

            self.refresh_all()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ---------------- Add Transaction ----------------

    def add_transaction(self):

        try:

            date = self.date_input.date().toString("yyyy-MM-dd")
            ttype = self.type_input.currentText()
            category = self.category_input.currentText()
            amount = float(self.amount_input.text())
            desc = self.desc_input.text()

            new_row = {
                "Date": date,
                "Type": ttype,
                "Category": category,
                "Amount": amount,
                "Description": desc
            }

            self.df = pd.concat(
                [self.df, pd.DataFrame([new_row])],
                ignore_index=True
            )

            self.refresh_all()

        except:
            QMessageBox.warning(self, "Error", "Invalid input")

    # ---------------- Refresh ----------------

    def refresh_all(self):

        if self.df.empty:
            return

        self.df["Date"] = pd.to_datetime(self.df["Date"])

        self.update_dashboard()
        self.update_table()
        self.update_chart()
        self.update_goal()

    # ---------------- Dashboard Update ----------------

    def update_dashboard(self):

        income = self.df[self.df["Type"] == "Income"]["Amount"].sum()
        expense = self.df[self.df["Type"] == "Expense"]["Amount"].sum()
        savings = income - expense

        rate = (savings / income * 100) if income else 0

        self.income_card.value.setText(f"${income:,.2f}")
        self.expense_card.value.setText(f"${expense:,.2f}")
        self.savings_card.value.setText(f"${savings:,.2f}")
        self.rate_card.value.setText(f"{rate:.1f}%")

    # ---------------- Goal Progress ----------------

    def update_goal(self):

        income = self.df[self.df["Type"] == "Income"]["Amount"].sum()
        expense = self.df[self.df["Type"] == "Expense"]["Amount"].sum()

        savings = income - expense

        percent = int((savings / self.savings_goal) * 100)
        percent = max(0, min(percent, 100))

        self.goal_bar.setValue(percent)

    # ---------------- Table ----------------

    def update_table(self):

        df = self.df.copy()

        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))

        self.table.setHorizontalHeaderLabels(df.columns)

        for i in range(len(df)):
            for j in range(len(df.columns)):
                self.table.setItem(
                    i, j,
                    QTableWidgetItem(str(df.iloc[i, j]))
                )

    # ---------------- Charts ----------------

    def update_chart(self):

        plt.close("all")

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

        df = self.df.copy()
        df["Month"] = df["Date"].dt.to_period("M")

        monthly = df.groupby(["Month", "Type"])["Amount"].sum().unstack(fill_value=0)
        monthly["Savings"] = monthly.get("Income", 0) - monthly.get("Expense", 0)

        monthly.plot(ax=ax1)
        ax1.set_title("Income vs Expenses")

        category = df[df["Type"] == "Expense"].groupby("Category")["Amount"].sum()

        if not category.empty:
            category.plot(kind="pie", ax=ax2, autopct="%1.0f%%")

        ax2.set_title("Expense Distribution")

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

        self.setStyleSheet("""
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
        """)


# ---------------- Run ----------------

if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = FinanceApp()
    window.show()

    sys.exit(app.exec())