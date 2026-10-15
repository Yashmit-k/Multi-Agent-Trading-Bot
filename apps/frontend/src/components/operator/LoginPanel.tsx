"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { OperatorLogin, useOperator } from "@/components/operator/OperatorGate";

export function LoginPanel({ next }: { next: string }) {
  const router = useRouter();
  const { status } = useOperator();
  useEffect(() => {
    if (status?.operator) router.replace(next);
  }, [status, next, router]);
  if (status === null) return <p className="text-sm text-[#94A3B8]">Checking…</p>;
  if (status.operator)
    return (
      <p className="text-sm">
        Signed in. Continue to{" "}
        <Link prefetch={false} href={next} className="text-[#60A5FA]">
          {next}
        </Link>
        .
      </p>
    );
  return <OperatorLogin />;
}
