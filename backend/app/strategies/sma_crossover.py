import pandas as pd

from app.strategies.base import Strategy


class SmaCrossover(Strategy):
    id = "sma_crossover"
    name = "SMA Crossover"
    description = "Go long when the fast SMA crosses above the slow SMA; exit on cross below."
    parameters = {
        "fast": {"type": "int", "default": 10, "min": 2, "max": 100, "step": 1},
        "slow": {"type": "int", "default": 30, "min": 5, "max": 200, "step": 1},
    }

    def generate_signals(self, data: pd.DataFrame, params: dict) -> pd.Series:
        params = self.resolve_params(params)
        fast = int(params["fast"])
        slow = int(params["slow"])
        if fast >= slow:
            raise ValueError("fast SMA period must be smaller than slow SMA period")

        close = data["Close"]
        fast_sma = close.rolling(fast).mean()
        slow_sma = close.rolling(slow).mean()

        signal = (fast_sma > slow_sma).astype(int)
        signal = signal.fillna(0)
        return signal
