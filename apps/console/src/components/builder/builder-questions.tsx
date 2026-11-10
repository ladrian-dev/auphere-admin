"use client";

import { CircleCheck, Info, ListChecks } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Input, Label } from "@nexus/ui";

import { answerDraftJobAction } from "@/app/(console)/clients/[ref]/agents/builder-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AnswersResult, BuilderAnswer, BuilderQuestion, QuestionScope } from "@/lib/backend/builder-types";

import type { Result } from "./builder-model";

const REGISTERS = new Set(["tu", "usted", "vos"]);

/** El trato llega como código (`tu`, `usted`): se enseña con palabras y se manda tal cual. */
function optionLabel(target: string, option: string, t: (key: MessageKey) => string): string {
  return target === "/voice/register" && REGISTERS.has(option) ? t(`builder.register.${option}` as MessageKey) : option;
}

/** Las preguntas que dejó el borrador de «Nuevo agente», tal como las devolvió su trabajo. */
export type PendingQuestionsView = {
  job: string;
  questions: BuilderQuestion[];
  /** Cuántas descartó y por qué; nunca una cifra fija (17.4). */
  discarded: { count: number; reasons: string[] };
};

export type AnswerQuestion = (body: { ref: string; job: string; answers: BuilderAnswer[] }) => Promise<Result<AnswersResult>>;

export const answerQuestion: AnswerQuestion = (body) => answerDraftJobAction(body);

type Answered = Record<string, { value: string; scope: QuestionScope }>;

/** Lo respondido se recuerda en esta pestaña del navegador: al recargar no se vuelve a preguntar. */
const memoryKey = (job: string) => `nexus.agent-questions.${job}`;

function readMemory(job: string): string | null {
  try {
    return window.sessionStorage.getItem(memoryKey(job));
  } catch {
    return null;
  }
}

function parseMemory(raw: string | null): Answered {
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" ? (parsed as Answered) : {};
  } catch {
    return {};
  }
}

const noSubscribe = () => () => {};

function writeMemory(job: string, answered: Answered) {
  try {
    window.sessionStorage.setItem(memoryKey(job), JSON.stringify(answered));
  } catch {
    // Sin almacenamiento, la pantalla funciona igual: solo no lo recuerda al recargar.
  }
}

/**
 * Las preguntas que le faltan al borrador recién generado (spec 047, requisitos
 * 17.4 y 17.5), como el prototipo aprobado (`agente.md` §3.3): encima de la
 * tabla del agente, «Me faltan {n} datos», lo que se descartó y por qué, y cada
 * pregunta con su porqué, dónde se guarda su respuesta y sus opciones.
 *
 * Se responden una a una y en el sitio: elegir una opción la guarda al momento
 * (`POST /console/jobs/{id}/answers` con esa sola respuesta y su `scope`); la
 * que no tiene opciones lleva su campo y «Guardar». Respondida, queda con su
 * respuesta y dónde se guardó. Un dato del negocio va a la ficha por defecto
 * («lo usarán todos sus agentes») y se puede quedar en «Solo este agente».
 *
 * No hay «Cambiar»: la API añade una regla o una pregunta frecuente por cada
 * respuesta, y responder dos veces la duplicaría. Lo respondido se cambia en su
 * fila de la tabla. Nunca se nombra al constructor.
 */
export function PendingQuestions({
  refId,
  view,
  canWrite,
  answer = answerQuestion,
  onAnswered,
  onPending,
}: {
  refId: string;
  view: PendingQuestionsView;
  canWrite: boolean;
  answer?: AnswerQuestion;
  /** Una respuesta guardada: el borrador cambió y hay que volver a leerlo. */
  onAnswered?: () => void;
  /** Cuántas quedan sin responder, para la barra flotante. */
  onPending?: (n: number) => void;
}) {
  const t = useT();
  const titleId = React.useId();
  const questions = view.questions;
  // Lo que ya se respondió en esta pestaña (al recargar la página) y lo de ahora.
  const remembered = React.useSyncExternalStore(
    noSubscribe,
    () => readMemory(view.job),
    () => null,
  );
  const [fresh, setAnswered] = React.useState<Answered>({});
  const answered = React.useMemo(() => ({ ...parseMemory(remembered), ...fresh }), [remembered, fresh]);
  const [agentOnly, setAgentOnly] = React.useState<Record<string, boolean>>({});
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState<{ id: string; value: string } | null>(null);
  const [errors, setErrors] = React.useState<Record<string, string | undefined>>({});
  const [said, setSaid] = React.useState("");

  const pending = questions.filter((q) => !answered[q.id]).length;
  React.useEffect(() => {
    onPending?.(pending);
  }, [pending, onPending]);

  function scopeOf(q: BuilderQuestion): QuestionScope {
    if (q.scope === "agent") return "agent";
    return q.can_be_agent_only && agentOnly[q.id] ? "agent" : "business";
  }

  async function save(q: BuilderQuestion, raw: string) {
    const value = raw.trim();
    if (!value || busy) return;
    setBusy({ id: q.id, value });
    setErrors((prev) => ({ ...prev, [q.id]: undefined }));
    const scope = scopeOf(q);
    const res = await answer({ ref: refId, job: view.job, answers: [{ question_id: q.id, value, scope }] });
    setBusy(null);
    if (!res.ok) {
      setErrors((prev) => ({
        ...prev,
        [q.id]:
          res.code === "invalid_answer" || res.code === "unknown_question"
            ? t("builder.questions.invalid")
            : res.status === 401 || res.status === 403
              ? t("common.forbidden")
              : t("builder.questions.error"),
      }));
      return;
    }
    const where = res.data.applied.find((a) => a.question_id === q.id)?.scope ?? scope;
    const next = { ...answered, [q.id]: { value, scope: where } };
    setAnswered(next);
    writeMemory(view.job, next);
    setSaid(`${q.text} ${summary(q, value, where)}`);
    onAnswered?.();
    if (questions.every((x) => next[x.id])) {
      toast.success(t("agentProto.q.toast"), {
        action: {
          label: t("agentProto.q.try"),
          // El chat de prueba está en la columna de al lado: se escribe ahí.
          onClick: () => document.querySelector<HTMLInputElement>("[data-slot=playground-form] input")?.focus(),
        },
      });
    }
  }

  function summary(q: BuilderQuestion, value: string, scope: QuestionScope): string {
    return `${optionLabel(q.target, value, t)} · ${scope === "business" ? t("agentProto.q.saved.business") : t("agentProto.q.saved.agent")}`;
  }

  const total = questions.length + view.discarded.count;
  const reasons = view.discarded.reasons.filter((r) => r.trim());

  return (
    <section aria-labelledby={titleId} className="grid min-w-0 gap-3" data-slot="pending-questions">
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id={titleId} className="text-base font-semibold text-balance">
          {pending === 0
            ? t("agentProto.q.allDone")
            : pending === 1
              ? t("agentProto.q.missing.one")
              : t("agentProto.q.missing.other", { n: pending })}
        </h2>
        <span className="text-xs text-muted-foreground">{t("agentProto.q.note")}</span>
      </div>

      {view.discarded.count > 0 ? (
        <div className="flex min-w-0 items-start gap-3 rounded-md bg-muted px-3 py-3 text-sm text-muted-foreground" data-slot="questions-validated">
          <ListChecks aria-hidden="true" className="mt-px size-4 shrink-0" />
          <div className="grid min-w-0 gap-1">
            <p className="text-pretty">
              {view.discarded.count === 1
                ? t("agentProto.q.validated.one", { total })
                : t("agentProto.q.validated.other", { total, n: view.discarded.count })}
              {reasons.length ? ":" : "."}
            </p>
            {reasons.length ? (
              <ul className="grid min-w-0 list-disc gap-1 pl-5">
                {reasons.map((reason) => (
                  <li key={reason} className="text-pretty break-words">
                    {reason}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
      ) : null}

      {questions.map((q) => {
        const done = answered[q.id];
        if (done) {
          return (
            <div key={q.id} className="grid min-w-0 gap-1 rounded-lg border border-border bg-card px-4 py-3" data-question={q.id} data-answered="true">
              <p className="text-xs text-pretty break-words text-muted-foreground">{q.text}</p>
              <p className="flex min-w-0 items-start gap-2 text-sm">
                <CircleCheck aria-hidden="true" className="mt-px size-4 shrink-0 text-status-positive-text" />
                <span className="min-w-0 text-pretty break-words">{summary(q, done.value, done.scope)}</span>
              </p>
            </div>
          );
        }
        return (
          <Question
            key={q.id}
            question={q}
            scope={scopeOf(q)}
            agentOnly={Boolean(agentOnly[q.id])}
            value={values[q.id] ?? ""}
            busy={busy?.id === q.id ? busy.value : null}
            locked={busy !== null || !canWrite}
            error={errors[q.id]}
            onAgentOnly={(v) => setAgentOnly((prev) => ({ ...prev, [q.id]: v }))}
            onValue={(v) => setValues((prev) => ({ ...prev, [q.id]: v }))}
            onSave={(v) => void save(q, v)}
          />
        );
      })}
      <p role="status" className="sr-only">
        {said}
      </p>
    </section>
  );
}

/** Una pregunta sin responder (§3.3, `.q`): su porqué, dónde se guarda y sus opciones o su campo. */
function Question({
  question: q,
  scope,
  agentOnly,
  value,
  busy,
  locked,
  error,
  onAgentOnly,
  onValue,
  onSave,
}: {
  question: BuilderQuestion;
  scope: QuestionScope;
  agentOnly: boolean;
  value: string;
  /** La respuesta que se está guardando, si es de esta pregunta. */
  busy: string | null;
  locked: boolean;
  error?: string;
  onAgentOnly: (value: boolean) => void;
  onValue: (value: string) => void;
  onSave: (value: string) => void;
}) {
  const t = useT();
  const base = React.useId();
  const textId = `${base}-text`;
  const whyId = `${base}-why`;
  const savesId = `${base}-saves`;
  const errorId = `${base}-error`;
  const options = q.options?.filter((o) => o.trim()) ?? [];

  return (
    <div
      role="group"
      aria-labelledby={textId}
      aria-describedby={[whyId, savesId, error ? errorId : null].filter(Boolean).join(" ")}
      className="grid min-w-0 gap-3 rounded-lg border border-warning/50 bg-card px-4 py-3"
      data-slot="builder-question"
      data-question={q.id}
    >
      <p id={textId} className="text-sm font-medium text-pretty break-words">
        {q.text}
      </p>
      <p id={whyId} className="flex min-w-0 items-start gap-2 text-sm text-muted-foreground">
        <Info aria-hidden="true" className="mt-px size-4 shrink-0" />
        <span className="min-w-0 text-pretty break-words">{q.why}</span>
      </p>
      <div className="grid min-w-0 gap-2">
        <p id={savesId} className="text-xs text-pretty" data-slot="question-saves">
          {scope === "business" ? t("builder.questions.saves.business") : t("builder.questions.saves.agent")}
        </p>
        {q.scope === "business" && q.can_be_agent_only ? (
          <label className="inline-flex min-h-6 w-fit cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={agentOnly} disabled={locked} onChange={(e) => onAgentOnly(e.target.checked)} />
            {t("builder.questions.agentOnly")}
          </label>
        ) : null}
      </div>
      {options.length ? (
        <div className="flex min-w-0 flex-wrap gap-2">
          {options.map((option) => (
            <Button
              key={option}
              type="button"
              size="sm"
              variant="outline"
              aria-pressed={busy === option}
              loading={busy === option}
              disabled={locked}
              onClick={() => onSave(option)}
              className="h-auto min-h-8 rounded-full py-1 text-left whitespace-normal aria-pressed:border-primary/50 aria-pressed:bg-primary/10"
            >
              {optionLabel(q.target, option, t)}
            </Button>
          ))}
        </div>
      ) : (
        <form
          className="grid min-w-0 gap-1"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            onSave(value);
          }}
        >
          <Label htmlFor={`${base}-input`}>{t("builder.questions.answer")}</Label>
          <div className="flex min-w-0 gap-2">
            <Input
              id={`${base}-input`}
              value={value}
              maxLength={1000}
              autoComplete="off"
              readOnly={locked}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : undefined}
              onChange={(e) => onValue(e.target.value)}
              className="min-w-0 flex-1"
            />
            <Button type="submit" loading={busy !== null} disabled={locked || !value.trim()} className="shrink-0">
              {t("builder.edit.save")}
            </Button>
          </div>
        </form>
      )}
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-pretty text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
