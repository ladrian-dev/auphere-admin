"use client";

import * as React from "react";

import { ErrorState, StatusBadge, type StatusBadgeProps } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { SectionState } from "@/lib/backend/business-sections";

/** Lo que devuelve una acción de servidor (`lib/actions.ts`), visto desde el navegador. */
export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string; code?: string | null; info?: Record<string, unknown> };

const TONE: Record<SectionState, NonNullable<StatusBadgeProps["tone"]>> = {
  complete: "positive",
  read_pending: "warn",
  pending: "info",
  optional: "muted",
};

/** El estado de una sección (requisito 8.5). */
export function SectionStateBadge({ state }: { state: SectionState }) {
  const t = useT();
  return <StatusBadge tone={TONE[state]}>{t(`business.section.state.${state}` as MessageKey)}</StatusBadge>;
}

/**
 * El marco de cada sección de Negocio: su título (que da nombre a la región),
 * su estado, «Solo lectura» si la persona no puede escribir y el contenido.
 */
export function SectionFrame({
  id,
  title,
  intro,
  state,
  canWrite,
  children,
}: {
  id: string;
  title: string;
  intro?: string;
  state?: SectionState | null;
  canWrite: boolean;
  children: React.ReactNode;
}) {
  const t = useT();
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      data-slot="business-section"
      className="grid min-w-0 scroll-mt-24 gap-4 rounded-lg border border-border bg-card p-4 sm:p-6"
    >
      <header className="flex min-w-0 flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="grid min-w-0 flex-1 basis-64 gap-1">
          <h2 id={`${id}-title`} className="text-base font-semibold text-balance">
            {title}
          </h2>
          {intro ? <p className="text-sm text-pretty text-muted-foreground">{intro}</p> : null}
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {state ? <SectionStateBadge state={state} /> : null}
          {!canWrite ? <span className="text-xs text-muted-foreground">{t("business.section.readonly")}</span> : null}
        </div>
      </header>
      {children}
    </section>
  );
}

/** Una sección que no cargó: lo dice y deja reintentar; las demás siguen. */
export function SectionError({ onRetry }: { onRetry?: () => void }) {
  const t = useT();
  return (
    <ErrorState
      className="py-8"
      title={t("business.section.error")}
      description={t("business.section.error.hint")}
      onRetry={onRetry}
      retryLabel={t("business.section.retry")}
    />
  );
}

/** El aviso de un 412: alguien guardó antes; nada se pisó. */
export function ConflictNotice({ onReload }: { onReload?: () => void }) {
  const t = useT();
  return (
    <div role="alert" className="flex min-w-0 flex-wrap items-center gap-3 rounded-md border border-status-warning/40 bg-status-warning/10 p-3 text-sm">
      <p className="min-w-0 flex-1 basis-64 text-pretty">{t("business.section.conflict")}</p>
      {onReload ? (
        <button type="button" onClick={onReload} className="min-h-6 font-medium underline underline-offset-4">
          {t("business.section.reload")}
        </button>
      ) : null}
    </div>
  );
}

/** Qué decirle a la persona de un «no» de la API. */
export function problemOf(res: Extract<Result<unknown>, { ok: false }>): "conflict" | string {
  if (res.status === 412) return "conflict";
  return res.code ?? "generic";
}
