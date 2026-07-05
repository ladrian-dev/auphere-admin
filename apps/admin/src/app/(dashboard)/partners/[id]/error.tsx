"use client";

import { Button } from "@/components/ui/button";

/** Error boundary scoped to the partner detail — keeps la shell y el
 *  resto del panel operativos si solo falla este segmento. */
export default function PartnerDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="rounded-md border border-dashed border-border bg-card px-6 py-16 text-center">
      <p className="text-sm font-medium">
        No se pudo cargar el detalle del partner
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        {error.message || "Error inesperado hablando con el backend."}
      </p>
      <Button className="mt-4" variant="outline" size="sm" onClick={reset}>
        Reintentar
      </Button>
    </div>
  );
}
