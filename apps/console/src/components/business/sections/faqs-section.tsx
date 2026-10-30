"use client";

import { Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Input, Textarea } from "@nexus/ui";

import { archiveFaqAction, createFaqAction, reloadSectionAction, updateFaqAction } from "@/app/(console)/clients/[ref]/business/actions";
import { decideSuggestionAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { useT } from "@/i18n/client";
import type { Faq, FaqBody, FaqPatch, Faqs } from "@/lib/backend/business-sections";
import type { Suggestion } from "@/lib/backend/client-records";

import { asFaq, faqSuggestions, sourceKey, type FaqValue } from "./proposals-model";
import { ConflictNotice, SectionFrame, problemOf, useSectionEdit, type Result } from "./section-frame";
import { SuggestionCard, type Decision } from "./suggestion-card";

export type FaqsActions = {
  create: (body: { ref: string; revision: number; body: FaqBody }) => Promise<Result<Faqs>>;
  update: (body: { ref: string; revision: number; id: string; body: FaqPatch }) => Promise<Result<Faqs>>;
  archive: (body: { ref: string; revision: number; id: string }) => Promise<Result<Faqs>>;
  decide: (body: { ref: string; id: string; decision: Decision; value?: unknown }) => Promise<Result<unknown>>;
  reload: (body: { ref: string; section: "faqs" }) => Promise<Result<unknown>>;
};

const SERVER_ACTIONS: FaqsActions = {
  create: (b) => createFaqAction(b),
  update: (b) => updateFaqAction(b),
  archive: (b) => archiveFaqAction(b),
  decide: (b) => decideSuggestionAction(b),
  reload: (b) => reloadSectionAction(b),
};

/**
 * «Preguntas frecuentes» de Negocio (spec 047, enmienda del 2026-10-29;
 * requisitos 60.4 y 60.5): las confirmadas, que entran en el prompt de todos sus
 * agentes, cada una con «Editar» y «Quitar», y «Añadir pregunta». Debajo, «Por
 * confirmar»: las guardadas como sugeridas (`suggested`, que no entran en el
 * prompt hasta confirmarlas) y las propuestas pendientes de la ficha
 * (`/faqs/-`), marcadas «Sugerido · confirma» con su procedencia y aceptar,
 * editar o descartar. Una guardada como sugerida se acepta con `suggested:
 * false` y se descarta archivándola; una propuesta, con `POST …/decide`.
 */
export function FaqsSection({
  refId,
  faqs: initial,
  suggestions: initialSuggestions,
  canWrite,
  actions = SERVER_ACTIONS,
}: {
  refId: string;
  faqs: Faqs;
  suggestions: Suggestion[] | null;
  canWrite: boolean;
  actions?: FaqsActions;
}) {
  const t = useT();
  const suggestedId = React.useId();
  const [faqs, setFaqs] = React.useState(initial);
  const [suggestions, setSuggestions] = React.useState(() => (initialSuggestions ? faqSuggestions(initialSuggestions) : null));
  const add = useSectionEdit("business-faqs");
  const confirmed = faqs.items.filter((f) => !f.suggested);
  const savedSuggested = faqs.items.filter((f) => f.suggested);
  const proposals = suggestions ?? [];
  const toConfirm = savedSuggested.length + proposals.length;

  /** Tras un 412: la lista de ahora (con su revisión); lo que se estaba escribiendo se queda. */
  async function reloadAfterConflict(): Promise<boolean> {
    const res = await actions.reload({ ref: refId, section: "faqs" });
    if (res.ok) setFaqs(res.data as Faqs);
    return res.ok;
  }

  async function proposalDecided(id: string, decision: Decision) {
    setSuggestions((prev) => (prev ? prev.filter((s) => s.id !== id) : prev));
    if (decision === "discard") return;
    const res = await actions.reload({ ref: refId, section: "faqs" });
    if (res.ok) setFaqs(res.data as Faqs);
  }

  /** Una guardada como sugerida: aceptar es confirmarla, editar la confirma con lo editado, descartar la archiva. */
  async function decideSaved(faq: Faq, decision: Decision, value?: FaqValue): Promise<Result<Faqs>> {
    const res =
      decision === "discard"
        ? await actions.archive({ ref: refId, revision: faqs.revision, id: faq.id })
        : await actions.update({ ref: refId, revision: faqs.revision, id: faq.id, body: decision === "edit" && value ? { ...value, suggested: false } : { suggested: false } });
    if (res.ok) setFaqs(res.data);
    return res;
  }

  return (
    <SectionFrame
      id="business-faqs"
      title={t("business.faqs.title")}
      state={faqs.state}
      canWrite={canWrite}
      action={
        add.editing ? null : (
          <Button type="button" size="sm" variant="outline" onClick={add.open}>
            <Plus aria-hidden="true" />
            {t("business.faqs.add")}
          </Button>
        )
      }
    >
      <p className="text-sm text-pretty text-muted-foreground">{t("business.proposals.everyAgent")}</p>
      {canWrite && add.editing ? (
        <FaqForm
          initial={{ q: "", a: "" }}
          onCancel={add.close}
          onReload={reloadAfterConflict}
          onSave={async (body) => {
            const res = await actions.create({ ref: refId, revision: faqs.revision, body });
            if (res.ok) {
              setFaqs(res.data);
              add.close();
              toast.success(t("business.faqs.saved"));
            }
            return res;
          }}
        />
      ) : null}

      {confirmed.length ? (
        <ul aria-label={t("business.faqs.list")} className="grid min-w-0 divide-y divide-border">
          {confirmed.map((faq) => (
            <FaqRow
              key={faq.id}
              faq={faq}
              canWrite={canWrite}
              onReload={reloadAfterConflict}
              onSave={async (body) => {
                const res = await actions.update({ ref: refId, revision: faqs.revision, id: faq.id, body });
                if (res.ok) {
                  setFaqs(res.data);
                  toast.success(t("business.faqs.saved"));
                }
                return res;
              }}
              onRemove={async () => {
                const res = await actions.archive({ ref: refId, revision: faqs.revision, id: faq.id });
                if (res.ok) {
                  setFaqs(res.data);
                  toast.success(t("business.faqs.removed"));
                } else {
                  toast.error(t("business.section.error.generic"));
                }
              }}
            />
          ))}
        </ul>
      ) : !toConfirm && !add.editing ? (
        <p className="text-sm text-muted-foreground">{t("business.faqs.empty")}</p>
      ) : null}

      {toConfirm ? (
        <div className="grid min-w-0 gap-2">
          <h3 id={suggestedId} className="text-sm font-medium text-balance">
            {t("business.faqs.suggested")}
          </h3>
          <ul aria-labelledby={suggestedId} className="grid min-w-0 gap-2">
            {savedSuggested.map((faq) => (
              <SuggestionCard
                key={faq.id}
                title={faq.q}
                value={{ q: faq.q, a: faq.a }}
                sourceLabel={t("business.suggested.from.other")}
                canWrite={canWrite}
                onDecide={(decision, value) => decideSaved(faq, decision, typeof value === "object" ? value : undefined)}
                onDecided={() => undefined}
              />
            ))}
            {proposals.map((s) => {
              const value = asFaq(s.proposed_value) ?? { q: "", a: "" };
              return (
                <SuggestionCard
                  key={s.id}
                  title={value.q}
                  value={value}
                  sourceLabel={t(sourceKey(s.source))}
                  canWrite={canWrite}
                  onDecide={(decision, edited) => actions.decide({ ref: refId, id: s.id, decision, ...(decision === "edit" ? { value: edited } : {}) })}
                  onDecided={(decision) => void proposalDecided(s.id, decision)}
                />
              );
            })}
          </ul>
        </div>
      ) : null}
      {suggestions === null ? <p className="text-xs text-pretty text-muted-foreground">{t("business.suggested.unavailable")}</p> : null}
    </SectionFrame>
  );
}

/** Una pregunta confirmada: se lee, y con permiso se edita o se quita. */
function FaqRow({
  faq,
  canWrite,
  onSave,
  onRemove,
  onReload,
}: {
  faq: Faq;
  canWrite: boolean;
  onSave: (body: FaqBody) => Promise<Result<Faqs>>;
  onRemove: () => Promise<void>;
  onReload: () => Promise<boolean>;
}) {
  const t = useT();
  const edit = useSectionEdit(`business-faqs-${faq.id}`);
  const [removing, setRemoving] = React.useState(false);
  if (canWrite && edit.editing) {
    return (
      <li className="min-w-0 py-3">
        <FaqForm
          initial={{ q: faq.q, a: faq.a }}
          onCancel={edit.close}
          onReload={onReload}
          onSave={async (body) => {
            const res = await onSave(body);
            if (res.ok) edit.close();
            return res;
          }}
        />
      </li>
    );
  }
  return (
    <li className="flex min-w-0 flex-wrap items-start justify-between gap-x-4 gap-y-2 py-3">
      <div className="grid min-w-0 flex-1 basis-64 gap-1">
        <p className="min-w-0 text-sm font-medium text-pretty break-words">{faq.q}</p>
        <p className="min-w-0 text-sm text-pretty break-words whitespace-pre-line text-muted-foreground">{faq.a}</p>
      </div>
      {canWrite ? (
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={edit.open} aria-label={t("business.suggested.edit.label", { item: faq.q })}>
            {t("business.section.edit")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            loading={removing}
            onClick={async () => {
              setRemoving(true);
              await onRemove();
              setRemoving(false);
            }}
            aria-label={t("business.faqs.remove.label", { q: faq.q })}
          >
            {t("business.faqs.remove")}
          </Button>
        </div>
      ) : null}
    </li>
  );
}

/** Pregunta (≤ 300) y respuesta (≤ 2.000), las dos obligatorias. Tras un 412, «Recargar» lee la lista sin perder lo escrito. */
function FaqForm({
  initial,
  onSave,
  onCancel,
  onReload,
}: {
  initial: FaqValue;
  onSave: (body: FaqBody) => Promise<Result<Faqs>>;
  onCancel: () => void;
  onReload: () => Promise<boolean>;
}) {
  const t = useT();
  const [q, setQ] = React.useState(initial.q);
  const [a, setA] = React.useState(initial.a);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const body = { q: q.trim(), a: a.trim() };
    if (!body.q || !body.a) {
      setProblem(t("business.faqs.error.required"));
      return;
    }
    startTransition(async () => {
      const res = await onSave(body);
      if (res.ok) {
        setProblem(null);
        return;
      }
      setProblem(problemOf(res) === "conflict" ? "conflict" : t("business.section.error.generic"));
    });
  }

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-3 rounded-md border border-border p-3">
      <Field label={t("business.faqs.q")} required>
        {(a11y) => <Input {...a11y} value={q} maxLength={300} autoComplete="off" onChange={(e) => setQ(e.target.value)} />}
      </Field>
      <Field label={t("business.faqs.a")} required>
        {(a11y) => <Textarea {...a11y} value={a} rows={3} maxLength={2000} onChange={(e) => setA(e.target.value)} />}
      </Field>
      {problem === "conflict" ? (
        <ConflictNotice
          onReload={() =>
            startTransition(async () => {
              setProblem((await onReload()) ? null : t("business.section.error.generic"));
            })
          }
        />
      ) : null}
      {problem && problem !== "conflict" ? (
        <p role="alert" className="text-xs text-pretty text-destructive">
          {problem}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" loading={pending}>
          {t("business.faqs.save")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          {t("business.section.cancel")}
        </Button>
      </div>
    </form>
  );
}
