"use client";

export function CandleChart({ rows }: { rows: Array<{ start: string; open: string; high: string; low: string; close: string }> }) {
  if (rows.length === 0) return <p>No candles.</p>;
  return (
    <table className="text-sm w-full" data-testid="candle-table">
      <thead>
        <tr>
          <th>start</th>
          <th>o</th>
          <th>h</th>
          <th>l</th>
          <th>c</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.start}>
            <td>{row.start}</td>
            <td>{row.open}</td>
            <td>{row.high}</td>
            <td>{row.low}</td>
            <td>{row.close}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
