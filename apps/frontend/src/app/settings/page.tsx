import { PageFrame } from "@/components/shell/PageFrame";
import { LivePanel } from "@/components/live/LivePanel";

export const metadata = { title: "Settings · StockX" };

// Momentum live, phase 1 (services/quant/docs/momentum-live-plan.md): settings and a read-only Zerodha account.
// Everything here is behind the operator sign-in; the old NIFTY 50 risk limits were removed with that system.
export default function SettingsPage() {
  return (
    <PageFrame title="Settings" description="Real-money trading of the momentum strategy, step by step. For now: your settings and a read-only view of your Zerodha account. No orders are placed.">
      <LivePanel />
    </PageFrame>
  );
}
