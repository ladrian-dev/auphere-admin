"use client";

import { useState } from "react";

import { Badge, Button, Field, Input, NativeSelect, StatusBadge } from "@nexus/ui";
import type { RouterPreview, RouterTask } from "@/lib/backend-models";

import { formatPrice } from "../models/labels";
import { previewAction } from "./actions";
import { OUTCOME_LABEL, PROFILE_LABEL, isUuid, rejectionLabel } from "./policy";

/**
 * Spec 047 (T150, 54.2): which deployment the router would choose for a task
 * of a given agent — the same `chain_for` as the turn, with the client's facts
 * read under its GUC — and why every other one was discarded. No model is
 * called.
 */
export function RoutePreview({ tasks, profiles }: { tasks: RouterTask[]; profiles: string[] }) {
  const [tenant, setTenant] = useState("");
  const [agent, setAgent] = useState("");
  const [task, setTask] = useState(tasks[0]?.code ?? "");
  const [profile, setProfile] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [result, setResult] = useState<RouterPreview | null>(null);
  const [pending, setPending] = useState(false);

  async function run() {
    const next: Record<string, string> = {};
    if (!isUuid(tenant)) next.tenant = "Escribe el identificador del cliente (un UUID).";
    if (agent.trim() && !isUuid(agent)) next.agent = "El identificador del agente es un UUID.";
    setErrors(next);
    setFailure(null);
    if (Object.keys(next).length) return;
    setPending(true);
    try {
      const response = await previewAction({
        tenant_id: tenant.trim(),
        task,
        ...(agent.trim() ? { agent_id: agent.trim() } : {}),
        ...(profile ? { profile } : {}),
      });
      if (!response.ok) {
        setResult(null);
        setFailure(response.error);
        return;
      }
      setResult(response.data);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <form
        className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <Field label="Cliente (id)" required requiredLabel="Obligatorio" error={errors.tenant}>
          {(a11y) => <Input {...a11y} value={tenant} onChange={(e) => setTenant(e.target.value)} />}
        </Field>
        <Field label="Agente (id)" optionalLabel="Opcional" hint="Sin agente, el principal no cuenta: solo el perfil." error={errors.agent}>
          {(a11y) => <Input {...a11y} value={agent} onChange={(e) => setAgent(e.target.value)} />}
        </Field>
        <Field label="Tarea">
          {(a11y) => (
            <NativeSelect {...a11y} value={task} onChange={(e) => setTask(e.target.value)}>
              {tasks.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.code}
                  {t.conversation ? " (conversación)" : ""}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Perfil" hint="Vacío: el del agente, o «Automático».">
          {(a11y) => (
            <NativeSelect {...a11y} value={profile} onChange={(e) => setProfile(e.target.value)}>
              <option value="">El del agente</option>
              {profiles.map((p) => (
                <option key={p} value={p}>
                  {PROFILE_LABEL[p] ?? p}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <div className="md:col-span-2 xl:col-span-4">
          <Button type="submit" disabled={pending}>
            {pending ? "Calculando…" : "Ver qué elegiría"}
          </Button>
        </div>
      </form>
      {failure ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {failure}
        </p>
      ) : null}
      {result ? <PreviewResult result={result} /> : null}
    </div>
  );
}

function PreviewResult({ result }: { result: RouterPreview }) {
  const tone = result.outcome === "no_model" ? "danger" : result.outcome === "reserve_model" ? "warning" : "positive";
  const facts = [
    result.facts.eu_only ? "Solo UE" : null,
    result.facts.sovereign ? "Restricción soberana" : null,
    result.facts.partner_allowed.length ? `${result.facts.partner_allowed.length} modelos permitidos al partner` : null,
    `${result.facts.agent_certified.length} despliegues certificados para el agente`,
  ].filter(Boolean);
  return (
    <section aria-label="Resultado" className="flex flex-col gap-3 rounded-md border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={tone}>{OUTCOME_LABEL[result.outcome]}</StatusBadge>
        <span className="text-sm text-muted-foreground">
          {PROFILE_LABEL[result.profile] ?? result.profile} · versión {result.policy_version} · {result.task}
        </span>
      </div>
      {result.facts.degraded ? (
        <p className="text-sm text-pretty">No se pudieron leer los datos del cliente: se aplicó «Solo UE».</p>
      ) : null}
      <p className="text-sm text-muted-foreground text-pretty">{facts.join(" · ")}</p>
      {result.chain.length ? (
        <ol className="flex flex-col gap-1 text-sm">
          {result.chain.map((d, i) => (
            <li key={d.deployment} className="flex min-w-0 flex-wrap gap-x-2">
              <Badge variant={i === 0 ? "default" : "outline"}>{i === 0 ? "Elegido" : `Alternativa ${i}`}</Badge>
              <code className="break-all">{d.deployment}</code>
              <span className="text-muted-foreground">{formatPrice(d.price)}</span>
            </li>
          ))}
        </ol>
      ) : null}
      {result.rejected.length ? (
        <details>
          <summary className="cursor-pointer text-sm font-medium">Descartados ({result.rejected.length})</summary>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {result.rejected.map((r) => (
              <li key={`${r.deployment}:${r.reason}`} className="flex min-w-0 flex-wrap gap-x-2">
                <code className="break-all">{r.deployment}</code>
                <span className="text-muted-foreground">{rejectionLabel(r.reason)}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
