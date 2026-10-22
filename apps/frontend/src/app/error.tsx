"use client";

import Link from "next/link";
import { PageFrame } from "@/components/shell/PageFrame";

// Next.js passes the thrown error and a reset() that re-renders the segment. The error itself
// is deliberately never shown: raw messages can leak internals and mean nothing to the reader.
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <PageFrame title="Something went wrong loading this page" description="This is usually temporary. Try again, or check the system status page.">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => reset()} className="rounded-md bg-[#2563EB] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1D4ED8]">
          Try again
        </button>
        <Link prefetch={false} href="/system" className="rounded-md border border-[#26303C] px-4 py-2 text-sm text-[#E6EDF3] hover:bg-[#121922]">
          Open system status
        </Link>
      </div>
    </PageFrame>
  );
}
