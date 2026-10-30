"use client";

import { ErrorState } from "@nexus/ui";

/**
 * Frontera de error del segmento: la API es otro servicio, y que no responda no
 * puede llevarse por delante el resto del panel.
 */
export default function SectorGuidesError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <ErrorState
      title="No se pudieron cargar los sectores sin guía"
      description="Es un fallo al hablar con la API, no un problema de tus permisos. Vuelve a intentarlo en un momento."
      onRetry={reset}
      retryLabel="Reintentar"
    />
  );
}
