import requests
import os
from dotenv import load_dotenv

load_dotenv()

class APIClient:
    def __init__(self):
        self.base_url = "https://www.alphavantage.co/query"

    @property
    def api_key(self):
        return os.getenv("API_KEY")

    def fetch_stock_data(self, symbol):
        key = self.api_key
        if not key:
            raise ValueError("API_KEY not found in environment.")
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": key
        }
        response = requests.get(self.base_url, params=params)
        response.raise_for_status()
        return response.json()
