"use client";

import { AlertTriangle, Check, CircleDashed, Loader2, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Checkbox, Input, Label, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { messages, type MessageKey } from "@/i18n/messages";
import type { Quota } from "@/lib/backend";
import type { SeedPlaceholder, SeedTemplate } from "@/lib/backend/onboarding";

import { wizardCreateClientAction, wizardPublishAndActivateAction, wizardSeedAgentAction } from "./actions";
import {
  STEPS,
  cleanPlaceholders,
  elapsedSeconds,
  missingPlaceholders,
  nextStage,
  planStages,
  runOutcome,
  slugify,
  stageReducer,
  type ChannelChoice,
  type Stage,
  type StageKey,
  type StepKey,
  type WizardValues,
} from "./wizard-state";

type Props = { quota: Quota; templates: SeedTemplate[] | null; canPublish: boolean };

const STEP_LABEL: Record<StepKey, MessageKey> = {
  details: "wizard.step.details",
  template: "wizard.step.template",
  channel: "wizard.step.channel",
  review: "wizard.step.review",
};
const STAGE_LABEL: Record<StageKey, MessageKey> = {
  create: "wizard.stage.create",
  seed: "wizard.stage.seed",
  publish: "wizard.stage.publish",
  channel: "wizard.stage.channel",
};

function placeholderLabel(t: ReturnType<typeof useT>, key: string): string {
  const k = `ph.${key}`;
  if (k in messages) return t(k as MessageKey);
  // Unknown seed key → humanise the last segment.
  return key.split(".").pop()!.replace(/_/g, " ");
}

export function NewClientWizard({ quota, templates, canPublish }: Props) {
  const t = useT();
  const router = useRouter();
  const full = quota.remaining_clients === 0;

  const [step, setStep] = React.useState<StepKey>("details");
  const [values, setValues] = React.useState<WizardValues>({
    name: "",
    external_client_ref: "",
    timezone: (typeof Intl !== "undefined" && Intl.DateTimeFormat().resolvedOptions().timeZone) || "UTC",
    seed_template: templates?.[0]?.name ?? null,
    placeholders: {},
    channel: "whatsapp",
    publish_now: canPublish,
  });
  const [refTouched, setRefTouched] = React.useState(false);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [stages, setStages] = React.useState<Stage[]>(() => planStages(values));
  const [running, setRunning] = React.useState(false);
  const stepIndex = STEPS.indexOf(step);
  const template = templates?.find((x) => x.name === values.seed_template) ?? null;
  const outcome = runOutcome(stages);
  const headingRef = React.useRef<HTMLHeadingElement>(null);

  React.useEffect(() => {
    headingRef.current?.focus();
  }, [step]);

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
    }
    if (step === "template" && template) {
      for (const k of missingPlaceholders(template.placeholders, values.placeholders)) e[`ph:${k}`] = t("validation.required");
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function goNext() {
    if (!validateStep()) return;
    const next = STEPS[stepIndex + 1];
    if (next) {
      setStep(next);
      setStages(planStages({ ...values }));
    }
  }
  function goBack() {
    const prev = STEPS[stepIndex - 1];
    if (prev) setStep(prev);
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
        if (key === "seed") {
          const res = await wizardSeedAgentAction({
            ref: values.external_client_ref,
            seed_template: values.seed_template,
            placeholders: cleanPlaceholders(values.placeholders),
          });
          return res.ok ? done() : fail(res.message);
        }
        if (key === "publish") {
          const res = await wizardPublishAndActivateAction({ ref: values.external_client_ref });
          return res.ok ? done() : fail(res.message);
        }
        return done(); // channel: informational, connect afterwards
      } catch (err) {
        return fail(err instanceof Error ? err.message : t("common.error.backend"));
      }
    },
    [t, values],
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
      toast.success(t("wizard.done.title"));
      router.refresh();
    }
  }

  async function retry(key: StageKey) {
    const reset = stageReducer(stages, { type: "reset", key });
    await runAll(reset);
  }

  const clientHref = `/clients/${encodeURIComponent(values.external_client_ref)}`;
  const seconds = elapsedSeconds(stages);

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      {/* step indicator */}
      <ol aria-label={t("wizard.steps.label")} className="flex flex-wrap gap-2 font-mono text-xs">
        {STEPS.map((s, i) => {
          const state = i < stepIndex ? "done" : i === stepIndex ? "current" : "todo";
          return (
            <li
              key={s}
              aria-current={state === "current" ? "step" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1",
                state === "current" && "border-foreground text-foreground",
                state === "done" && "border-primary/40 bg-primary/10 text-foreground",
                state === "todo" && "border-border text-muted-foreground",
              )}
            >
              <span className="tabular-nums" aria-hidden="true">
                {i + 1}
              </span>
              <span>{t(STEP_LABEL[s])}</span>
              {state === "done" ? <Check className="size-3" aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>
      <p className="sr-only" aria-live="polite">
        {t("wizard.stepOf", { n: stepIndex + 1, total: STEPS.length })}
      </p>

      {full ? (
        <p role="alert" className="rounded-md border border-status-warning/40 bg-status-warning/10 px-4 py-3 text-sm">
          {t("wizard.quota.blocked", { used: quota.used_clients, max: quota.max_clients })}
        </p>
      ) : null}

      <section aria-labelledby="wizard-step-title" className="flex flex-col gap-4">
        <h2 id="wizard-step-title" ref={headingRef} tabIndex={-1} className="text-lg font-semibold text-balance outline-none">
          {t(STEP_LABEL[step])}
        </h2>

        {step === "details" ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="wz-name">{t("common.name")}</Label>
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
            <div className="flex flex-col gap-2">
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
              <p id="wz-ref-hint" className="text-sm text-muted-foreground text-pretty">
                {t("clients.create.refHint")}
              </p>
              {errors.external_client_ref ? <p className="text-sm text-destructive">{errors.external_client_ref}</p> : null}
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="wz-tz">{t("clients.timezone")}</Label>
              <Input id="wz-tz" className="font-mono" value={values.timezone} aria-invalid={!!errors.timezone} onChange={(e) => set("timezone", e.target.value)} />
              {errors.timezone ? <p className="text-sm text-destructive">{errors.timezone}</p> : null}
            </div>
          </div>
        ) : null}

        {step === "template" ? (
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <p className="text-sm text-muted-foreground text-pretty">{t("wizard.template.body")}</p>
              {templates === null ? (
                <p role="alert" className="text-sm text-destructive">
                  {t("wizard.template.loadError")}
                </p>
              ) : templates.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("wizard.template.empty")}</p>
              ) : null}
              <div role="radiogroup" aria-label={t("wizard.template.title")} className="grid gap-2 sm:grid-cols-2">
                {(templates ?? []).map((tpl) => {
                  const selected = values.seed_template === tpl.name;
                  return (
                    <button
                      key={tpl.name}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => {
                        set("seed_template", tpl.name);
                        set("placeholders", {});
                      }}
                      className={cn(
                        "flex min-w-0 flex-col items-start gap-1 rounded-md border px-3 py-2 text-left text-sm transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                        selected ? "border-foreground bg-muted" : "border-border hover:bg-muted/60",
                      )}
                    >
                      <span className="min-w-0 w-full truncate font-medium" title={tpl.display_name}>
                        {tpl.display_name}
                      </span>
                      <span className="font-mono text-xs text-muted-foreground">
                        {tpl.name} · {t("wizard.template.tools", { count: tpl.tools_count })}
                      </span>
                    </button>
                  );
                })}
                <button
                  type="button"
                  role="radio"
                  aria-checked={values.seed_template === null}
                  onClick={() => set("seed_template", null)}
                  className={cn(
                    "flex min-w-0 flex-col items-start gap-1 rounded-md border border-dashed px-3 py-2 text-left text-sm transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                    values.seed_template === null ? "border-foreground bg-muted" : "border-border hover:bg-muted/60",
                  )}
                >
                  <span className="font-medium">{t("wizard.template.none")}</span>
                </button>
              </div>
            </div>

            {template && template.placeholders.length > 0 ? (
              <fieldset className="flex flex-col gap-4">
                <legend className="text-sm font-medium">{t("wizard.placeholders.title")}</legend>
                <p className="text-sm text-muted-foreground text-pretty">{t("wizard.placeholders.body")}</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  {template.placeholders.map((ph) => (
                    <PlaceholderField
                      key={ph.key}
                      ph={ph}
                      value={values.placeholders[ph.key] ?? ""}
                      error={errors[`ph:${ph.key}`]}
                      onChange={(v) => set("placeholders", { ...values.placeholders, [ph.key]: v })}
                    />
                  ))}
                </div>
              </fieldset>
            ) : null}
          </div>
        ) : null}

        {step === "channel" ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground text-pretty">{t("wizard.channel.body")}</p>
            <div role="radiogroup" aria-label={t("wizard.channel.title")} className="grid gap-2 sm:grid-cols-3">
              {(["whatsapp", "later"] as ChannelChoice[]).map((c) => {
                const selected = values.channel === c;
                const label = c === "whatsapp" ? t("wizard.channel.whatsapp") : t("wizard.channel.later");
                const body = c === "whatsapp" ? t("wizard.channel.whatsapp.body") : null;
                return (
                  <button
                    key={c}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => set("channel", c)}
                    className={cn(
                      "flex min-w-0 flex-col items-start gap-1 rounded-md border px-3 py-2 text-left text-sm transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                      selected ? "border-foreground bg-muted" : "border-border hover:bg-muted/60",
                    )}
                  >
                    <span className="font-medium">{label}</span>
                    {body ? <span className="text-xs text-muted-foreground text-pretty">{body}</span> : null}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {step === "review" ? (
          <div className="flex flex-col gap-6">
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
              <dt className="text-muted-foreground">{t("common.name")}</dt>
              <dd className="min-w-0 truncate" title={values.name}>
                {values.name}
              </dd>
              <dt className="text-muted-foreground">{t("clients.ref")}</dt>
              <dd className="min-w-0 truncate font-mono" title={values.external_client_ref}>
                {values.external_client_ref}
              </dd>
              <dt className="text-muted-foreground">{t("clients.timezone")}</dt>
              <dd className="font-mono">{values.timezone}</dd>
              <dt className="text-muted-foreground">{t("wizard.review.template")}</dt>
              <dd className="min-w-0 truncate">{template ? `${template.display_name} (${template.name})` : t("wizard.template.none")}</dd>
              <dt className="text-muted-foreground">{t("wizard.review.channel")}</dt>
              <dd>{t(values.channel === "whatsapp" ? "wizard.review.channel.whatsapp" : "wizard.review.channel.later")}</dd>
            </dl>
            {template && canPublish ? (
              <div className="flex items-start gap-3">
                <Checkbox
                  id="wz-publish"
                  checked={values.publish_now}
                  disabled={running || outcome !== "idle"}
                  onCheckedChange={(v) => {
                    set("publish_now", Boolean(v));
                    setStages(planStages({ seed_template: values.seed_template, publish_now: Boolean(v) }));
                  }}
                />
                <div className="flex flex-col gap-1">
                  <Label htmlFor="wz-publish">{t("wizard.review.publishNow")}</Label>
                  <p className="text-xs text-muted-foreground text-pretty">{t("wizard.review.publishNow.hint")}</p>
                </div>
              </div>
            ) : null}

            {/* progress */}
            <section aria-labelledby="wz-progress" aria-live="polite" className="flex flex-col gap-2 rounded-md border border-border bg-card p-4">
              <h3 id="wz-progress" className="font-mono text-xs tracking-eyebrow text-muted-foreground uppercase">
                {t("wizard.progress.title")}
              </h3>
              <ol className="flex flex-col gap-2">
                {stages.map((s) => (
                  <li key={s.key} className="flex min-w-0 items-start gap-3 text-sm">
                    <StageIcon status={s.status} />
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <span className={cn("min-w-0 truncate", s.status === "skipped" && "text-muted-foreground line-through")}>{t(STAGE_LABEL[s.key])}</span>
                        <span className="shrink-0 font-mono text-xs text-muted-foreground">
                          {t(
                            s.status === "pending"
                              ? "wizard.stage.pending"
                              : s.status === "running"
                                ? "wizard.stage.running"
                                : s.status === "done"
                                  ? "wizard.stage.done"
                                  : s.status === "skipped"
                                    ? "wizard.stage.skipped"
                                    : "wizard.stage.failed",
                          )}
                        </span>
                      </div>
                      {s.key === "channel" && s.status === "done" ? (
                        <span className="text-xs text-muted-foreground text-pretty">
                          {t(values.channel === "whatsapp" ? "wizard.stage.channel.whatsapp" : "wizard.stage.channel.later")}
                        </span>
                      ) : null}
                      {s.status === "failed" ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <span role="alert" className="min-w-0 text-xs text-destructive text-pretty">
                            {s.error}
                          </span>
                          <Button type="button" size="sm" variant="outline" disabled={running} onClick={() => void retry(s.key)}>
                            <RotateCcw className="size-3" aria-hidden="true" />
                            {t("wizard.stage.retry")}
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
              {outcome === "done" ? (
                <div className="mt-2 flex flex-col gap-2 rounded-md border border-primary/30 bg-primary/10 p-3" role="status">
                  <p className="text-sm font-medium">{t("wizard.done.title")}</p>
                  <p className="text-sm text-muted-foreground text-pretty">{t("wizard.done.body", { seconds: seconds ?? 0 })}</p>
                  <div className="flex flex-wrap gap-2">
                    <Button nativeButton={false} render={<Link href={clientHref} />}>
                      {t("wizard.done.open")}
                    </Button>
                    <Button variant="outline" nativeButton={false} render={<Link href={`${clientHref}/playground`} />}>
                      {t("wizard.done.playground")}
                    </Button>
                    {values.channel !== "later" ? (
                      <Button variant="outline" nativeButton={false} render={<Link href={`${clientHref}/channels`} />}>
                        {t("wizard.done.channels")}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {outcome === "partial" && !running ? (
                <p className="text-sm text-muted-foreground text-pretty" role="status">
                  {t("wizard.done.partial")}{" "}
                  <Link className="underline underline-offset-4" href={clientHref}>
                    {t("wizard.done.open")}
                  </Link>
                </p>
              ) : null}
            </section>
          </div>
        ) : null}
      </section>

      {/* nav */}
      <div className="flex flex-wrap items-center gap-2">
        {stepIndex === 0 ? (
          <Button type="button" variant="outline" onClick={() => router.back()}>
            {t("wizard.leave")}
          </Button>
        ) : (
          <Button type="button" variant="outline" onClick={goBack} disabled={running || outcome === "done"}>
            {t("wizard.back")}
          </Button>
        )}
        {step !== "review" ? (
          <Button type="button" onClick={goNext} disabled={full}>
            {t("wizard.next")}
          </Button>
        ) : outcome === "idle" ? (
          <Button type="button" onClick={() => void runAll()} disabled={full || running}>
            {running ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
            {running ? t("wizard.running") : t("wizard.run")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function StageIcon({ status }: { status: Stage["status"] }) {
  const cls = "mt-1 size-4 shrink-0";
  switch (status) {
    case "running":
      return <Loader2 className={cn(cls, "animate-spin text-primary")} aria-hidden="true" />;
    case "done":
      return <Check className={cn(cls, "text-primary")} aria-hidden="true" />;
    case "failed":
      return <AlertTriangle className={cn(cls, "text-destructive")} aria-hidden="true" />;
    default:
      return <CircleDashed className={cn(cls, "text-muted-foreground")} aria-hidden="true" />;
  }
}

function PlaceholderField({ ph, value, error, onChange }: { ph: SeedPlaceholder; value: string; error?: string; onChange: (v: string) => void }) {
  const t = useT();
  const id = `ph-${ph.key.replace(/\W/g, "-")}`;
  const hintId = `${id}-hint`;
  const label = placeholderLabel(t, ph.key);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label htmlFor={id} className="min-w-0">
        <span className="min-w-0 truncate" title={ph.key}>
          {label}
        </span>
        {!ph.required ? <span className="ml-1 font-normal text-muted-foreground">({t("wizard.placeholders.optional")})</span> : null}
        {ph.secret ? <span className="ml-1 font-normal text-status-warning">· {t("wizard.placeholders.secret")}</span> : null}
      </Label>
      <Input
        id={id}
        type={ph.secret ? "password" : ph.kind === "number" ? "number" : "text"}
        inputMode={ph.kind === "number" ? "decimal" : undefined}
        autoComplete={ph.secret ? "off" : undefined}
        value={value}
        required={ph.required}
        aria-required={ph.required}
        aria-invalid={!!error}
        aria-describedby={hintId}
        placeholder={ph.example ?? undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      <p id={hintId} className="min-w-0 truncate text-xs text-muted-foreground" title={ph.key}>
        {ph.kind === "list" ? t("wizard.placeholders.list") : ph.example ? t("wizard.placeholders.default", { value: ph.example }) : ph.key}
      </p>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
