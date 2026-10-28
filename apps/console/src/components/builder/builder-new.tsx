"use client";

import { LayoutTemplate, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Field, Input, StatusDot, Textarea, buttonVariants, formatNumber } from "@nexus/ui";

import { answerDraftJobAction, draftJobAction, startDraftJobAction } from "@/app/(console)/clients/[ref]/agents/builder-actions";
import { agentHref } from "@/components/shell/routes-v2";
import { useLocale, useT } from "@/i18n/client";
import type {
  AnswersResult,
  BuilderAnswer,
  DraftJob,
  DraftJobAccepted,
  DraftJobBody,
  DraftOptions,
  TemplateOption,
} from "@/lib/backend/builder-types";
import { BUILDER_BLOCKS } from "@/lib/backend/builder-types";

import { BlockValue, blockTitleKey } from "./block-view";
import { BuilderQuestions } from "./builder-questions";
import {
  LIMITS,
  POLL_FIRST_MS,
  arrivedBlocks,
  cleanName,
  describeProblems,
  groupTemplates,
  nextDelay,
  sleep,
  type Result,
} from "./builder-model";

export type BuilderActions = {
  start: (body: { ref: string } & DraftJobBody) => Promise<Result<DraftJobAccepted>>;
  poll: (body: { ref: string; job: string }) => Promise<Result<DraftJob>>;
  answer: (body: { ref: string; job: string; answers: BuilderAnswer[] }) => Promise<Result<AnswersResult>>;
};

const SERVER_ACTIONS: BuilderActions = {
  start: (body) => startDraftJobAction(body),
  poll: (body) => draftJobAction(body),
  answer: (body) => answerDraftJobAction(body),
};

type Phase = "idle" | "starting" | "building" | "done" | "failed";
type Failure = "unavailable" | "other";
type Errors = { name?: string; description?: string; template?: string; form?: string };

/**
 * «Nuevo agente» (spec 047, historia 7; requisitos 17.1–17.9 y 15.8): una sola
 * pantalla. A la izquierda, la descripción —el nombre (1 a 40), «¿Qué tiene que
 * hacer?» (20 a 1.024) con sus contadores y los ejemplos para empezar— y las
 * alternativas: «Empezar desde una plantilla» (por grupos, la del partner
 * primero y sin elegir sola) y «En blanco». A la derecha, el borrador: los
 * bloques van apareciendo en orden según los cuenta el trabajo, y al terminar,
 * las preguntas que quedan (cada una dice dónde se guarda), las descartadas con
 * su porqué y, en la fila de cada habilidad, «Conectar {conector}».
 *
 * El agente nace al terminar el primer borrador, no al abrir esta pantalla
 * (17.2). Si el constructor no responde, se ofrecen la plantilla y el blanco
 * sin perder lo escrito. Al terminar, se va a la pantalla del agente.
 */
export function BuilderNew({
  refId,
  options,
  initial,
  actions = SERVER_ACTIONS,
  wait = sleep,
}: {
  refId: string;
  /** Lo que trae «Crear este agente» del constructor del cliente (18.4): se rellena, no se crea. */
  initial?: { name?: string; description?: string };
  /** `null` si `draft-options` no respondió: sin ejemplos ni plantillas, con los límites de siempre. */
  options: DraftOptions | null;
  actions?: BuilderActions;
  wait?: (ms: number) => Promise<void>;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const limits = options ?? LIMITS;
  const base = React.useId();
  const nameRef = React.useRef<HTMLInputElement>(null);
  const descriptionRef = React.useRef<HTMLTextAreaElement>(null);
  const templatesRef = React.useRef<HTMLFieldSetElement>(null);
  const progressRef = React.useRef<HTMLElement>(null);

  const [name, setName] = React.useState(() => (initial?.name ?? "").slice(0, limits.name_max));
  const [description, setDescription] = React.useState(() => (initial?.description ?? "").slice(0, limits.description_max));
  const [errors, setErrors] = React.useState<Errors>({});
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [failure, setFailure] = React.useState<Failure | null>(null);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [job, setJob] = React.useState<DraftJob | null>(null);
  const [showTemplates, setShowTemplates] = React.useState(false);
  const [templateId, setTemplateId] = React.useState<string | null>(null);
  const [alt, setAlt] = React.useState<"template" | "blank" | null>(null);
  const [answering, setAnswering] = React.useState(false);
  const [answerError, setAnswerError] = React.useState<string | null>(null);
  const [invalidQuestion, setInvalidQuestion] = React.useState<string | null>(null);

  const locked = phase === "starting" || phase === "building" || phase === "done" || alt !== null;
  const nameMax = limits.name_max;
  const nameError = () => t("builder.new.error.name", { max: nameMax });
  const descriptionError = () =>
    t("builder.new.error.description", { min: limits.description_min, max: formatNumber(limits.description_max, locale) });

  const goToAgent = React.useCallback((agentId: string) => router.push(agentHref(refId, agentId)), [router, refId]);

  /** Lo que dijo la API al empezar, en palabras y junto a su campo. */
  const startFailed = React.useCallback(
    (res: Extract<Result<unknown>, { ok: false }>) => {
      if (res.code === "name_taken") setErrors({ name: t("builder.new.error.name_taken") });
      else if (res.code === "name_length") setErrors({ name: t("builder.new.error.name", { max: nameMax }) });
      else if (res.code === "description_length")
        setErrors({ description: t("builder.new.error.description", { min: limits.description_min, max: formatNumber(limits.description_max, locale) }) });
      else if (res.code === "template_required") setErrors({ template: t("builder.alt.templates.required") });
      // Spec 047 (46.5): sin partida de construcción no se construye; se dice dónde pedir más.
      else if (res.code === "build_budget_exhausted" || res.status === 402) setErrors({ form: t("money.build.blocked") });
      else if (res.status === 401 || res.status === 403) setErrors({ form: t("common.forbidden") });
      else setErrors({ form: t("builder.new.error.generic") });
    },
    [t, nameMax, limits.description_min, limits.description_max, locale],
  );

  // La espera creciente (1, 2, 4… 10 s) mientras el trabajo escribe; vuelve a
  // 1 s cada vez que llega un bloque. Se para al terminar o al fallar.
  React.useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    void (async () => {
      let delay = POLL_FIRST_MS;
      let seen = 0;
      for (;;) {
        await wait(delay);
        if (cancelled) return;
        const res = await actions.poll({ ref: refId, job: jobId });
        if (cancelled) return;
        if (!res.ok) {
          if (res.status === 401 || res.status === 403 || res.status === 404) {
            setFailure("other");
            setPhase("failed");
            return;
          }
          delay = nextDelay(delay, false);
          continue;
        }
        const current = res.data;
        setJob(current);
        if (current.status === "done") {
          setPhase("done");
          const agentId = current.result?.agent_id ?? current.agent_id;
          if (agentId && !(current.result?.questions?.length ?? 0)) goToAgent(agentId);
          return;
        }
        if (current.status === "failed") {
          const input = current.progress?.input;
          // 15.8: lo escrito sigue ahí, aunque la pantalla se hubiera vaciado.
          setName((prev) => prev || input?.name || "");
          setDescription((prev) => prev || input?.description || "");
          if (current.error_code === "name_taken" || current.error_code === "name_length" || current.error_code === "description_length") {
            startFailed({ ok: false, status: 422, message: "", code: current.error_code });
            setFailure(null);
            setPhase("idle");
            return;
          }
          const unavailable = current.error_code === "builder_unavailable";
          setFailure(unavailable ? "unavailable" : "other");
          if (unavailable) setShowTemplates(true);
          setPhase("failed");
          return;
        }
        const count = arrivedBlocks(current).length;
        delay = nextDelay(delay, count > seen);
        seen = count;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId, refId, actions, wait, goToAgent, startFailed]);

  function validate(needsDescription: boolean): boolean {
    const problems = describeProblems(name, description, limits);
    const next: Errors = {};
    if (problems.name) next.name = nameError();
    if (needsDescription && problems.description) next.description = descriptionError();
    setErrors(next);
    if (next.name) nameRef.current?.focus();
    else if (next.description) descriptionRef.current?.focus();
    return !next.name && !next.description;
  }

  async function generate(event: React.FormEvent) {
    event.preventDefault();
    if (locked || !validate(true)) return;
    setPhase("starting");
    setFailure(null);
    setJob(null);
    setJobId(null);
    const res = await actions.start({ ref: refId, name: cleanName(name), description: description.trim(), start: "describe" });
    if (!res.ok) {
      startFailed(res);
      setPhase("idle");
      return;
    }
    if (res.data.status === "done" && res.data.agent_id) {
      goToAgent(res.data.agent_id);
      return;
    }
    setPhase("building");
    setJobId(res.data.job_id);
    // En una columna, el borrador queda debajo de la descripción: que se vea llegar.
    progressRef.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }

  async function startFrom(start: "template" | "blank") {
    if (locked && phase !== "failed") return;
    if (!validate(false)) return;
    if (start === "template" && !templateId) {
      setErrors({ template: t("builder.alt.templates.required") });
      templatesRef.current?.querySelector<HTMLInputElement>("input[type=radio]")?.focus();
      return;
    }
    setAlt(start);
    const text = description.trim();
    const res = await actions.start({
      ref: refId,
      name: cleanName(name),
      start,
      ...(text.length >= limits.description_min && text.length <= limits.description_max ? { description: text } : {}),
      ...(start === "template" && templateId ? { template_id: templateId } : {}),
    });
    if (!res.ok) {
      setAlt(null);
      startFailed(res);
      return;
    }
    if (res.data.agent_id) {
      goToAgent(res.data.agent_id);
      return;
    }
    setAlt(null);
    setFailure(null);
    setPhase("building");
    setJobId(res.data.job_id);
  }

  async function answer(answers: BuilderAnswer[]) {
    if (!jobId) return;
    setAnswering(true);
    setAnswerError(null);
    setInvalidQuestion(null);
    const res = await actions.answer({ ref: refId, job: jobId, answers });
    setAnswering(false);
    if (res.ok) {
      toast.success(t("builder.questions.saved"));
      goToAgent(res.data.agent_id);
      return;
    }
    if (res.code === "invalid_answer" || res.code === "unknown_question") {
      const id = res.info?.question_id;
      setInvalidQuestion(typeof id === "string" ? id : null);
    }
    setAnswerError(res.status === 401 || res.status === 403 ? t("common.forbidden") : t("builder.questions.error"));
  }

  function pickExample(example: string) {
    setDescription(example.slice(0, limits.description_max));
    setErrors((prev) => ({ ...prev, description: undefined }));
    descriptionRef.current?.focus();
  }

  function openTemplates() {
    setShowTemplates(true);
    requestAnimationFrame(() => templatesRef.current?.querySelector<HTMLInputElement>("input[type=radio]")?.focus());
  }

  const blocks = arrivedBlocks(job);
  const result = phase === "done" ? job?.result ?? null : null;
  const agentId = result?.agent_id ?? job?.agent_id ?? null;
  const templates = options?.templates ?? [];
  const nameLen = cleanName(name).length;
  const descLen = description.trim().length;

  return (
    <div className="grid min-w-0 gap-6" data-slot="builder-new">
      <div className="grid min-w-0 gap-1">
        <h2 className="text-xl font-semibold text-balance">{t("builder.new.title")}</h2>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("builder.new.intro")}</p>
      </div>

      <div className="grid min-w-0 gap-6 lg:grid-cols-2 lg:items-start">
        {/* ── la descripción ── */}
        <section aria-labelledby={`${base}-describe`} className="grid min-w-0 gap-4 rounded-md border border-border bg-card p-4 sm:p-6">
          <h3 id={`${base}-describe`} className="text-base font-semibold">
            {t("builder.new.describe")}
          </h3>
          <form onSubmit={generate} className="grid min-w-0 gap-4" noValidate>
            <Field label={t("builder.new.name")} hint={t("builder.new.name.hint")} error={errors.name} required>
              {(a11y) => (
                <div className="grid min-w-0 gap-1">
                  <Input
                    {...a11y}
                    ref={nameRef}
                    value={name}
                    maxLength={nameMax}
                    readOnly={locked}
                    autoComplete="off"
                    onChange={(e) => {
                      setName(e.target.value);
                      if (errors.name) setErrors((prev) => ({ ...prev, name: undefined }));
                    }}
                  />
                  <Counter n={nameLen} max={nameMax} />
                </div>
              )}
            </Field>
            <Field
              label={t("builder.new.description")}
              hint={t("builder.new.description.hint", { min: limits.description_min, max: formatNumber(limits.description_max, locale) })}
              error={errors.description}
              required
            >
              {(a11y) => (
                <div className="grid min-w-0 gap-1">
                  <Textarea
                    {...a11y}
                    ref={descriptionRef}
                    value={description}
                    rows={6}
                    maxLength={limits.description_max}
                    readOnly={locked}
                    onChange={(e) => {
                      setDescription(e.target.value);
                      if (errors.description) setErrors((prev) => ({ ...prev, description: undefined }));
                    }}
                  />
                  <Counter n={descLen} max={limits.description_max} />
                </div>
              )}
            </Field>

            {options?.examples.length && !locked ? (
              <div className="grid min-w-0 gap-2">
                <p className="text-sm font-medium" id={`${base}-examples`}>
                  {t("builder.new.examples")}
                </p>
                <p className="text-xs text-pretty text-muted-foreground">{t("builder.new.examples.hint")}</p>
                <ul aria-labelledby={`${base}-examples`} className="grid min-w-0 gap-2">
                  {options.examples.map((example) => (
                    <li key={example} className="min-w-0">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => pickExample(example)}
                        className="h-auto min-h-8 w-full justify-start py-2 text-left whitespace-normal"
                      >
                        <span className="min-w-0 text-pretty">{example}</span>
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {errors.form ? (
              <p role="alert" className="text-sm text-destructive text-pretty">
                {errors.form}
              </p>
            ) : null}

            {phase !== "done" ? (
              <div>
                <Button type="submit" loading={phase === "starting" || phase === "building"} disabled={alt !== null}>
                  <Sparkles aria-hidden="true" />
                  {t("builder.new.generate")}
                </Button>
              </div>
            ) : null}
          </form>

          {phase !== "done" && phase !== "building" && phase !== "starting" ? (
            <div className="grid min-w-0 gap-3 border-t border-border pt-4" data-slot="builder-alternatives">
              <p className="text-sm font-medium">{t("builder.alt.title")}</p>
              <div className="flex min-w-0 flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  aria-expanded={showTemplates}
                  aria-controls={`${base}-templates`}
                  onClick={() => (showTemplates ? setShowTemplates(false) : openTemplates())}
                  disabled={alt !== null}
                >
                  <LayoutTemplate aria-hidden="true" />
                  {t("builder.alt.template")}
                </Button>
                <Button type="button" variant="outline" onClick={() => void startFrom("blank")} loading={alt === "blank"} disabled={alt === "template"}>
                  {t("builder.alt.blank")}
                </Button>
              </div>
              <p className="text-xs text-pretty text-muted-foreground">{t("builder.alt.blank.hint")}</p>
              {showTemplates ? (
                <div id={`${base}-templates`} className="grid min-w-0 gap-3">
                  {options === null ? (
                    <p className="text-sm text-pretty text-muted-foreground">{t("builder.alt.templates.error")}</p>
                  ) : !templates.length ? (
                    <p className="text-sm text-pretty text-muted-foreground">{t("builder.alt.templates.none")}</p>
                  ) : (
                    <>
                      <TemplatePicker
                        ref={templatesRef}
                        templates={templates}
                        value={templateId}
                        error={errors.template}
                        onChange={(id) => {
                          setTemplateId(id);
                          setErrors((prev) => ({ ...prev, template: undefined }));
                        }}
                      />
                      <div>
                        <Button type="button" onClick={() => void startFrom("template")} loading={alt === "template"} disabled={alt === "blank"}>
                          {t("builder.alt.templates.create")}
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              ) : null}
            </div>
          ) : null}
        </section>

        {/* ── el borrador que llega ── */}
        <section
          ref={progressRef}
          aria-labelledby={`${base}-progress`}
          className="grid min-w-0 gap-4 rounded-md border border-border bg-card p-4 sm:p-6"
          data-slot="builder-progress"
        >
          <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
            <h3 id={`${base}-progress`} className="text-base font-semibold">
              {t("builder.progress.title")}
            </h3>
            {phase === "done" && agentId ? (
              <Link href={agentHref(refId, agentId)} className={buttonVariants({ size: "sm", variant: "outline" })}>
                {t("builder.progress.open")}
              </Link>
            ) : null}
          </div>

          <p role="status" className="inline-flex min-w-0 items-center gap-2 text-sm text-pretty text-muted-foreground" data-slot="builder-status">
            {phase === "starting" || phase === "building" ? <StatusDot tone="info" pulse /> : null}
            <span className="min-w-0">{statusText(phase, job, blocks.length, t)}</span>
          </p>

          {phase === "failed" ? (
            <Callout
              tone="warning"
              title={failure === "unavailable" ? t("builder.progress.failed.title") : undefined}
              action={
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="outline" onClick={openTemplates}>
                    {t("builder.alt.template")}
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={() => void startFrom("blank")} loading={alt === "blank"}>
                    {t("builder.alt.blank")}
                  </Button>
                </div>
              }
            >
              {failure === "unavailable" ? t("builder.progress.failed.body") : t("builder.progress.failed.other")}
            </Callout>
          ) : null}

          {blocks.length ? (
            <ol aria-label={t("builder.progress.blocks")} className="grid min-w-0 gap-3" data-slot="builder-blocks">
              {blocks.map((block) => (
                <li key={block.key} className="grid min-w-0 gap-2 border-l-2 border-primary/40 pl-3" data-block={block.key}>
                  <h4 className="text-sm font-semibold">{t(blockTitleKey(block.key))}</h4>
                  <BlockValue block={block} refId={refId} />
                </li>
              ))}
            </ol>
          ) : null}

          {result && result.discarded.count > 0 ? (
            <div className="grid min-w-0 gap-1 text-sm" data-slot="builder-discarded">
              <p className="text-pretty">
                {result.discarded.count === 1 ? t("builder.discarded.one") : t("builder.discarded.other", { n: result.discarded.count })}
                {result.discarded.reasons.length ? ":" : "."}
              </p>
              {result.discarded.reasons.length ? (
                <ul className="grid min-w-0 list-disc gap-1 pl-5 text-muted-foreground">
                  {result.discarded.reasons.map((reason) => (
                    <li key={reason} className="text-pretty">
                      {reason}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {result && result.questions.length && agentId ? (
            <BuilderQuestions
              questions={result.questions.slice(0, 5)}
              busy={answering}
              invalid={invalidQuestion}
              error={answerError}
              onSubmit={(answers) => void answer(answers)}
              onSkip={() => goToAgent(agentId)}
            />
          ) : null}
        </section>
      </div>
    </div>
  );
}

function statusText(phase: Phase, job: DraftJob | null, arrived: number, t: ReturnType<typeof useT>): string {
  if (phase === "idle") return t("builder.progress.idle");
  if (phase === "done") return t("builder.progress.done");
  if (phase === "failed") return "";
  if (job?.progress?.step === "writing" || arrived > 0) return t("builder.progress.writing", { n: arrived, total: BUILDER_BLOCKS.length });
  if (job?.progress?.step === "reading" || job?.status === "running") return t("builder.progress.reading");
  return t("builder.progress.queued");
}

function Counter({ n, max }: { n: number; max: number }) {
  const t = useT();
  const locale = useLocale();
  return (
    <span className="justify-self-end text-xs text-muted-foreground tabular-nums" aria-hidden="true">
      {t("builder.new.count", { n: formatNumber(n, locale), max: formatNumber(max, locale) })}
    </span>
  );
}

/** Las plantillas por grupo de negocio; la del partner, la primera y sin elegir (17.9). */
const TemplatePicker = React.forwardRef<
  HTMLFieldSetElement,
  { templates: readonly TemplateOption[]; value: string | null; error?: string; onChange: (id: string) => void }
>(function TemplatePicker({ templates, value, error, onChange }, ref) {
  const t = useT();
  const base = React.useId();
  const errorId = `${base}-error`;
  return (
    <fieldset ref={ref} className="grid min-w-0 gap-3" aria-describedby={error ? errorId : undefined} data-slot="builder-templates">
      <legend className="mb-1 text-sm font-medium">{t("builder.alt.templates")}</legend>
      {groupTemplates(templates).map((g) => (
        <fieldset key={g.group} className="grid min-w-0 gap-2">
          <legend className="mb-1 text-xs font-medium text-muted-foreground">{g.group}</legend>
          {g.items.map((tpl) => (
            <label key={tpl.id} className="flex min-h-6 min-w-0 cursor-pointer items-start gap-2 text-sm">
              <input
                type="radio"
                name={`${base}-template`}
                value={tpl.id}
                checked={value === tpl.id}
                onChange={() => onChange(tpl.id)}
                className="mt-1 size-4 shrink-0 accent-primary"
              />
              <span className="min-w-0 text-pretty break-words">
                {tpl.is_default ? t("builder.alt.templates.default", { name: tpl.name }) : tpl.name}
              </span>
            </label>
          ))}
        </fieldset>
      ))}
      {error ? (
        <p id={errorId} role="alert" className="text-xs text-destructive text-pretty">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
});
