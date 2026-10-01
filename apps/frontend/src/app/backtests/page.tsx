import { NotAvailableState } from "@/components/States";

export default function BacktestsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold">Backtests</h1>
      <NotAvailableState feature="GET /api/v1/backtests" />
    </div>
  );
}
