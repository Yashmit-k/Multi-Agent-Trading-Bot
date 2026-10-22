import { PageFrame } from "@/components/shell/PageFrame";
import { Card } from "@/components/ui";
import { LoginPanel } from "@/components/operator/LoginPanel";

export const metadata = { title: "Sign in · StockX" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
  return (
    <PageFrame title="Operator sign-in" description="Visitors can browse everything read-only. The operator signs in to change risk limits, place or cancel paper orders, and save strategies.">
      <Card title="Sign in">
        <LoginPanel next={target} />
      </Card>
      <p className="text-xs text-[#64748B]">
        Paper trading only. Signing in never enables live orders: no code path sends an order to a broker.
      </p>
    </PageFrame>
  );
}
