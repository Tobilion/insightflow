# InsightFlow

A desktop stock-analysis tool built with Python, PySide6 and Pandas. It fetches
daily price history, runs a quantitative analysis pass over it, and charts the
result — with a guided three-step wizard and a layered architecture that keeps
network, cleaning, statistics and presentation strictly separate.

## Try it in 30 seconds

No API key. No signup. No network.

```bash
git clone <this-repo>
pip install -r insightflow/requirements.txt
python -m insightflow.main --demo
```

Demo mode is backed by sample JSON committed to `data/samples/` in the exact
Alpha Vantage response format, so the entire pipeline — parsing, cleaning,
analysis, charting — runs on real-shaped data. You can also tick **Use sample
data** on the first screen at any time.

For live data, get a free [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
key and either enter it on the first screen or put it in a `.env` file:

```
API_KEY=your_key_here
```

```bash
python -m insightflow.main            # live mode, caching on
python -m insightflow.main --no-cache # live mode, cache disabled
```

## Features

**Demo mode.** A bundled offline dataset means the app is usable the moment it
is cloned, and the test suite can exercise the full pipeline without a network.

**Real analysis.** `services/analysis.py` computes daily and log returns,
20-day rolling mean and volatility (optionally annualised), max drawdown and
the underwater curve, and flags anomalous sessions beyond ±2σ. Every function
is pure Pandas/NumPy, takes a DataFrame, returns a new object, and is
independently unit-tested.

**Charts.** A pyqtgraph price chart overlays the rolling mean on the close
price and marks the anomalous days in red. A second tab compares two tickers
rebased to 100 at their first shared date, so relative performance is readable
regardless of share price.

**Caching.** Responses are cached in SQLite (`~/.insightflow/cache.sqlite3`,
6-hour TTL), so repeat lookups cost nothing against the free tier's 5-calls-per-
minute budget. Failed requests are never cached, so a transient rate-limit
response cannot poison a symbol.

**Real failure handling.** Alpha Vantage signals throttling, unknown tickers
and errors with HTTP 200 and a different JSON key, so status codes alone are
not enough. `services/errors.py` defines a typed exception per failure mode —
rate limit, unknown symbol, network failure, missing key, malformed payload —
each carrying a user-facing hint that the UI renders instead of a traceback.

## Architecture

```
main.py                  CLI entry point (--demo, --no-cache)
ui/
  main_window.py         Three-step wizard; orchestration and display only
  chart_widget.py        pyqtgraph price and comparison charts
services/
  api_client.py          APIClient (live) and DemoClient (bundled samples)
  cache.py               SQLite store + CachedClient decorator
  processor.py           Raw payload -> clean, sorted, numeric DataFrame
  analysis.py            Pure statistical functions
  errors.py              Typed, user-facing exceptions
data/samples/            Bundled Alpha Vantage-shaped JSON for demo mode
tests/                   Unit tests + fixtures
```

The three data sources — `APIClient`, `DemoClient` and `CachedClient` — all
satisfy the same one-method interface, `fetch_stock_data(symbol) -> dict`, and
`CachedClient` wraps either of the others. The UI holds one of them and never
learns which: whether a chart was drawn from the network, from SQLite or from a
bundled sample changes nothing above the service layer. Swapping the data
provider or the cache backend is a one-file change.

Layers are also ordered by purity. `processor.py` cleans and never computes;
`analysis.py` computes and never does I/O; `ui/` displays and never computes.
That is what makes the analysis layer testable without Qt or a network.

## Tests

```bash
python -m unittest discover -s insightflow/tests -t .
```

87 tests, no network access and no display server required. Coverage is
deliberately aimed at the claims this README makes:

- Every analysis function is tested against hand-built fixtures with
  known answers — a series engineered for a -50% drawdown, one with a single
  planted outlier, one with constant +10% daily returns — so the assertions are
  verifiable by hand rather than by re-running the code under test.
- Demo mode is proven: every bundled sample runs the full pipeline, and
  `requests.get` is patched to raise if it is called at all.
- Each API failure mode is exercised with a mocked response: rate-limit
  (both the `Note` and `Information` variants), unknown symbol, empty series,
  connection error, timeout, HTTP 5xx, and non-JSON bodies.
- Cache behaviour is proven: a repeat lookup makes exactly one call to the
  inner client, TTL expiry is a miss, corrupt rows degrade to a miss, and
  errors propagate without being cached.
- The CLI is tested headlessly, including a guard that Qt is never imported at
  module scope in `main.py`.

## Tech stack

Python · PySide6 (Qt) · pyqtgraph · Pandas · NumPy · SQLite · Requests
