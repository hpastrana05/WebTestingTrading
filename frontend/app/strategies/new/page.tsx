"use client";

import { Suspense } from "react";
import StrategyCreator from "@/components/StrategyCreator";

export default function NewStrategyPage() {
  return (
    <Suspense fallback={<p className="muted">Loading…</p>}>
      <StrategyCreator />
    </Suspense>
  );
}
