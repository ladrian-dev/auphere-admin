"use client";

import { Lightbulb } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
  ErrorState,
  Field,
  StatusBadge,
  Textarea,
  formatDate,
} from "@nexus/ui";

import { acceptImprovementAction, discardImprovementAction, improvementsAction } from "@/app/(console)/clients/[ref]/agents/improve-actions";
import { useLocale, useT } from "@/i18n/client";
import type { Improvement, ImprovementAccepted, ImprovementDiscarded, Improvements } from "@/lib/backend/agent-improve-types";

import type { Result } from "./builder-model";
import { improvementReach, originKey } from "./improve-model";
import { OpLine } from "./proposals";

export type ImprovementsActions = {
  reload: (body: { ref: string; agent: string }) => Promise<Result<Improvements>>;
  accept: (body: { ref: string; agent: string; id: string }) => Promise<Result<ImprovementAccepted>>;
  discard: (body: { ref: string; agent: string; id: string; reason: string }) => Promise<Result<ImprovementDiscarded>>;
};

const SERVER_ACTIONS: ImprovementsActions = {
  reload: (b) => improvementsAction(b),
  accept: (b) => acceptImprovementAction(b),
  discard: (b) => discardImprovementAction(b),
};

type Failure = Extract<Result<unknown>, { ok: false }>;
const REASON_MIN = 3;
const REASON_MAX = 300;

/**
 * Las Mejoras del agente (spec 047, T174; requisitos 51.3, 51.4, 52.2 y 52.3):
 * las sugerencias de la semana —agregadas, con a cuántas conversaciones y
 * clientes afecta, nunca cuáles— y las correcciones de comportamiento que manda
 * el negocio desde su Bandeja, con la lección que escribió y la paráfrasis de lo
 * que preguntó el cliente, nunca el mensaje (C1). Cada una trae su propuesta: el
 * cambio y la prueba nueva.
 *
 * Como el prototipo (`agente.md` §6, hueco H9; requisito 63.2): la tarjeta
 * «Sugerencias de esta semana», a la derecha de los 30 días, con una fila por
 * mejora —su bombilla, lo que pasó, a cuántos afecta o de dónde viene— y «Ver».
 * «Ver» abre la propuesta entera con «Aceptar» y «Descartar».
 *
 * «Aceptar» lleva el cambio y la prueba al borrador y dice en qué quedó; nada se
 * publica hasta «Guardar», que pasa la puerta. «Descartar» pide el motivo, y una
 * sugerencia descartada no vuelve en 30 días. Quien solo lee lo ve todo, sin
 * botones (§V).
 */
export function AgentImprovementsPanel({
  refId,
  agentId,
  improvements: initial,
  onAccepted,
  actions = SERVER_ACTIONS,
}: {
  refId: string;
  agentId: string;
  improvements: Improvements | null;
  /** El borrador cambió: la pantalla lo vuelve a leer. */
  onAccepted?: (result: ImprovementAccepted) => void;
  actions?: ImprovementsActions;
}) {
  const t = useT();
  const [data, setData] = React.useState(initial);
  const [busy, setBusy] = React.useState(false);
  const [accepted, setAccepted] = React.useState<ImprovementAccepted | null>(null);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [viewing, setViewing] = React.useState<Improvement | null>(null);
  const [discarding, setDiscarding] = React.useState<Improvement | null>(null);
  const [reloading, startReload] = React.useTransition();
  const titleId = React.useId();

  const items = data?.items ?? [];
  const allowed = data?.allowed ?? [];

  function retry() {
    startReload(async () => {
      const res = await actions.reload({ ref: refId, agent: agentId });
      setData(res.ok ? res.data : null);
    });
  }

  function failure(res: Failure): string {
    switch (res.code) {
      case "improvement_closed":
        return t("improve.error.closed");
      case "improvement_outdated":
        return t("improve.error.outdated");
      case "invalid_proposal":
        return t("improve.error.invalid");
      case "no_version":
        return t("improve.error.noVersion");
      default:
        if (res.status === 404) return t("improve.error.closed");
        if (res.status === 403) return t("common.forbidden");
        return t("improve.error.generic");
    }
  }

  function drop(id: string) {
    setData((d) => (d ? { ...d, items: d.items.filter((i) => i.id !== id) } : d));
  }

  function view(item: Improvement | null) {
    setViewing(item);
    setProblem(null);
  }

  async function accept(item: Improvement) {
    setBusy(true);
    setProblem(null);
    const res = await actions.accept({ ref: refId, agent: agentId, id: item.id });
    setBusy(false);
    if (res.ok) {
      drop(item.id);
      setViewing(null);
      setAccepted(res.data);
      onAccepted?.(res.data);
      return;
    }
    setProblem(failure(res));
    if (res.code === "improvement_closed") drop(item.id);
  }

  async function discard(item: Improvement, reason: string): Promise<string | null> {
    const res = await actions.discard({ ref: refId, agent: agentId, id: item.id, reason });
    if (!res.ok) return failure(res);
    drop(item.id);
    setDiscarding(null);
    toast.success(item.kind === "suggestion" ? t("improve.discarded.suggestion") : t("improve.discarded.correction"));
    return null;
  }

  return (
    <section
      id="agente-mejoras"
      aria-labelledby={titleId}
      aria-busy={reloading || undefined}
      className="grid min-w-0 scroll-mt-24 content-start gap-3 rounded-lg border border-border bg-card p-4 sm:px-5"
      data-slot="agent-improvements"
    >
      <h2 id={titleId} className="text-base font-semibold text-balance">
        {t("improve.suggestions.title")}
      </h2>
      {data === null ? (
        <ErrorState className="py-4" title={t("improve.error.load")} description={t("improve.error.load.hint")} onRetry={retry} retryLabel={t("improve.retry")} />
      ) : (
        <>
          {accepted ? (
            <Callout tone="positive" title={t("improve.accepted.title")} dismissible dismissLabel={t("improve.accepted.dismiss")} onDismiss={() => setAccepted(null)}>
              {t("improve.accepted.body", { n: accepted.draft_revision })}
            </Callout>
          ) : null}
          {items.length === 0 ? (
            <EmptyState icon={Lightbulb} title={t("improve.empty")} description={t("improve.empty.hint")} readonly />
          ) : (
            <ul aria-label={t("improve.list")} className="grid min-w-0 divide-y divide-border">
              {items.map((item) => (
                <li key={item.id} className="flex min-w-0 items-center gap-3 py-3 first:pt-0 last:pb-0" data-improvement={item.kind}>
                  <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                    <Lightbulb className="size-4" />
                  </span>
                  <span className="grid min-w-0 flex-1 gap-1">
                    <span className="text-sm font-medium text-pretty break-words">{item.topic}</span>
                    <span className="text-xs text-pretty text-muted-foreground">{subtitle(t, item)}</span>
                  </span>
                  <Button type="button" size="sm" variant="outline" className="shrink-0" aria-label={t("improve.view.aria", { topic: item.topic })} onClick={() => view(item)}>
                    {t("improve.view")}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {viewing ? (
        <ImprovementDialog
          item={viewing}
          allowed={allowed}
          busy={busy}
          problem={problem}
          onClose={() => view(null)}
          onAccept={() => void accept(viewing)}
          onDiscard={() => {
            setDiscarding(viewing);
            view(null);
          }}
        />
      ) : null}
      {discarding ? <DiscardDialog item={discarding} onClose={() => setDiscarding(null)} onDiscard={(reason) => discard(discarding, reason)} /> : null}
    </section>
  );
}

/** La línea de debajo del título: a cuántos afecta una sugerencia, de dónde viene una corrección. */
function subtitle(t: ReturnType<typeof useT>, item: Improvement): string {
  return item.kind === "suggestion" ? improvementReach(t, item) : `${t("improve.kind.correction")} · ${t(originKey(item.origin))}`;
}

/** «Ver»: la mejora entera —lo que pasó, la propuesta y su prueba— con «Aceptar» y «Descartar» si se puede. */
function ImprovementDialog({
  item,
  allowed,
  busy,
  problem,
  onClose,
  onAccept,
  onDiscard,
}: {
  item: Improvement;
  allowed: readonly string[];
  busy: boolean;
  problem: string | null;
  onClose: () => void;
  onAccept: () => void;
  onDiscard: () => void;
}) {
  const t = useT();
  const locale = useLocale();
  const ops = item.diff.ops ?? [];
  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-pretty break-words">{item.topic}</DialogTitle>
          <DialogDescription>{improvementReach(t, item)}</DialogDescription>
        </DialogHeader>
        <div className="grid min-w-0 gap-3" data-improvement={item.kind}>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <StatusBadge tone={item.kind === "suggestion" ? "info" : "warn"}>
              {t(item.kind === "suggestion" ? "improve.kind.suggestion" : "improve.kind.correction")}
            </StatusBadge>
            <span className="text-xs text-muted-foreground">
              {item.kind === "suggestion" && item.week ? t("improve.week", { date: formatDate(item.week, locale) }) : t(originKey(item.origin))}
            </span>
          </div>
          {item.kind === "correction" && item.lesson ? (
            <p className="text-sm text-pretty break-words">
              <span className="font-medium">{t("improve.lesson")} </span>
              {item.lesson}
            </p>
          ) : item.summary ? (
            <p className="text-sm text-pretty break-words">{item.summary}</p>
          ) : null}
          <div className="grid min-w-0 gap-2 rounded-md bg-muted/50 px-3 py-2">
            <p className="text-sm font-medium">{t("improve.proposal")}</p>
            {ops.length ? (
              <ul className="grid min-w-0 gap-2 text-sm">
                {ops.map((op, i) => (
                  <OpLine key={`${op.path}-${i}`} op={op} />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t("improve.proposal.none")}</p>
            )}
            {item.test ? (
              <div className="grid min-w-0 gap-1 text-sm">
                <p className="font-medium">{t("improve.test", { name: item.test.name })}</p>
                {item.test.first_message ? <p className="text-pretty break-words text-muted-foreground">{t("improve.test.first", { text: item.test.first_message })}</p> : null}
                {item.test.plan ? <p className="text-pretty break-words text-muted-foreground">{item.test.plan}</p> : null}
                {item.test.critical ? <StatusBadge tone="warn" className="justify-self-start">{t("improve.test.critical")}</StatusBadge> : null}
              </div>
            ) : null}
          </div>
          {problem ? (
            <p role="alert" className="text-sm text-destructive">
              {problem}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
            {t("improve.close")}
          </Button>
          {allowed.includes("discard") ? (
            <Button type="button" variant="outline" onClick={onDiscard} disabled={busy}>
              {t("improve.discard")}
            </Button>
          ) : null}
          {allowed.includes("accept") ? (
            <Button type="button" onClick={onAccept} loading={busy}>
              {t("improve.accept")}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DiscardDialog({ item, onClose, onDiscard }: { item: Improvement; onClose: () => void; onDiscard: (reason: string) => Promise<string | null> }) {
  const t = useT();
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const clean = reason.split(/\s+/).filter(Boolean).join(" ");
    if (clean.length < REASON_MIN) return setError(t("improve.discard.reason.required"));
    startTransition(async () => {
      const problem = await onDiscard(clean);
      if (problem) setError(problem);
    });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("improve.discard.title")}</DialogTitle>
          <DialogDescription>{item.kind === "suggestion" ? t("improve.discard.body.suggestion") : t("improve.discard.body.correction")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid min-w-0 gap-4" noValidate>
          <p className="text-sm font-medium text-pretty break-words">{item.topic}</p>
          <Field label={t("improve.discard.reason")} required hint={t("improve.discard.reason.hint")} error={error ?? undefined}>
            {(a11y) => <Textarea {...a11y} value={reason} maxLength={REASON_MAX} rows={3} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("improve.cancel")}
            </Button>
            <Button type="submit" variant="destructive" loading={pending}>
              {t("improve.discard.confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

