import { Table, Td, SymbolLink } from "@/components/ui";
import { pct, price } from "@/lib/format";
import { change, type StockRow } from "@/lib/stocks";

export function StockTable({ rows }: { rows: StockRow[] }) {
  return (
    <Table head={["Symbol", "Last close (₹)", "Previous close (₹)", "Day change"]} minWidth={480}>
      {rows.map((row) => {
        const value = change(row);
        const tone = value === null ? "text-[#64748B]" : value > 0 ? "text-[#22C55E]" : value < 0 ? "text-[#EF4444]" : "text-[#94A3B8]";
        return (
          <tr key={row.symbol}>
            <Td>
              <SymbolLink symbol={row.symbol} />
            </Td>
            <Td className="tabular-nums">{price(row.last_price)}</Td>
            <Td className="tabular-nums text-[#94A3B8]">{price(row.prev_close)}</Td>
            <Td className={`tabular-nums ${tone}`}>{pct(row.change_pct)}</Td>
          </tr>
        );
      })}
    </Table>
  );
}
