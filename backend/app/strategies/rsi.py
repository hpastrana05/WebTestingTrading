import pandas as pd

from app.strategies.base import Strategy


class RsiStrategy(Strategy):
    id = "rsi"
    name = "RSI Mean Reversion"
    description = "Buy when RSI drops below oversold; sell when RSI rises above overbought."
    parameters = {
        "period": {"type": "int", "default": 14, "min": 5, "max": 50, "step": 1},
        "oversold": {"type": "int", "default": 30, "min": 5, "max": 40, "step": 1},
        "overbought": {"type": "int", "default": 70, "min": 60, "max": 95, "step": 1},
    }

    def generate_signals(self, data: pd.DataFrame, params: dict) -> pd.Series:
        params = self.resolve_params(params)
        period = int(params["period"])
        oversold = int(params["oversold"])
        overbought = int(params["overbought"])

        close = data["Close"]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))

        # Hold long while between oversold entry and overbought exit
        signal = pd.Series(0, index=data.index, dtype=int)
        position = 0
        for i, value in enumerate(rsi):
            if pd.isna(value):
                signal.iloc[i] = position
                continue
            if position == 0 and value <= oversold:
                position = 1
            elif position == 1 and value >= overbought:
                position = 0
            signal.iloc[i] = position

        return signal
