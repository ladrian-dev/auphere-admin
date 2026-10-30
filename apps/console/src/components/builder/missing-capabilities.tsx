"use client";

import { Pencil } from "lucide-react";
import * as React from "react";

import { Button, Callout, Skeleton } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { MissingCapability } from "@/lib/backend/builder-types";

import { missingCapabilities } from "./missing-model";

/** Cargando, leído o que no se pudo volver a leer. */
export type MissingState = "loading" | "ready" | "failed";

/**
 * «No tenemos herramienta para: …» (spec 047, enmienda del 2026-10-30, T228;
 * requisitos 65.3 y 65.4; `contracts/console-api.md` §11). Sale de
 * `missing_capabilities` —del borrador, del trabajo que lo escribió o del
 * copiloto— con la `label` de cada elemento, y dice la alternativa con la que
 * se queda el agente: pasar a una persona. Nada de esto lleva «Conectar {X}».
 * Una promesa del texto (`kind: "action"`) dice que la promete su texto y, a
 * quien puede editar, lleva con «Quitar la promesa» al punto donde está.
 *
 * Sus cinco estados:
 * - **cargando**: un esqueleto con el tamaño de lo que había (el título, una
 *   línea por cada una y la alternativa), anunciado; sin nada antes, nada, para
 *   que no salte la pantalla;
 * - **vacío**: no se enseña nada (el contrato);
 * - **error**: lo dice, sin enseñar lo de antes como si fuera de ahora, con
 *   «Reintentar», que no se pulsa dos veces mientras vuelve a leer;
 * - **parcial**: uno sin `label` se nombra por su clave;
 * - **ideal**: una frase con una, o una lista con varias.
 */
export function MissingCapabilities({
  items,
  state = "ready",
  canEdit = false,
  onEdit,
  onRetry,
}: {
  items: readonly MissingCapability[] | null | undefined;
  state?: MissingState;
  /** Quien puede editar el agente ve «Quitar la promesa». */
  canEdit?: boolean;
  /** «Quitar la promesa»: abrir el bloque al que apunta. */
  onEdit?: (pointer: string) => void;
  /** «Reintentar» tras un error: volver a leer. */
  onRetry?: () => Promise<void> | void;
}) {
  const t = useT();
  const titleId = React.useId();
  const [retrying, setRetrying] = React.useState(false);
  const list = missingCapabilities(items);

  async function retry() {
    if (retrying || !onRetry) return;
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  }

  if (state === "failed") {
    return (
      <div data-slot="missing-capabilities" data-state="failed" className="min-w-0">
        <Callout
          tone="danger"
          action={
            onRetry ? (
              <Button size="sm" variant="outline" loading={retrying} onClick={() => void retry()}>
                {t("builder.suite.retry")}
              </Button>
            ) : undefined
          }
        >
          {t("builder.missing.error")}
        </Callout>
      </div>
    );
  }

  if (!list.length) return null;

  if (state === "loading") {
    // El título, una línea por cada una (con una sola va en el título) y la alternativa.
    const lines = list.length === 1 ? 1 : list.length + 1;
    return (
      <div
        role="status"
        aria-label={t("builder.missing.loading")}
        data-slot="missing-capabilities"
        data-state="loading"
        className="grid min-w-0 gap-2 rounded-md border border-border px-3 py-2"
      >
        <Skeleton className="h-5 w-64 max-w-full" />
        {Array.from({ length: lines }, (_, i) => (
          <Skeleton key={i} className={i === lines - 1 ? "h-4 w-80 max-w-full" : "h-4 w-48 max-w-full"} />
        ))}
      </div>
    );
  }

  const promises = list.some((m) => m.kind === "action");
  const one = list.length === 1 ? list[0]! : null;
  const remove = (m: MissingCapability) =>
    canEdit && onEdit && m.kind === "action" && m.pointer ? (
      <Button
        size="sm"
        variant="outline"
        className="shrink-0"
        onClick={() => onEdit(m.pointer!)}
        aria-label={t("builder.missing.remove.label", { label: m.label })}
      >
        <Pencil aria-hidden="true" />
        {t("builder.missing.remove")}
      </Button>
    ) : null;

  return (
    <div data-slot="missing-capabilities" data-state="ready" className="min-w-0">
      {/* Una promesa del texto pide hacer algo (quitarla); lo demás solo se sabe. */}
      <Callout
        tone={promises ? "warning" : "info"}
        title={
          <span id={titleId} className="min-w-0 break-words">
            {one ? t("builder.missing.title", { label: one.label }) : t("builder.missing.title.list")}
          </span>
        }
      >
        <div className="grid min-w-0 gap-2">
          {one ? (
            one.kind === "action" ? (
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <span className="min-w-0 flex-1 basis-40 text-pretty">{t("builder.missing.promise")}</span>
                {remove(one)}
              </div>
            ) : null
          ) : (
            <ul aria-labelledby={titleId} className="grid min-w-0 gap-2 text-foreground">
              {list.map((m) => (
                <li key={`${m.kind}:${m.key || m.label}`} className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1">
                  <span className="grid min-w-0 flex-1 basis-48 gap-1">
                    <span data-slot="missing-label" className="min-w-0 font-medium text-pretty break-words">
                      {m.label}
                    </span>
                    {m.kind === "action" ? <span className="text-xs text-pretty text-muted-foreground">{t("builder.missing.promise")}</span> : null}
                  </span>
                  {remove(m)}
                </li>
              ))}
            </ul>
          )}
          <p className="text-pretty">{t("builder.missing.fallback")}</p>
        </div>
      </Callout>
    </div>
  );
}
