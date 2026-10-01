"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  NativeSelect,
  Textarea,
  cn,
} from "@nexus/ui";

import { createTemplateAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";

import {
  LANGUAGES,
  LIMITS,
  SUGGESTED_VARIABLES,
  bodyIssues,
  buttonIssue,
  finalTemplateName,
  insertVariable,
  missingPieces,
  previewParts,
  templateVariables,
  toTemplateName,
  type BodyIssue,
  type ButtonDraft,
} from "./template-rules";

type Category = "UTILITY" | "MARKETING" | "AUTHENTICATION";
const CATEGORIES: Category[] = ["UTILITY", "MARKETING", "AUTHENTICATION"];

function issueText(t: ReturnType<typeof useT>, issue: BodyIssue): string {
  switch (issue.code) {
    case "bad_variable":
      return t("tpl.issue.bad_variable", { text: issue.text });
    case "positional_gap":
      return t("tpl.issue.positional_gap", { n: issue.missing });
    default:
      return t(`tpl.issue.${issue.code}` as MessageKey);
  }
}

/** A character counter that turns amber near the limit. */
function Counter({ value, max }: { value: string; max: number }) {
  const t = useT();
  const near = value.length > max * 0.9;
  return (
    <span className={cn("text-xs tabular-nums", near ? "text-status-warning" : "text-muted-foreground")} aria-live="polite">
      {t("tpl.compose.counter", { n: value.length, max })}
    </span>
  );
}

/**
 * The WhatsApp template composer (spec 025 follow-up, 2026-10-01).
 *
 * One screen, two columns: what to write on the left, and on the right the
 * message as the customer will see it, updated on every keystroke with the
 * examples in place of the variables. Every rule Meta enforces is said in
 * words under the field it concerns, before sending; and next to the send
 * button the composer says what is still missing instead of just greying
 * it out.
 */
export function TemplateComposer({ refId, open, onOpenChange }: { refId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [category, setCategory] = React.useState<Category>("UTILITY");
  const [name, setName] = React.useState("");
  const [language, setLanguage] = React.useState("es");
  const [header, setHeader] = React.useState("");
  const [body, setBody] = React.useState("");
  const [footer, setFooter] = React.useState("");
  const [buttons, setButtons] = React.useState<ButtonDraft[]>([]);
  const [examples, setExamples] = React.useState<Record<string, string>>({});
  const [customVar, setCustomVar] = React.useState("");
  const [serverError, setServerError] = React.useState<string | null>(null);
  const [touched, setTouched] = React.useState(false);
  const bodyRef = React.useRef<HTMLTextAreaElement>(null);

  const variables = templateVariables(body);
  const issues = bodyIssues(body);
  const missing = missingPieces({ name, body, examples, buttons });
  const ready = missing.length === 0;

  function reset() {
    setCategory("UTILITY");
    setName("");
    setLanguage("es");
    setHeader("");
    setBody("");
    setFooter("");
    setButtons([]);
    setExamples({});
    setCustomVar("");
    setServerError(null);
    setTouched(false);
  }

  function addVariable(raw: string) {
    const varName = toTemplateName(raw).replace(/_+$/, "");
    if (!varName) return;
    const el = bodyRef.current;
    const cursor = el ? el.selectionStart : body.length;
    const next = insertVariable(body, cursor, varName);
    setBody(next.text.slice(0, LIMITS.body));
    setCustomVar("");
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(next.cursor, next.cursor);
    });
  }

  function updateButton(i: number, patch: Partial<ButtonDraft>) {
    setButtons((prev) => prev.map((b, j) => (j === i ? { ...b, ...patch } : b)));
  }

  function submit() {
    setTouched(true);
    if (!ready) return;
    setServerError(null);
    startTransition(async () => {
      const res = await createTemplateAction({
        ref: refId,
        name: finalTemplateName(name),
        language,
        category,
        header_text: header.trim() || undefined,
        body_text: body.trim(),
        footer_text: footer.trim() || undefined,
        buttons: buttons.map((b) => ({
          type: b.type,
          label: b.label.trim(),
          url: b.type === "URL" ? b.url?.trim() : undefined,
          phone_number: b.type === "PHONE_NUMBER" ? b.phone_number?.replace(/[\s-]/g, "") : undefined,
        })),
        examples: Object.fromEntries(variables.map((v) => [v, (examples[v] ?? "").trim()])),
      });
      if (!res.ok) return void setServerError(res.message);
      toast.success(t("tpl.created"));
      reset();
      onOpenChange(false);
      router.refresh();
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>{t("tpl.new")}</DialogTitle>
          <DialogDescription>{t("tpl.compose.intro")}</DialogDescription>
        </DialogHeader>

        <form
          noValidate
          className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="flex min-w-0 flex-col gap-6">
            {/* 1 · What it is for */}
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium">{t("tpl.compose.purpose")}</legend>
              <div role="radiogroup" aria-label={t("tpl.compose.purpose")} className="grid gap-2 sm:grid-cols-3">
                {CATEGORIES.map((c) => {
                  const selected = category === c;
                  return (
                    <button
                      key={c}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setCategory(c)}
                      className={cn(
                        "flex flex-col items-start gap-1 rounded-md border p-3 text-left text-sm transition-colors",
                        selected ? "border-foreground" : "border-border hover:border-foreground/40",
                      )}
                    >
                      <span className="font-medium">{t(`tpl.category.${c}` as MessageKey)}</span>
                      <span className="text-xs text-muted-foreground">{t(`tpl.category.${c}.help` as MessageKey)}</span>
                    </button>
                  );
                })}
              </div>
            </fieldset>

            {/* 2 · Name and language */}
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem]">
              <div className="flex flex-col gap-1">
                <Label htmlFor="tpl-name">{t("tpl.compose.name")}</Label>
                <Input
                  id="tpl-name"
                  value={name}
                  maxLength={LIMITS.name}
                  autoComplete="off"
                  placeholder={t("tpl.compose.name.eg")}
                  onChange={(e) => setName(toTemplateName(e.target.value))}
                  aria-invalid={touched && !finalTemplateName(name) ? true : undefined}
                  className="font-mono"
                />
                <p className="text-xs text-muted-foreground">{t("tpl.compose.name.help")}</p>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="tpl-lang">{t("tpl.form.language")}</Label>
                <NativeSelect id="tpl-lang" wrapperClassName="w-full" value={language} onChange={(e) => setLanguage(e.target.value)}>
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.label}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            </div>

            {/* 3 · The message */}
            <fieldset className="flex flex-col gap-3">
              <legend className="mb-1 text-sm font-medium">{t("tpl.compose.message")}</legend>
              <div className="flex flex-col gap-1">
                <div className="flex items-baseline justify-between gap-2">
                  <Label htmlFor="tpl-header">{t("tpl.form.header")}</Label>
                  <Counter value={header} max={LIMITS.header} />
                </div>
                <Input id="tpl-header" value={header} maxLength={LIMITS.header} onChange={(e) => setHeader(e.target.value)} />
              </div>

              <div className="flex flex-col gap-1">
                <div className="flex items-baseline justify-between gap-2">
                  <Label htmlFor="tpl-body">{t("tpl.form.body")}</Label>
                  <Counter value={body} max={LIMITS.body} />
                </div>
                <Textarea
                  id="tpl-body"
                  ref={bodyRef}
                  value={body}
                  maxLength={LIMITS.body}
                  rows={7}
                  placeholder={t("tpl.compose.body.eg")}
                  onChange={(e) => setBody(e.target.value)}
                  aria-invalid={(touched && !body.trim()) || issues.length > 0 ? true : undefined}
                  aria-describedby="tpl-body-help"
                />
                <p id="tpl-body-help" className="text-xs text-muted-foreground">
                  {t("tpl.form.body.help")}
                </p>
                <div className="flex flex-wrap items-center gap-2" aria-label={t("tpl.compose.insert")}>
                  <span className="text-xs text-muted-foreground">{t("tpl.compose.insert")}</span>
                  {SUGGESTED_VARIABLES.map((v) => (
                    <Button key={v} type="button" variant="outline" size="sm" onClick={() => addVariable(v)}>
                      {`{{${v}}}`}
                    </Button>
                  ))}
                  <div className="flex items-center gap-1">
                    <Input
                      aria-label={t("tpl.compose.variable.other")}
                      placeholder={t("tpl.compose.variable.other")}
                      value={customVar}
                      maxLength={40}
                      className="h-8 w-36 font-mono text-xs"
                      onChange={(e) => setCustomVar(toTemplateName(e.target.value))}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addVariable(customVar);
                        }
                      }}
                    />
                    <Button type="button" variant="ghost" size="sm" disabled={!customVar} onClick={() => addVariable(customVar)}>
                      <Plus aria-hidden="true" />
                      {t("tpl.compose.variable.add")}
                    </Button>
                  </div>
                </div>
                {issues.length > 0 ? (
                  <ul className="flex flex-col gap-1" role="alert">
                    {issues.map((issue) => (
                      <li key={`${issue.code}-${"text" in issue ? issue.text : ""}`} className="text-xs text-destructive">
                        {issueText(t, issue)}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              {variables.length > 0 ? (
                <div className="flex flex-col gap-2 rounded-md bg-muted/50 p-3" data-slot="template-examples">
                  <p className="text-sm font-medium">{t("tpl.form.examples")}</p>
                  <p className="text-xs text-muted-foreground">{t("tpl.form.examples.help")}</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {variables.map((v) => (
                      <div key={v} className="flex flex-col gap-1">
                        <Label htmlFor={`tpl-ex-${v}`} className="font-mono text-xs">
                          {t("tpl.form.example", { name: v })}
                        </Label>
                        <Input
                          id={`tpl-ex-${v}`}
                          value={examples[v] ?? ""}
                          maxLength={LIMITS.example}
                          aria-invalid={touched && !(examples[v] ?? "").trim() ? true : undefined}
                          onChange={(e) => setExamples((prev) => ({ ...prev, [v]: e.target.value }))}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="flex flex-col gap-1">
                <div className="flex items-baseline justify-between gap-2">
                  <Label htmlFor="tpl-footer">{t("tpl.form.footer")}</Label>
                  <Counter value={footer} max={LIMITS.footer} />
                </div>
                <Input id="tpl-footer" value={footer} maxLength={LIMITS.footer} onChange={(e) => setFooter(e.target.value)} />
              </div>
            </fieldset>

            {/* 4 · Buttons */}
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium">{t("tpl.compose.buttons")}</legend>
              <p className="text-xs text-muted-foreground">{t("tpl.compose.buttons.help")}</p>
              {buttons.map((b, i) => {
                const problem = touched || b.label ? buttonIssue(b) : null;
                return (
                  <div key={i} className="flex flex-col gap-1 rounded-md border border-border p-2">
                    <div className="grid gap-2 sm:grid-cols-[10rem_minmax(0,1fr)_auto]">
                      <NativeSelect
                        aria-label={t("tpl.compose.button.type", { n: i + 1 })}
                        value={b.type}
                        onChange={(e) => updateButton(i, { type: e.target.value as ButtonDraft["type"] })}
                      >
                        {(["QUICK_REPLY", "URL", "PHONE_NUMBER"] as const).map((k) => (
                          <option key={k} value={k}>
                            {t(`tpl.form.button.${k}` as MessageKey)}
                          </option>
                        ))}
                      </NativeSelect>
                      <Input
                        aria-label={t("tpl.compose.button.label", { n: i + 1 })}
                        placeholder={t("tpl.form.button.label")}
                        value={b.label}
                        maxLength={LIMITS.button}
                        onChange={(e) => updateButton(i, { label: e.target.value })}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t("tpl.compose.button.remove", { n: i + 1 })}
                        onClick={() => setButtons((prev) => prev.filter((_, j) => j !== i))}
                      >
                        <Trash2 aria-hidden="true" />
                      </Button>
                    </div>
                    {b.type === "URL" ? (
                      <Input
                        aria-label={t("tpl.compose.button.url", { n: i + 1 })}
                        placeholder="https://"
                        inputMode="url"
                        value={b.url ?? ""}
                        onChange={(e) => updateButton(i, { url: e.target.value })}
                      />
                    ) : null}
                    {b.type === "PHONE_NUMBER" ? (
                      <Input
                        aria-label={t("tpl.compose.button.phone", { n: i + 1 })}
                        placeholder="+56 9 1234 5678"
                        inputMode="tel"
                        value={b.phone_number ?? ""}
                        onChange={(e) => updateButton(i, { phone_number: e.target.value })}
                      />
                    ) : null}
                    {problem ? (
                      <p className="text-xs text-destructive" role="alert">
                        {t(`tpl.button.${problem}` as MessageKey)}
                      </p>
                    ) : null}
                  </div>
                );
              })}
              {buttons.length < LIMITS.buttons ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="self-start"
                  onClick={() => setButtons((prev) => [...prev, { type: "QUICK_REPLY", label: "" }])}
                >
                  <Plus aria-hidden="true" />
                  {t("tpl.form.button.add")}
                </Button>
              ) : null}
            </fieldset>
          </div>

          {/* Preview */}
          <aside className="flex min-w-0 flex-col gap-2 lg:sticky lg:top-0 lg:self-start" aria-label={t("tpl.compose.preview")}>
            <p className="text-sm font-medium">{t("tpl.compose.preview")}</p>
            <TemplatePreview header={header} body={body} footer={footer} buttons={buttons} examples={examples} />
          </aside>

          <div className="flex flex-col gap-3 lg:col-span-2">
            {serverError ? (
              <Callout tone="danger" title={t("tpl.compose.error")}>
                {serverError}
              </Callout>
            ) : null}
            <DialogFooter className="flex-wrap items-center gap-3 sm:justify-between">
              <p className="text-xs text-muted-foreground" aria-live="polite">
                {ready
                  ? t("tpl.compose.ready")
                  : t("tpl.compose.missing", { list: missing.map((m) => t(`tpl.missing.${m}` as MessageKey)).join(", ") })}
              </p>
              <div className="flex gap-2">
                <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
                  {t("common.cancel")}
                </Button>
                <Button type="submit" loading={pending} disabled={pending || !ready}>
                  {t("tpl.form.submit")}
                </Button>
              </div>
            </DialogFooter>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The message as WhatsApp shows it, with the examples in place of the variables. */
export function TemplatePreview({
  header,
  body,
  footer,
  buttons,
  examples,
}: {
  header: string;
  body: string;
  footer: string;
  buttons: ButtonDraft[];
  examples: Record<string, string>;
}) {
  const t = useT();
  const empty = !header.trim() && !body.trim() && !footer.trim();
  return (
    <div className="rounded-md bg-muted p-3" data-slot="template-preview">
      {empty ? (
        <p className="py-8 text-center text-xs text-muted-foreground">{t("tpl.compose.preview.empty")}</p>
      ) : (
        <div className="flex flex-col gap-1">
          <div className="max-w-full rounded-md bg-background px-3 py-2 text-sm shadow-sm ring-1 ring-foreground/5">
            {header.trim() ? <p className="mb-1 font-semibold break-words">{header}</p> : null}
            <p className="whitespace-pre-wrap break-words">
              {previewParts(body, examples).map((part, i) =>
                part.kind === "text" ? (
                  <React.Fragment key={i}>{part.value}</React.Fragment>
                ) : part.value ? (
                  <span key={i} className="rounded-sm bg-primary/10 px-1">
                    {part.value}
                  </span>
                ) : (
                  <span key={i} className="rounded-sm bg-status-warning/15 px-1 font-mono text-xs">
                    {`{{${part.name}}}`}
                  </span>
                ),
              )}
            </p>
            {footer.trim() ? <p className="mt-1 text-xs text-muted-foreground break-words">{footer}</p> : null}
          </div>
          {buttons
            .filter((b) => b.label.trim())
            .map((b, i) => (
              <div key={i} className="rounded-md bg-background px-3 py-2 text-center text-sm font-medium text-primary shadow-sm ring-1 ring-foreground/5">
                {b.label}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
