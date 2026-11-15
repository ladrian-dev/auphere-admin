"use client";

import { useRouter } from "next/navigation";

import { ErrorState } from "@nexus/ui";

/**
 * A page whose read failed, with «Reintentar»: the page is a server component
 * and cannot hand `ErrorState` a handler, so this island reads it again.
 */
export function ReadError({ title, description }: { title: string; description: string }) {
  const router = useRouter();
  return <ErrorState title={title} description={description} onRetry={() => router.refresh()} retryLabel="Reintentar" />;
}
