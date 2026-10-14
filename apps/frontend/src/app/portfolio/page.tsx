import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";
import { PageFrame } from "@/components/shell/PageFrame";

export default async function PortfolioPage() {
  try {
    const snap = await fetchApi<Record<string, string>>("/api/v1/portfolio");
    return (
      <PageFrame title="Portfolio">
        <pre className="overflow-auto rounded-[12px] border border-[#26303C] bg-[#121922] p-3 text-sm">{JSON.stringify(snap, null, 2)}</pre>
      </PageFrame>
    );
  } catch (error) {
    return (
      <PageFrame title="Portfolio">
        <ErrorState message={error instanceof Error ? error.message : "unknown"} />
      </PageFrame>
    );
  }
}
