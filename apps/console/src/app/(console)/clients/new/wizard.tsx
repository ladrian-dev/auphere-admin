"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Checklist, type ChecklistItem, Combobox, ConfirmDialog, Input, Label, Stepper } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { messages, type MessageKey } from "@/i18n/messages";
import type { SeedTemplate } from "@/lib/backend/onboarding";

import { HoursField } from "@/components/clients/new/hours-field";
import { defaultHours, hoursLabel, type Hours } from "@/components/clients/new/hours";
import { TemplatePicker } from "@/components/clients/new/template-picker";

import { wizardCheckRefAction, wizardCreateClientAction, wizardSeedAgentAction } from "./actions";
import {
  browserIanaTimeZone,
  isIanaTimeZone,
  pickWizardTimezone,
  wizardTimezoneOptions,
  STEPS,
  cleanPlaceholders,
  missingPlaceholders,
  nextStage,
  requiredPlaceholders,
  planStages,
  resolvePlaceholderLabel,
  runOutcome,
  slugify,
  stageReducer,
  wizardIsDirty,
  wizardShouldBlockLeave,
  type Stage,
  type StageKey,
  type StepKey,
  type WizardValues,
} from "./wizard-state";

type Props = { templates: SeedTemplate[] | null };

const STEP_LABEL: Record<StepKey, MessageKey> = {
  template: "wizard.template.title",
  details: "wizard.step.details",
  review: "wizard.step.review",
};
const STAGE_LABEL: Record<StageKey, MessageKey> = {
  create: "wizard.stage.create",
  seed: "wizard.stage.seed",
};

/** El campo del horario no es un input: es el control de la spec 019 R7. */
const HOURS_KEY = "tenant.business_hours_label";

function placeholderLabel(t: ReturnType<typeof useT>, key: string): string {
  return resolvePlaceholderLabel(key, messages, (k) => t(k as MessageKey));
}

export function NewClientWizard({ templates }: Props) {
  const t = useT();
  const router = useRouter();

  const [step, setStep] = React.useState<StepKey>("template");
  // Spec 019 R7: el horario se elige. Lo que la plantilla recibe es la cadena
  // que compone `hoursLabel`, así que la frontera con la semilla no cambia.
  const [hours, setHours] = React.useState<Hours>(() => defaultHours());
  // `seed_template` es `string | null` y `null` es una elección legítima
  // —«ninguna de estas»—, así que «aún no ha elegido» necesita su bandera.
  const [templateChosen, setTemplateChosen] = React.useState(false);
  const [browserTz] = React.useState(() => browserIanaTimeZone());
  const [values, setValues] = React.useState<WizardValues>(() => {
    const tz = browserIanaTimeZone();
    return {
      name: "",
      external_client_ref: "",
      timezone: pickWizardTimezone(tz, wizardTimezoneOptions(tz)),
      // **Nada preseleccionado** (spec 019, R2.2). Antes venía marcada la que
      // la API devuelve primera, que es la más pesada de las trece.
      seed_template: null,
      placeholders: {},
    };
  });
  const [refTouched, setRefTouched] = React.useState(false);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [stages, setStages] = React.useState<Stage[]>(() => planStages(values));
  const [running, setRunning] = React.useState(false);
  const [checkingRef, setCheckingRef] = React.useState(false);
  const [leaveOpen, setLeaveOpen] = React.useState(false);
  const [leaveKind, setLeaveKind] = React.useState<"back" | "leave">("leave");
  const allowLeaveRef = React.useRef(false);
  const pendingHrefRef = React.useRef<string | null>(null);
  const stepIndex = STEPS.indexOf(step);
  const template = templates?.find((x) => x.name === values.seed_template) ?? null;
  /** Solo lo imprescindible (spec 019, R1.1): lo opcional vive en los ajustes
   *  del agente. Sale de la plantilla, no de una lista escrita a mano. */
  const needed = React.useMemo(() => requiredPlaceholders(template), [template]);
  /** El horario no se teclea: lo compone el control. Lo demás, tal cual. */
  const placeholderValues = React.useCallback(
    (): Record<string, string> => ({
      ...values.placeholders,
      ...(needed.some((p) => p.key === HOURS_KEY) ? { [HOURS_KEY]: hoursLabel(hours) } : {}),
    }),
    [values.placeholders, needed, hours],
  );
  const outcome = runOutcome(stages);
  const dirty = wizardIsDirty(values);
  const blockLeave = wizardShouldBlockLeave(dirty, outcome);
  const headingRef = React.useRef<HTMLHeadingElement>(null);

  React.useEffect(() => {
    headingRef.current?.focus();
  }, [step]);

  React.useEffect(() => {
    if (!blockLeave) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [blockLeave]);

  // Browser Back is a popstate, not beforeunload — that was the silent leave QA saw.
  React.useEffect(() => {
    if (!blockLeave) return;
    window.history.pushState({ wizardGuard: 1 }, "");
    const onPopState = () => {
      if (allowLeaveRef.current) return;
      pendingHrefRef.current = "/clients";
      setLeaveKind("leave");
      setLeaveOpen(true);
      window.history.pushState({ wizardGuard: 1 }, "");
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [blockLeave]);

  React.useEffect(() => {
    if (!blockLeave) return;
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const el = e.target instanceof Element ? e.target.closest("a[href]") : null;
      if (!el) return;
      const href = el.getAttribute("href");
      if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return;
      if (el.getAttribute("target") === "_blank") return;
      let next = href;
      try {
        const u = new URL(href, window.location.origin);
        if (u.origin !== window.location.origin) return;
        if (u.pathname.startsWith("/clients/new")) return;
        next = `${u.pathname}${u.search}`;
      } catch {
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      pendingHrefRef.current = next;
      setLeaveKind("leave");
      setLeaveOpen(true);
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [blockLeave]);

  function set<K extends keyof WizardValues>(k: K, v: WizardValues[K]) {
    setValues((prev) => ({ ...prev, [k]: v }));
  }

  function validateStep(): boolean {
    const e: Record<string, string> = {};
    if (step === "details") {
      if (!values.name.trim()) e.name = t("validation.required");
      else if (values.name.length > 255) e.name = t("validation.tooLong");
      if (!values.external_client_ref.trim()) e.external_client_ref = t("validation.required");
      else if (!/^[A-Za-z0-9._:-]+$/.test(values.external_client_ref)) e.external_client_ref = t("validation.refFormat");
      if (!values.timezone.trim()) e.timezone = t("validation.required");
      else if (!isIanaTimeZone(values.timezone)) e.timezone = t("validation.timezone");
      // Solo los imprescindibles: los opcionales ya no se enseñan.
      for (const k of missingPlaceholders(needed, placeholderValues())) e[`ph:${k}`] = t("validation.required");
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function goNext() {
    if (!validateStep()) return;
    if (step === "details") {
      setCheckingRef(true);
      try {
        const res = await wizardCheckRefAction({ ref: values.external_client_ref });
        if (!res.ok) {
          setErrors((e) => ({
            ...e,
            external_client_ref: res.status === 409 ? t("clients.create.duplicate") : res.message,
          }));
          return;
        }
      } finally {
        setCheckingRef(false);
      }
    }
    const next = STEPS[stepIndex + 1];
    if (next) {
      setStep(next);
      setStages(planStages(values));
    }
  }
  function performLeave(kind: "back" | "leave") {
    if (kind === "leave") {
      allowLeaveRef.current = true;
      const href = pendingHrefRef.current;
      pendingHrefRef.current = null;
      router.push(href || "/clients");
      return;
    }
    const prev = STEPS[stepIndex - 1];
    if (prev) setStep(prev);
  }
  function requestLeave(kind: "back" | "leave") {
    if (wizardShouldBlockLeave(dirty, outcome)) {
      setLeaveKind(kind);
      setLeaveOpen(true);
      return;
    }
    performLeave(kind);
  }
  function goBack() {
    requestLeave("back");
  }

  // ── run: real calls, one per stage, individually retryable ──────────
  const runStage = React.useCallback(
    async (key: StageKey, current: Stage[]): Promise<Stage[]> => {
      let st = stageReducer(current, { type: "start", key, at: Date.now() });
      setStages(st);
      const fail = (msg: string) => {
        st = stageReducer(st, { type: "fail", key, at: Date.now(), error: msg });
        setStages(st);
        return st;
      };
      const done = () => {
        st = stageReducer(st, { type: "done", key, at: Date.now() });
        setStages(st);
        return st;
      };
      try {
        if (key === "create") {
          const res = await wizardCreateClientAction({
            external_client_ref: values.external_client_ref,
            name: values.name.trim(),
            timezone: values.timezone,
          });
          return res.ok ? done() : fail(res.message);
        }
        // El agente se escribe y **se queda en borrador**: publicarlo es un
        // paso de la ficha (spec 019, R6.4).
        const res = await wizardSeedAgentAction({
          ref: values.external_client_ref,
          seed_template: values.seed_template,
          placeholders: cleanPlaceholders(placeholderValues()),
        });
        return res.ok ? done() : fail(res.message);
      } catch (err) {
        return fail(err instanceof Error ? err.message : t("common.error.backend"));
      }
    },
    [t, values, placeholderValues],
  );

  async function runAll(from?: Stage[]) {
    setRunning(true);
    let st = from ?? planStages(values);
    setStages(st);
    let key = nextStage(st);
    while (key) {
      st = await runStage(key, st);
      if (st.find((s) => s.key === key)?.status === "failed") break;
      key = nextStage(st);
    }
    setRunning(false);
    if (runOutcome(st) === "done") {
      toast.success(t("clients.create.done"));
      // Spec 016 (R4.4): land on the card, on the setup state — what is
      // missing is named there with the action a click away.
      router.push(`/clients/${encodeURIComponent(values.external_client_ref)}#setup`);
    }
  }

  async function retry(key: StageKey) {
    const reset = stageReducer(stages, { type: "reset", key });
    await runAll(reset);
  }

  const clientHref = `/clients/${encodeURIComponent(values.external_client_ref)}`;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      {/* step indicator */}
      <Stepper
        ariaLabel={t("wizard.steps.label")}
        steps={STEPS.map((s) => ({ key: s, label: t(STEP_LABEL[s]) }))}
        current={stepIndex}
        stepOfLabel={(n, total) => t("wizard.stepOf", { n, total })}
      />

      <section aria-labelledby="wizard-step-title" className="flex flex-col gap-4">
        <h2 id="wizard-step-title" ref={headingRef} tabIndex={-1} className="text-lg font-semibold text-balance outline-none">
          {t(STEP_LABEL[step])}
        </h2>

        {step === "template" ? (
          <TemplatePicker
            templates={templates}
            value={values.seed_template}
            onChange={(name) => {
              setTemplateChosen(true);
              set("seed_template", name);
              set("placeholders", {});
            }}
          />
        ) : null}

        {step === "details" ? (
          <div className="flex flex-col gap-4">
            {/* La frase que hace corto un formulario corto. Sin ella, cuatro
                campos se leen como «cuatro, de momento». */}
            <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("wizard.details.body")}</p>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="grid min-w-0 content-start gap-2">
                <Label htmlFor="wz-name">{t("wizard.details.name")}</Label>
                <Input
                  id="wz-name"
                  autoComplete="organization"
                  value={values.name}
                  aria-invalid={!!errors.name}
                  aria-describedby={errors.name ? "wz-name-err" : undefined}
                  onChange={(e) => {
                    set("name", e.target.value);
                    if (!refTouched) set("external_client_ref", slugify(e.target.value));
                  }}
                />
                {errors.name ? (
                  <p id="wz-name-err" className="text-sm text-destructive">
                    {errors.name}
                  </p>
                ) : null}
              </div>

              <div className="grid min-w-0 content-start gap-2">
                <Label htmlFor="wz-tz">{t("clients.timezone")}</Label>
                {/* Elegible y con autocompletado: lo que se guarda sale de la
                    lista, así que no hay zona inventada. */}
                <Combobox
                  id="wz-tz"
                  items={wizardTimezoneOptions(browserTz)}
                  value={values.timezone}
                  onValueChange={(v) => set("timezone", v)}
                  placeholder={t("clients.timezone.placeholder")}
                  emptyLabel={t("common.noMatches")}
                  aria-invalid={!!errors.timezone}
                />
                {errors.timezone ? <p className="text-sm text-destructive">{errors.timezone}</p> : null}
              </div>

              {/* Solo los imprescindibles de esta plantilla. El horario no es
                  un input: se elige (R7.1). */}
              {needed
                .filter((ph) => ph.key !== HOURS_KEY)
                .map((ph) => (
                  <div key={ph.key} className="grid min-w-0 content-start gap-2 sm:col-span-2">
                    <Label htmlFor={`wz-${ph.key}`}>{placeholderLabel(t, ph.key)}</Label>
                    <Input
                      id={`wz-${ph.key}`}
                      value={values.placeholders[ph.key] ?? ""}
                      placeholder={ph.example ?? undefined}
                      aria-invalid={!!errors[`ph:${ph.key}`]}
                      onChange={(e) => set("placeholders", { ...values.placeholders, [ph.key]: e.target.value })}
                    />
                    {errors[`ph:${ph.key}`] ? (
                      <p className="text-sm text-destructive">{errors[`ph:${ph.key}`]}</p>
                    ) : null}
                  </div>
                ))}
            </div>

            {needed.some((ph) => ph.key === HOURS_KEY) ? <HoursField value={hours} onChange={setHours} /> : null}

            {/* La referencia, fuera del camino: se deriva del nombre y casi
                nadie quiere tocarla (R4.2). */}
            <details className="flex flex-col gap-2">
              <summary className="cursor-pointer text-sm text-muted-foreground">{t("wizard.details.advanced")}</summary>
              <div className="mt-2 grid min-w-0 max-w-md content-start gap-2">
                <Label htmlFor="wz-ref">{t("clients.ref")}</Label>
                <Input
                  id="wz-ref"
                  className="font-mono"
                  autoComplete="off"
                  spellCheck={false}
                  value={values.external_client_ref}
                  aria-invalid={!!errors.external_client_ref}
                  aria-describedby="wz-ref-hint"
                  onChange={(e) => {
                    setRefTouched(true);
                    set("external_client_ref", e.target.value);
                  }}
                />
                <p id="wz-ref-hint" className="text-sm text-pretty text-muted-foreground">
                  {t("clients.create.refHint")}
                </p>
                {errors.external_client_ref ? (
                  <p className="text-sm text-destructive">{errors.external_client_ref}</p>
                ) : null}
              </div>
            </details>
          </div>
        ) : null}

        {step === "review" ? (
          <div className="flex flex-col gap-4">
            {/* Quién es, con la cara de su rubro. No repite lo que acabas de
                escribir campo a campo: lo dice de un vistazo. */}
            <div className="flex min-w-0 flex-col gap-1 rounded-md bg-card p-4 ring-1 ring-foreground/10">
              <span className="font-medium">{values.name}</span>
              <span className="text-sm text-muted-foreground">
                {[template?.display_name, values.timezone].filter(Boolean).join(" · ")}
              </span>
              {needed.some((ph) => ph.key === HOURS_KEY) ? (
                <span className="text-sm text-muted-foreground">{hoursLabel(hours)}</span>
              ) : null}
            </div>

            {/* Qué va a pasar al pulsar, en dos cosas y no en cuatro frases:
                lo que se crea, y lo que quedará pendiente. Y esos tres
                pendientes son los tres pasos de la ficha. */}
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-medium">{t("wizard.review.onCreate")}</h3>
                <p className="max-w-prose text-sm text-pretty text-muted-foreground">
                  {template
                    ? t("wizard.review.onCreate.body", { n: template.tools_count })
                    : t("wizard.review.onCreate.noTemplate")}
                </p>
              </div>
              <div className="flex flex-col gap-2">
                <h3 className="text-sm font-medium">{t("wizard.review.pending")}</h3>
                <Checklist
                  dense
                  ariaLabel={t("wizard.review.pending")}
                  items={[
                    { key: "publish", label: t("wizard.review.pending.publish"), status: "todo", detail: t("wizard.review.pending.publish.body") },
                    { key: "credit", label: t("wizard.review.pending.credit"), status: "todo", detail: t("wizard.review.pending.credit.body") },
                    { key: "channel", label: t("wizard.review.pending.channel"), status: "todo", detail: t("wizard.review.pending.channel.body") },
                  ]}
                />
                <p className="text-sm text-muted-foreground">{t("wizard.review.pending.foot")}</p>
              </div>
            </div>

            {outcome !== "idle" ? (
              <section aria-label={t("wizard.progress.title")} aria-live="polite" className="flex flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10">
                <Checklist
                  ariaLabel={t("wizard.progress.title")}
                  items={stages.map<ChecklistItem>((s) => ({
                    key: s.key,
                    label: t(STAGE_LABEL[s.key]),
                    status: s.status === "pending" ? "todo" : s.status,
                    detail: s.status === "failed" ? s.error : undefined,
                    onRetry: s.status === "failed" && !running ? () => void retry(s.key) : undefined,
                    retryLabel: t("wizard.stage.retry"),
                  }))}
                />
                {outcome === "partial" && !running ? (
                  // §V: lo que quedó hecho no se pierde, y se dice.
                  <p className="text-sm text-pretty text-muted-foreground" role="status">
                    {t("wizard.done.partial")}{" "}
                    <Link className="underline underline-offset-4" href={clientHref}>
                      {t("wizard.done.open")}
                    </Link>
                  </p>
                ) : null}
              </section>
            ) : null}
          </div>
        ) : null}
      </section>

      {/* nav */}
      <div className="flex flex-wrap items-center gap-2">
        {stepIndex === 0 ? (
          <Button type="button" variant="outline" onClick={() => requestLeave("leave")}>
            {t("wizard.leave")}
          </Button>
        ) : (
          <Button type="button" variant="outline" onClick={goBack} disabled={running || outcome === "done"}>
            {t("wizard.back")}
          </Button>
        )}
        {step !== "review" ? (
          // R2.2: no se puede continuar sin elegir. `null` es una elección
          // legítima —«ninguna de estas»—, así que lo que se mira es si la
          // ha tomado, no su valor.
          <Button
            type="button"
            onClick={() => void goNext()}
            disabled={step === "template" && !templateChosen}
            loading={checkingRef}
          >
            {t("wizard.next")}
          </Button>
        ) : outcome === "idle" ? (
          <Button type="button" onClick={() => void runAll()} loading={running}>
            {running ? t("wizard.running") : t("wizard.run")}
          </Button>
        ) : null}
      </div>
      <ConfirmDialog
        open={leaveOpen}
        onOpenChange={(open) => {
          setLeaveOpen(open);
          if (!open) pendingHrefRef.current = null;
        }}
        title={t("wizard.dirty.title")}
        description={t("wizard.dirty.body")}
        confirmLabel={leaveKind === "leave" ? t("wizard.dirty.confirm") : t("wizard.dirty.back")}
        cancelLabel={t("common.cancel")}
        onConfirm={() => {
          setLeaveOpen(false);
          performLeave(leaveKind);
        }}
      />
    </div>
  );
}
