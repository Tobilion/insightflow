"""pyqtgraph chart widgets.

Two views:

* :class:`PriceChart` -- close price, rolling-mean overlay, anomaly markers.
* :class:`ComparisonChart` -- several tickers rebased to 100 at the first
  shared date.

These widgets only plot. They take a DataFrame that ``analysis.enrich`` has
already decorated and render it; they never compute statistics themselves, so
what appears on screen is exactly what the tested functions produced.
"""

from __future__ import annotations

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

pg.setConfigOptions(antialias=True, background="w", foreground="k")

PRICE_PEN = pg.mkPen("#1f77b4", width=2)
MEAN_PEN = pg.mkPen("#ff7f0e", width=2, style=Qt.DashLine)
ANOMALY_BRUSH = pg.mkBrush("#d62728")
SERIES_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#8c564b"]


def _epochs(index: pd.DatetimeIndex):
    """pyqtgraph's DateAxisItem wants POSIX seconds, not datetimes."""
    return index.astype("int64") // 1_000_000_000


class _BasePlot(QWidget):
    def __init__(self, y_label: str, parent=None):
        super().__init__(parent)
        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(orientation="bottom")})
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("left", y_label)
        self.plot.setLabel("bottom", "Date")
        self.legend = self.plot.addLegend(offset=(10, 10))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot)

    def clear(self) -> None:
        self.plot.clear()
        self.legend.clear()


class PriceChart(_BasePlot):
    """Price line + rolling mean, with anomaly days marked."""

    def __init__(self, parent=None):
        super().__init__("Price", parent)

    def plot_frame(self, df: pd.DataFrame, symbol: str = "", window: int = 20) -> None:
        self.clear()
        if df is None or df.empty:
            return

        x = _epochs(df.index)
        self.plot.setTitle(f"{symbol} — daily close" if symbol else "Daily close")
        self.plot.plot(x, df["close"].to_numpy(), pen=PRICE_PEN, name=f"{symbol or 'Close'}")

        mean_col = f"rolling_mean_{window}"
        if mean_col in df.columns:
            mean = df[mean_col]
            valid = mean.notna()
            if valid.any():
                self.plot.plot(
                    _epochs(df.index[valid]),
                    mean[valid].to_numpy(),
                    pen=MEAN_PEN,
                    name=f"{window}-day mean",
                )

        if "anomaly" in df.columns:
            flagged = df[df["anomaly"].fillna(False).astype(bool)]
            if not flagged.empty:
                self.plot.plot(
                    _epochs(flagged.index),
                    flagged["close"].to_numpy(),
                    pen=None,
                    symbol="o",
                    symbolSize=9,
                    symbolBrush=ANOMALY_BRUSH,
                    symbolPen=None,
                    name=f"Anomalies (n={len(flagged)})",
                )

        self.plot.enableAutoRange()


class ComparisonChart(_BasePlot):
    """Normalised multi-ticker view: every series starts at 100."""

    def __init__(self, parent=None):
        super().__init__("Indexed to 100", parent)

    def plot_normalized(self, normalized: pd.DataFrame) -> None:
        self.clear()
        if normalized is None or normalized.empty:
            return

        self.plot.setTitle("Relative performance (first shared date = 100)")
        x = _epochs(normalized.index)
        for i, column in enumerate(normalized.columns):
            pen = pg.mkPen(SERIES_COLORS[i % len(SERIES_COLORS)], width=2)
            self.plot.plot(x, normalized[column].to_numpy(), pen=pen, name=str(column))

        # Baseline makes "ahead or behind the start" readable at a glance.
        self.plot.addLine(y=100, pen=pg.mkPen("#888888", width=1, style=Qt.DotLine))
        self.plot.enableAutoRange()
