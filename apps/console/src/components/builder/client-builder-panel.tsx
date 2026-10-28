"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Input, StatusBadge, StatusDot, Textarea, buttonVariants } from "@nexus/ui";

import { clientBuilderJobAction, startClientBuilderAction } from "@/app/(console)/clients/[ref]/business/client-builder-actions";
import { decideSuggestionAction, getBusinessAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ClientBuilderResult } from "@/lib/backend/agent-life-types";
import type { QualityJob } from "@/lib/backend/agent-quality-types";
import type { BusinessRecord, Suggestion } from "@/lib/backend/client-records";

import { sleep, type Result } from "./builder-model";
import { builderSuggestions, proposedAgentHref } from "./life-model";
import { waitForJob } from "./quality-model";

export type ClientBuilderActions = {
  start: (body: { ref: string }) => Promise<Result<{ job_id: string }>>;
  poll: (body: { ref: string; job: string }) => Promise<Result<QualityJob>>;
  load: (body: { ref: string }) => Promise<Result<BusinessRecord>>;
  decide: (body: { ref: string; id: string; decision: "accept" | "edit" | "discard"; value?: unknown }) => Promise<Result<{ decision: string }>>;
};

const SERVER_ACTIONS: ClientBuilderActions = {
  start: (body) => startClientBuilderAction(body),
  poll: (body) => clientBuilderJobAction(body),
  load: (body) => getBusinessAction(body),
  decide: (body) => decideSuggestionAction(body),
};

const POLICIES = new Set(["cancellation", "payments", "deposit", "no_show"]);
const SECTIONS = ["policies", "faqs"] as const;

type Faq = { q: string; a: string };
function asFaq(value: unknown): Faq | null {
  if (value && typeof value === "object" && "q" in value && "a" in value) {
    const v = value as { q: unknown; a: unknown };
    return { q: String(v.q ?? ""), a: String(v.a ?? "") };
  }
  return null;
}
function asText(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : JSON.stringify(value);
}

/**
 * «Completar con el constructor» en Negocio (spec 047, historia 18; requisito
 * 18): propone, a partir del nicho y de la ficha, políticas y preguntas
 * frecuentes probables —marcadas «Sugerido · confirma», que no se dan por
 * ciertas (18.3)— y se aceptan, editan o descartan una a una (18.2). Propone
 * también agentes para el cliente, sin crearlos: «Crear este agente» abre
 * «Nuevo agente» con su nombre y su descripción (18.4).
 *
 * Quien solo lee ve lo que queda por confirmar, sin botones (§V).
 */
export function ClientBuilderPanel({
  refId,
  canWrite,
  suggestions: initial,
  actions = SERVER_ACTIONS,
  wait = sleep,
}: {
  refId: string;
  canWrite: boolean;
  /** Las sugerencias del constructor pendientes; `null` si la ficha no se pudo leer. */
  suggestions: Suggestion[] | null;
  actions?: ClientBuilderActions;
  wait?: (ms: number) => Promise<void>;
}) {
  const t = useT();
  const base = React.useId();
  const [suggestions, setSuggestions] = React.useState<Suggestion[]>(initial ?? []);
  const [phase, setPhase] = React.useState<"idle" | "running" | "done" | "failed">("idle");
  const [result, setResult] = React.useState<ClientBuilderResult | null>(null);

  if (!canWrite && !suggestions.length) return null;

  async function run() {
    setPhase("running");
    setResult(null);
    const res = await actions.start({ ref: refId });
    if (!res.ok) {
      setPhase("failed");
      return;
    }
    const done = await waitForJob(() => actions.poll({ ref: refId, job: res.data.job_id }), { wait });
    if (!done || !done.ok || done.data.status !== "done") {
      setPhase("failed");
      return;
    }
    const out = (done.data.result ?? {}) as Partial<ClientBuilderResult>;
    setResult({ sections: out.sections ?? {}, agents: out.agents ?? [], discarded: out.discarded ?? [] });
    const record = await actions.load({ ref: refId });
    if (record.ok) setSuggestions(builderSuggestions(record.data));
    setPhase("done");
  }

  const groups = [
    ...SECTIONS.map((section) => ({ section, items: suggestions.filter((s) => s.section === section) })),
    { section: "other" as const, items: suggestions.filter((s) => !(SECTIONS as readonly string[]).includes(s.section)) },
  ].filter((g) => g.items.length);

  return (
    <section aria-labelledby={`${base}-title`} className="grid min-w-0 gap-4 rounded-md border border-border bg-card p-4 sm:p-6" data-slot="client-builder">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="grid min-w-0 flex-1 basis-64 gap-1">
          <h2 id={`${base}-title`} className="inline-flex items-center gap-2 text-base font-semibold">
            <Sparkles aria-hidden="true" className="size-4 text-muted-foreground" />
            {t("builder.cb.title")}
          </h2>
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("builder.cb.intro")}</p>
        </div>
        {canWrite ? (
          <Button onClick={() => void run()} loading={phase === "running"}>
            {t("builder.cb.run")}
          </Button>
        ) : null}
      </div>

      <p role="status" className="inline-flex items-center gap-2 text-sm text-muted-foreground empty:hidden">
        {phase === "running" ? (
          <>
            <StatusDot tone="info" pulse />
            {t("builder.cb.running")}
          </>
        ) : phase === "done" ? (
          t("builder.cb.done")
        ) : null}
      </p>
      {phase === "failed" ? (
        <p role="alert" className="text-sm text-destructive">
          {t("builder.cb.failed")}
        </p>
      ) : null}

      {groups.length ? (
        <div className="grid min-w-0 gap-4" data-slot="client-builder-suggestions">
          <h3 className="text-sm font-semibold">{t("builder.cb.pending")}</h3>
          {groups.map((g) => (
            <div key={g.section} className="grid min-w-0 gap-2">
              <h4 className="text-xs font-medium text-muted-foreground" id={`${base}-${g.section}`}>
                {t(`builder.cb.section.${g.section}` as MessageKey)}
              </h4>
              <ul aria-labelledby={`${base}-${g.section}`} className="grid min-w-0 gap-2">
                {g.items.map((s) => (
                  <SuggestionRow
                    key={s.id}
                    refId={refId}
                    suggestion={s}
                    canWrite={canWrite}
                    decide={actions.decide}
                    onDecided={() => setSuggestions((prev) => prev.filter((x) => x.id !== s.id))}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : phase === "done" ? (
        <p className="text-sm text-muted-foreground">{t("builder.cb.none")}</p>
      ) : null}

      {result?.discarded.length ? (
        <div className="grid min-w-0 gap-1 text-sm" data-slot="client-builder-discarded">
          <p>
            {result.discarded.length === 1 ? t("builder.cb.discarded.one") : t("builder.cb.discarded.other", { n: result.discarded.length })}
          </p>
          <ul className="grid min-w-0 list-disc gap-1 pl-5 text-muted-foreground">
            {result.discarded.map((reason, i) => (
              <li key={i} className="text-pretty">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {result?.agents.length ? (
        <div className="grid min-w-0 gap-2" data-slot="client-builder-agents">
          <h3 className="text-sm font-semibold">{t("builder.cb.agents")}</h3>
          <p className="text-xs text-pretty text-muted-foreground">{t("builder.cb.agents.intro")}</p>
          <ul className="grid min-w-0 gap-2 sm:grid-cols-2">
            {result.agents.map((agent) => (
              <li key={agent.name} className="grid min-w-0 content-between gap-3 rounded-md border border-border p-3">
                <div className="grid min-w-0 gap-1">
                  <p className="text-sm font-medium break-words">{agent.name}</p>
                  <p className="text-xs text-pretty break-words text-muted-foreground">{agent.description}</p>
                </div>
                {canWrite ? (
                  <div>
                    <Link
                      href={proposedAgentHref(refId, agent)}
                      className={buttonVariants({ size: "sm", variant: "outline" })}
                      aria-label={t("builder.cb.agents.create.label", { name: agent.name })}
                    >
                      {t("builder.cb.agents.create")}
                    </Link>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function SuggestionRow({
  refId,
  suggestion: s,
  canWrite,
  decide,
  onDecided,
}: {
  refId: string;
  suggestion: Suggestion;
  canWrite: boolean;
  decide: ClientBuilderActions["decide"];
  onDecided: () => void;
}) {
  const t = useT();
  const titleId = React.useId();
  const faq = s.section === "faqs" ? asFaq(s.proposed_value) : null;
  const key = s.pointer.split("/").pop() ?? "";
  const title = faq ? faq.q : s.section === "policies" && POLICIES.has(key) ? t(`builder.cb.policy.${key}` as MessageKey) : key || s.pointer;
  const body = faq ? faq.a : asText(s.proposed_value);
  const [editing, setEditing] = React.useState(false);
  const [q, setQ] = React.useState(faq?.q ?? "");
  const [a, setA] = React.useState(faq?.a ?? body);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function send(decision: "accept" | "edit" | "discard") {
    setBusy(decision);
    setError(null);
    const value = decision === "edit" ? (faq ? { q: q.trim(), a: a.trim() } : a.trim()) : undefined;
    const res = await decide({ ref: refId, id: s.id, decision, ...(value !== undefined ? { value } : {}) });
    setBusy(null);
    if (res.ok) {
      toast.success(decision === "discard" ? t("builder.cb.discarded") : t("builder.cb.accepted"));
      onDecided();
      return;
    }
    setError(
      res.code === "already_decided"
        ? t("builder.cb.error.decided")
        : res.code === "invalid_value"
          ? t("builder.cb.error.invalid")
          : res.status === 403
            ? t("common.forbidden")
            : t("builder.cb.error.generic"),
    );
  }

  return (
    <li aria-labelledby={titleId} className="grid min-w-0 gap-2 rounded-md border border-border p-3" data-slot="client-builder-suggestion">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <p id={titleId} className="min-w-0 flex-1 basis-48 text-sm font-medium text-pretty break-words">
          {title}
        </p>
        <StatusBadge tone="warn">{t("builder.cb.suggested")}</StatusBadge>
      </div>
      {editing ? (
        <form
          noValidate
          className="grid min-w-0 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send("edit");
          }}
        >
          {faq ? (
            <Field label={t("builder.cb.faq.q")} required>
              {(a11y) => <Input {...a11y} value={q} maxLength={300} autoComplete="off" onChange={(e) => setQ(e.target.value)} />}
            </Field>
          ) : null}
          <Field label={faq ? t("builder.cb.faq.a") : t("builder.cb.value")} required>
            {(a11y) => <Textarea {...a11y} value={a} rows={3} maxLength={2000} onChange={(e) => setA(e.target.value)} />}
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" loading={busy === "edit"}>
              {t("builder.cb.save")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={busy !== null}>
              {t("builder.cb.cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-pretty break-words whitespace-pre-line text-muted-foreground">{body}</p>
      )}
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
      {canWrite && !editing ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => void send("accept")} loading={busy === "accept"} disabled={busy !== null && busy !== "accept"} aria-label={t("builder.cb.accept.label", { item: title })}>
            {t("builder.cb.accept")}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setEditing(true)} disabled={busy !== null} aria-label={t("builder.cb.edit.label", { item: title })}>
            {t("builder.cb.edit")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void send("discard")} loading={busy === "discard"} disabled={busy !== null && busy !== "discard"} aria-label={t("builder.cb.discard.label", { item: title })}>
            {t("builder.cb.discard")}
          </Button>
        </div>
      ) : null}
    </li>
  );
}
