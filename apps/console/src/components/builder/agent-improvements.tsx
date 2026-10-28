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
import { RowActions, type RowAction } from "@/components/row-actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
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
  const [busy, setBusy] = React.useState<string | null>(null);
  const [accepted, setAccepted] = React.useState<ImprovementAccepted | null>(null);
  const [problem, setProblem] = React.useState<{ id: string; text: string } | null>(null);
  const [discarding, setDiscarding] = React.useState<Improvement | null>(null);
  const [reloading, startReload] = React.useTransition();

  const items = data?.items ?? [];
  const allowed = data?.allowed ?? [];
  const menu = foldsIntoMenu(items.length * allowed.length);

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

  async function accept(item: Improvement) {
    setBusy(item.id);
    setProblem(null);
    const res = await actions.accept({ ref: refId, agent: agentId, id: item.id });
    setBusy(null);
    if (res.ok) {
      drop(item.id);
      setAccepted(res.data);
      onAccepted?.(res.data);
      return;
    }
    setProblem({ id: item.id, text: failure(res) });
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

  if (data === null) {
    return <ErrorState className="py-6" title={t("improve.error.load")} description={t("improve.error.load.hint")} onRetry={retry} retryLabel={t("improve.retry")} />;
  }

  return (
    <div className="grid min-w-0 gap-4" data-slot="agent-improvements" aria-busy={reloading}>
      <p className="text-sm text-pretty text-muted-foreground">{t("improve.intro")}</p>
      {accepted ? (
        <Callout tone="positive" title={t("improve.accepted.title")} dismissible dismissLabel={t("improve.accepted.dismiss")} onDismiss={() => setAccepted(null)}>
          {t("improve.accepted.body", { n: accepted.draft_revision })}
        </Callout>
      ) : null}
      {items.length === 0 ? (
        <EmptyState icon={Lightbulb} title={t("improve.empty")} description={t("improve.empty.hint")} readonly />
      ) : (
        <ul aria-label={t("improve.list")} className="grid min-w-0 divide-y divide-border-soft border-y border-border-soft">
          {items.map((item) => {
            const rowActions: RowAction[] = allowed.map((a) =>
              a === "accept"
                ? { label: t("improve.accept"), primary: true, disabled: busy !== null, onSelect: () => void accept(item) }
                : { label: t("improve.discard"), disabled: busy !== null, onSelect: () => setDiscarding(item) },
            );
            return (
              <li key={item.id} className="min-w-0 py-3">
                <ImprovementRow item={item} actions={rowActions} menu={menu} problem={problem?.id === item.id ? problem.text : null} />
              </li>
            );
          })}
        </ul>
      )}
      {discarding ? <DiscardDialog item={discarding} onClose={() => setDiscarding(null)} onDiscard={(reason) => discard(discarding, reason)} /> : null}
    </div>
  );
}

function ImprovementRow({ item, actions, menu, problem }: { item: Improvement; actions: RowAction[]; menu: boolean; problem: string | null }) {
  const t = useT();
  const locale = useLocale();
  const titleId = React.useId();
  const ops = item.diff.ops ?? [];
  return (
    <article aria-labelledby={titleId} className="grid min-w-0 gap-2" data-improvement={item.kind}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="grid min-w-0 flex-1 basis-56 gap-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <StatusBadge tone={item.kind === "suggestion" ? "info" : "warn"}>
              {t(item.kind === "suggestion" ? "improve.kind.suggestion" : "improve.kind.correction")}
            </StatusBadge>
            <span className="text-xs text-muted-foreground">
              {item.kind === "suggestion" && item.week ? t("improve.week", { date: formatDate(item.week, locale) }) : t(originKey(item.origin))}
            </span>
          </div>
          <h3 id={titleId} className="text-sm font-semibold text-pretty break-words">
            {item.topic}
          </h3>
          <p className="text-xs text-muted-foreground">{improvementReach(t, item)}</p>
        </div>
        {actions.length && menu ? <RowActions actions={actions} menu ariaLabel={t("improve.actions", { topic: item.topic })} /> : null}
        {actions.length && !menu ? (
          // Pocos botones en la lista: van a la vista, el principal primero (la regla de los tres puntos).
          <div className="flex shrink-0 flex-wrap gap-2">
            {actions.map((a) => (
              <Button key={a.label} size="sm" variant={a.primary ? "default" : "outline"} disabled={a.disabled} onClick={a.onSelect}>
                {a.label}
              </Button>
            ))}
          </div>
        ) : null}
      </div>
      {item.kind === "correction" && item.lesson ? (
        <p className="text-sm text-pretty break-words">
          <span className="font-medium">{t("improve.lesson")} </span>
          {item.lesson}
        </p>
      ) : item.summary ? (
        <p className="text-sm text-pretty break-words">{item.summary}</p>
      ) : null}
      <details className="group min-w-0 rounded-md bg-muted/50 px-3 py-2">
        <summary className="min-h-6 cursor-pointer text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
          {t("improve.proposal")}
        </summary>
        <div className="mt-2 grid min-w-0 gap-3">
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
      </details>
      {problem ? (
        <p role="alert" className="text-sm text-destructive">
          {problem}
        </p>
      ) : null}
    </article>
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

