import "./globals.css";
import { Inter } from "next/font/google";
import { AppShell } from "@/components/shell/AppShell";
import { fetchApi } from "@/lib/api";
import type { ProvisionalRiskStatus, ProvisionalSystemStatus } from "@/api/generated/provisional";
import { parseMode } from "@/lib/mode";

export const dynamic = "force-dynamic";
export const metadata = { title: "Trading Overview" };

const inter = Inter({ subsets: ["latin"] });

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  let mode: ReturnType<typeof parseMode> = "UNKNOWN";
  let killSwitch = "UNKNOWN";
  try {
    const status = await fetchApi<ProvisionalSystemStatus>("/api/v1/system/status");
    mode = parseMode(status.trading_mode);
  } catch {
    mode = "UNKNOWN";
  }
  try {
    const risk = await fetchApi<ProvisionalRiskStatus>("/api/v1/risk/status");
    killSwitch = risk.kill_switch ?? "UNKNOWN";
  } catch {
    killSwitch = "UNKNOWN";
  }
  return (
    <html lang="en">
      <body className={inter.className}>
        <AppShell mode={mode} killSwitch={killSwitch}>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
