import requests
import os
from dotenv import load_dotenv

load_dotenv()

class APIClient:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        self.base_url = "https://www.alphavantage.co/query"

    def fetch_stock_data(self, symbol):
        if not self.api_key:
            raise ValueError("API_KEY not found in environment.")
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": self.api_key
        }
        response = requests.get(self.base_url, params=params)
        response.raise_for_status()
        return response.json()
