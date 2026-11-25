"use client";

import { Plus, Trash2 } from "lucide-react";
import * as React from "react";

import {
  LANGUAGES,
  LIMITS,
  OTP_LIMITS,
  SUGGESTED_VARIABLES,
  bodyIssues,
  buttonIssue,
  defaultOtp,
  finalTemplateName,
  insertVariable,
  isSpanishTemplate,
  languageLabel,
  missingOtpPieces,
  missingPieces,
  otpMinutes,
  otpPreviewText,
  previewParts,
  systemVariableIssues,
  templateVariables,
  toSubmission,
  toTemplateName,
  type BodyIssue,
  type ButtonDraft,
  type ButtonIssue,
  type MissingPiece,
  type OtpDraft,
  type SystemVariables,
  type TemplateConfirmReason,
  type TemplateDraft,
  type TemplateSubmission,
} from "../lib/template-rules";
import { cn } from "../lib/utils";
import { Button } from "./button";
import { Callout } from "./callout";
import { ConfirmDialog } from "./confirm-dialog";
import { DialogFooter } from "./dialog";
import { Input } from "./input";
import { Label } from "./label";
import { NativeSelect } from "./native-select";
import { Textarea } from "./textarea";

/**
 * El editor de plantillas de WhatsApp (spec 075, R9). Uno solo para la consola
 * y para el panel: lo que se escribe a la izquierda y, a la derecha, el mensaje
 * como lo verá el cliente, con los ejemplos en lugar de las variables. Cada
 * regla de Meta se dice bajo su campo antes de enviar, y junto al botón se dice
 * qué falta en vez de solo apagarlo.
 *
 * **No sabe dónde vive.** Ni la acción de servidor, ni el diálogo que lo
 * envuelve, ni el idioma de la pantalla: los textos le llegan por `labels`, y lo
 * escrito sale por `onSubmit`. Quien lo usa pone el diálogo, el toast y lo que
 * se hace con la respuesta.
 *
 * **Al editar**, el nombre y el idioma son el título y no campos: Meta no deja
 * cambiarlos (1.3). Con `categoryLocked` la categoría no se pinta: no es un
 * control apagado, es que no existe (2.3).
 *
 * **Autenticación** (077; aquí desde la 075, requisito 10): Meta fija el texto,
 * así que en lugar del mensaje y los botones se eligen el botón de copiar
 * código, la caducidad y el aviso, y la vista previa es el texto fijo de Meta.
 * Solo al crear: una de autenticación no se edita (3.2).
 */

export type TemplateCategoryChoice = TemplateDraft["category"];

// Authentication is created in Meta's fixed one-time code format (077, 3.4),
// never as free text (QA 2026-10-30). It is not offered when editing: an
// authentication template is never edited here (075, 1.4 and 3.2).
const CREATE_CATEGORIES: TemplateCategoryChoice[] = ["UTILITY", "MARKETING", "AUTHENTICATION"];
const EDIT_CATEGORIES: TemplateCategoryChoice[] = ["UTILITY", "MARKETING"];

/**
 * What came of a save, as far as the editor cares. `confirmation_required`
 * opens the confirmation and, if accepted, the same draft goes again with
 * `confirm: true`; `system_variables` marks the variables in the editor.
 * Anything else the caller says through `serverError`.
 */
export type TemplateEditorOutcome =
  | { kind: "done" }
  | { kind: "confirmation_required"; reasons: TemplateConfirmReason[] }
  | { kind: "system_variables"; missing: string[]; extra: string[] }
  | { kind: "failed" };

export type TemplateEditorLabels = {
  purpose: string;
  category: (category: string) => string;
  categoryHelp: (category: string) => string;
  name: string;
  nameExample: string;
  nameHelp: string;
  language: string;
  message: string;
  header: string;
  body: string;
  bodyHelp: string;
  bodyExample: string;
  counter: (n: number, max: number) => string;
  insertVariable: string;
  otherVariable: string;
  addVariable: string;
  examples: string;
  examplesHelp: string;
  example: (name: string) => string;
  footer: string;
  buttons: string;
  buttonsHelp: string;
  buttonKind: (kind: ButtonDraft["type"]) => string;
  buttonType: (n: number) => string;
  buttonLabel: (n: number) => string;
  buttonLabelPlaceholder: string;
  buttonUrl: (n: number) => string;
  buttonPhone: (n: number) => string;
  buttonRemove: (n: number) => string;
  addButton: string;
  buttonIssue: (issue: ButtonIssue) => string;
  bodyIssue: (issue: BodyIssue) => string;
  preview: string;
  previewEmpty: string;
  /** The title of the box with what the server answered. */
  errorTitle: string;
  ready: string;
  /** «Falta el nombre, el texto del mensaje.» — the caller owns the list's grammar. */
  missing: (pieces: MissingPiece[]) => string;
  cancel: string;
  submit: string;
  /** Spec 077 (3.1): the fields of an authentication template and Meta's fixed text. */
  otp: {
    legend: string;
    intro: string;
    button: string;
    /** The copy-code button a new one starts with, in the screen's language. */
    buttonDefault: string;
    buttonHelp: string;
    minutes: string;
    minutesHelp: string;
    security: string;
    securityHelp: string;
    /** Over Meta's fixed text, which is shown in Spanish whatever the screen's language. */
    previewSpanish: string;
    /** For a template in another language: Meta writes the fixed text in it. */
    previewOther: (language: string) => string;
  };
  systemVariables: {
    title: string;
    help: (mode: SystemVariables["mode"]) => string;
    missing: (names: string[]) => string;
    extra: (names: string[]) => string;
  };
  confirm: {
    title: string;
    confirm: string;
    cancel: string;
    /** One sentence per reason; an unknown kind still gets one. */
    reason: (reason: TemplateConfirmReason) => string;
  };
};

export type TemplateEditorProps = {
  mode: "create" | "edit";
  /** Where it starts. In `edit`, its name and language are the template's. Read once (remount with a key to change it). */
  initial?: TemplateDraft | null;
  /** An approved template keeps its category (2.3): the control is not drawn. */
  categoryLocked?: boolean;
  /** A template Auphere sends by its name, and the variables it may carry (4.1). */
  systemVariables?: SystemVariables | null;
  /** The caller is saving. The editor is also busy while `onSubmit` runs. */
  pending?: boolean;
  /** What the server answered, in words. What was written stays. */
  serverError?: React.ReactNode;
  /** A button that resolves the error (e.g. «Recargar» after `template_changed`). */
  serverErrorAction?: React.ReactNode;
  onSubmit: (
    draft: TemplateSubmission,
    options: { confirm: boolean },
  ) => Promise<TemplateEditorOutcome | void> | TemplateEditorOutcome | void;
  onCancel: () => void;
  labels: TemplateEditorLabels;
  className?: string;
};

const EMPTY: TemplateDraft = {
  name: "",
  language: "es",
  category: "UTILITY",
  header: "",
  body: "",
  footer: "",
  buttons: [],
  examples: {},
};

/** A character counter that turns amber near the limit. */
function Counter({ value, max, labels }: { value: string; max: number; labels: TemplateEditorLabels }) {
  const near = value.length > max * 0.9;
  return (
    // No aria-live: a screen reader would read it on every keystroke.
    <span className={cn("text-xs tabular-nums", near ? "text-status-warning-text" : "text-muted-foreground")}>
      {labels.counter(value.length, max)}
    </span>
  );
}

export function TemplateEditor({
  mode,
  initial = null,
  categoryLocked = false,
  systemVariables = null,
  pending = false,
  serverError,
  serverErrorAction,
  onSubmit,
  onCancel,
  labels,
  className,
}: TemplateEditorProps) {
  const start = initial ?? EMPTY;
  const editing = mode === "edit";
  const [category, setCategory] = React.useState<TemplateCategoryChoice>(start.category);
  const [name, setName] = React.useState(start.name);
  const [language, setLanguage] = React.useState(start.language);
  const [header, setHeader] = React.useState(start.header);
  const [body, setBody] = React.useState(start.body);
  const [footer, setFooter] = React.useState(start.footer);
  const [buttons, setButtons] = React.useState<ButtonDraft[]>(start.buttons);
  const [examples, setExamples] = React.useState<Record<string, string>>(start.examples);
  // «Duplicar» of an authentication template brings its choices; an empty button gets the default.
  const [otp, setOtp] = React.useState<OtpDraft>(() =>
    start.otp ? { ...start.otp, buttonText: start.otp.buttonText || labels.otp.buttonDefault } : defaultOtp(labels.otp.buttonDefault),
  );
  const [customVar, setCustomVar] = React.useState("");
  const [touched, setTouched] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  // 2.2, 5.1 · The server asked to confirm: what was about to be sent, and why.
  const [confirming, setConfirming] = React.useState<{ draft: TemplateSubmission; reasons: TemplateConfirmReason[] } | null>(null);
  // 4.2, 4.3 · What the server said about the variables, until the text changes.
  const [serverVariables, setServerVariables] = React.useState<{ missing: string[]; extra: string[] } | null>(null);
  const bodyRef = React.useRef<HTMLTextAreaElement>(null);
  const formRef = React.useRef<HTMLFormElement>(null);
  const ids = React.useId();
  const id = (part: string) => `${ids}-${part}`;

  const busy = pending || submitting;
  const isAuth = category === "AUTHENTICATION";
  const categories = editing ? EDIT_CATEGORIES : CREATE_CATEGORIES;
  const variables = templateVariables(body);
  const issues = bodyIssues(body);
  // Said while typing, and it stops the save: what Auphere sends and what Meta
  // is asked to approve cannot drift apart (043, 15.8).
  const live = systemVariables ? systemVariableIssues(body, systemVariables, start.body) : { missing: [], extra: [] };
  const systemBlocked = live.missing.length > 0 || live.extra.length > 0;
  const systemIssues = {
    missing: [...new Set([...live.missing, ...(serverVariables?.missing ?? [])])],
    extra: [...new Set([...live.extra, ...(serverVariables?.extra ?? [])])],
  };
  const missing: MissingPiece[] = isAuth
    ? missingOtpPieces({ name, otp })
    : [...missingPieces({ name, body, examples, buttons }), ...(systemBlocked ? (["system_variables"] as const) : [])];
  const ready = missing.length === 0;
  const suggested = systemVariables ? systemVariables.variables : SUGGESTED_VARIABLES;
  const systemOff = systemIssues.missing.length > 0 || systemIssues.extra.length > 0;
  // What is wrong with the body is said under it and read with it.
  const bodyDescribedBy = [id("body-help"), issues.length > 0 ? id("body-issues") : null, systemVariables && systemOff ? id("system-issues") : null]
    .filter(Boolean)
    .join(" ");

  function changeBody(text: string) {
    setBody(text);
    setServerVariables(null);
  }

  function addVariable(raw: string) {
    const varName = toTemplateName(raw).replace(/_+$/, "");
    if (!varName) return;
    const el = bodyRef.current;
    const cursor = el ? el.selectionStart : body.length;
    const next = insertVariable(body, cursor, varName);
    changeBody(next.text.slice(0, LIMITS.body));
    setCustomVar("");
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(next.cursor, next.cursor);
    });
  }

  function updateButton(i: number, patch: Partial<ButtonDraft>) {
    setButtons((prev) => prev.map((b, j) => (j === i ? { ...b, ...patch } : b)));
  }

  function draft(): TemplateSubmission {
    return toSubmission({ name, language, category, header, body, footer, buttons, examples, ...(isAuth ? { otp } : {}) });
  }

  async function send(confirm: boolean, payload: TemplateSubmission = draft()) {
    setSubmitting(true);
    try {
      const outcome = await onSubmit(payload, { confirm });
      if (outcome?.kind === "confirmation_required") setConfirming({ draft: payload, reasons: outcome.reasons });
      if (outcome?.kind === "system_variables") setServerVariables({ missing: outcome.missing, extra: outcome.extra });
    } finally {
      setSubmitting(false);
    }
  }

  function submit() {
    setTouched(true);
    if (!ready) {
      // Say where: the fields mark themselves invalid once touched; focus the first.
      requestAnimationFrame(() => {
        formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
      });
      return;
    }
    void send(false);
  }

  return (
    <>
      <form
        ref={formRef}
        noValidate
        aria-busy={busy || undefined}
        className={cn("grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]", className)}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="flex min-w-0 flex-col gap-6">
          {editing ? (
            // 1.3 · Meta does not let a template change its name or language: they are its title.
            <div className="grid min-w-0 gap-1" data-testid="template-identity">
              <p className="font-mono text-sm font-medium break-all">{start.name}</p>
              <p className="text-xs text-muted-foreground">
                {categoryLocked ? `${languageLabel(start.language)} · ${labels.category(start.category)}` : languageLabel(start.language)}
              </p>
            </div>
          ) : null}

          {/* 1 · What it is for — absent, not disabled, when the category is locked (2.3). */}
          {categoryLocked ? null : (
            <fieldset className="flex min-w-0 flex-col gap-2">
              <legend className="mb-1 text-sm font-medium">{labels.purpose}</legend>
              {/* Native radios, as in the connect dialog and the audience: arrows work. */}
              <div className="grid gap-2 sm:grid-cols-2">
                {categories.map((c) => (
                  <label
                    key={c}
                    // A third card takes the whole row instead of leaving a hole next to it.
                    className="flex min-w-0 cursor-pointer items-start gap-3 rounded-md border border-input p-3 text-sm transition-colors last:odd:sm:col-span-2 has-[:checked]:border-primary has-[:checked]:ring-1 has-[:checked]:ring-primary has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring motion-reduce:transition-none"
                  >
                    <input
                      type="radio"
                      name={id("category")}
                      value={c}
                      checked={category === c}
                      onChange={() => setCategory(c)}
                      className="mt-1 size-4 shrink-0 accent-primary"
                    />
                    <span className="grid min-w-0 gap-1">
                      <span className="font-medium">{labels.category(c)}</span>
                      <span className="text-xs text-pretty text-muted-foreground">{labels.categoryHelp(c)}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          {/* 2 · Name and language — only when creating. */}
          {editing ? null : (
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem]">
              <div className="flex min-w-0 flex-col gap-1">
                <Label htmlFor={id("name")}>{labels.name}</Label>
                <Input
                  id={id("name")}
                  value={name}
                  maxLength={LIMITS.name}
                  autoComplete="off"
                  placeholder={labels.nameExample}
                  onChange={(e) => setName(toTemplateName(e.target.value))}
                  aria-invalid={touched && !finalTemplateName(name) ? true : undefined}
                  aria-describedby={id("name-help")}
                  className="font-mono"
                />
                <p id={id("name-help")} className="text-xs text-pretty text-muted-foreground">
                  {labels.nameHelp}
                </p>
              </div>
              <div className="flex min-w-0 flex-col gap-1">
                <Label htmlFor={id("lang")}>{labels.language}</Label>
                <NativeSelect id={id("lang")} wrapperClassName="w-full" value={language} onChange={(e) => setLanguage(e.target.value)}>
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.label}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            </div>
          )}

          {systemVariables && !isAuth ? (
            <SystemVariablesBox system={systemVariables} issues={systemIssues} labels={labels} issuesId={id("system-issues")} />
          ) : null}

          {/* 3 · Authentication: what can be chosen, instead of the message and the buttons. */}
          {isAuth ? <OtpFields otp={otp} onChange={setOtp} touched={touched} labels={labels} id={id} /> : null}

          {/* 3 · The message */}
          {isAuth ? null : (
          <fieldset className="flex min-w-0 flex-col gap-3">
            <legend className="mb-1 text-sm font-medium">{labels.message}</legend>
            <div className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between gap-2">
                <Label htmlFor={id("header")}>{labels.header}</Label>
                <Counter value={header} max={LIMITS.header} labels={labels} />
              </div>
              <Input id={id("header")} value={header} maxLength={LIMITS.header} onChange={(e) => setHeader(e.target.value)} />
            </div>

            <div className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between gap-2">
                <Label htmlFor={id("body")}>{labels.body}</Label>
                <Counter value={body} max={LIMITS.body} labels={labels} />
              </div>
              <Textarea
                id={id("body")}
                ref={bodyRef}
                value={body}
                maxLength={LIMITS.body}
                rows={7}
                placeholder={labels.bodyExample}
                onChange={(e) => changeBody(e.target.value)}
                aria-invalid={(touched && !body.trim()) || issues.length > 0 || systemBlocked ? true : undefined}
                aria-describedby={bodyDescribedBy}
              />
              <p id={id("body-help")} className="text-xs text-pretty text-muted-foreground">
                {labels.bodyHelp}
              </p>
              <div className="flex flex-wrap items-center gap-2" role="group" aria-label={labels.insertVariable}>
                <span className="text-xs text-muted-foreground">{labels.insertVariable}</span>
                {suggested.map((v) => (
                  <Button key={v} type="button" variant="outline" size="sm" onClick={() => addVariable(v)}>
                    {`{{${v}}}`}
                  </Button>
                ))}
                {systemVariables ? null : (
                  <div className="flex items-center gap-1">
                    <Input
                      aria-label={labels.otherVariable}
                      placeholder={labels.otherVariable}
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
                      {labels.addVariable}
                    </Button>
                  </div>
                )}
              </div>
              {issues.length > 0 ? (
                // The alert wraps the list: on the <ul> itself, the role would take away its list semantics.
                <div id={id("body-issues")} role="alert">
                  <ul className="flex flex-col gap-1">
                    {issues.map((issue) => (
                      <li key={`${issue.code}-${"text" in issue ? issue.text : ""}`} className="text-xs text-pretty text-destructive">
                        {labels.bodyIssue(issue)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>

            {variables.length > 0 ? (
              <div className="flex flex-col gap-2 rounded-md bg-muted/50 p-3" data-slot="template-examples">
                <p className="text-sm font-medium">{labels.examples}</p>
                <p id={id("examples-help")} className="text-xs text-pretty text-muted-foreground">
                  {labels.examplesHelp}
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {variables.map((v) => (
                    <div key={v} className="flex min-w-0 flex-col gap-1">
                      <Label htmlFor={id(`ex-${v}`)} className="font-mono text-xs break-all">
                        {labels.example(v)}
                      </Label>
                      <Input
                        id={id(`ex-${v}`)}
                        value={examples[v] ?? ""}
                        maxLength={LIMITS.example}
                        aria-describedby={id("examples-help")}
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
                <Label htmlFor={id("footer")}>{labels.footer}</Label>
                <Counter value={footer} max={LIMITS.footer} labels={labels} />
              </div>
              <Input id={id("footer")} value={footer} maxLength={LIMITS.footer} onChange={(e) => setFooter(e.target.value)} />
            </div>
          </fieldset>
          )}

          {/* 4 · Buttons */}
          {isAuth ? null : (
          <fieldset className="flex min-w-0 flex-col gap-2">
            <legend className="mb-1 text-sm font-medium">{labels.buttons}</legend>
            <p className="text-xs text-pretty text-muted-foreground">{labels.buttonsHelp}</p>
            {buttons.map((b, i) => {
              const problem = touched || b.label ? buttonIssue(b) : null;
              // The field the problem is about is marked and described by it, so «Enviar» can take focus there.
              const problemId = id(`button-${i}-issue`);
              const invalid = (issue: ButtonIssue) =>
                problem === issue ? { "aria-invalid": true as const, "aria-describedby": problemId } : {};
              return (
                <div key={i} className="flex min-w-0 flex-col gap-1 rounded-md border border-border p-2">
                  <div className="grid gap-2 sm:grid-cols-[10rem_minmax(0,1fr)_auto]">
                    <NativeSelect
                      aria-label={labels.buttonType(i + 1)}
                      value={b.type}
                      onChange={(e) => updateButton(i, { type: e.target.value as ButtonDraft["type"] })}
                    >
                      {(["QUICK_REPLY", "URL", "PHONE_NUMBER"] as const).map((k) => (
                        <option key={k} value={k}>
                          {labels.buttonKind(k)}
                        </option>
                      ))}
                    </NativeSelect>
                    <Input
                      aria-label={labels.buttonLabel(i + 1)}
                      placeholder={labels.buttonLabelPlaceholder}
                      value={b.label}
                      maxLength={LIMITS.button}
                      onChange={(e) => updateButton(i, { label: e.target.value })}
                      {...invalid("label_missing")}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={labels.buttonRemove(i + 1)}
                      onClick={() => setButtons((prev) => prev.filter((_, j) => j !== i))}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </div>
                  {b.type === "URL" ? (
                    <Input
                      aria-label={labels.buttonUrl(i + 1)}
                      placeholder="https://"
                      inputMode="url"
                      value={b.url ?? ""}
                      onChange={(e) => updateButton(i, { url: e.target.value })}
                      {...invalid("url_invalid")}
                    />
                  ) : null}
                  {b.type === "PHONE_NUMBER" ? (
                    <Input
                      aria-label={labels.buttonPhone(i + 1)}
                      placeholder="+56 9 1234 5678"
                      inputMode="tel"
                      value={b.phone_number ?? ""}
                      onChange={(e) => updateButton(i, { phone_number: e.target.value })}
                      {...invalid("phone_invalid")}
                    />
                  ) : null}
                  {problem ? (
                    <p id={problemId} className="text-xs text-pretty text-destructive" role="alert">
                      {labels.buttonIssue(problem)}
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
                {labels.addButton}
              </Button>
            ) : null}
          </fieldset>
          )}
        </div>

        {/* Preview */}
        <aside className="flex min-w-0 flex-col gap-2 lg:sticky lg:top-0 lg:self-start" aria-label={labels.preview}>
          <p className="text-sm font-medium">{labels.preview}</p>
          {isAuth ? (
            <OtpPreview otp={otp} language={language} labels={labels.otp} />
          ) : (
            <TemplatePreview header={header} body={body} footer={footer} buttons={buttons} examples={examples} emptyLabel={labels.previewEmpty} />
          )}
        </aside>

        <div className="flex min-w-0 flex-col gap-3 lg:col-span-2">
          {serverError ? (
            <Callout tone="danger" title={labels.errorTitle} action={serverErrorAction}>
              {serverError}
            </Callout>
          ) : null}
          {/* On a phone two nowrap buttons side by side need more than the ~296 px a 360 px
              dialog leaves (estimated from the classes, not measured): what is missing goes
              first, then the buttons stacked full width, «Enviar» on top. */}
          <DialogFooter className="flex-col flex-wrap gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="min-w-0 text-xs text-pretty text-muted-foreground" aria-live="polite">
              {ready ? labels.ready : labels.missing(missing)}
            </p>
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>
                {labels.cancel}
              </Button>
              <Button type="submit" loading={busy} disabled={busy}>
                {labels.submit}
              </Button>
            </div>
          </DialogFooter>
        </div>
      </form>

      {/* Outside the form: a portal still bubbles React events to its tree parents. */}
      <ConfirmDialog
        open={confirming !== null}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={labels.confirm.title}
        // The reasons are the dialog's description, so they are read when it opens
        // (focus lands on «Seguir editando»): spans, because it renders as a <p>.
        description={
          <span className="grid gap-2 text-popover-foreground" data-slot="template-confirm-reasons">
            {(confirming?.reasons.length ? confirming.reasons : [{ kind: "unknown" }]).map((reason, i) => (
              <span key={`${reason.kind}-${i}`} className="block text-pretty">
                {labels.confirm.reason(reason)}
              </span>
            ))}
          </span>
        }
        confirmLabel={labels.confirm.confirm}
        cancelLabel={labels.confirm.cancel}
        onConfirm={async () => {
          // The same draft goes again, now confirmed; the editor stays as it was.
          const payload = confirming?.draft;
          setConfirming(null);
          if (payload) await send(true, payload);
        }}
      />
    </>
  );
}

/** Spec 077 (3.1): the three things an authentication template lets us choose; Meta writes the rest. */
function OtpFields({
  otp,
  onChange,
  touched,
  labels,
  id,
}: {
  otp: OtpDraft;
  onChange: (otp: OtpDraft) => void;
  touched: boolean;
  labels: TemplateEditorLabels;
  id: (part: string) => string;
}) {
  const button = otp.buttonText.trim();
  const buttonBad = (touched || otp.buttonText !== "") && (!button || button.length > OTP_LIMITS.button);
  const minutesBad = otpMinutes(otp.minutes) === "invalid";
  return (
    <fieldset className="flex min-w-0 flex-col gap-3" data-slot="template-otp">
      <legend className="mb-1 text-sm font-medium">{labels.otp.legend}</legend>
      <p className="text-xs text-pretty text-muted-foreground">{labels.otp.intro}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex items-baseline justify-between gap-2">
            <Label htmlFor={id("otp-button")}>{labels.otp.button}</Label>
            <Counter value={otp.buttonText} max={OTP_LIMITS.button} labels={labels} />
          </div>
          <Input
            id={id("otp-button")}
            value={otp.buttonText}
            maxLength={OTP_LIMITS.button}
            onChange={(e) => onChange({ ...otp, buttonText: e.target.value })}
            aria-invalid={buttonBad ? true : undefined}
            aria-describedby={id("otp-button-help")}
          />
          <p id={id("otp-button-help")} className={cn("text-xs text-pretty", buttonBad ? "text-destructive" : "text-muted-foreground")}>
            {labels.otp.buttonHelp}
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <Label htmlFor={id("otp-minutes")}>{labels.otp.minutes}</Label>
          <Input
            id={id("otp-minutes")}
            type="number"
            inputMode="numeric"
            min={OTP_LIMITS.minMinutes}
            max={OTP_LIMITS.maxMinutes}
            step={1}
            value={otp.minutes}
            onChange={(e) => onChange({ ...otp, minutes: e.target.value })}
            aria-invalid={minutesBad ? true : undefined}
            aria-describedby={id("otp-minutes-help")}
            className="tabular-nums"
          />
          <p id={id("otp-minutes-help")} className={cn("text-xs text-pretty", minutesBad ? "text-destructive" : "text-muted-foreground")}>
            {labels.otp.minutesHelp}
          </p>
        </div>
      </div>
      <label htmlFor={id("otp-security")} className="flex min-h-6 cursor-pointer items-start gap-2 text-sm">
        <input
          id={id("otp-security")}
          type="checkbox"
          checked={otp.security}
          onChange={(e) => onChange({ ...otp, security: e.target.checked })}
          className="mt-1 size-4 shrink-0 accent-primary"
        />
        <span className="grid min-w-0 gap-1">
          <span>{labels.otp.security}</span>
          <span className="text-xs text-pretty text-muted-foreground">{labels.otp.securityHelp}</span>
        </span>
      </label>
    </fieldset>
  );
}

/**
 * Meta's fixed text of an authentication template, following the fields. Meta
 * writes it in the template's language, not the screen's: the sample is
 * Spanish, so it is shown only for a Spanish template (in Spanish even with
 * the screen in English); for any other language, one line says so.
 */
export function OtpPreview({
  otp,
  language,
  labels,
}: {
  otp: OtpDraft;
  language: string;
  labels: Pick<TemplateEditorLabels["otp"], "buttonDefault" | "previewSpanish" | "previewOther">;
}) {
  if (!isSpanishTemplate(language)) {
    return (
      <p className="rounded-md bg-muted p-3 text-xs text-pretty text-muted-foreground" data-slot="template-preview">
        {labels.previewOther(languageLabel(language))}
      </p>
    );
  }
  const text = otpPreviewText(otp);
  return (
    <div className="flex flex-col gap-1 rounded-md bg-muted p-3" data-slot="template-preview">
      <p className="text-xs text-muted-foreground">{labels.previewSpanish}</p>
      <div lang="es" className="max-w-full rounded-md bg-background px-3 py-2 text-sm shadow-sm ring-1 ring-foreground/5">
        <p className="text-pretty break-words">{text.body}</p>
        {text.expiry ? <p className="mt-1 text-xs text-muted-foreground">{text.expiry}</p> : null}
      </div>
      <div className="rounded-md bg-background px-3 py-2 text-center text-sm font-medium text-primary shadow-sm ring-1 ring-foreground/5">
        {otp.buttonText.trim() || labels.buttonDefault}
      </div>
    </div>
  );
}

/** 4.1 · The template is sent by Auphere by its name: which variables it has to carry, and what is off. */
function SystemVariablesBox({
  system,
  issues,
  labels,
  issuesId,
}: {
  system: SystemVariables;
  issues: { missing: string[]; extra: string[] };
  labels: TemplateEditorLabels;
  /** The body is described by what is off, so it is read with the field. */
  issuesId: string;
}) {
  const off = issues.missing.length > 0 || issues.extra.length > 0;
  return (
    <div className="grid min-w-0 gap-2 rounded-md border border-status-info-border bg-status-info-bg p-3 text-sm" data-testid="template-system-variables">
      <p className="font-medium text-balance">{labels.systemVariables.title}</p>
      <p className="text-xs text-pretty text-muted-foreground">{labels.systemVariables.help(system.mode)}</p>
      <ul className="flex flex-wrap gap-2">
        {system.variables.map((v) => (
          <li key={v} className="rounded-sm bg-background px-2 py-1 font-mono text-xs ring-1 ring-foreground/10">
            {`{{${v}}}`}
          </li>
        ))}
      </ul>
      {off ? (
        <p id={issuesId} role="alert" className="text-xs text-pretty text-destructive">
          {[issues.missing.length ? labels.systemVariables.missing(issues.missing) : null, issues.extra.length ? labels.systemVariables.extra(issues.extra) : null]
            .filter(Boolean)
            .join(" ")}
        </p>
      ) : null}
    </div>
  );
}

/** The message as WhatsApp shows it, with the examples in place of the variables. */
export function TemplatePreview({
  header,
  body,
  footer,
  buttons,
  examples,
  emptyLabel,
}: {
  header: string;
  body: string;
  footer: string;
  buttons: ButtonDraft[];
  examples: Record<string, string>;
  emptyLabel: string;
}) {
  const empty = !header.trim() && !body.trim() && !footer.trim();
  return (
    <div className="rounded-md bg-muted p-3" data-slot="template-preview">
      {empty ? (
        <p className="py-8 text-center text-xs text-muted-foreground">{emptyLabel}</p>
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
                  <span key={i} className="rounded-sm bg-status-warning-bg px-1 font-mono text-xs">
                    {`{{${part.name}}}`}
                  </span>
                ),
              )}
            </p>
            {footer.trim() ? <p className="mt-1 text-xs break-words text-muted-foreground">{footer}</p> : null}
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
