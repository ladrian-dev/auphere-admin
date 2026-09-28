"use client";

import { Plug } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Alert, AlertDescription, AlertTitle, CatalogBrowser, EmptyState } from "@nexus/ui";

import { useCatalog, useCatalogLabels } from "@/components/catalog/use-catalog";
import { useT } from "@/i18n/client";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";

import { ConnectorCard } from "./connector-card";

/**
 * Conectores (spec 017 R4; spec 018 R4): lo que conecta al agente con lo que
 * el negocio ya usa, con **el mismo patrón de navegación** que Habilidades y
 * Canales.
 *
 * **Ordena por lo que necesita atención, no por nombre.** Alfabético es
 * cómodo de programar y no ayuda a nadie: un conector roto y otro sin
 * conectar son lo único que el partner tiene que hacer aquí, así que van
 * primero. Con la spec 018 ese orden se conserva **dentro de cada grupo**,
 * que es donde se sigue leyendo de izquierda a derecha.
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

/** Las categorías que la consola sabe nombrar. Una que no esté aquí existe
 *  —la fuente puede añadirlas— pero no tiene nombre de negocio, así que cae
 *  en «El resto» en vez de enseñar su clave interna (R4.5). */
const NAMED = new Set(["booking", "calendar", "billing", "catalog", "ecommerce", "messaging", "docs", "crm"]);

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
  const catalog = useCatalog(`/clients/${encodeURIComponent(refId)}/integrations`);
  const labels = useCatalogLabels({
    title: t("int.title"),
    category: (key) => t(`int.cat.${key}` as "int.cat.booking"),
  });

  const items = React.useMemo(
    () =>
      [...connectors]
        .sort((a, b) => urgency(a.status) - urgency(b.status) || a.display_name.localeCompare(b.display_name))
        .map((c) => ({
          id: c.slug,
          name: c.display_name,
          search: `${c.vendor} ${c.capabilities.join(" ")}`,
          category: NAMED.has(c.category) ? c.category : null,
          // «Conectado» incluye `partial`: funciona, aunque no todo. Decir
          // que no lo está sería más falso que decir que sí.
          active: c.status === "connected" || c.status === "partial",
          connector: c,
        })),
    [connectors],
  );

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>{t("connectors.error")}</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <CatalogBrowser
        {...catalog}
        items={items}
        labels={labels}
        renderLink={(href, children, props) => (
          <Link href={href} {...props}>
            {children}
          </Link>
        )}
        renderItem={({ id, connector }) => (
          <ConnectorCard key={id} refId={refId} connector={connector} canWrite={canWrite} />
        )}
        empty={<EmptyState icon={Plug} title={t("int.empty.title")} description={t("int.empty.body")} readonly />}
        notice={!canWrite ? <p className="text-sm text-muted-foreground">{t("int.readonly")}</p> : null}
      />
    </div>
  );
}
