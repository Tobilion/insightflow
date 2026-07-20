"""Wizard UI: configure -> select -> results.

The window's only job is orchestration and display. It holds a client object
that satisfies ``fetch_stock_data(symbol) -> dict`` and never asks whether that
object is live, cached, or bundled sample data.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from insightflow.services import analysis
from insightflow.services.api_client import APIClient, DemoClient, available_sample_symbols
from insightflow.services.cache import CachedClient, PayloadCache
from insightflow.services.errors import InsightFlowError
from insightflow.services.processor import DataProcessor
from insightflow.ui.chart_widget import ComparisonChart, PriceChart

STEP_CONFIG, STEP_SELECT, STEP_RESULT = 0, 1, 2
ROLLING_WINDOW = 20
SIGMA = 2.0


class MainWindow(QMainWindow):
    def __init__(self, demo: bool = False, use_cache: bool = True):
        super().__init__()
        self.setWindowTitle("InsightFlow")
        self.setMinimumSize(980, 720)

        self.demo = demo
        self.use_cache = use_cache
        self.processor = DataProcessor()
        self.client = None
        self.frames: dict = {}

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        self.status = self.statusBar()

        self._build_config_step()
        self._build_select_step()
        self._build_result_step()

        if self.demo:
            self.demo_checkbox.setChecked(True)
            self._enter_select_step()

    # ------------------------------------------------------------------ steps

    def _build_config_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(12)

        layout.addWidget(QLabel("<h2>Welcome to InsightFlow</h2>"))
        blurb = QLabel(
            "Enter an Alpha Vantage API key to fetch live data, or tick the box "
            "below to explore the app with bundled sample data — no key, no "
            "network, no signup."
        )
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        form = QFormLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Alpha Vantage API key")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        form.addRow("API key:", self.api_key_input)
        layout.addLayout(form)

        self.demo_checkbox = QCheckBox("Use sample data (offline demo mode)")
        self.demo_checkbox.toggled.connect(self._on_demo_toggled)
        layout.addWidget(self.demo_checkbox)

        self.cache_checkbox = QCheckBox("Cache responses locally (saves API calls)")
        self.cache_checkbox.setChecked(self.use_cache)
        layout.addWidget(self.cache_checkbox)

        self.config_error = QLabel()
        self.config_error.setStyleSheet("color: #b00020;")
        self.config_error.setWordWrap(True)
        layout.addWidget(self.config_error)

        next_button = QPushButton("Continue")
        next_button.setDefault(True)
        next_button.clicked.connect(self._enter_select_step)
        layout.addWidget(next_button)
        layout.addStretch(1)

        self.stacked_widget.addWidget(page)

    def _build_select_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(12)

        layout.addWidget(QLabel("<h2>Choose what to analyse</h2>"))

        self.primary_input = QComboBox()
        self.primary_input.setEditable(True)
        self.secondary_input = QComboBox()
        self.secondary_input.setEditable(True)

        form = QFormLayout()
        form.addRow("Ticker:", self.primary_input)
        form.addRow("Compare with (optional):", self.secondary_input)
        layout.addLayout(form)

        self.source_hint = QLabel()
        self.source_hint.setWordWrap(True)
        self.source_hint.setStyleSheet("color: #555;")
        layout.addWidget(self.source_hint)

        buttons = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(STEP_CONFIG))
        fetch = QPushButton("Analyse")
        fetch.setDefault(True)
        fetch.clicked.connect(self.fetch_data)
        buttons.addWidget(back)
        buttons.addStretch(1)
        buttons.addWidget(fetch)
        layout.addLayout(buttons)

        self.select_error = QLabel()
        self.select_error.setStyleSheet("color: #b00020;")
        self.select_error.setWordWrap(True)
        layout.addWidget(self.select_error)
        layout.addStretch(1)

        self.stacked_widget.addWidget(page)

    def _build_result_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        self.summary_box = QGroupBox("Summary")
        summary_layout = QVBoxLayout(self.summary_box)
        self.summary_label = QLabel()
        self.summary_label.setTextFormat(Qt.RichText)
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_box)

        self.tabs = QTabWidget()
        self.price_chart = PriceChart()
        self.comparison_chart = ComparisonChart()
        self.result_display = QTextEdit()
        self.result_display.setReadOnly(True)
        self.result_display.setLineWrapMode(QTextEdit.NoWrap)
        self.result_display.setStyleSheet("font-family: monospace;")

        self.tabs.addTab(self.price_chart, "Price && anomalies")
        self.tabs.addTab(self.comparison_chart, "Comparison")
        self.tabs.addTab(self.result_display, "Data")
        layout.addWidget(self.tabs, 1)

        back = QPushButton("Analyse another ticker")
        back.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(STEP_SELECT))
        layout.addWidget(back)

        self.stacked_widget.addWidget(page)

    # ----------------------------------------------------------------- wiring

    def _on_demo_toggled(self, checked: bool):
        self.api_key_input.setEnabled(not checked)
        self.cache_checkbox.setEnabled(not checked)
        if checked:
            self.config_error.clear()

    def _build_client(self):
        """Assemble the client stack once, based on the config screen."""
        if self.demo_checkbox.isChecked():
            self.demo = True
            return DemoClient()

        self.demo = False
        client = APIClient(api_key=self.api_key_input.text().strip() or None)
        if self.cache_checkbox.isChecked():
            return CachedClient(client, PayloadCache())
        return client

    def _enter_select_step(self):
        if not self.demo_checkbox.isChecked() and not self.api_key_input.text().strip():
            self.config_error.setText(
                "Enter an API key, or tick 'Use sample data' to run the offline demo."
            )
            return

        self.config_error.clear()
        self.client = self._build_client()

        samples = available_sample_symbols()
        for box in (self.primary_input, self.secondary_input):
            box.clear()
        self.secondary_input.addItem("")
        if self.demo:
            self.primary_input.addItems(samples)
            self.secondary_input.addItems(samples)
            self.source_hint.setText(
                f"Demo mode — bundled sample data for: {', '.join(samples)}."
            )
        else:
            self.primary_input.addItems(["AAPL", "MSFT", "TSLA"])
            self.secondary_input.addItems(["AAPL", "MSFT", "TSLA"])
            self.primary_input.setCurrentText("")
            self.source_hint.setText(
                "Live mode — the free tier allows 5 calls per minute. "
                "Repeat lookups are served from the local cache."
            )
        self.secondary_input.setCurrentText("")
        self.select_error.clear()
        self.stacked_widget.setCurrentIndex(STEP_SELECT)

    # ---------------------------------------------------------------- actions

    def _load(self, symbol: str):
        """Fetch + clean + enrich one ticker. Returns (frame, source)."""
        payload = self.client.fetch_stock_data(symbol)
        frame = self.processor.process_stock_data(payload)
        enriched = analysis.enrich(frame, window=ROLLING_WINDOW, sigma=SIGMA)
        source = getattr(self.client, "last_source", None) or (
            "sample data" if self.demo else "network"
        )
        return enriched, source

    def fetch_data(self):
        primary = self.primary_input.currentText().strip().upper()
        secondary = self.secondary_input.currentText().strip().upper()

        if not primary:
            self.select_error.setText("Enter a ticker symbol.")
            return

        self.select_error.clear()
        self.status.showMessage(f"Fetching {primary}…")

        try:
            frames, sources = {}, {}
            frames[primary], sources[primary] = self._load(primary)
            if secondary and secondary != primary:
                frames[secondary], sources[secondary] = self._load(secondary)
        except InsightFlowError as exc:
            self.status.clearMessage()
            hint = f"<br><i>{exc.hint}</i>" if exc.hint else ""
            self.select_error.setText(f"{exc}{hint}")
            return
        except Exception as exc:  # unexpected -- still must not crash the app
            self.status.clearMessage()
            self.select_error.setText(f"Unexpected error: {exc}")
            return

        self.frames = frames
        self._render(primary, frames, sources)
        self.stacked_widget.setCurrentIndex(STEP_RESULT)
        self.status.showMessage(
            "   ".join(f"{sym}: {src}" for sym, src in sources.items()), 8000
        )

    def _render(self, primary: str, frames: dict, sources: dict):
        stats = analysis.summarize(frames[primary], window=ROLLING_WINDOW, sigma=SIGMA)
        self.summary_label.setText(
            "<table cellpadding='4'>"
            f"<tr><td><b>{primary}</b></td>"
            f"<td>{stats['start_date']:%Y-%m-%d} → {stats['end_date']:%Y-%m-%d}</td>"
            f"<td>{stats['observations']} sessions</td>"
            f"<td>source: {sources.get(primary, '—')}</td></tr>"
            f"<tr><td>Total return</td><td>{stats['total_return']:+.2%}</td>"
            f"<td>Annualised volatility</td><td>{stats['annualized_volatility']:.2%}</td></tr>"
            f"<tr><td>Max drawdown</td><td>{stats['max_drawdown']:.2%}</td>"
            f"<td>Anomaly days (±{SIGMA:g}σ)</td><td>{stats['anomaly_count']}</td></tr>"
            "</table>"
        )

        self.price_chart.plot_frame(frames[primary], symbol=primary, window=ROLLING_WINDOW)

        if len(frames) > 1:
            self.tabs.setTabEnabled(1, True)
            self.comparison_chart.plot_normalized(analysis.compare(frames))
        else:
            self.comparison_chart.clear()
            self.tabs.setTabEnabled(1, False)

        columns = [
            "close",
            f"rolling_mean_{ROLLING_WINDOW}",
            "daily_return",
            "drawdown",
            "anomaly",
        ]
        self.result_display.setPlainText(frames[primary][columns].tail(60).to_string())
