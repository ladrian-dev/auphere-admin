"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Checkbox, Checklist, type ChecklistItem, ConfirmDialog, DescriptionList, Input, Label, NativeSelect, Stepper, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import { messages, type MessageKey } from "@/i18n/messages";
import type { Quota } from "@/lib/backend";
import type { SeedPlaceholder, SeedTemplate } from "@/lib/backend/onboarding";

import { wizardActivateAction, wizardCheckRefAction, wizardCreateClientAction, wizardPublishAction, wizardSeedAgentAction } from "./actions";
import {
  browserIanaTimeZone,
  isIanaTimeZone,
  pickWizardTimezone,
  wizardTimezoneOptions,
  STEPS,
  cleanPlaceholders,
  elapsedSeconds,
  missingPlaceholders,
  nextStage,
  planStages,
  resolvePlaceholderLabel,
  runOutcome,
  slugify,
  stageReducer,
  wizardIsDirty,
  wizardShouldBlockLeave,
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
  activate: "wizard.stage.activate",
  channel: "wizard.stage.channel",
};

function placeholderLabel(t: ReturnType<typeof useT>, key: string): string {
  return resolvePlaceholderLabel(key, messages, (k) => t(k as MessageKey));
}

export function NewClientWizard({ quota, templates, canPublish }: Props) {
  const t = useT();
  const router = useRouter();
  const full = quota.remaining_clients === 0;

  const [step, setStep] = React.useState<StepKey>("details");
  const [browserTz] = React.useState(() => browserIanaTimeZone());
  const [values, setValues] = React.useState<WizardValues>(() => {
    const tz = browserIanaTimeZone();
    return {
      name: "",
      external_client_ref: "",
      timezone: pickWizardTimezone(tz, wizardTimezoneOptions(tz)),
      seed_template: templates?.[0]?.name ?? null,
      placeholders: {},
      channel: "whatsapp",
      publish_now: canPublish,
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
    }
    if (step === "template" && template) {
      for (const k of missingPlaceholders(template.placeholders, values.placeholders)) e[`ph:${k}`] = t("validation.required");
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
      setStages(planStages({ ...values }));
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
        if (key === "seed") {
          const res = await wizardSeedAgentAction({
            ref: values.external_client_ref,
            seed_template: values.seed_template,
            placeholders: cleanPlaceholders(values.placeholders),
          });
          return res.ok ? done() : fail(res.message);
        }
        if (key === "publish") {
          const res = await wizardPublishAction({ ref: values.external_client_ref });
          return res.ok ? done() : fail(actionErrorText(res, t));
        }
        if (key === "activate") {
          const res = await wizardActivateAction({ ref: values.external_client_ref });
          return res.ok ? done() : fail(actionErrorText(res, t));
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
  const seconds = elapsedSeconds(stages);

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      {/* step indicator */}
      <Stepper
        ariaLabel={t("wizard.steps.label")}
        steps={STEPS.map((s) => ({ key: s, label: t(STEP_LABEL[s]) }))}
        current={stepIndex}
        stepOfLabel={(n, total) => t("wizard.stepOf", { n, total })}
      />

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
              <NativeSelect
                id="wz-tz"
                wrapperClassName="w-full"
                className="font-mono"
                value={values.timezone}
                aria-invalid={!!errors.timezone}
                onChange={(e) => set("timezone", e.target.value)}
              >
                <option value="">{t("clients.timezone.placeholder")}</option>
                {wizardTimezoneOptions(browserTz).map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </NativeSelect>
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
            <DescriptionList
              layout="inline"
              items={[
                { key: "name", term: t("common.name"), detail: values.name, truncate: true },
                { key: "ref", term: t("clients.ref"), detail: values.external_client_ref, mono: true, truncate: true },
                { key: "tz", term: t("clients.timezone"), detail: values.timezone, mono: true },
                { key: "template", term: t("wizard.review.template"), detail: template ? `${template.display_name} (${template.name})` : t("wizard.template.none"), truncate: true },
                { key: "channel", term: t("wizard.review.channel"), detail: t(values.channel === "whatsapp" ? "wizard.review.channel.whatsapp" : "wizard.review.channel.later") },
              ]}
            />
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
              <Checklist
                ariaLabel={t("wizard.progress.title")}
                items={stages.map<ChecklistItem>((s) => ({
                  key: s.key,
                  label: t(STAGE_LABEL[s.key]),
                  status: s.status === "pending" ? "todo" : s.status,
                  meta: t(
                    s.status === "pending"
                      ? "wizard.stage.pending"
                      : s.status === "running"
                        ? "wizard.stage.running"
                        : s.status === "done"
                          ? "wizard.stage.done"
                          : s.status === "skipped"
                            ? "wizard.stage.skipped"
                            : "wizard.stage.failed",
                  ),
                  detail:
                    s.status === "failed"
                      ? s.error
                      : s.key === "channel" && s.status === "done"
                        ? t(values.channel === "whatsapp" ? "wizard.stage.channel.whatsapp" : "wizard.stage.channel.later")
                        : undefined,
                  onRetry: s.status === "failed" && !running ? () => void retry(s.key) : undefined,
                  retryLabel: t("wizard.stage.retry"),
                }))}
              />
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
          <Button type="button" variant="outline" onClick={() => requestLeave("leave")}>
            {t("wizard.leave")}
          </Button>
        ) : (
          <Button type="button" variant="outline" onClick={goBack} disabled={running || outcome === "done"}>
            {t("wizard.back")}
          </Button>
        )}
        {step !== "review" ? (
          <Button type="button" onClick={() => void goNext()} disabled={full} loading={checkingRef}>
            {t("wizard.next")}
          </Button>
        ) : outcome === "idle" ? (
          <Button type="button" onClick={() => void runAll()} disabled={full} loading={running}>
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

function PlaceholderField({ ph, value, error, onChange }: { ph: SeedPlaceholder; value: string; error?: string; onChange: (v: string) => void }) {
  const t = useT();
  const id = `ph-${ph.key.replace(/\W/g, "-")}`;
  const hintId = `${id}-hint`;
  const label = placeholderLabel(t, ph.key);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label htmlFor={id} className="min-w-0">
        <span className="min-w-0 truncate" title={label}>
          {label}
        </span>
        {!ph.required ? <span className="ml-1 font-normal text-muted-foreground">({t("wizard.placeholders.optional")})</span> : null}
        {ph.secret ? <span className="ml-1 font-normal text-warning">· {t("wizard.placeholders.secret")}</span> : null}
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
      <p id={hintId} className="min-w-0 truncate text-xs text-muted-foreground" title={label}>
        {ph.kind === "list"
          ? t("wizard.placeholders.list")
          : ph.example
            ? t("wizard.placeholders.default", { value: ph.example })
            : placeholderLabel(t, ph.key)}
      </p>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
