import pandas as pd

class DataProcessor:
    @staticmethod
    def process_stock_data(json_data):
        if "Time Series (Daily)" not in json_data:
            raise ValueError("Invalid data format or API limit reached.")
        
        data = json_data["Time Series (Daily)"]
        df = pd.DataFrame.from_dict(data, orient="index")
        df.index = pd.to_datetime(df.index)
        df.columns = ["open", "high", "low", "close", "volume"]
        return df.astype(float)
