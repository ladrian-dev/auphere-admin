"use client";

import { Button } from "@/components/ui/button";

/**
 * Frontera de error del segmento. La API es otro servicio: que no responda no
 * puede llevarse por delante el resto del panel.
 */
export default function SignupsError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="rounded-md border border-dashed border-border bg-card px-6 py-16 text-center">
      <p className="text-sm font-medium">No se pudieron cargar las altas</p>
      <p className="mt-1 text-pretty text-sm text-muted-foreground">
        Es un fallo al hablar con la API, no un problema de tus permisos.
      </p>
      <Button className="mt-6" variant="outline" onClick={reset}>
        Reintentar
      </Button>
    </div>
  );
}
