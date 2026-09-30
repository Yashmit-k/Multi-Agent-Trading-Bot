import { NotAvailableState } from "@/components/States";

export default function NewsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold">News</h1>
      <NotAvailableState feature="Global news list" />
      <p className="mt-2 text-sm">Per-symbol news lives on each stock page via GET /api/v1/stocks/{"{symbol}"}/news.</p>
    </div>
  );
}
