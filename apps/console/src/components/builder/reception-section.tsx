"use client";

import { ArrowRight, Pencil } from "lucide-react";
import * as React from "react";

import { Button, Callout, Field, StatusBadge, Textarea } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { ClientAgent } from "@/lib/backend";
import type { BuilderDraft, SpecProblem } from "@/lib/backend/builder-types";

import type { Result } from "./builder-model";
import { RECEPTION_LIMITS, receptionPayload, receptionProblems, type Reception } from "./improve-model";
import { visibleText, visibleTone } from "./life-model";

type Failure = Extract<Result<unknown>, { ok: false }>;

/**
 * La sección Recepción del agente (spec 047, T178; requisito 53): marcarlo como
 * «Recepción», elegir a qué agentes **de este cliente** deriva y cuándo derivar a
 * cada uno. Se guarda en su AgentSpec (`reception`), en el mismo borrador y con
 * la misma revisión que los bloques: publicar pasa la puerta como cualquier
 * cambio. La herramienta de derivar la pone y la quita la API.
 *
 * Lo que la persona tiene que saber está a la vista: la conversación sigue en el
 * mismo número y el mismo hilo; a la tercera ida y vuelta pasa a una persona; a
 * un agente en pausa o archivado no se deriva; el gasto cuenta en quien responde.
 */
/**
 * La marca «Recepción» de la cabecera: lo que dice la versión publicada
 * (`is_reception` de la API) y, si el borrador lo cambia, lo que pasará al
 * publicar. Sin el dato de la API (respuestas de antes), manda el borrador.
 */
export function ReceptionBadge({ published, drafted }: { published: boolean | undefined; drafted: boolean }) {
  const t = useT();
  const live = published ?? drafted;
  if (live && drafted) {
    return (
      <StatusBadge tone="info" data-slot="agent-reception">
        {t("reception.title")}
      </StatusBadge>
    );
  }
  if (live) {
    return (
      <StatusBadge tone="warn" data-slot="agent-reception">
        {t("reception.badge.leaving")}
      </StatusBadge>
    );
  }
  if (drafted) {
    return (
      <StatusBadge tone="muted" data-slot="agent-reception">
        {t("reception.badge.draft")}
      </StatusBadge>
    );
  }
  return null;
}

export function ReceptionSection({
  agentId,
  reception,
  agents,
  canWrite,
  onSave,
  onReload,
}: {
  agentId: string;
  reception: Reception;
  /** Los agentes del cliente (este incluido): los destinos posibles son los demás, vivos. */
  agents: readonly ClientAgent[];
  canWrite: boolean;
  onSave: (next: Reception) => Promise<Result<BuilderDraft>>;
  /** Alguien guardó el agente antes: la pantalla vuelve a leer el borrador. */
  onReload?: () => void;
}) {
  const t = useT();
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState<Reception>(reception);
  const [pending, startTransition] = React.useTransition();
  const [problem, setProblem] = React.useState<string | null>(null);
  const [apiProblems, setApiProblems] = React.useState<SpecProblem[]>([]);
  const [showErrors, setShowErrors] = React.useState(false);
  const editRef = React.useRef<HTMLButtonElement>(null);

  const candidates = agents.filter((a) => a.id !== agentId && a.status !== "archived" && a.lifecycle !== "archived");
  const byId = new Map(agents.map((a) => [a.id, a]));
  const targets = draft.targets ?? [];
  const chosen = new Map(targets.map((x) => [x.agent_id, x.when]));
  const problems = showErrors ? receptionProblems(draft) : [];
  const whenError = (id: string) => {
    const p = problems.find((x) => x.agent_id === id);
    if (!p) return undefined;
    return p.problem === "when_required" ? t("reception.error.whenRequired") : t("reception.error.whenTooLong", { max: RECEPTION_LIMITS.when });
  };

  function open() {
    setDraft(reception);
    setEditing(true);
    setProblem(null);
    setApiProblems([]);
    setShowErrors(false);
  }

  function close() {
    setEditing(false);
    window.requestAnimationFrame(() => editRef.current?.focus());
  }

  function toggle(id: string, on: boolean) {
    const next = on ? [...targets, { agent_id: id, when: "" }] : targets.filter((x) => x.agent_id !== id);
    setDraft({ ...draft, targets: next });
  }

  function setWhen(id: string, when: string) {
    setDraft({ ...draft, targets: targets.map((x) => (x.agent_id === id ? { ...x, when } : x)) });
  }

  function failure(res: Failure): string {
    if (res.status === 412) return t("reception.error.conflict");
    if (res.code === "spec_invalid") return t("reception.error.invalid");
    if (res.status === 403) return t("common.forbidden");
    return t("reception.error.generic");
  }

  function save(event: React.FormEvent) {
    event.preventDefault();
    setShowErrors(true);
    if (receptionProblems(draft).length) return;
    setProblem(null);
    setApiProblems([]);
    startTransition(async () => {
      const res = await onSave(receptionPayload(draft));
      if (res.ok) {
        close();
        return;
      }
      setProblem(failure(res));
      const list = res.info?.problems;
      if (Array.isArray(list)) setApiProblems((list as SpecProblem[]).filter((p) => p.pointer.startsWith("/reception")));
      if (res.status === 412) onReload?.();
    });
  }

  if (!editing) {
    const live = (reception.targets ?? []).filter(() => reception.enabled);
    return (
      <div className="grid min-w-0 gap-3" data-slot="reception">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
          <div className="grid min-w-0 flex-1 basis-64 gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={reception.enabled ? "positive" : "muted"}>{t(reception.enabled ? "reception.on" : "reception.off")}</StatusBadge>
            </div>
            <p className="text-sm text-pretty text-muted-foreground">{t(reception.enabled ? "reception.on.hint" : "reception.off.hint")}</p>
          </div>
          {canWrite && candidates.length ? (
            <Button ref={editRef} size="sm" variant="ghost" onClick={open} aria-label={t("reception.edit.label")}>
              <Pencil aria-hidden="true" />
              {t("builder.edit")}
            </Button>
          ) : null}
        </div>
        {live.length ? (
          <ul aria-label={t("reception.targets")} className="grid min-w-0 gap-2">
            {live.map((x) => {
              const agent = byId.get(x.agent_id);
              return (
                <li key={x.agent_id} className="grid min-w-0 gap-1 rounded-md bg-muted/50 px-3 py-2">
                  <span className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-medium">
                    <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
                    <span className="min-w-0 break-words">{agent?.name ?? t("reception.target.gone")}</span>
                    {agent?.visible_state ? <StatusBadge tone={visibleTone(agent.visible_state)}>{visibleText(t, agent.visible_state)}</StatusBadge> : null}
                  </span>
                  <span className="text-sm text-pretty break-words text-muted-foreground">{t("reception.target.when", { when: x.when })}</span>
                </li>
              );
            })}
          </ul>
        ) : null}
        {!candidates.length ? <p className="text-sm text-pretty text-muted-foreground">{t("reception.noCandidates")}</p> : null}
        <p className="text-xs text-pretty text-muted-foreground">{t("reception.rules")}</p>
      </div>
    );
  }

  return (
    <form onSubmit={save} className="grid min-w-0 gap-4" noValidate data-slot="reception-editor" aria-label={t("reception.edit.label")}>
      <label className="flex min-h-6 items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1 size-4 accent-primary"
          checked={draft.enabled}
          onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
        />
        <span className="grid">
          <span className="font-medium">{t("reception.mark")}</span>
          <span className="text-xs text-muted-foreground">{t("reception.mark.hint")}</span>
        </span>
      </label>
      {draft.enabled ? (
        <fieldset className="grid min-w-0 gap-3">
          <legend className="text-sm font-medium">{t("reception.targets.legend")}</legend>
          <ul className="grid min-w-0 gap-3">
            {candidates.map((a) => {
              const on = chosen.has(a.id);
              const paused = a.visible_state?.code === "paused";
              return (
                <li key={a.id} className="grid min-w-0 gap-2">
                  <label className="flex min-h-6 items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="size-4 accent-primary"
                      checked={on}
                      disabled={!on && targets.length >= RECEPTION_LIMITS.targets}
                      onChange={(e) => toggle(a.id, e.target.checked)}
                    />
                    <span className="min-w-0 break-words">{t("reception.target.to", { name: a.name })}</span>
                    {a.is_reception ? <span className="text-xs text-muted-foreground">{t("reception.target.isReception")}</span> : null}
                    {paused ? <span className="text-xs text-muted-foreground">{t("reception.target.paused")}</span> : null}
                  </label>
                  {on ? (
                    <Field label={t("reception.when", { name: a.name })} required hint={t("reception.when.hint")} error={whenError(a.id)} className="pl-6">
                      {(a11y) => (
                        <Textarea
                          {...a11y}
                          value={chosen.get(a.id) ?? ""}
                          maxLength={RECEPTION_LIMITS.when}
                          rows={2}
                          onChange={(e) => setWhen(a.id, e.target.value)}
                        />
                      )}
                    </Field>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {problems.some((p) => p.problem === "no_targets") ? (
            <p role="alert" className="text-sm text-destructive">
              {t("reception.error.noTargets")}
            </p>
          ) : null}
        </fieldset>
      ) : null}
      {problem ? (
        <Callout tone="danger" title={problem}>
          {apiProblems.length ? (
            <ul className="grid list-disc gap-1 pl-5">
              {apiProblems.map((p, i) => (
                <li key={`${p.pointer}-${i}`} className="break-words">
                  {p.message || p.code}
                </li>
              ))}
            </ul>
          ) : null}
        </Callout>
      ) : null}
      <p className="text-xs text-pretty text-muted-foreground">{t("reception.rules")}</p>
      <div className="flex min-w-0 flex-wrap gap-2">
        <Button type="submit" loading={pending}>
          {t("reception.save")}
        </Button>
        <Button type="button" variant="outline" onClick={close} disabled={pending}>
          {t("reception.cancel")}
        </Button>
      </div>
    </form>
  );
}
