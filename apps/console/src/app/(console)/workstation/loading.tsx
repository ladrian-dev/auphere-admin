import { CardSkeleton, PageHeader } from "@nexus/ui";

/**
 * Cargando `/workstation`: el esqueleto respeta las dimensiones finales —una
 * cabecera y dos tarjetas— para que el contenido no salte al llegar (sin CLS).
 */
export default function WorkstationLoading() {
  return (
    <>
      <PageHeader title="Teammate" />
      <CardSkeleton />
      <CardSkeleton />
    </>
  );
}
