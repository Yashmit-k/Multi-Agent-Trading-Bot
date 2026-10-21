import Link from "next/link";
import { PageFrame } from "@/components/shell/PageFrame";

export const metadata = { title: "Page not found · StockX" };

export default function NotFound() {
  return (
    <PageFrame title="Page not found" description="We could not find the page you asked for. It may have moved, or the address may be mistyped.">
      <Link prefetch={false} href="/dashboard" className="inline-block rounded-md bg-[#2563EB] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1D4ED8]">
        Back to the dashboard
      </Link>
    </PageFrame>
  );
}
