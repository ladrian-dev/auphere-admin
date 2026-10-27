"use client";

import { History, Undo2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  formatRelative,
} from "@nexus/ui";

import { getHistoryAction, undoChangeAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Change, Section } from "@/lib/backend/client-records";

type Failed = { ok: false; status: number; message: string; code?: string | null };
type Result<T> = { ok: true; data: T } | Failed;

export type SectionHistoryActions = {
  load: (body: { ref: string; section?: Section }) => Promise<Result<Change[]>>;
  undo: (body: { ref: string; change_id: string }) => Promise<Result<{ revision: number | null }>>;
};

const DEFAULT_ACTIONS: SectionHistoryActions = {
  load: (b) => getHistoryAction(b),
  undo: (b) => undoChangeAction(b),
};

/**
 * El historial de una sección de la ficha, con «Deshacer» en el último cambio
 * (spec 047, requisito 13.3). Se abre en un panel lateral y se carga al abrirlo.
 * Si alguien escribió la sección después, deshacer no pisa a nadie: la API
 * responde 412 y aquí se dice. Estados: cargando, vacío, error e ideal.
 */
export function SectionHistory({
  refId,
  section,
  meId,
  canUndo,
  actions,
  onChanged,
}: {
  refId: string;
  section: Section;
  meId: string | null;
  canUndo: boolean;
  actions?: Partial<SectionHistoryActions>;
  onChanged?: () => void;
}) {
  const t = useT();
  const locale = useLocale();
  const act = React.useMemo(() => ({ ...DEFAULT_ACTIONS, ...actions }), [actions]);
  const [open, setOpen] = React.useState(false);
  const [items, setItems] = React.useState<Change[] | null>(null);
  const [failed, setFailed] = React.useState(false);
  const [pending, startTransition] = React.useTransition();
  const sectionName = t(`business.history.section.${section}` as MessageKey);

  const load = React.useCallback(async () => {
    setFailed(false);
    const res = await act.load({ ref: refId, section });
    if (res.ok) setItems(res.data);
    else setFailed(true);
  }, [act, refId, section]);

  React.useEffect(() => {
    if (!open) return;
    // Fuera del cuerpo del efecto: cargar pone estado.
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [open, load]);

  function undo(change: Change) {
    startTransition(async () => {
      const res = await act.undo({ ref: refId, change_id: change.id });
      if (!res.ok) {
        toast.error(
          res.status === 412
            ? t("business.history.conflict")
            : res.code === "undo_not_available"
              ? t("business.history.unavailable")
              : t("business.sources.error.generic"),
        );
        await load();
        return;
      }
      toast.success(t("business.history.undoneToast"));
      onChanged?.();
      await load();
    });
  }

  const who = (c: Change) =>
    c.by?.id && meId && c.by.id === meId ? t("business.prov.self") : (c.by?.name ?? t("business.prov.someone"));

  return (
    <>
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(true)} aria-label={t("business.history.open", { section: sectionName })}>
        <History aria-hidden="true" />
        {t("business.history.title")}
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle className="text-balance">{`${t("business.history.title")} · ${sectionName}`}</SheetTitle>
            <SheetDescription className="sr-only">{t("business.history.open", { section: sectionName })}</SheetDescription>
          </SheetHeader>
          <div className="grid min-w-0 gap-3 overflow-y-auto px-4 pb-4" aria-busy={items === null && !failed}>
            {failed ? (
              <div className="grid gap-2" role="alert">
                <p className="text-sm text-pretty">{t("business.history.error")}</p>
                <Button type="button" size="sm" variant="outline" onClick={() => void load()} className="justify-self-start">
                  {t("panel.retry")}
                </Button>
              </div>
            ) : items === null ? (
              <div className="grid gap-2" aria-label={t("business.history.loading")}>
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : items.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("business.history.empty")}</p>
            ) : (
              <ol className="grid min-w-0 gap-2">
                {items.map((c) => (
                  <li key={c.id} className="flex min-w-0 items-start justify-between gap-3 rounded-md border border-border p-3">
                    <div className="grid min-w-0 gap-1">
                      <span className="text-sm font-medium">{t(`business.history.kind.${c.kind}` as MessageKey)}</span>
                      <span className="text-xs text-muted-foreground text-pretty">
                        {t("business.history.by", { who: who(c), when: formatRelative(c.at, locale) })}
                      </span>
                    </div>
                    {c.undone_at ? (
                      <span className="shrink-0 text-xs text-muted-foreground">{t("business.history.undone")}</span>
                    ) : c.undoable && canUndo ? (
                      <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => undo(c)} className="shrink-0">
                        <Undo2 aria-hidden="true" />
                        {t("business.history.undo")}
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
