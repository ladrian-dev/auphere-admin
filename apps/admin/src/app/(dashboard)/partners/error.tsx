"use client";

import { Button } from "@/components/ui/button";

/**
 * Segment error boundary for /partners — the backend is a separate
 * service, so a fetch failure here must not take down the whole shell.
 * Retry re-renders the segment (Next re-runs the server component).
 */
export default function PartnersError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="rounded-md border border-dashed border-border bg-card px-6 py-16 text-center">
      <p className="text-sm font-medium">No se pudieron cargar los partners</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {error.message || "Error inesperado hablando con el backend."}
      </p>
      <Button className="mt-4" variant="outline" size="sm" onClick={reset}>
        Reintentar
      </Button>
    </div>
  );
}
