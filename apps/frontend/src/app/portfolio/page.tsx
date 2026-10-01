import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";

export default async function PortfolioPage() {
  try {
    const snap = await fetchApi<Record<string, string>>("/api/v1/portfolio");
    return (
      <div>
        <h1 className="text-2xl font-bold">Portfolio</h1>
        <pre className="text-sm">{JSON.stringify(snap, null, 2)}</pre>
      </div>
    );
  } catch (error) {
    return <ErrorState message={error instanceof Error ? error.message : "unknown"} />;
  }
}
