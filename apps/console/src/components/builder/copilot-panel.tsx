"use client";

import { Send, Sparkles } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Label, StatusBadge, StatusDot, Textarea } from "@nexus/ui";

import { decideProposalAction } from "@/app/(console)/clients/[ref]/agents/builder-actions";
import { copilotAction, copilotFixAction } from "@/app/(console)/clients/[ref]/agents/life-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Citation, CopilotAnswer, CopilotContext, CopilotFixOffer, CopilotFixResult } from "@/lib/backend/agent-life-types";
import type { Proposal } from "@/lib/backend/builder-types";

import { blockOfPointer, type Result } from "./builder-model";
import { ProposalList, type DecideProposal } from "./proposals";

type Ids = { ref: string; agent: string };
export type CopilotActions = {
  ask: (body: Ids & { message: string; context?: CopilotContext }) => Promise<Result<CopilotAnswer>>;
  fix: (body: Ids & { test: string; scope: "business" | "agent"; value: string }) => Promise<Result<CopilotFixResult>>;
  decide: DecideProposal;
};

const SERVER_ACTIONS: CopilotActions = {
  ask: (body) => copilotAction(body),
  fix: (body) => copilotFixAction(body),
  decide: (body) => decideProposalAction(body),
};

/** Lo que la pantalla le pide al copiloto desde fuera: «¿Por qué dijo esto?». */
export type CopilotHandle = { ask: (message: string, context?: CopilotContext, about?: string) => void };

type Exchange = {
  id: number;
  message: string;
  about: string | null;
  answer: CopilotAnswer | null;
  error: string | null;
};

const KINDS = new Set(["business", "instruction", "knowledge", "tool"]);
const SECTION_ANCHOR: Record<string, string> = {
  basics: "business-basics",
  locations: "business-locations",
  hours: "business-hours",
  special_dates: "business-special-dates",
  services: "business-services",
};

/** Adónde lleva una cita: la sección de la ficha, el bloque del borrador o las habilidades. */
export function citationHref(refId: string, link: Citation["link"]): string | null {
  if (!link) return null;
  const base = `/clients/${encodeURIComponent(refId)}`;
  if (link.target.startsWith("business/")) {
    const anchor = SECTION_ANCHOR[link.target.slice("business/".length)];
    return `${base}/business${anchor ? `#${anchor}` : ""}`;
  }
  if (link.target === "agent") {
    const block = link.pointer ? blockOfPointer(link.pointer) : null;
    return `#${block ? `bloque-${block}` : "agente-borrador"}`;
  }
  if (link.target === "capabilities") return `${base}/capabilities`;
  if (link.target === "knowledge") return `${base}/knowledge`;
  return null;
}

/**
 * El copiloto, en el lateral de la pantalla del agente (spec 047, historia 18;
 * requisito 19). Acepta peticiones con palabras normales y responde con
 * propuestas revisables (19.1, 19.3), que se aplican o se rechazan como
 * cualquier otra. «¿Por qué dijo esto?» —en cada burbuja del probador y en cada
 * prueba que falla— cita sus fuentes con enlace: la ficha, una instrucción, el
 * conocimiento o una herramienta (19.2). Si el arreglo es un dato, pregunta
 * dónde se corrige —en la ficha o solo en este agente— y solo entonces lo
 * aplica (19.4). A quien solo lee le explica, sin un control de aplicar (19.5).
 */
export const CopilotPanel = React.forwardRef<
  CopilotHandle,
  {
    refId: string;
    agentId: string;
    canWrite: boolean;
    /** Se aplicó algo: el borrador o la ficha cambiaron. */
    onChanged?: () => void;
    actions?: CopilotActions;
  }
>(function CopilotPanel({ refId, agentId, canWrite, onChanged, actions = SERVER_ACTIONS }, ref) {
  const t = useT();
  const base = React.useId();
  const [exchanges, setExchanges] = React.useState<Exchange[]>([]);
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const counter = React.useRef(0);
  const endRef = React.useRef<HTMLLIElement>(null);

  const errorText = React.useCallback(
    (res: Extract<Result<unknown>, { ok: false }>) =>
      res.code === "build_budget_exhausted" || res.status === 402
        ? t("builder.copilot.error.budget")
        : res.code === "no_version"
          ? t("builder.copilot.error.noVersion")
          : res.status === 401 || res.status === 403
            ? t("common.forbidden")
            : t("builder.copilot.error.generic"),
    [t],
  );

  const ask = React.useCallback(
    async (message: string, context?: CopilotContext, about?: string) => {
      const id = ++counter.current;
      setExchanges((prev) => [...prev, { id, message, about: about ?? null, answer: null, error: null }]);
      setBusy(true);
      const res = await actions.ask({ ref: refId, agent: agentId, message, ...(context ? { context } : {}) });
      setBusy(false);
      setExchanges((prev) =>
        prev.map((x) => (x.id === id ? { ...x, answer: res.ok ? res.data : null, error: res.ok ? null : errorText(res) } : x)),
      );
      requestAnimationFrame(() => endRef.current?.scrollIntoView?.({ block: "nearest" }));
    },
    [actions, refId, agentId, errorText],
  );

  React.useImperativeHandle(ref, () => ({ ask: (message, context, about) => void ask(message, context, about) }), [ask]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    void ask(message);
  }

  return (
    <section aria-labelledby={`${base}-title`} className="grid min-w-0 gap-3" data-slot="copilot-panel">
      <div className="grid min-w-0 gap-1">
        <h2 id={`${base}-title`} className="inline-flex items-center gap-2 text-base font-semibold">
          <Sparkles aria-hidden="true" className="size-4 text-muted-foreground" />
          {t("builder.copilot.title")}
        </h2>
        <p className="text-sm text-pretty text-muted-foreground">{canWrite ? t("builder.copilot.intro") : t("builder.copilot.readonly")}</p>
      </div>

      <ol aria-label={t("builder.copilot.conversation")} aria-live="polite" className="grid max-h-[32rem] min-w-0 gap-3 overflow-y-auto" data-slot="copilot-conversation">
        {!exchanges.length ? <li className="text-sm text-muted-foreground">{t("builder.copilot.empty")}</li> : null}
        {exchanges.map((x) => (
          <li key={x.id} className="grid min-w-0 gap-2" data-slot="copilot-exchange">
            <div className="grid min-w-0 justify-items-end gap-1">
              <span className="sr-only">{t("builder.copilot.you")}</span>
              <p className="max-w-[90%] rounded-md bg-primary px-3 py-2 text-sm text-pretty break-words text-primary-foreground">{x.message}</p>
              {x.about ? <p className="max-w-[90%] text-right text-xs text-pretty break-words text-muted-foreground">{x.about}</p> : null}
            </div>
            {x.answer ? (
              <CopilotReply
                refId={refId}
                agentId={agentId}
                answer={x.answer}
                canWrite={canWrite}
                actions={actions}
                onChanged={onChanged}
              />
            ) : x.error ? (
              <p role="alert" className="text-sm text-destructive text-pretty">
                {x.error}
              </p>
            ) : (
              <p role="status" className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                <StatusDot tone="info" pulse />
                {t("builder.copilot.thinking")}
              </p>
            )}
          </li>
        ))}
        <li ref={endRef} aria-hidden="true" className="h-0" />
      </ol>

      <form onSubmit={submit} className="grid min-w-0 gap-2" data-slot="copilot-form">
        <Label htmlFor={`${base}-text`} className="sr-only">
          {t("builder.copilot.message")}
        </Label>
        <div className="flex min-w-0 items-end gap-2">
          <Textarea
            id={`${base}-text`}
            value={text}
            rows={2}
            maxLength={1000}
            placeholder={t("builder.copilot.placeholder")}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            className="min-h-10 flex-1"
          />
          <Button type="submit" loading={busy} className="shrink-0">
            <Send aria-hidden="true" />
            {t("builder.copilot.send")}
          </Button>
        </div>
      </form>
    </section>
  );
});

function CopilotReply({
  refId,
  agentId,
  answer,
  canWrite,
  actions,
  onChanged,
}: {
  refId: string;
  agentId: string;
  answer: CopilotAnswer;
  canWrite: boolean;
  actions: CopilotActions;
  onChanged?: () => void;
}) {
  const t = useT();
  const proposals: Proposal[] = answer.proposals.map((p) => ({
    id: p.id,
    kind: p.kind,
    author: "copilot",
    summary: p.summary,
    diff: p.diff,
    status: "open",
    created_at: p.expires_at,
    expires_at: p.expires_at,
  }));
  return (
    <div className="grid min-w-0 gap-3 rounded-md border border-border bg-background p-3" data-slot="copilot-reply">
      <p className="sr-only">{t("builder.copilot.title")}</p>
      <p className="text-sm text-pretty break-words whitespace-pre-line">{answer.text}</p>
      {answer.citations.length ? (
        <div className="grid min-w-0 gap-1">
          <p className="text-xs font-medium text-muted-foreground">{t("builder.copilot.sources")}</p>
          <ul className="grid min-w-0 gap-2" data-slot="copilot-citations">
            {answer.citations.map((c, i) => (
              <CitationRow key={i} refId={refId} citation={c} />
            ))}
          </ul>
        </div>
      ) : null}
      {proposals.length ? (
        <ProposalList
          bare
          refId={refId}
          agentId={agentId}
          proposals={proposals}
          canWrite={canWrite}
          decide={actions.decide}
          onApplied={() => onChanged?.()}
          onRetry={() => undefined}
        />
      ) : null}
      {answer.fix && canWrite ? <FixForm refId={refId} agentId={agentId} offer={answer.fix} actions={actions} onChanged={onChanged} /> : null}
    </div>
  );
}

function CitationRow({ refId, citation }: { refId: string; citation: Citation }) {
  const t = useT();
  const href = citationHref(refId, citation.link);
  const kind = KINDS.has(citation.kind) ? t(`builder.copilot.kind.${citation.kind}` as MessageKey) : citation.kind;
  return (
    <li className="grid min-w-0 gap-1 text-sm" data-slot="copilot-citation" data-kind={citation.kind}>
      <span className="flex min-w-0 flex-wrap items-center gap-2">
        <StatusBadge tone="muted" dot={false}>
          {kind}
        </StatusBadge>
        {href ? (
          <Link href={href} className="min-w-0 font-medium break-words underline underline-offset-4 hover:no-underline" aria-label={t("builder.copilot.open", { label: `${kind} · ${citation.label}` })}>
            {citation.label}
          </Link>
        ) : (
          <span className="min-w-0 font-medium break-words">{citation.label}</span>
        )}
      </span>
      {citation.excerpt ? <span className="text-xs text-pretty break-words text-muted-foreground">«{citation.excerpt}»</span> : null}
    </li>
  );
}

/** «¿Dónde lo corrijo?»: la ficha (lo sabrán todos sus agentes) o solo este agente (19.4). */
function FixForm({
  refId,
  agentId,
  offer,
  actions,
  onChanged,
}: {
  refId: string;
  agentId: string;
  offer: CopilotFixOffer;
  actions: CopilotActions;
  onChanged?: () => void;
}) {
  const t = useT();
  const base = React.useId();
  const scopes = offer.scopes.filter((s) => s === "business" || s === "agent");
  const [scope, setScope] = React.useState<"business" | "agent" | null>(null);
  const [value, setValue] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [done, setDone] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!scope || !value.trim()) {
      setError(t("builder.copilot.fix.required"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await actions.fix({ ref: refId, agent: agentId, test: offer.test_id, scope, value: value.trim() });
    setBusy(false);
    if (res.ok) {
      setDone(true);
      toast.success(t("builder.copilot.fix.done"));
      onChanged?.();
      return;
    }
    setError(res.code === "invalid_fix" ? t("builder.copilot.fix.invalid") : res.status === 403 ? t("common.forbidden") : t("builder.copilot.error.generic"));
  }

  if (done) return <p className="text-sm text-muted-foreground">{t("builder.copilot.fix.done")}</p>;

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-3" data-slot="copilot-fix">
      <fieldset className="grid min-w-0 gap-2">
        <legend className="mb-1 text-sm font-medium">{t("builder.copilot.fix.title")}</legend>
        {scopes.map((s) => (
          <label key={s} className="flex min-h-6 min-w-0 items-start gap-2 text-sm">
            <input type="radio" name={`${base}-scope`} className="mt-1 size-4 shrink-0 accent-primary" checked={scope === s} onChange={() => setScope(s)} />
            <span className="min-w-0 text-pretty">{s === "business" ? t("builder.copilot.fix.business") : t("builder.copilot.fix.agent")}</span>
          </label>
        ))}
      </fieldset>
      <Field label={t("builder.copilot.fix.value")} error={error ?? undefined} required>
        {(a11y) => <Textarea {...a11y} value={value} rows={2} maxLength={2000} onChange={(e) => setValue(e.target.value)} />}
      </Field>
      <div>
        <Button type="submit" size="sm" loading={busy}>
          {t("builder.copilot.fix.apply")}
        </Button>
      </div>
    </form>
  );
}
