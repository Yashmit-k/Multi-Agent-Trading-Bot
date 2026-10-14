import { NotAvailableState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

export default function NewsPage() {
  return (
    <PageFrame
      title="News"
      description="Per-symbol news lives on each stock page via GET /api/v1/stocks/{symbol}/news."
    >
      <NotAvailableState feature="Global news list" />
    </PageFrame>
  );
}
