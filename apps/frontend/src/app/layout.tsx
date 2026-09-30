import "./globals.css";
import { Nav } from "@/components/Nav";
import { ModeBanner } from "@/components/ModeBanner";
import { fetchApi } from "@/lib/api";
import type { ProvisionalSystemStatus } from "@/api/generated/provisional";
import { parseMode } from "@/lib/mode";

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
      <body>
        <ModeBanner mode={mode} />
        <Nav />
        <main className="p-4">{children}</main>
      </body>
    </html>
  );
}
