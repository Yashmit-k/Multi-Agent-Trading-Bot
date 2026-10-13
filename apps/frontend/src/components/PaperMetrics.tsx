export type PaperPortfolio = {
  snapshot: Record<string, string> | null;
  total_pnl: string | null;
  equity: string;
  gross_exposure: string | null;
  session_id?: string | null;
};

export function PaperMetrics({ portfolio }: { portfolio: PaperPortfolio }) {
  return (
    <div>
      <h2 className="font-semibold">Active paper session</h2>
      {portfolio.snapshot == null ? (
        <p data-testid="missing-pnl">Daily equity history is unavailable. No paper P&amp;L is shown.</p>
      ) : (
        <p data-testid="session-snapshot">
          Active session snapshot P&amp;L {portfolio.total_pnl} · equity {portfolio.equity} · exposure {portfolio.gross_exposure}
        </p>
      )}
      <p data-testid="equity-graph-empty">No equity graph. Daily equity history is unavailable.</p>
    </div>
  );
}
