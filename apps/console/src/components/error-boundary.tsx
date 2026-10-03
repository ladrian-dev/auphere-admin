"use client";

import { ErrorState } from "@nexus/ui";

import { useT } from "@/i18n/client";

/**
 * Shared body for route ``error.tsx`` files.
 *
 * ``showMessage`` exists for the pages someone can reach **before** proving to
 * be anyone. ``BackendError.message`` carries the API URL and a slice of its
 * response body: useful to a partner staring at a broken console, and no one
 * else's business. Inside the console it stays on; on the access pages it does
 * not. The ``digest`` goes to the server log either way, which is where it
 * helps.
 */
export function RouteError({
  error,
  reset,
  titleKey,
  showMessage = true,
}: {
  error: Error & { digest?: string };
  reset: () => void;
  titleKey?: Parameters<ReturnType<typeof useT>>[0];
  showMessage?: boolean;
}) {
  const t = useT();
  return (
    <ErrorState
      title={t(titleKey ?? "common.error.title")}
      description={(showMessage ? error.message : "") || t("common.error.backend")}
      onRetry={reset}
      retryLabel={t("common.retry")}
    />
  );
}
