import { Suspense } from "react";
import BacktestClient from "./BacktestClient";

export default function Page() {
  return (
    <Suspense fallback={<p className="muted">Loading backtest…</p>}>
      <BacktestClient />
    </Suspense>
  );
}
