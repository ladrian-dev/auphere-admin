"use client";

import * as React from "react";

import { Button, Input, Label } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { BuilderAnswer, BuilderQuestion, QuestionScope } from "@/lib/backend/builder-types";

const REGISTERS = new Set(["tu", "usted", "vos"]);

/** El trato llega como código (`tu`, `usted`): se enseña con palabras y se manda tal cual. */
function optionLabel(target: string, option: string, t: (key: MessageKey) => string): string {
  return target === "/voice/register" && REGISTERS.has(option) ? t(`builder.register.${option}` as MessageKey) : option;
}

type Props = {
  questions: readonly BuilderQuestion[];
  busy: boolean;
  /** La pregunta que la API rechazó (`invalid_answer`), si dijo cuál. */
  invalid?: string | null;
  error?: string | null;
  onSubmit: (answers: BuilderAnswer[]) => void;
  onSkip: () => void;
};

/**
 * Las preguntas del constructor (spec 047, requisitos 17.4 y 17.5): como mucho
 * cinco, cada una con su porqué y con respuestas cerradas cuando las hay.
 *
 * Cada una DICE dónde se guarda su respuesta. Un dato del negocio va a la ficha
 * por defecto («lo usarán todos sus agentes») y se puede quedar en «Solo este
 * agente»; lo que es del agente se guarda en él. Se mandan solo las que tienen
 * respuesta, cada una con su `scope`. Lo que no se responde se completa después.
 */
export function BuilderQuestions({ questions, busy, invalid, error, onSubmit, onSkip }: Props) {
  const t = useT();
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [agentOnly, setAgentOnly] = React.useState<Record<string, boolean>>({});
  const [empty, setEmpty] = React.useState(false);
  const titleId = React.useId();

  function scopeOf(q: BuilderQuestion): QuestionScope {
    if (q.scope === "agent") return "agent";
    return q.can_be_agent_only && agentOnly[q.id] ? "agent" : "business";
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const answers = questions.flatMap((q) => {
      const value = (values[q.id] ?? "").trim();
      return value ? [{ question_id: q.id, value, scope: scopeOf(q) }] : [];
    });
    if (!answers.length) {
      setEmpty(true);
      return;
    }
    setEmpty(false);
    onSubmit(answers);
  }

  return (
    <form onSubmit={submit} aria-labelledby={titleId} className="grid min-w-0 gap-4" data-slot="builder-questions" noValidate>
      <div className="grid min-w-0 gap-1">
        <h4 id={titleId} className="text-base font-semibold text-balance">
          {t("builder.questions.title")}
        </h4>
        <p className="text-sm text-pretty text-muted-foreground">{t("builder.questions.intro")}</p>
      </div>
      {questions.map((q, i) => (
        <QuestionField
          key={q.id}
          index={i}
          question={q}
          value={values[q.id] ?? ""}
          agentOnly={Boolean(agentOnly[q.id])}
          scope={scopeOf(q)}
          invalid={invalid === q.id}
          onValue={(v) => setValues((prev) => ({ ...prev, [q.id]: v }))}
          onAgentOnly={(v) => setAgentOnly((prev) => ({ ...prev, [q.id]: v }))}
        />
      ))}
      {empty ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {t("builder.questions.required")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={busy}>
          {t("builder.questions.save")}
        </Button>
        <Button type="button" variant="outline" onClick={onSkip} disabled={busy}>
          {t("builder.questions.skip")}
        </Button>
      </div>
    </form>
  );
}

function QuestionField({
  index,
  question: q,
  value,
  agentOnly,
  scope,
  invalid,
  onValue,
  onAgentOnly,
}: {
  index: number;
  question: BuilderQuestion;
  value: string;
  agentOnly: boolean;
  scope: QuestionScope;
  invalid: boolean;
  onValue: (value: string) => void;
  onAgentOnly: (value: boolean) => void;
}) {
  const t = useT();
  const base = React.useId();
  const whyId = `${base}-why`;
  const savesId = `${base}-saves`;
  const errorId = `${base}-error`;
  const describedBy = [whyId, savesId, invalid ? errorId : null].filter(Boolean).join(" ");
  const options = q.options?.filter((o) => o.trim()) ?? [];

  return (
    <div className="min-w-0 rounded-md border border-border p-3" data-slot="builder-question" data-question={q.id}>
      <fieldset className="grid min-w-0 gap-3" aria-describedby={describedBy}>
        <legend className="mb-1 text-sm font-medium text-pretty break-words">
          <span className="text-muted-foreground tabular-nums">{index + 1}. </span>
          {q.text}
        </legend>
        <p id={whyId} className="text-xs text-pretty text-muted-foreground">
          {t("builder.questions.why", { why: q.why })}
        </p>
        {options.length ? (
          <div className="grid min-w-0 gap-2">
            {options.map((option) => (
              <label key={option} className="flex min-h-6 min-w-0 cursor-pointer items-start gap-2 text-sm">
                <input
                  type="radio"
                  name={`${base}-answer`}
                  value={option}
                  checked={value === option}
                  onChange={() => onValue(option)}
                  className="mt-1 size-4 shrink-0 accent-primary"
                />
                <span className="min-w-0 text-pretty break-words">{optionLabel(q.target, option, t)}</span>
              </label>
            ))}
          </div>
        ) : (
          <div className="grid min-w-0 gap-1">
            <Label htmlFor={`${base}-input`}>{t("builder.questions.answer")}</Label>
            <Input
              id={`${base}-input`}
              value={value}
              maxLength={1000}
              onChange={(e) => onValue(e.target.value)}
              aria-describedby={describedBy}
              aria-invalid={invalid || undefined}
              autoComplete="off"
            />
          </div>
        )}
        <div className="grid min-w-0 gap-2">
          <p id={savesId} className="text-xs text-pretty" data-slot="question-saves">
            {scope === "business" ? t("builder.questions.saves.business") : t("builder.questions.saves.agent")}
          </p>
          {q.scope === "business" && q.can_be_agent_only ? (
            <label className="inline-flex min-h-6 w-fit cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" className="size-4 accent-primary" checked={agentOnly} onChange={(e) => onAgentOnly(e.target.checked)} />
              {t("builder.questions.agentOnly")}
            </label>
          ) : null}
        </div>
        {invalid ? (
          <p id={errorId} role="alert" className="text-xs text-destructive text-pretty">
            {t("builder.questions.invalid")}
          </p>
        ) : null}
      </fieldset>
    </div>
  );
}
