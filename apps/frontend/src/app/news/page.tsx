import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";
import { Empty, Score, SymbolLink, Table, Td } from "@/components/ui";
import { istTime } from "@/lib/format";
import { provenance, sourceLabel } from "@/lib/signal-provenance";
import { loadSignals } from "@/lib/signals";

export const metadata = { title: "News · StockX" };
export const dynamic = "force-dynamic";

// Live headlines, as scored by the News agent. Each row is a stored agent signal; the
// headline list comes from that signal's metadata, so nothing here is a fixture.
export default async function NewsPage() {
  try {
    const rows = await loadSignals({ agent: "news", limit: 800 });
    // One row per distinct headline and stock, newest first: every live headline the News agent scored.
    const seen = new Set<string>();
    const scored: Array<{ row: (typeof rows)[number]; title: string; source?: string }> = [];
    for (const row of rows) {
      for (const item of provenance(row as unknown as Record<string, unknown>).headlines) {
        const key = `${row.symbol}|${item.title}`;
        if (!item.title || seen.has(key)) continue;
        seen.add(key);
        scored.push({ row, title: item.title, source: item.source });
      }
    }
    const shown = scored.slice(0, 200);
    const stocks = new Set(shown.map((item) => item.row.symbol)).size;
    return (
      <PageFrame
        title="News"
        description="Live RSS headlines mapped to NIFTY 50 stocks and scored by the News agent (Gemini). Newest first."
      >
        {shown.length === 0 ? (
          <Empty>The News agent has not scored a live headline yet. Feeds are polled every 5 minutes.</Empty>
        ) : (
          <>
            <p className="text-xs text-[#64748B]">
              {shown.length} headlines across {stocks} NIFTY 50 stocks, from 16 feeds (ET, Business Standard, Mint, BusinessLine, NDTV Profit, CNBC-TV18). Headlines that name no NIFTY 50 company are not shown.
            </p>
            <Table head={["Stock", "Score", "Headline", "Scored by", "Time (IST)"]} minWidth={820}>
              {shown.map(({ row, title, source }) => (
                <tr key={`${row.signal_id}-${title}`}>
                  <Td>
                    <SymbolLink symbol={row.symbol} />
                  </Td>
                  <Td>
                    <Score value={row.signal} />
                  </Td>
                  <Td>
                    {title} <span className="text-xs text-[#64748B]">({source})</span>
                  </Td>
                  <Td className="text-xs text-[#94A3B8]">{sourceLabel("news", row as unknown as Record<string, unknown>)}</Td>
                  <Td className="whitespace-nowrap text-xs text-[#94A3B8]">{istTime(row.timestamp)}</Td>
                </tr>
              ))}
            </Table>
          </>
        )}
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="News">
        <ErrorState message={error instanceof Error ? error.message : "news_unavailable"} />
      </PageFrame>
    );
  }
}
