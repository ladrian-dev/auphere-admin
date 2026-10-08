"use client";

import * as React from "react";
import { toast } from "sonner";

import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  Input,
  NativeSelect,
  Skeleton,
} from "@nexus/ui";

import { createAgentAction } from "@/app/(console)/clients/[ref]/agents/actions";
import { listSeedTemplatesAction } from "@/app/(console)/clients/new/actions";
import {
  cleanPlaceholders,
  missingPlaceholders,
  requiredPlaceholders,
  resolvePlaceholderExtra,
  resolvePlaceholderLabel,
} from "@/app/(console)/clients/new/wizard-state";
import { HoursField } from "@/components/clients/new/hours-field";
import { defaultHours, hoursLabel, type Hours } from "@/components/clients/new/hours";
import { useT } from "@/i18n/client";
import { messages, type MessageKey } from "@/i18n/messages";
import { actionErrorText } from "@/lib/action-error";
import type { ClientAgent } from "@/lib/backend";
import type { SeedTemplate } from "@/lib/backend/onboarding";

/** The hours are chosen with their own control, as in the new-client wizard. */
const HOURS_KEY = "tenant.business_hours_label";

/**
 * «Nuevo agente» (spec 030, R14.1): a name, a template and only what the
 * template cannot render without — like the new-client wizard, minus the
 * client. The agent is born as a draft: it answers on no number until it is
 * published and given one, and the dialog says so before anyone wonders.
 */
export function NewAgentDialog({
  refId,
  open,
  onOpenChange,
  onCreated,
}: {
  refId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (agent: ClientAgent) => void;
}) {
  const t = useT();
  const [templates, setTemplates] = React.useState<SeedTemplate[] | null>(null);
  const [failed, setFailed] = React.useState(false);
  // Bumped by «Reintentar»: reading the templates again is a new attempt.
  const [attempt, setAttempt] = React.useState(0);
  const [name, setName] = React.useState("");
  const [template, setTemplate] = React.useState("");
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [hours, setHours] = React.useState<Hours>(() => defaultHours());
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [pending, startTransition] = React.useTransition();

  // The templates are read when the dialog opens: most visits to the record
  // never create an agent.
  React.useEffect(() => {
    if (!open || templates) return;
    let live = true;
    void listSeedTemplatesAction().then((r) => {
      if (!live) return;
      if (r.ok) {
        setTemplates(r.data);
        setFailed(false);
        setTemplate((current) => current || r.data[0]?.name || "");
      } else {
        setFailed(true);
      }
    });
    return () => {
      live = false;
    };
  }, [open, templates, attempt]);

  const chosen = templates?.find((x) => x.name === template) ?? null;
  const needed = requiredPlaceholders(chosen);
  const label = (key: string) => resolvePlaceholderLabel(key, messages, (k) => t(k as MessageKey));
  const extra = (key: string, suffix: "hint" | "eg") => resolvePlaceholderExtra(key, suffix, messages, (k) => t(k as MessageKey));

  function close(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName("");
      setValues({});
      setErrors({});
      // A failed read is not remembered: reopening reads again.
      if (failed) {
        setFailed(false);
        setAttempt((n) => n + 1);
      }
    }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const placeholders = {
      ...values,
      ...(needed.some((p) => p.key === HOURS_KEY) ? { [HOURS_KEY]: hoursLabel(hours) } : {}),
    };
    const found: Record<string, string> = {};
    if (!name.trim()) found.name = t("validation.required");
    if (!chosen) found.template = t("validation.required");
    for (const k of missingPlaceholders(needed, placeholders)) found[`ph:${k}`] = t("validation.required");
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    startTransition(async () => {
      const res = await createAgentAction({
        ref: refId,
        name: name.trim(),
        seed_template: template,
        placeholders: cleanPlaceholders(placeholders),
      });
      if (res.ok) {
        toast.success(t("agents.new.created", { name: res.data.name }));
        close(false);
        onCreated(res.data);
        return;
      }
      if (res.code === "name_taken") setErrors({ name: t("agents.error.name_taken") });
      else toast.error(actionErrorText(res, t));
    });
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("agents.new")}</DialogTitle>
          <DialogDescription>{t("agents.new.description")}</DialogDescription>
        </DialogHeader>
        {failed ? (
          <div className="flex flex-col items-start gap-3">
            <Alert variant="destructive" role="alert">
              <AlertDescription>{t("agents.new.templatesError")}</AlertDescription>
            </Alert>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setFailed(false);
                setAttempt((n) => n + 1);
              }}
            >
              {t("agents.new.retry")}
            </Button>
          </div>
        ) : templates === null ? (
          <div role="status" aria-label={t("agents.new.loading")} className="flex flex-col gap-4">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : templates.length === 0 ? (
          <p role="status" className="text-sm text-muted-foreground text-pretty">
            {t("agents.new.noTemplates")}
          </p>
        ) : (
          <form onSubmit={submit} noValidate className="flex min-w-0 flex-col gap-4">
            <Field label={t("agents.new.name")} hint={t("agents.new.name.hint")} error={errors.name}>
              {(a11y) => <Input {...a11y} value={name} maxLength={80} autoComplete="off" onChange={(e) => setName(e.target.value)} />}
            </Field>
            <Field label={t("agents.new.template")} error={errors.template}>
              {(a11y) => (
                <NativeSelect
                  {...a11y}
                  wrapperClassName="w-full"
                  value={template}
                  onChange={(e) => {
                    setTemplate(e.target.value);
                    setValues({});
                  }}
                >
                  {templates.map((x) => (
                    <option key={x.name} value={x.name}>
                      {x.display_name}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            {needed
              .filter((ph) => ph.key !== HOURS_KEY)
              .map((ph) => (
                <Field key={ph.key} label={label(ph.key)} hint={extra(ph.key, "hint")} error={errors[`ph:${ph.key}`]}>
                  {(a11y) => (
                    <Input
                      {...a11y}
                      value={values[ph.key] ?? ""}
                      placeholder={extra(ph.key, "eg") ?? ph.example ?? undefined}
                      onChange={(e) => setValues((v) => ({ ...v, [ph.key]: e.target.value }))}
                    />
                  )}
                </Field>
              ))}
            {needed.some((ph) => ph.key === HOURS_KEY) ? <HoursField value={hours} onChange={setHours} /> : null}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => close(false)} disabled={pending}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" loading={pending}>
                {t("agents.new.create")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
