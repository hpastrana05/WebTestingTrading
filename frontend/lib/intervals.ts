/** Candle intervals supported by Yahoo Finance / yfinance. */
export const DATA_INTERVALS = [
  { value: "1m", label: "1 Minute" },
  { value: "2m", label: "2 Minutes" },
  { value: "5m", label: "5 Minutes" },
  { value: "15m", label: "15 Minutes" },
  { value: "30m", label: "30 Minutes" },
  { value: "60m", label: "60 Minutes" },
  { value: "90m", label: "90 Minutes" },
  { value: "1h", label: "1 Hour" },
  { value: "1d", label: "1 Day" },
  { value: "5d", label: "5 Days" },
  { value: "1wk", label: "1 Week" },
  { value: "1mo", label: "1 Month" },
  { value: "3mo", label: "3 Months" },
] as const;
