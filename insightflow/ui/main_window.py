from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget, QPushButton, QLabel, QLineEdit, QTextEdit
from insightflow.services.api_client import APIClient
from insightflow.services.processor import DataProcessor

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("InsightFlow")
        self.setMinimumSize(400, 300)

        self.api_client = APIClient()
        self.processor = DataProcessor()

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.init_steps()

    def init_steps(self):
        # Step 1: Config
        self.step1 = QWidget()
        layout1 = QVBoxLayout()
        layout1.addWidget(QLabel("Enter API Key:"))
        self.api_key_input = QLineEdit()
        layout1.addWidget(self.api_key_input)
        btn1 = QPushButton("Next")
        btn1.clicked.connect(self.go_to_step2)
        layout1.addWidget(btn1)
        self.step1.setLayout(layout1)

        # Step 2: Selection
        self.step2 = QWidget()
        layout2 = QVBoxLayout()
        layout2.addWidget(QLabel("Enter Ticker Symbol:"))
        self.ticker_input = QLineEdit()
        layout2.addWidget(self.ticker_input)
        btn2 = QPushButton("Fetch")
        btn2.clicked.connect(self.fetch_data)
        layout2.addWidget(btn2)
        self.step2.setLayout(layout2)

        # Step 3: Result
        self.step3 = QWidget()
        layout3 = QVBoxLayout()
        self.result_display = QTextEdit()
        layout3.addWidget(self.result_display)
        self.step3.setLayout(layout3)

        self.stacked_widget.addWidget(self.step1)
        self.stacked_widget.addWidget(self.step2)
        self.stacked_widget.addWidget(self.step3)

    def go_to_step2(self):
        # Save key temporarily, normally would be .env
        import os
        os.environ["API_KEY"] = self.api_key_input.text()
        self.stacked_widget.setCurrentIndex(1)

    def fetch_data(self):
        try:
            data = self.api_client.fetch_stock_data(self.ticker_input.text())
            df = self.processor.process_stock_data(data)
            self.result_display.setPlainText(df.head().to_string())
            self.stacked_widget.setCurrentIndex(2)
        except Exception as e:
            self.result_display.setPlainText(f"Error: {e}")
            self.stacked_widget.setCurrentIndex(2)
