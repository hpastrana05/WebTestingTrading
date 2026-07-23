import pandas as pd
import yfinance as yf


def _session():
    """
    Yahoo often blocks plain requests; curl_cffi Chrome impersonation
    is the current reliable approach used by recent yfinance versions.
    """
    try:
        from curl_cffi import requests as curl_requests

        return curl_requests.Session(impersonate="chrome")
    except Exception:
        return None


def fetch_ohlcv(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Download OHLCV data from Yahoo Finance via yf.download()."""
    session = _session()
    kwargs = {
        "tickers": symbol,
        "period": period,
        "interval": interval,
        "auto_adjust": True,
        "progress": False,
        "threads": False,
    }
    if session is not None:
        kwargs["session"] = session

    data = yf.download(**kwargs)

    if data is None or data.empty:
        raise ValueError(
            f"No data returned for symbol '{symbol}'. "
            "Yahoo may be rate-limiting or blocking requests — "
            "upgrade yfinance/curl_cffi, wait a bit, then retry."
        )

    # yf.download can return MultiIndex columns even for a single ticker
    if isinstance(data.columns, pd.MultiIndex):
        # Prefer (Price, Ticker) -> Price when ticker level exists
        if symbol in data.columns.get_level_values(-1):
            data = data.xs(symbol, axis=1, level=-1)
        else:
            data.columns = data.columns.get_level_values(0)

    columns = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in columns if c not in data.columns]
    if missing:
        raise ValueError(f"Missing columns for '{symbol}': {missing}")

    return data[columns].dropna(how="all")


print(fetch_ohlcv("AAPL", period="1mo", interval="1d").head())