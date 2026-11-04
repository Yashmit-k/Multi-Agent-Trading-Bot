import "./globals.css";
import { Inter } from "next/font/google";
import { AppShell } from "@/components/shell/AppShell";
import { fetchApi } from "@/lib/api";
import type { ProvisionalSystemStatus } from "@/api/generated/provisional";
import { parseMode } from "@/lib/mode";

export const dynamic = "force-dynamic";
export const metadata = { title: "StockX · Momentum paper trial" };

const inter = Inter({ subsets: ["latin"] });

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  let mode: ReturnType<typeof parseMode> = "UNKNOWN";
  try {
    const status = await fetchApi<ProvisionalSystemStatus>("/api/v1/system/status");
    mode = parseMode(status.trading_mode);
  } catch {
    mode = "UNKNOWN";
  }
  return (
    <html lang="en">
      <body className={inter.className}>
        <AppShell mode={mode}>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
