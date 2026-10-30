"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Textarea } from "@nexus/ui";

import { reloadSectionAction, savePoliciesAction } from "@/app/(console)/clients/[ref]/business/actions";
import { decideSuggestionAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import { POLICY_KEYS, type Policies, type PoliciesBody, type PolicyKey } from "@/lib/backend/business-sections";
import type { Suggestion } from "@/lib/backend/client-records";

import { asText, policySuggestions, sourceKey } from "./proposals-model";
import { ConflictNotice, EditAction, ReadList, SectionFrame, problemOf, useSectionEdit, type Result } from "./section-frame";
import { SuggestionCard, type Decision } from "./suggestion-card";

export type PoliciesActions = {
  save: (body: { ref: string; revision: number; body: PoliciesBody }) => Promise<Result<Policies>>;
  decide: (body: { ref: string; id: string; decision: Decision; value?: unknown }) => Promise<Result<unknown>>;
  reload: (body: { ref: string; section: "policies" }) => Promise<Result<unknown>>;
};

const SERVER_ACTIONS: PoliciesActions = {
  save: (b) => savePoliciesAction(b),
  decide: (b) => decideSuggestionAction(b),
  reload: (b) => reloadSectionAction(b),
};

const LABEL: Record<PolicyKey, MessageKey> = {
  cancellation: "business.policies.cancellation",
  payments: "business.policies.payments",
  deposit: "business.policies.deposit",
  no_show: "business.policies.no_show",
};

function valuesOf(p: Policies): Record<PolicyKey, string> {
  return { cancellation: p.cancellation ?? "", payments: p.payments ?? "", deposit: p.deposit ?? "", no_show: p.no_show ?? "" };
}

/**
 * «Políticas» de Negocio (spec 047, enmienda del 2026-10-29; requisitos 60.4 y
 * 60.5): cancelación, pagos, señal y no presentarse, lo que ya entraba en el
 * prompt de todos sus agentes. Se leen primero y «Editar» las escribe las cuatro
 * (`PUT …/policies` las sustituye, con `If-Match`). Lo propuesto para cada una
 * sale debajo de su valor, «Sugerido · confirma», con su procedencia y aceptar,
 * editar o descartar; nada entra en el prompt hasta que una persona lo acepta
 * (60.7). Aceptar vuelve a leer la sección; descartar solo la quita.
 *
 * `suggestions` es `null` si la ficha no se pudo leer: lo escrito se ve igual y
 * se avisa de que lo sugerido no cargó.
 */
export function PoliciesSection({
  refId,
  policies: initial,
  suggestions: initialSuggestions,
  canWrite,
  actions = SERVER_ACTIONS,
}: {
  refId: string;
  policies: Policies;
  suggestions: Suggestion[] | null;
  canWrite: boolean;
  actions?: PoliciesActions;
}) {
  const t = useT();
  const [policies, setPolicies] = React.useState(initial);
  const [values, setValues] = React.useState(() => valuesOf(initial));
  const [suggestions, setSuggestions] = React.useState(initialSuggestions);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  const edit = useSectionEdit("business-policies");
  const byKey = policySuggestions(suggestions ?? []);

  function cancel() {
    setValues(valuesOf(policies));
    setProblem(null);
    edit.close();
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const body = Object.fromEntries(POLICY_KEYS.map((k) => [k, values[k].trim() || null])) as PoliciesBody;
    startTransition(async () => {
      const res = await actions.save({ ref: refId, revision: policies.revision, body });
      if (res.ok) {
        setPolicies(res.data);
        setValues(valuesOf(res.data));
        setProblem(null);
        edit.close();
        toast.success(t("business.section.saved"));
        return;
      }
      setProblem(problemOf(res) === "conflict" ? "conflict" : t("business.section.error.generic"));
    });
  }

  /** Tras un 412: lo nuevo de la sección, en el formulario, para revisarlo antes de volver a guardar. */
  function reloadAfterConflict() {
    startTransition(async () => {
      const res = await actions.reload({ ref: refId, section: "policies" });
      if (!res.ok) return setProblem(t("business.section.error.generic"));
      const next = res.data as Policies;
      setPolicies(next);
      setValues(valuesOf(next));
      setProblem(null);
    });
  }

  async function decided(id: string, decision: Decision) {
    setSuggestions((prev) => (prev ? prev.filter((s) => s.id !== id) : prev));
    if (decision === "discard") return;
    const res = await actions.reload({ ref: refId, section: "policies" });
    if (res.ok) {
      const next = res.data as Policies;
      setPolicies(next);
      setValues(valuesOf(next));
    }
  }

  return (
    <SectionFrame
      id="business-policies"
      title={t("business.policies.title")}
      state={policies.state}
      canWrite={canWrite}
      action={edit.editing ? null : <EditAction label={t("business.section.edit.label", { section: t("business.policies.title") })} onClick={edit.open} />}
    >
      <p className="text-sm text-pretty text-muted-foreground">{t("business.proposals.everyAgent")}</p>
      {canWrite && edit.editing ? (
        <form onSubmit={submit} className="grid min-w-0 gap-4" noValidate>
          {POLICY_KEYS.map((key) => (
            <Field key={key} label={t(LABEL[key])} className="min-w-0">
              {(a11y) => <Textarea {...a11y} value={values[key]} rows={2} maxLength={1000} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />}
            </Field>
          ))}
          {problem === "conflict" ? <ConflictNotice onReload={reloadAfterConflict} /> : null}
          {problem && problem !== "conflict" ? (
            <p role="alert" className="text-sm text-destructive">
              {problem}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" loading={pending}>
              {t("business.policies.save")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={cancel}>
              {t("business.section.cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <ReadList
          rows={POLICY_KEYS.map((key) => {
            const value = policies[key];
            const proposals = byKey.get(key) ?? [];
            return {
              label: t(LABEL[key]),
              value: (
                <div className="grid min-w-0 gap-2">
                  <p className={`min-w-0 text-pretty break-words whitespace-pre-line ${value ? "" : "text-muted-foreground"}`}>
                    {value || t("business.policies.none")}
                  </p>
                  {proposals.length ? (
                    <ul className="grid min-w-0 gap-2">
                      {proposals.map((s) => (
                        <SuggestionCard
                          key={s.id}
                          title={t(LABEL[key])}
                          value={asText(s.proposed_value)}
                          sourceLabel={t(sourceKey(s.source))}
                          current={value}
                          canWrite={canWrite}
                          onDecide={(decision, edited) =>
                            actions.decide({ ref: refId, id: s.id, decision, ...(decision === "edit" ? { value: edited } : {}) })
                          }
                          onDecided={(decision) => void decided(s.id, decision)}
                        />
                      ))}
                    </ul>
                  ) : null}
                </div>
              ),
            };
          })}
        />
      )}
      {suggestions === null ? <p className="text-xs text-pretty text-muted-foreground">{t("business.suggested.unavailable")}</p> : null}
    </SectionFrame>
  );
}
