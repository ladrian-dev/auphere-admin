"use client";

import { Plug } from "lucide-react";

import { Alert, AlertDescription, AlertTitle, EmptyState } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";

import { ConnectorCard } from "./connector-card";

/**
 * Integraciones (spec 017, R4): lo que conecta al agente con lo que el
 * negocio ya usa.
 *
 * **Ordena por lo que necesita atención, no por nombre.** Alfabético es
 * cómodo de programar y no ayuda a nadie: una integración rota y otra sin
 * conectar son lo único que el partner tiene que hacer aquí, así que van
 * primero. Las que funcionan se leen al final, que es donde se mira cuando
 * se quiere comprobar algo, no cuando se quiere arreglar algo.
 */

/** Cuanto más bajo, más arriba: primero lo que se ha roto, luego lo que falta. */
function urgency(status: string | null): number {
  // Sin fila de conector no hay estado: está sin conectar, que es lo segundo
  // más urgente después de lo que se ha roto.
  if (!status) return 1;
  switch (status) {
    case "error":
    case "revoked":
    case "expired":
      return 0;
    case "pending":
      return 2;
    case "paused":
      return 3;
    default:
      return 4;
  }
}

export function IntegrationsList({
  refId,
  connectors,
  error,
  canWrite,
}: {
  refId: string;
  connectors: ConnectorOut[];
  error: string | null;
  canWrite: boolean;
}) {
  const t = useT();
  const ordered = [...connectors].sort(
    (a, b) =>
      urgency(a.status) - urgency(b.status) || a.display_name.localeCompare(b.display_name),
  );
  // «Conectada» incluye `partial`: funciona, aunque no todo. Decir que no lo
  // está sería más falso que decir que sí.
  const on = connectors.filter((c) => c.status === "connected" || c.status === "partial").length;

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>{t("connectors.error")}</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {connectors.length === 0 ? (
        <EmptyState icon={Plug} title={t("int.empty.title")} description={t("int.empty.body")} readonly />
      ) : (
        <>
          <p className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
            {t("int.count", { on, total: connectors.length })}
          </p>
          {!canWrite ? <p className="text-sm text-muted-foreground">{t("int.readonly")}</p> : null}
          {/* En rejilla: la lista va a tener decenas, y una tarjeta por
              fila deja el ancho entero sin usar (owner, 2026-09-28). El
              orden por urgencia se lee igual de izquierda a derecha. */}
          <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {ordered.map((c) => (
              <ConnectorCard key={c.slug} refId={refId} connector={c} canWrite={canWrite} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
