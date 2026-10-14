import { Suspense } from "react";
import { TradingDashboard } from "@/components/dashboard/TradingDashboard";

export default function DashboardPage() {
  return (
    <Suspense fallback={<p data-testid="loading">Loading…</p>}>
      <TradingDashboard />
    </Suspense>
  );
}
