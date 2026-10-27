export const metadata = { title: "Overview · StockX" };
export const dynamic = "force-dynamic";
import { Suspense } from "react";
import { PipelineStrip } from "@/components/PipelineStrip";
import { GlobalOpenLine } from "@/components/GlobalOpenLine";
import { TradingDashboard } from "@/components/dashboard/TradingDashboard";

export default function DashboardPage() {
  return (
    <>
      <Suspense fallback={null}>
        <PipelineStrip />
      </Suspense>
      <Suspense fallback={null}>
        <GlobalOpenLine />
      </Suspense>
      <Suspense fallback={<p data-testid="loading">Loading…</p>}>
        <TradingDashboard />
      </Suspense>
    </>
  );
}
