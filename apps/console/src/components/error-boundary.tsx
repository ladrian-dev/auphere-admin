"use client";

import * as React from "react";

import { ErrorState } from "@nexus/ui";

import { useT } from "@/i18n/client";

/**
 * Who is looking at the console: a partner member or the person of a client
 * (spec 056, 10.1). The console frame says it (`ConsoleShellV1` with `who.kind`,
 * the new frame always `partner`); outside it —a layout that failed, the access
 * pages— nobody said, and nothing technical is shown.
 */
type ViewerKind = "partner" | "client" | "unknown";

const ViewerKindContext = React.createContext<ViewerKind>("unknown");

export function ViewerKindProvider({ kind, children }: { kind: "partner" | "client"; children: React.ReactNode }) {
  return <ViewerKindContext.Provider value={kind}>{children}</ViewerKindContext.Provider>;
}

/**
 * Shared body for route ``error.tsx`` files: it says, in the person's language,
 * that the screen could not load, and offers Reintentar (spec 056, 10.1).
 *
 * ``error.message`` is only ever shown to a **partner member**, and only when
 * Next did not give the error a ``digest``. With a digest the message is Next's
 * own sentence («An error occurred in the Server Components render…»), in
 * English and of no use to anyone; a client person never reads it, and neither
 * does whoever is outside the console frame, because ``BackendError.message``
 * carries the API URL and a slice of its response body. ``showMessage={false}``
 * still turns it off for the pages someone reaches before proving to be
 * anyone. The ``digest`` goes to the server log (``instrumentation.ts``), which
 * is where it helps.
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
  const viewer = React.useContext(ViewerKindContext);
  const technical = showMessage && viewer === "partner" && !error.digest ? error.message : "";
  return (
    <ErrorState
      title={t(titleKey ?? "shell.error.load.title")}
      description={technical || t("shell.error.load.body")}
      onRetry={reset}
      retryLabel={t("common.retry")}
    />
  );
}
