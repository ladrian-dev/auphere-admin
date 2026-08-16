"use client";

import { ErrorState } from "@nexus/ui";

import { useT } from "@/i18n/client";

/** Shared body for route ``error.tsx`` files. */
export function RouteError({ error, reset, titleKey }: { error: Error & { digest?: string }; reset: () => void; titleKey?: Parameters<ReturnType<typeof useT>>[0] }) {
  const t = useT();
  return (
    <ErrorState
      title={t(titleKey ?? "common.error.title")}
      description={error.message || t("common.error.backend")}
      onRetry={reset}
      retryLabel={t("common.retry")}
    />
  );
}
