"use client";

import { use } from "react";
import StrategyCreator from "@/components/StrategyCreator";

export default function EditStrategyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <StrategyCreator strategyId={id} />;
}
