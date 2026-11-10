"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Field, Textarea } from "@nexus/ui";

import { requestBalanceAction } from "@/app/(console)/usage/money-actions";
import { useT } from "@/i18n/client";

import { REQUEST_NOTE_MAX, moneyErrorText, noteProblem, requestedText, type Failed } from "./money-model";

type Result<T> = { ok: true; data: T } | Failed;
export type RequestActions = { request: (body: { ref: string; note: string | null }) => Promise<Result<{ status: string }>> };
const SERVER: RequestActions = { request: (b) => requestBalanceAction(b) };

// ── quién ya pidió hoy ─────────────────────────────────────────────────────
//
// «Pedir saldo» se puede una vez al día por cliente, pida quien pida (45.7).
// La API lo hace cumplir (429); aquí se recuerda lo pedido en esta sesión para
// que todos los botones de ese cliente digan «Pedido hace…» sin volver a
// preguntar. `null` = se sabe que se pidió hoy, pero no a qué hora (el 429).

const requested = new Map<string, number | null>();
const listeners = new Set<() => void>();

export function markRequested(ref: string, at: number | null) {
  requested.set(ref, at);
  for (const l of listeners) l();
}

/** Solo para los tests: empezar sin nada pedido. */
export function resetRequested() {
  requested.clear();
  for (const l of listeners) l();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Lo que la API sabe de hoy (`GET /console/wallet/bags` → `requested_at`): así
 * «Pedido hace…» sobrevive a recargar la página y vale para todo el equipo.
 */
export function SeedRequested({ items }: { items: { ref: string; requested_at?: string | null }[] }) {
  React.useEffect(() => {
    for (const { ref, requested_at } of items) {
      if (!requested_at || requested.has(ref)) continue;
      const at = Date.parse(requested_at);
      markRequested(ref, Number.isNaN(at) ? null : at);
    }
  }, [items]);
  return null;
}

/** `undefined` si no consta que se haya pedido; si no, cuándo (o `null`: hoy). */
export function useRequested(ref: string): number | null | undefined {
  return React.useSyncExternalStore(
    subscribe,
    () => (requested.has(ref) ? (requested.get(ref) ?? null) : undefined),
    () => undefined,
  );
}

/**
 * «Pedir saldo» (spec 047, requisito 45.7): para quien no puede asignar
 * (builder, analyst y billing). Una nota de hasta 280 caracteres; avisa a owners
 * y admins por la campana y el correo. Después, el botón dice «Pedido hace…».
 * No existe en la consola lite ni en la app (45.8): solo se monta en la del partner.
 */
export function RequestBalanceDialog({
  refId,
  name,
  onOpenChange,
  actions = SERVER,
}: {
  refId: string;
  name: string;
  onOpenChange: (open: boolean) => void;
  actions?: RequestActions;
}) {
  const t = useT();
  const at = useRequested(refId);
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const done = at !== undefined;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (done) return;
    if (noteProblem(note)) {
      setError(t("money.request.note.tooLong", { max: REQUEST_NOTE_MAX }));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await actions.request({ ref: refId, note: note.trim() || null });
    setBusy(false);
    if (res.ok) {
      markRequested(refId, Date.now());
      toast.success(t("money.request.sent", { name }));
      onOpenChange(false);
      return;
    }
    if (res.code === "request_already_sent_today") {
      markRequested(refId, null);
      setError(null);
      return;
    }
    setError(moneyErrorText(t, res));
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4" data-slot="request-balance">
          <DialogHeader>
            <DialogTitle>{t("money.request.title", { name })}</DialogTitle>
            <DialogDescription>{t("money.request.body", { name })}</DialogDescription>
          </DialogHeader>
          {done ? (
            <p role="status" className="text-sm text-pretty" data-slot="request-done">
              {requestedText(t, at)}. {t("money.request.again")}
            </p>
          ) : (
            <Field
              label={t("money.request.note")}
              optionalLabel={t("money.optional")}
              hint={t("money.request.note.count", { n: note.length, max: REQUEST_NOTE_MAX })}
              error={error ?? undefined}
            >
              {(a11y) => (
                <Textarea {...a11y} value={note} rows={3} maxLength={REQUEST_NOTE_MAX} onChange={(e) => setNote(e.target.value)} />
              )}
            </Field>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {done ? t("money.close") : t("money.cancel")}
            </Button>
            {done ? null : (
              <Button type="submit" loading={busy}>
                {t("money.request.submit")}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
