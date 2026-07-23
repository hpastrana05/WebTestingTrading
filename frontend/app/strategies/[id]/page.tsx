"use client";

import { Suspense, use } from "react";
import StrategyCreator from "@/components/StrategyCreator";

export default function EditStrategyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <Suspense fallback={<p className="muted">Loading…</p>}>
      <StrategyCreator strategyId={id} />
    </Suspense>
  );
}
