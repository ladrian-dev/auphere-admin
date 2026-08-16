"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, ShieldAlert, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useFieldArray, useForm, useWatch, type Resolver } from "react-hook-form";
import { toast } from "sonner";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
  formatDateTime,
} from "@nexus/ui";

import { saveAgentSettingsAction } from "@/app/(console)/clients/[ref]/agent/actions";
import { useLocale, useT } from "@/i18n/client";
import {
  ESCALATION_TRIGGERS,
  TONES,
  type AgentSettingsOut,
  type ConsolePolicy,
  type EscalationTrigger,
  type Tone,
  type Weekday,
} from "@/lib/backend/agent-tools-types";

import { buildConsolePolicySchema, groupSlotsByDay, parseLanguageList } from "./settings-schema";

type Props = { refId: string; data: AgentSettingsOut; canWrite: boolean; actor: string };

/**
 * Structured editor of `policies.console` (CP-11 / CP-31). react-hook-form +
 * the same Zod schema the Server Action uses. Read-only roles see the form
 * disabled with a hint. Save → draft toast with a "publish" link.
 */
export function AgentSettingsForm({ refId, data, canWrite, actor }: Props) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const base = `/clients/${encodeURIComponent(refId)}`;

  const schema = React.useMemo(
    () =>
      buildConsolePolicySchema({
        tooLong: t("validation.tooLong"),
        time: t("agentSettings.validation.time"),
        openBeforeClose: t("agentSettings.validation.openBeforeClose"),
        timezone: t("agentSettings.validation.timezone"),
        turnsRequired: t("agentSettings.validation.turnsRequired"),
        language: t("agentSettings.validation.language"),
      }),
    [t],
  );
  const form = useForm<ConsolePolicy>({ resolver: zodResolver(schema) as unknown as Resolver<ConsolePolicy>, defaultValues: data.settings, disabled: !canWrite });
  const weekly = useFieldArray({ control: form.control, name: "schedule.weekly" });
  const weeklyValues = useWatch({ control: form.control, name: "schedule.weekly" });
  const disclosureEnabled = useWatch({ control: form.control, name: "ai_disclosure.enabled" });
  const escalationEnabled = useWatch({ control: form.control, name: "escalation.enabled" });
  const triggers = useWatch({ control: form.control, name: "escalation.triggers" });
  const [allowedText, setAllowedText] = React.useState(data.settings.languages.allowed.join(", "));

  const toneItems = React.useMemo(
    () => TONES.map((v) => ({ value: v, label: t(`agentSettings.tone.${v}`) })),
    [t],
  );

  function onSubmit(values: ConsolePolicy) {
    const changed = values.ai_disclosure.enabled !== data.settings.ai_disclosure.enabled;
    const settings: ConsolePolicy = changed
      ? { ...values, ai_disclosure: { ...values.ai_disclosure, decided_by: actor, decided_at: new Date().toISOString() } }
      : values;
    startTransition(async () => {
      const res = await saveAgentSettingsAction({ ref: refId, settings });
      if (!res.ok) return void toast.error(res.message);
      const v = res.data.version ?? 0;
      toast.success(t(res.data.draft_created ? "agentSettings.draft.saved" : "agentSettings.draft.updated", { v }), {
        action: { label: t("agentSettings.draft.publishLink"), onClick: () => router.push(`${base}/agent`) },
      });
      form.reset(res.data.settings);
      setAllowedText(res.data.settings.languages.allowed.join(", "));
      router.refresh();
    });
  }

  const context =
    data.version_status === "staged" && data.version != null
      ? data.active_version != null
        ? t("agentSettings.draft.editing", { v: data.version, a: data.active_version })
        : t("agentSettings.draft.editingNoActive", { v: data.version })
      : data.active_version != null
        ? t("agentSettings.draft.fromActive", { a: data.active_version })
        : t("agentSettings.draft.none");

  return (
    <Form {...form}>
      <form
        noValidate
        aria-busy={pending}
        className="flex min-w-0 flex-col gap-4"
        onSubmit={form.handleSubmit(onSubmit, () => toast.error(t("agentSettings.fixErrors")))}
      >
        <p className="text-xs text-muted-foreground">{context}</p>
        {!canWrite ? <p className="text-xs text-muted-foreground">{t("agentSettings.readonly")}</p> : null}

        {/* identity */}
        <Card>
          <CardHeader>
            <CardTitle>{t("agentSettings.section.identity")}</CardTitle>
            <CardDescription>{t("agentSettings.section.identity.help")}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <FormField
              control={form.control}
              name="identity.name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.identity.name")}</FormLabel>
                  <FormControl>
                    <Input maxLength={120} autoComplete="off" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="identity.persona"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.identity.persona")}</FormLabel>
                  <FormControl>
                    <Textarea maxLength={2000} className="min-h-24" {...field} />
                  </FormControl>
                  <FormDescription>{t("agentSettings.identity.persona.help")}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        {/* tone + objective */}
        <Card>
          <CardHeader>
            <CardTitle>{t("agentSettings.section.tone")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <FormField
              control={form.control}
              name="tone.style"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.tone.style")}</FormLabel>
                  <Select items={toneItems} value={field.value} onValueChange={(v) => field.onChange(v as Tone)} disabled={!canWrite}>
                    <FormControl>
                      <SelectTrigger aria-label={t("agentSettings.tone.style")}>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {toneItems.map((it) => (
                        <SelectItem key={it.value} value={it.value}>
                          {it.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="tone.guidance"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.tone.guidance")}</FormLabel>
                  <FormControl>
                    <Textarea maxLength={2000} className="min-h-20" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="objective"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.section.objective")}</FormLabel>
                  <FormControl>
                    <Textarea maxLength={4000} className="min-h-24" {...field} />
                  </FormControl>
                  <FormDescription>{t("agentSettings.objective.help")}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        {/* schedule */}
        <Card>
          <CardHeader>
            <CardTitle>{t("agentSettings.section.schedule")}</CardTitle>
            <CardDescription>{t("agentSettings.schedule.help")}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <FormField
              control={form.control}
              name="schedule.timezone"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.schedule.timezone")}</FormLabel>
                  <FormControl>
                    <Input className="font-mono" maxLength={64} placeholder="Europe/Madrid" autoComplete="off" spellCheck={false} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <ol className="grid gap-3" aria-label={t("agentSettings.section.schedule")}>
              {groupSlotsByDay(weeklyValues ?? []).map(({ day, slots }) => (
                <li key={day} className="grid gap-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium">{t(`agentSettings.day.${day}`)}</span>
                    {slots.length === 0 ? <span className="text-xs text-muted-foreground">{t("agentSettings.schedule.closed")}</span> : null}
                    {canWrite ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        disabled={(weeklyValues?.length ?? 0) >= 21}
                        onClick={() => weekly.append({ day, open: "09:00", close: "18:00" })}
                        aria-label={`${t("agentSettings.schedule.addSlot")} · ${t(`agentSettings.day.${day}`)}`}
                      >
                        <Plus aria-hidden="true" />
                        {t("agentSettings.schedule.addSlot")}
                      </Button>
                    ) : null}
                  </div>
                  {slots.map(({ index }) => (
                    <SlotRow key={weekly.fields[index]?.id ?? index} index={index} day={day} canWrite={canWrite} onRemove={() => weekly.remove(index)} />
                  ))}
                </li>
              ))}
            </ol>
            <p className="text-xs text-muted-foreground">{t("agentSettings.schedule.max")}</p>
            <FormField
              control={form.control}
              name="schedule.closed_message"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.schedule.closedMessage")}</FormLabel>
                  <FormControl>
                    <Textarea maxLength={1000} className="min-h-16" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        {/* languages */}
        <Card>
          <CardHeader>
            <CardTitle>{t("agentSettings.section.languages")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <FormField
              control={form.control}
              name="languages.primary"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.languages.primary")}</FormLabel>
                  <FormControl>
                    <Input className="font-mono" maxLength={8} placeholder="es" autoComplete="off" {...field} onChange={(e) => field.onChange(e.target.value.toLowerCase())} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="languages.allowed"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.languages.allowed")}</FormLabel>
                  <FormControl>
                    <Input
                      className="font-mono"
                      placeholder="es, en, pt"
                      autoComplete="off"
                      name={field.name}
                      ref={field.ref}
                      disabled={field.disabled}
                      value={allowedText}
                      onBlur={field.onBlur}
                      onChange={(e) => {
                        setAllowedText(e.target.value);
                        field.onChange(parseLanguageList(e.target.value));
                      }}
                    />
                  </FormControl>
                  <FormDescription>{t("agentSettings.languages.allowed.help")}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        {/* escalation */}
        <Card>
          <CardHeader>
            <CardTitle>{t("agentSettings.section.escalation")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <FormField
              control={form.control}
              name="escalation.enabled"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2">
                  <FormControl>
                    <Checkbox checked={field.value} onCheckedChange={(c) => field.onChange(c)} disabled={field.disabled} />
                  </FormControl>
                  <FormLabel className="font-normal">{t("agentSettings.escalation.enabled")}</FormLabel>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="escalation.triggers"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.escalation.triggers")}</FormLabel>
                  <div className="grid gap-2" role="group" aria-label={t("agentSettings.escalation.triggers")}>
                    {ESCALATION_TRIGGERS.map((trigger) => {
                      const id = `trigger-${trigger}`;
                      const on = field.value.includes(trigger);
                      return (
                        <div key={trigger} className="flex items-center gap-2">
                          <Checkbox
                            id={id}
                            checked={on}
                            disabled={!canWrite || !escalationEnabled}
                            onCheckedChange={(c) => field.onChange(toggle(field.value, trigger, c))}
                          />
                          <Label htmlFor={id} className="font-normal">
                            {t(`agentSettings.escalation.trigger.${trigger}`)}
                          </Label>
                        </div>
                      );
                    })}
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="escalation.after_n_turns"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.escalation.afterNTurns")}</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={100}
                      className="max-w-32 tabular-nums"
                      name={field.name}
                      ref={field.ref}
                      onBlur={field.onBlur}
                      disabled={field.disabled || !escalationEnabled || !triggers.includes("after_n_turns")}
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(e.target.value === "" ? null : Number(e.target.value))}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="escalation.handoff_message"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.escalation.handoff")}</FormLabel>
                  <FormControl>
                    <Textarea maxLength={1000} className="min-h-16" disabled={field.disabled || !escalationEnabled} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        {/* AI disclosure */}
        <Card>
          <CardHeader>
            <CardTitle>{t("agentSettings.section.aiDisclosure")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <FormField
              control={form.control}
              name="ai_disclosure.enabled"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2">
                  <FormControl>
                    <Checkbox checked={field.value} onCheckedChange={(c) => field.onChange(c)} disabled={field.disabled} aria-describedby="ai-disclosure-warning" />
                  </FormControl>
                  <FormLabel className="font-normal">{t("agentSettings.aiDisclosure.enabled")}</FormLabel>
                </FormItem>
              )}
            />
            {!disclosureEnabled ? (
              <Alert variant="destructive" id="ai-disclosure-warning">
                <ShieldAlert aria-hidden="true" />
                <AlertTitle>{t("agentSettings.aiDisclosure.warning.title")}</AlertTitle>
                <AlertDescription>{t("agentSettings.aiDisclosure.warning.body")}</AlertDescription>
              </Alert>
            ) : null}
            <FormField
              control={form.control}
              name="ai_disclosure.disclosure_message"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("agentSettings.aiDisclosure.message")}</FormLabel>
                  <FormControl>
                    <Textarea maxLength={500} className="min-h-16" disabled={field.disabled || !disclosureEnabled} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {data.settings.ai_disclosure.decided_by && data.settings.ai_disclosure.decided_at ? (
              <p className="min-w-0 truncate text-xs text-muted-foreground" title={data.settings.ai_disclosure.decided_by}>
                {t("agentSettings.aiDisclosure.decided", {
                  who: data.settings.ai_disclosure.decided_by.replace(/^console:/, ""),
                  when: formatDateTime(data.settings.ai_disclosure.decided_at, locale),
                })}
              </p>
            ) : null}
          </CardContent>
        </Card>

        {canWrite ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={pending || !form.formState.isDirty}>
              {t("agentSettings.save")}
            </Button>
            <Link href={`${base}/agent`} className="text-sm text-muted-foreground underline-offset-4 hover:underline">
              {t("agentSettings.draft.publishLink")}
            </Link>
          </div>
        ) : null}
      </form>
    </Form>
  );
}

function toggle(list: EscalationTrigger[], item: EscalationTrigger, on: boolean): EscalationTrigger[] {
  const set = new Set(list);
  if (on) set.add(item);
  else set.delete(item);
  return ESCALATION_TRIGGERS.filter((x) => set.has(x));
}

function SlotRow({ index, day, canWrite, onRemove }: { index: number; day: Weekday; canWrite: boolean; onRemove: () => void }) {
  const t = useT();
  const dayLabel = t(`agentSettings.day.${day}`);
  return (
    <div className="flex flex-wrap items-start gap-2">
      <FormField
        name={`schedule.weekly.${index}.open` as const}
        render={({ field }) => (
          <FormItem className="min-w-0">
            <FormLabel className="sr-only">{`${dayLabel} · ${t("agentSettings.schedule.open")}`}</FormLabel>
            <FormControl>
              <Input type="time" step={60} className="w-32 font-mono tabular-nums" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <span className="pt-2 text-xs text-muted-foreground" aria-hidden="true">
        –
      </span>
      <FormField
        name={`schedule.weekly.${index}.close` as const}
        render={({ field }) => (
          <FormItem className="min-w-0">
            <FormLabel className="sr-only">{`${dayLabel} · ${t("agentSettings.schedule.close")}`}</FormLabel>
            <FormControl>
              <Input type="time" step={60} className="w-32 font-mono tabular-nums" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      {canWrite ? (
        <Button type="button" variant="ghost" size="icon-sm" onClick={onRemove} aria-label={`${t("agentSettings.schedule.removeSlot")} · ${dayLabel}`}>
          <X aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  );
}
