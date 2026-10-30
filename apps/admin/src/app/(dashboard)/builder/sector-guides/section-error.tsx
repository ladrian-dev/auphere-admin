"use client";

import { useRouter } from "next/navigation";

import { ErrorState } from "@nexus/ui";

import { loadErrorCopy } from "./sector-guides";

/**
 * A read of this screen that failed: a `401` says it is the panel's token, any
 * other answer that the API did not respond. «Reintentar» reads again.
 */
export function SectionError({ title, status }: { title: string; status: number | null }) {
  const router = useRouter();
  return <ErrorState title={title} description={loadErrorCopy(status)} onRetry={() => router.refresh()} retryLabel="Reintentar" />;
}
