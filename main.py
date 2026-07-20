"""Entry point.

``python -m insightflow.main --demo`` gives a fully working app on a fresh
clone: no API key, no network, no signup.
"""

from __future__ import annotations

import argparse
import sys


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="insightflow",
        description="Desktop stock analysis wizard (PySide6 + Pandas).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Start in demo mode using bundled sample data — no API key required.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable the local SQLite response cache.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # Qt is imported inside main() rather than at module scope so that
    # --help, and importing this module in tests, work without PySide6 loaded.
    from PySide6.QtWidgets import QApplication

    from insightflow.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    window = MainWindow(demo=args.demo, use_cache=not args.no_cache)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
