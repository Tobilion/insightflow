"""Typed exceptions for the data layer.

The UI catches these to show actionable messages instead of a raw traceback.
Every failure mode the Alpha Vantage free tier can produce has a class here.
"""


class InsightFlowError(ValueError):
    """Base class for all InsightFlow data errors.

    Subclasses ``ValueError`` so that callers written against the older API --
    which raised plain ``ValueError`` from the client and processor -- keep
    working while new code can catch the specific subclass it cares about.
    """

    #: Short, user-facing suggestion shown beneath the error message in the UI.
    hint = ""


class MissingAPIKeyError(InsightFlowError):
    """No API key was configured and demo mode was not enabled."""

    hint = "Add an API key, or tick 'Use sample data' to explore the app offline."


class RateLimitError(InsightFlowError):
    """Alpha Vantage returned its 'Note'/'Information' throttle payload.

    The free tier allows 5 calls per minute and 25-500 calls per day depending
    on the plan. The API signals this with HTTP 200 and a JSON body, not a 429.
    """

    hint = "Free tier allows 5 calls/minute. Wait a minute, or use sample data."


class UnknownSymbolError(InsightFlowError):
    """The ticker was rejected by the API."""

    hint = "Check the ticker spelling, e.g. AAPL, MSFT, TSLA."


class NetworkError(InsightFlowError):
    """DNS failure, timeout, connection reset, or a non-2xx HTTP status."""

    hint = "Check your internet connection, or tick 'Use sample data'."


class DataFormatError(InsightFlowError):
    """The response parsed as JSON but did not contain the expected series."""

    hint = "The API returned an unexpected payload shape."
