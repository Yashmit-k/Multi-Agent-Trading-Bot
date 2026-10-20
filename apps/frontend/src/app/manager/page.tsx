import { ManagerReviews } from "@/components/manager/ManagerReviews";
import { PageFrame } from "@/components/shell/PageFrame";

export const metadata = { title: "Portfolio manager · StockX" };
export const dynamic = "force-dynamic";

export default function ManagerPage() {
  return (
    <PageFrame
      title="Portfolio manager"
      description="An LLM agent that critiques every agent BUY before the risk engine sees it. It plans which evidence to gather, calls tools (agent opinions, news, fundamentals, prices, the market, the book, its own past reviews), asks other agents to re-check, and approves, shrinks or vetoes the trade. It can never create or enlarge one. Every step below is a real message on the event bus."
    >
      <ManagerReviews />
    </PageFrame>
  );
}
