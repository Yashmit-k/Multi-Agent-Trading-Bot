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
    const rows = await loadSignals({ agent: "news", limit: 400 });
    const seen = new Set<string>();
    const scored = rows.filter((row) => {
      if (provenance(row as unknown as Record<string, unknown>).headlines.length === 0 || seen.has(row.symbol)) return false;
      seen.add(row.symbol);
      return true;
    });
    return (
      <PageFrame
        title="News"
        description="Live RSS headlines (ET Markets, Business Standard, Mint) mapped to NIFTY 50 stocks and scored by the News agent. Newest score per stock."
      >
        {scored.length === 0 ? (
          <Empty>The News agent has not scored a live headline yet. Feeds are polled every 5 minutes.</Empty>
        ) : (
          <Table head={["Stock", "Score", "Headline", "Scored by", "Time (IST)"]} minWidth={820}>
            {scored.map((row) => {
              const p = provenance(row as unknown as Record<string, unknown>);
              return (
                <tr key={row.signal_id}>
                  <Td>
                    <SymbolLink symbol={row.symbol} />
                  </Td>
                  <Td>
                    <Score value={row.signal} />
                  </Td>
                  <Td>
                    {p.headlines.slice(0, 2).map((item) => (
                      <div key={item.title} className="mb-1">
                        {item.title} <span className="text-xs text-[#64748B]">({item.source})</span>
                      </div>
                    ))}
                  </Td>
                  <Td className="text-xs text-[#94A3B8]">{sourceLabel("news", row as unknown as Record<string, unknown>)}</Td>
                  <Td className="whitespace-nowrap text-xs text-[#94A3B8]">{istTime(row.timestamp)}</Td>
                </tr>
              );
            })}
          </Table>
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
