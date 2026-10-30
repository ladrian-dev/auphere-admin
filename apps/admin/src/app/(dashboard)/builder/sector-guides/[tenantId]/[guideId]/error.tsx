"use client";

import { ErrorState } from "@nexus/ui";

/** Frontera de error de una guía generada: el resto del panel sigue en pie. */
export default function GeneratedGuideError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <ErrorState
      title="No se pudo cargar la guía generada"
      description="Es un fallo al hablar con la API, no un problema de tus permisos. Vuelve a intentarlo en un momento."
      onRetry={reset}
      retryLabel="Reintentar"
    />
  );
}
