"use client";

import { CircleAlert, CircleCheck, CircleDashed, CirclePlay, FlaskConical, LoaderCircle, WandSparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button, Callout, Field, Input, Label, StatusBadge, Switch, Tabs, TabsContent, TabsList, TabsTrigger, Textarea, cn, formatNumber } from "@nexus/ui";

import { answerDraftJobAction, draftJobAction, startDraftJobAction } from "@/app/(console)/clients/[ref]/agents/builder-actions";
import { ReservasFields } from "@/components/clients/access/reservas-fields";
import { agentHref } from "@/components/shell/routes-v2";
import { ShellBackButton } from "@/components/shell/shell-back-button";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type {
  AnswersResult,
  BuilderAnswer,
  DraftJob,
  DraftJobAccepted,
  DraftJobBody,
  DraftOptions,
  TemplateOption,
} from "@/lib/backend/builder-types";
import type { CapacityKind, ReservasMode } from "@/lib/backend/client-access";

import {
  LIMITS,
  POLL_FIRST_MS,
  agendaSuggested,
  arrivedBlocks,
  caseTests,
  cleanName,
  describeProblems,
  draftSteps,
  groupTemplates,
  nextDelay,
  sleep,
  withExample,
  type Result,
  type StepState,
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
/** `facts`: la ficha del negocio no se pudo leer (65.12); sin ella no hay borrador ni plantilla. */
type Failure = "unavailable" | "facts" | "other";
/** `agenda`: lo que dijo la API al encender Reservas (spec 057, 1.5), junto a «Gestiona citas». */
type Errors = { name?: string; description?: string; template?: string; form?: string; agenda?: string };

/** Spec 057 (1.5; `console-api.md` §2): lo que puede fallar al encender Reservas desde el alta. */
const AGENDA_ERRORS: ReadonlySet<string> = new Set(["reservas_mode_required", "reservas_kind_required", "reservas_kind_forbidden", "archived", "no_partner"]);

/** Los cuatro ejemplos del prototipo (§3.1), con textos generales: ni negocios ni personas concretas. */
const EXAMPLES = ["reception", "sales", "support", "billing"] as const;

/** La barra flotante de vidrio: las mismas clases que en la pantalla del agente (§4.5). */
const BAR =
  "glass sticky bottom-4 z-(--z-sticky) min-w-0 rounded-xl p-3 ring-1 ring-foreground/10 min-[560px]:rounded-full min-[560px]:py-2 min-[560px]:pr-2 min-[560px]:pl-4";
const LINK = "cursor-pointer font-medium text-primary-text underline underline-offset-4 hover:no-underline disabled:cursor-default disabled:opacity-50";

/**
 * «Nuevo agente» (spec 047, historia 7; requisitos 17.1–17.9 y 15.8) como el
 * prototipo aprobado (`specs/047-…/evidence/prototipo/agente.md` §3 y hueco H7):
 * la misma pantalla del agente —«Nuevo agente», «Borrador · de {cliente}», sus
 * pestañas (Canales y Conectores llegan cuando el agente exista), dos columnas
 * y la barra de vidrio abajo—.
 *
 * - **Describir** (§3.1): a la izquierda el nombre, «¿Qué tiene que hacer?» y
 *   cuatro ejemplos que se añaden a ella (y el nombre, si está vacío); debajo, discreto,
 *   «Otras formas de empezar»: una plantilla (por grupos, la del partner primero y
 *   sin elegir sola) o en blanco (17.8, 17.9). A la derecha, «Probar el agente ·
 *   Aún no». La barra dice qué falta y «Generar borrador» espera a que esté.
 * - **Preparando** (§3.2): cuatro pasos que siguen al trabajo de verdad, no a un
 *   reloj: leer la ficha (hasta que el trabajo pasa a escribir), proponer
 *   instrucciones y habilidades (hasta que llegan las pruebas), escribir las
 *   pruebas (hasta que llegan las preguntas, con cuántas son del caso) y validar
 *   las preguntas (hasta que termina). Lo que la consulta no llega a ver se marca
 *   hecho de una vez al terminar.
 * - **Listo** (§3.3): la pantalla del agente; si al borrador le faltan datos, con
 *   las preguntas encima de su tabla (`?job=`), que se responden una a una.
 *
 * El agente nace al terminar el primer borrador, no al abrir esta pantalla
 * (17.2). Si el borrador no se puede escribir, se ofrecen la plantilla y el
 * blanco sin perder lo escrito (15.8). Nunca se nombra al constructor.
 *
 * Enmienda del 2026-10-30 (T228; 65.12): si la ficha del negocio no se puede
 * leer (`facts_unavailable`: el trabajo falla, o 503 al empezar desde una
 * plantilla) no hay borrador. Se dice, sin perder lo escrito, con «Reintentar»
 * —que repite lo que se intentó, sin doble envío— y sin ofrecer «Desde una
 * plantilla», que también la lee. Si al borrador le falta algo que no tenemos,
 * la pantalla del agente se abre con su trabajo (`?job=`).
 *
 * Spec 057 (requisitos 1.1–1.3): «Gestiona citas» bajo «¿Qué tiene que hacer?»,
 * para las tres formas de empezar, solo si Reservas se ofrece al cliente (§V).
 * Mientras nadie lo toque, sigue a la descripción (`BOOKING_WORDS`) y a la
 * plantilla elegida (`books`), y dice por qué se encendió. Con Reservas apagado,
 * dice que generar lo encenderá y pide cómo reserva el negocio, con el modo de su
 * sector ya elegido. Lo que dice la API al encenderlo sale junto al interruptor,
 * sin navegar y sin perder lo escrito.
 */
export function BuilderNew({
  refId,
  options,
  initial,
  clientName = null,
  actions = SERVER_ACTIONS,
  wait = sleep,
}: {
  refId: string;
  /** Lo que trae «Crear este agente» del cliente (18.4): se rellena, no se crea. */
  initial?: { name?: string; description?: string };
  /** `null` si `draft-options` no respondió: sin plantillas, con los límites de siempre. */
  options: DraftOptions | null;
  /** El cliente: «de Flor y Encanto» bajo el título y «Leo la ficha de Flor y Encanto…». */
  clientName?: string | null;
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
  // Lo último que se intentó, para que «Reintentar» lo repita (65.12).
  const [lastStart, setLastStart] = React.useState<"describe" | "template">("describe");
  // Spec 057: «Gestiona citas». `null` mientras nadie lo toque: entonces sigue a
  // la descripción y a la plantilla.
  const agendaOptions = options?.agenda?.offered ? options.agenda : null;
  const agendaRef = React.useRef<HTMLDivElement>(null);
  const [agendaTouched, setAgendaTouched] = React.useState<boolean | null>(null);
  const [reservasMode, setReservasMode] = React.useState<ReservasMode | null>(() => agendaOptions?.suggested_mode ?? null);
  const [reservasKind, setReservasKind] = React.useState<CapacityKind | null>(() =>
    agendaOptions?.suggested_mode === "capacity" ? (agendaOptions.suggested_kind ?? null) : null,
  );

  const preparing = phase === "starting" || phase === "building" || phase === "done";
  const locked = preparing || alt !== null;
  const chosenTemplate = showTemplates && templateId ? (options?.templates ?? []).find((tpl) => tpl.id === templateId) : null;
  const agendaWhy = agendaOptions ? agendaSuggested(description, chosenTemplate) : null;
  const agendaOn = agendaOptions ? (agendaTouched ?? agendaWhy !== null) : false;
  // Generar encenderá Reservas: hay que decir cómo reserva el negocio (1.3).
  const turnsOn = agendaOn && agendaOptions !== null && !agendaOptions.module_on;
  const nameMax = limits.name_max;
  const problems = describeProblems(name, description, limits);
  const ready = !problems.name && !problems.description;

  // Como el prototipo: el foco empieza en el nombre.
  React.useEffect(() => {
    nameRef.current?.focus();
  }, []);

  const goToAgent = React.useCallback(
    (agentId: string, job?: string) => router.push(job ? `${agentHref(refId, agentId)}?job=${encodeURIComponent(job)}` : agentHref(refId, agentId)),
    [router, refId],
  );

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
          // Con preguntas, la pantalla del agente las enseña encima de su tabla; con
          // lo que no tenemos (65.4), lee también lo que dejó el trabajo.
          const withJob = Boolean(current.result?.questions?.length || current.result?.missing_capabilities?.length);
          if (agentId) goToAgent(agentId, withJob ? current.job_id : undefined);
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
          if (current.error_code === "facts_unavailable") {
            // 65.12: sin la ficha no hay borrador, y una plantilla también la lee.
            setFailure("facts");
            setShowTemplates(false);
            setPhase("failed");
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
    const next: Errors = {};
    if (problems.name) next.name = t("builder.new.error.name", { max: nameMax });
    if (needsDescription && problems.description)
      next.description = t("builder.new.error.description", { min: limits.description_min, max: formatNumber(limits.description_max, locale) });
    setErrors(next);
    if (next.name) nameRef.current?.focus();
    else if (next.description) descriptionRef.current?.focus();
    return !next.name && !next.description;
  }

  /**
   * Lo que el alta dice de la agenda (`console-api.md` §2): nada si no se ofrece,
   * `agenda` si se ofrece y, si generar enciende Reservas, cómo se reserva. Sin
   * el modo o, en Aforo, sin el tipo, no se manda nada y el foco va al campo.
   */
  function agendaFields(): Pick<DraftJobBody, "agenda" | "reservas"> | null {
    if (!agendaOptions) return {};
    if (!agendaOn) return { agenda: false };
    if (!turnsOn) return { agenda: true };
    if (reservasMode === null) {
      agendaRef.current?.querySelector<HTMLInputElement>("input[type=radio]")?.focus();
      return null;
    }
    if (reservasMode === "capacity" && reservasKind === null) {
      agendaRef.current?.querySelector<HTMLSelectElement>("select")?.focus();
      return null;
    }
    return { agenda: true, reservas: { mode: reservasMode, capacity_kind: reservasMode === "capacity" ? reservasKind : null } };
  }

  /** Spec 057 (1.5): encender Reservas falló. Se dice junto al interruptor y no se crea nada. */
  function agendaFailed(res: Extract<Result<unknown>, { ok: false }>): boolean {
    if (!agendaOn || !res.code || !AGENDA_ERRORS.has(res.code)) return false;
    setErrors({ agenda: t(`agenda.error.${res.code}` as MessageKey) });
    agendaRef.current?.scrollIntoView?.({ block: "nearest" });
    return true;
  }

  async function generate(event: React.FormEvent) {
    event.preventDefault();
    await describe();
  }

  /** «Generar borrador»: el trabajo que escribe el borrador a partir de lo que se describió. */
  async function describe() {
    if (locked || !validate(true)) return;
    const agenda = agendaFields();
    if (!agenda) return;
    setLastStart("describe");
    setPhase("starting");
    setFailure(null);
    setShowTemplates(false);
    setJob(null);
    setJobId(null);
    const res = await actions.start({ ref: refId, name: cleanName(name), description: description.trim(), start: "describe", ...agenda });
    if (!res.ok) {
      if (res.code === "facts_unavailable") {
        setFailure("facts");
        setPhase("failed");
        return;
      }
      if (!agendaFailed(res)) startFailed(res);
      setPhase("idle");
      return;
    }
    if (res.data.status === "done" && res.data.agent_id) {
      goToAgent(res.data.agent_id);
      return;
    }
    setPhase("building");
    setJobId(res.data.job_id);
  }

  async function startFrom(start: "template" | "blank") {
    if (locked) return;
    if (!validate(false)) return;
    if (start === "template" && !templateId) {
      setErrors({ template: t("builder.alt.templates.required") });
      templatesRef.current?.querySelector<HTMLInputElement>("input[type=radio]")?.focus();
      return;
    }
    const agenda = agendaFields();
    if (!agenda) return;
    if (start === "template") setLastStart("template");
    setAlt(start);
    const text = description.trim();
    const res = await actions.start({
      ref: refId,
      name: cleanName(name),
      start,
      ...(text.length >= limits.description_min && text.length <= limits.description_max ? { description: text } : {}),
      ...(start === "template" && templateId ? { template_id: templateId } : {}),
      ...agenda,
    });
    if (!res.ok) {
      setAlt(null);
      if (res.code === "facts_unavailable") {
        // 65.12: 503 al empezar desde una plantilla, que también lee la ficha.
        setFailure("facts");
        setShowTemplates(false);
        setPhase("failed");
        return;
      }
      if (!agendaFailed(res)) startFailed(res);
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

  /** Un ejemplo se añade a la descripción y, si no hay nombre, pone el suyo (§3.1; spec 055, requisito 5). */
  function pickExample(key: (typeof EXAMPLES)[number]) {
    const added = withExample(description, t(`agentProto.new.example.${key}.text` as MessageKey), limits.description_max);
    descriptionRef.current?.focus();
    if (added.kind === "no_room") {
      setErrors((prev) => ({ ...prev, description: t("agentProto.new.example.noRoom") }));
      return;
    }
    if (added.kind === "ok") setDescription(added.text);
    if (!cleanName(name)) setName(t(`agentProto.new.example.${key}.name` as MessageKey).slice(0, nameMax));
    setErrors((prev) => ({ ...prev, name: undefined, description: undefined }));
  }

  function toggleTemplates() {
    if (showTemplates) return setShowTemplates(false);
    setShowTemplates(true);
    requestAnimationFrame(() => templatesRef.current?.querySelector<HTMLInputElement>("input[type=radio]")?.focus());
  }

  /** «Reintentar» cuando no se pudo leer la ficha: lo mismo que se intentó. */
  function retry() {
    if (locked) return;
    if (lastStart === "template") void startFrom("template");
    else void describe();
  }

  const templates = options?.templates ?? [];
  const title = preparing && cleanName(name) ? cleanName(name) : t("builder.new.title");
  const noFacts = phase === "failed" && failure === "facts";

  return (
    <div className="grid min-w-0 gap-5" data-slot="builder-new">
      {/* Como la pantalla del agente: el título, su estado y de qué cliente es. */}
      <header className="grid min-w-0 gap-2 border-b border-border pb-5">
        <div className="flex min-w-0 items-center gap-3">
          <ShellBackButton />
          <h1 className="min-w-0 text-2xl font-semibold tracking-tighter text-balance break-words sm:text-display">{title}</h1>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
          <StatusBadge tone="muted">{t("clients.v2.agent.draft")}</StatusBadge>
          {clientName ? (
            <>
              <span aria-hidden="true" className="text-muted-foreground">
                ·
              </span>
              <span className="text-base text-muted-foreground">{t("builder.agent.ofClient", { name: clientName })}</span>
            </>
          ) : null}
        </div>
      </header>

      <Tabs value="build" className="min-w-0 flex-col gap-6">
        {/* Canales y Conectores son del agente: llegan cuando exista. Sin números (el owner, 2026-10-28). */}
        <TabsList floating aria-label={t("builder.screen.sections")}>
          <TabsTrigger value="build">{t("builder.screen.tab.build")}</TabsTrigger>
          <TabsTrigger value="channels" disabled>
            {t("builder.screen.channels")}
          </TabsTrigger>
          <TabsTrigger value="connectors" disabled>
            {t("agentConn.title")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="build" className="min-w-0">
          <form onSubmit={generate} noValidate className="grid min-w-0 gap-5">
            {/* Como el prototipo (§4.1): dos columnas desde 1060 px. */}
            <div className="grid min-w-0 items-start gap-5 min-[1060px]:grid-cols-[minmax(0,1fr)_minmax(360px,440px)]">
              <div className="grid min-w-0 gap-4">
                {preparing ? (
                  <DraftSteps job={job} clientName={clientName} />
                ) : (
                  <section
                    aria-labelledby={`${base}-describe`}
                    className="grid min-w-0 gap-5 rounded-lg border border-border bg-card px-4 py-4 sm:px-5"
                    data-slot="builder-describe"
                  >
                    <h2 id={`${base}-describe`} className="sr-only">
                      {t("agentProto.new.describe")}
                    </h2>
                    {noFacts ? (
                      <Callout
                        tone="warning"
                        title={clientName ? t("builder.facts.title.named", { client: clientName }) : t("builder.facts.title")}
                        action={
                          <Button type="button" size="sm" variant="outline" loading={alt !== null} onClick={retry}>
                            {t("builder.suite.retry")}
                          </Button>
                        }
                      >
                        {t("builder.facts.body")}
                      </Callout>
                    ) : phase === "failed" ? (
                      <Callout tone="warning" title={failure === "unavailable" ? t("builder.progress.failed.title") : undefined}>
                        {failure === "unavailable" ? t("builder.progress.failed.body") : t("builder.progress.failed.other")}
                      </Callout>
                    ) : null}
                    <Field label={t("builder.new.name")} error={errors.name} required>
                      {(a11y) => (
                        <Input
                          {...a11y}
                          ref={nameRef}
                          value={name}
                          maxLength={nameMax}
                          readOnly={locked}
                          autoComplete="off"
                          placeholder={t("agentProto.new.name.placeholder")}
                          onChange={(e) => {
                            setName(e.target.value);
                            if (errors.name) setErrors((prev) => ({ ...prev, name: undefined }));
                          }}
                        />
                      )}
                    </Field>
                    <div className="grid min-w-0 gap-3">
                      <Field label={t("builder.new.description")} error={errors.description} required>
                        {(a11y) => (
                          <Textarea
                            {...a11y}
                            ref={descriptionRef}
                            value={description}
                            rows={5}
                            maxLength={limits.description_max}
                            readOnly={locked}
                            placeholder={t("agentProto.new.description.placeholder")}
                            onChange={(e) => {
                              setDescription(e.target.value);
                              if (errors.description) setErrors((prev) => ({ ...prev, description: undefined }));
                            }}
                          />
                        )}
                      </Field>
                      <div role="group" aria-labelledby={`${base}-examples`} className="flex min-w-0 flex-wrap items-center gap-2" data-slot="builder-examples">
                        <span id={`${base}-examples`} className="text-xs text-muted-foreground">
                          {t("agentProto.new.examples")}
                        </span>
                        {EXAMPLES.map((key) => (
                          <Button key={key} type="button" size="sm" variant="outline" className="rounded-full" disabled={locked} onClick={() => pickExample(key)}>
                            {t(`agentProto.new.example.${key}` as MessageKey)}
                          </Button>
                        ))}
                      </div>
                    </div>

                    {agendaOptions ? (
                      <AgendaSwitch
                        ref={agendaRef}
                        on={agendaOn}
                        why={agendaTouched === null ? agendaWhy : null}
                        turnsOn={turnsOn}
                        clientName={clientName}
                        mode={reservasMode}
                        kind={reservasKind}
                        disabled={locked}
                        error={errors.agenda}
                        onToggle={(on) => {
                          setAgendaTouched(on);
                          setErrors((prev) => ({ ...prev, agenda: undefined }));
                        }}
                        onMode={(m) => {
                          setReservasMode(m);
                          if (m === "capacity" && reservasKind === null) setReservasKind(agendaOptions.suggested_kind ?? null);
                          setErrors((prev) => ({ ...prev, agenda: undefined }));
                        }}
                        onKind={(k) => {
                          setReservasKind(k);
                          setErrors((prev) => ({ ...prev, agenda: undefined }));
                        }}
                      />
                    ) : null}

                    {/* Decisión D4 de `agente.md`: plantilla y en blanco, discretos bajo los ejemplos. */}
                    <div className="grid min-w-0 gap-3 border-t border-border pt-4" data-slot="builder-alternatives">
                      <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
                        <span>{t("agentProto.new.other")}</span>
                        {/* 65.12: sin la ficha, una plantilla tampoco se puede preparar. */}
                        {noFacts ? null : (
                          <>
                            <button
                              type="button"
                              className={LINK}
                              aria-expanded={showTemplates}
                              aria-controls={`${base}-templates`}
                              disabled={alt !== null}
                              onClick={toggleTemplates}
                            >
                              {t("builder.alt.template")}
                            </button>
                            <span aria-hidden="true">·</span>
                          </>
                        )}
                        <button type="button" className={LINK} disabled={alt !== null} aria-busy={alt === "blank" || undefined} onClick={() => void startFrom("blank")}>
                          {t("builder.alt.blank")}
                        </button>
                      </p>
                      {showTemplates && !noFacts ? (
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
                              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
                                <Button type="button" size="sm" onClick={() => void startFrom("template")} loading={alt === "template"} disabled={alt === "blank"}>
                                  {t("builder.alt.templates.create")}
                                </Button>
                                {/* Spec 057: lo que la plantilla cambió más arriba, dicho junto a su botón y anunciado. */}
                                <p role="status" className="min-w-0 flex-1 basis-56 text-sm text-pretty text-muted-foreground" data-slot="builder-template-agenda">
                                  {agendaOn && chosenTemplate?.books
                                    ? [t("agenda.template.on"), turnsOn ? t("agenda.template.turnsOn") : null].filter(Boolean).join(" ")
                                    : ""}
                                </p>
                              </div>
                            </>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </section>
                )}
              </div>
              <TryPanel preparing={preparing} />
            </div>

            {/* La barra flotante de vidrio (§4.5, filas 1 y 2). */}
            <div data-slot="agent-actionbar" className={BAR}>
              <div role="region" aria-label={t("builder.publish.bar")} className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2">
                {errors.form ? (
                  <p role="alert" className="inline-flex min-w-0 items-center gap-2 text-sm text-pretty text-destructive">
                    <CircleAlert aria-hidden="true" className="size-4 shrink-0" />
                    <span className="min-w-0">{errors.form}</span>
                  </p>
                ) : (
                  <p role="status" className="inline-flex min-w-0 items-center gap-2 text-sm text-pretty text-muted-foreground">
                    {phase === "done" ? (
                      <CircleCheck aria-hidden="true" className="size-4 shrink-0 text-status-positive-text" />
                    ) : preparing ? (
                      <LoaderCircle aria-hidden="true" className="size-4 shrink-0 animate-spin motion-reduce:animate-none" />
                    ) : null}
                    <span className="min-w-0">
                      {phase === "done"
                        ? t("builder.progress.done")
                        : preparing
                          ? t("builder.progress.queued")
                          : ready
                            ? t("agentProto.new.bar.ready")
                            : t("agentProto.new.bar.missing")}
                    </span>
                  </p>
                )}
                {!preparing ? (
                  <div className="ml-auto flex min-w-0 gap-2 max-[560px]:w-full max-[560px]:*:flex-1">
                    <Button type="submit" className="rounded-full" disabled={!ready || alt !== null}>
                      <WandSparkles aria-hidden="true" />
                      {t("builder.new.generate")}
                    </Button>
                  </div>
                ) : null}
              </div>
            </div>
          </form>
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * «Gestiona citas» (spec 057, 1.1–1.3): el interruptor con su línea, por qué se
 * encendió solo y, si generar enciende Reservas, el aviso y cómo se reserva. Lo
 * que dijo la API al encenderlo, debajo.
 */
const AgendaSwitch = React.forwardRef<
  HTMLDivElement,
  {
    on: boolean;
    why: "description" | "template" | null;
    turnsOn: boolean;
    clientName: string | null;
    mode: ReservasMode | null;
    kind: CapacityKind | null;
    disabled: boolean;
    error?: string;
    onToggle: (on: boolean) => void;
    onMode: (m: ReservasMode) => void;
    onKind: (k: CapacityKind | null) => void;
  }
>(function AgendaSwitch({ on, why, turnsOn, clientName, mode, kind, disabled, error, onToggle, onMode, onKind }, ref) {
  const t = useT();
  const id = React.useId();
  return (
    <div ref={ref} className="grid min-w-0 gap-3 rounded-md border border-border px-3 py-3" data-slot="builder-agenda" data-on={on}>
      <div className="flex min-w-0 items-start gap-3">
        <Switch
          id={`${id}-switch`}
          checked={on}
          disabled={disabled}
          onCheckedChange={(v) => onToggle(v === true)}
          aria-describedby={why ? `${id}-hint ${id}-why` : `${id}-hint`}
          className="mt-1"
        />
        <div className="grid min-w-0 flex-1 gap-1">
          <Label htmlFor={`${id}-switch`} className="text-sm font-medium">
            {t("agenda.switch")}
          </Label>
          <p id={`${id}-hint`} className="text-sm text-pretty text-muted-foreground">
            {t("agenda.switch.hint")}
          </p>
          {why ? (
            <p id={`${id}-why`} className="text-xs text-pretty text-muted-foreground" data-slot="agenda-why">
              {t(`agenda.switch.why.${why}`)}
            </p>
          ) : null}
        </div>
      </div>
      {turnsOn ? (
        <div className="grid min-w-0 gap-3 border-l border-border pl-4">
          <p className="text-sm text-pretty">{clientName ? t("agenda.turnOn.notice.named", { client: clientName }) : t("agenda.turnOn.notice")}</p>
          <ReservasFields mode={mode} kind={kind} disabled={disabled} onMode={onMode} onKind={onKind} />
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-pretty text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
});

/**
 * «Preparando el borrador» (§3.2): los cuatro pasos con su icono —hecho, en
 * curso, pendiente— y lo mismo dicho en palabras para un lector de pantalla.
 */
function DraftSteps({ job, clientName }: { job: DraftJob | null; clientName: string | null }) {
  const t = useT();
  const id = React.useId();
  const states = draftSteps(job);
  const tests = caseTests(job);
  const texts = [
    clientName ? t("agentProto.new.step.read", { client: clientName }) : t("agentProto.new.step.read.generic"),
    t("agentProto.new.step.propose"),
    tests === null
      ? t("agentProto.new.step.tests")
      : tests === 1
        ? t("agentProto.new.step.tests.one")
        : t("agentProto.new.step.tests.other", { n: tests }),
    t("agentProto.new.step.questions"),
  ];
  return (
    <section aria-labelledby={id} className="min-w-0 rounded-lg border border-border bg-card px-4 py-4 sm:px-5" data-slot="builder-steps">
      <h2 id={id} className="sr-only">
        {t("agentProto.new.steps")}
      </h2>
      <ol aria-labelledby={id} className="grid min-w-0 gap-2">
        {texts.map((text, i) => {
          const state = states[i]!;
          return (
            <li key={i} data-state={state} className={cn("flex min-w-0 items-center gap-3 text-sm", state === "wait" && "text-muted-foreground")}>
              <StepIcon state={state} />
              <span className="min-w-0 text-pretty">
                <span data-slot="step-text">{text}</span>
                <span className="sr-only"> · {t(`agentProto.new.step.state.${state}` as MessageKey)}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "done") return <CircleCheck aria-hidden="true" className="size-4 shrink-0 text-status-positive-text" />;
  if (state === "active") return <LoaderCircle aria-hidden="true" className="size-4 shrink-0 animate-spin motion-reduce:animate-none" />;
  return <CircleDashed aria-hidden="true" className="size-4 shrink-0" />;
}

/** «Probar el agente · Aún no» (§3.1): el sitio del chat y las pruebas, antes de que haya borrador. */
function TryPanel({ preparing }: { preparing: boolean }) {
  const t = useT();
  const id = React.useId();
  return (
    <section aria-labelledby={id} className="grid min-w-0 overflow-hidden rounded-lg border border-border bg-card" data-slot="builder-try">
      <div className="flex min-w-0 items-center justify-between gap-2 border-b border-border px-3 py-2">
        <h2 id={id} className="inline-flex min-w-0 items-center gap-2 text-sm font-medium">
          <FlaskConical aria-hidden="true" className="size-4 shrink-0" />
          {t("agentProto.new.try")}
        </h2>
        <StatusBadge tone="muted">{t("agentProto.new.try.notYet")}</StatusBadge>
      </div>
      <div className="grid min-w-0 justify-items-center gap-3 px-5 py-7 text-center">
        <span className="grid size-11 place-items-center rounded-lg bg-muted">
          <CirclePlay aria-hidden="true" className="size-5 text-muted-foreground" />
        </span>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{preparing ? t("builder.progress.queued") : t("agentProto.new.try.body")}</p>
        <p className="max-w-prose text-xs text-pretty text-muted-foreground">{t("agentProto.new.try.note")}</p>
      </div>
    </section>
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
