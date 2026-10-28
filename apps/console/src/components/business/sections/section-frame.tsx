"use client";

import { Check, Globe, Pencil } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, ErrorState, StatusBadge } from "@nexus/ui";

import { confirmSectionAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { SectionState } from "@/lib/backend/business-sections";
import type { Section } from "@/lib/backend/client-records";

/** Lo que devuelve una acción de servidor (`lib/actions.ts`), visto desde el navegador. */
export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string; code?: string | null; info?: Record<string, unknown> };

/**
 * Como el prototipo aprobado: una sola sección en edición a la vez. Empezar
 * otra cierra la anterior sin guardar. Sin proveedor (una sección suelta), cada
 * una lleva su propio estado.
 */
type EditState = { editing: string | null; setEditing: React.Dispatch<React.SetStateAction<string | null>> };
const EditContext = React.createContext<EditState | null>(null);

export function SectionEditProvider({ children }: { children: React.ReactNode }) {
  const [editing, setEditing] = React.useState<string | null>(null);
  const value = React.useMemo(() => ({ editing, setEditing }), [editing]);
  return <EditContext.Provider value={value}>{children}</EditContext.Provider>;
}

export function useSectionEdit(id: string) {
  const shared = React.useContext(EditContext);
  const [own, setOwn] = React.useState(false);
  const editing = shared ? shared.editing === id : own;
  const open = React.useCallback(() => (shared ? shared.setEditing(id) : setOwn(true)), [shared, id]);
  const close = React.useCallback(() => (shared ? shared.setEditing((cur) => (cur === id ? null : cur)) : setOwn(false)), [shared, id]);
  return { editing, open, close };
}

/**
 * La marca del índice (prototipo): un círculo de 16 px. Completa, con su ✓;
 * leída de la web, con el globo; pendiente, un anillo; opcional, el anillo al
 * 50 %. El nombre del estado va para los lectores de pantalla.
 */
export function SectionStateMark({ state }: { state: SectionState }) {
  const t = useT();
  const label = t(`business.section.state.${state}` as MessageKey);
  return (
    <span className="inline-flex shrink-0" data-state={state} title={state === "read_pending" ? t("business.section.mark.web") : undefined}>
      <span
        aria-hidden="true"
        className={
          state === "complete"
            ? "grid size-4 place-items-center rounded-full bg-status-positive-bg text-status-positive-text"
            : state === "read_pending"
              ? "grid size-4 place-items-center rounded-full bg-status-info-bg text-status-info-text"
              : state === "pending"
                ? "size-4 rounded-full ring-2 ring-foreground/40 ring-inset"
                : "size-4 rounded-full ring-2 ring-foreground/20 ring-inset"
        }
      >
        {state === "complete" ? <Check className="size-3" strokeWidth={3} /> : state === "read_pending" ? <Globe className="size-3" /> : null}
      </span>
      <span className="sr-only">{label}</span>
    </span>
  );
}

/** «Editar», la acción de la cabecera de una sección en lectura. */
export function EditAction({ label, onClick }: { label: string; onClick: () => void }) {
  const t = useT();
  return (
    <Button type="button" size="sm" variant="outline" onClick={onClick} aria-label={label}>
      <Pencil aria-hidden="true" />
      {t("business.section.edit")}
    </Button>
  );
}

/**
 * El marco de cada sección de Negocio, como el prototipo: una tarjeta con el
 * título, solo dos marcas («Leído de la web · revísalo», con «Es correcto», y
 * «Falta») y la acción de la cabecera («Editar», «Añadir sede»…). Lo completo
 * y lo opcional no llevan marca. `nested` es una parte dentro de otra tarjeta
 * (Fechas especiales dentro de Horarios).
 */
export function SectionFrame({
  id,
  title,
  state,
  canWrite,
  action,
  confirm,
  nested = false,
  children,
}: {
  id: string;
  title: string;
  state?: SectionState | null;
  canWrite: boolean;
  /** Lo que va a la derecha del título: «Editar», «Añadir…». */
  action?: React.ReactNode;
  /** «Es correcto» de lo leído (13.2): la sección de la API y qué hacer después. */
  confirm?: { refId: string; section: Section; onConfirmed: () => void };
  nested?: boolean;
  children: React.ReactNode;
}) {
  const t = useT();
  const Heading = nested ? "h3" : "h2";
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      data-slot="business-section"
      className={
        nested
          ? "grid min-w-0 scroll-mt-36 gap-3 border-t border-border pt-5"
          : "grid min-w-0 scroll-mt-36 gap-4 rounded-lg border border-border bg-card px-4 pt-4 pb-5 sm:px-5"
      }
    >
      <header className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <Heading id={`${id}-title`} className="text-[15px] font-semibold text-balance">
            {title}
          </Heading>
          {state === "read_pending" ? (
            <StatusBadge tone="info">
              <Globe aria-hidden="true" className="size-3" />
              {t("business.section.mark.web")}
            </StatusBadge>
          ) : state === "pending" ? (
            <StatusBadge tone="muted">{t("business.section.mark.missing")}</StatusBadge>
          ) : null}
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {state === "read_pending" && canWrite && confirm ? <ConfirmButton {...confirm} /> : null}
          {canWrite ? action : <span className="text-xs text-muted-foreground">{t("business.section.readonly")}</span>}
        </div>
      </header>
      {children}
    </section>
  );
}

/** «Es correcto»: lo leído pasa a escrito por quien lo confirma. */
function ConfirmButton({ refId, section, onConfirmed }: { refId: string; section: Section; onConfirmed: () => void }) {
  const t = useT();
  const [pending, startTransition] = React.useTransition();
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      disabled={pending}
      onClick={() =>
        startTransition(async () => {
          const res = await confirmSectionAction({ ref: refId, section });
          if (res.ok) {
            onConfirmed();
            toast.success(t("business.section.confirmed"));
          } else {
            toast.error(t("business.section.error.generic"));
          }
        })
      }
    >
      <Check aria-hidden="true" />
      {t("business.section.confirm")}
    </Button>
  );
}

/** Lectura de una sección: etiqueta y valor, a dos columnas desde el móvil grande. */
export function ReadList({ rows }: { rows: { label: string; value: React.ReactNode; muted?: boolean }[] }) {
  return (
    <dl className="grid min-w-0 gap-x-4 gap-y-3 sm:grid-cols-[10rem_minmax(0,1fr)]">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="text-sm text-muted-foreground">{row.label}</dt>
          <dd className={`mb-1 min-w-0 text-sm text-pretty break-words sm:mb-0 ${row.muted ? "text-muted-foreground" : ""}`}>{row.value}</dd>
        </div>
      ))}
    </dl>
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
