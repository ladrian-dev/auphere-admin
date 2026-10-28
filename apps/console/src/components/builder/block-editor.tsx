"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";

import { Button, Field, Input, NativeSelect, Textarea, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type {
  AgentSpec,
  EditableBlock,
  EscalationCode,
  EscalationTrigger,
  Register,
  SpecProcedure,
  SpecSection,
} from "@/lib/backend/builder-types";
import { ESCALATION_CODES } from "@/lib/backend/builder-types";

import { INSTRUCTIONS_MAX, cleanName, isCustomTrigger, parseLanguages, procedureId, sectionsChars } from "./builder-model";

type T = ReturnType<typeof useT>;

/** Lo que entrega un editor: el valor nuevo de su bloque (`undefined` lo quita). */
export type BlockSave<K extends EditableBlock = EditableBlock> = (value: AgentSpec[K] | undefined) => void;

type EditorProps<K extends EditableBlock> = {
  spec: AgentSpec;
  busy: boolean;
  label: string;
  onSave: BlockSave<K>;
  onCancel: () => void;
};

/**
 * Editar un bloque del AgentSpec en línea (spec 047, requisito 17.7): el mismo
 * sitio donde se lee, sin pantalla «Revisar» aparte. Cada editor comprueba los
 * límites del esquema antes de mandar nada (`contracts/agent-spec.schema.json`)
 * y entrega solo su bloque. Guardar lo hace quien lo monta, con la revisión que
 * leyó la pantalla; el validador de la API tiene la última palabra.
 */
export function BlockEditor({
  block,
  ...props
}: { block: EditableBlock } & Omit<EditorProps<EditableBlock>, "onSave"> & { onSave: (value: unknown) => void }) {
  switch (block) {
    case "identity":
      return <IdentityEditor {...props} />;
    case "voice":
      return <VoiceEditor {...props} />;
    case "instructions":
      return <InstructionsEditor {...props} />;
    case "procedures":
      return <ProceduresEditor {...props} />;
    case "escalation":
      return <EscalationEditor {...props} />;
    case "rules":
      return <RulesEditor {...props} />;
  }
}

function lengthError(t: T, value: string, min: number, max: number): string | undefined {
  const n = value.trim().length;
  if (min > 0 && n === 0) return t("builder.error.required");
  if (n < min || n > max) return t("builder.error.length", { min, max });
  return undefined;
}

function maxError(t: T, value: string, max: number): string | undefined {
  return value.trim().length > max ? t("builder.error.max", { max }) : undefined;
}

type Errors = Record<string, string | undefined>;
const hasErrors = (errors: Errors) => Object.values(errors).some(Boolean);

/** El marco de cada editor: su formulario, «Guardar» y «Cancelar». */
function EditorForm({
  label,
  busy,
  errors,
  onSubmit,
  onCancel,
  children,
}: {
  label: string;
  busy: boolean;
  errors: Errors;
  onSubmit: () => void;
  onCancel: () => void;
  children: React.ReactNode;
}) {
  const t = useT();
  const formRef = React.useRef<HTMLFormElement>(null);
  React.useEffect(() => {
    formRef.current?.querySelector<HTMLElement>("input, textarea")?.focus();
  }, []);
  return (
    <form
      ref={formRef}
      aria-label={label}
      noValidate
      className="grid min-w-0 gap-4"
      data-slot="block-editor"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      {children}
      {hasErrors(errors) ? (
        <p role="alert" className="text-xs text-destructive">
          {t("builder.edit.fix")}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={busy}>
          {t("builder.edit.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("builder.edit.cancel")}
        </Button>
      </div>
    </form>
  );
}

// ── Qué hace ────────────────────────────────────────────────────────────────

function IdentityEditor({ spec, busy, label, onSave, onCancel }: EditorProps<"identity">) {
  const t = useT();
  const locale = useLocale();
  const [name, setName] = React.useState(spec.identity.name);
  const [description, setDescription] = React.useState(spec.identity.description);
  const [goal, setGoal] = React.useState(spec.identity.goal ?? "");
  const [errors, setErrors] = React.useState<Errors>({});

  function submit() {
    const next: Errors = {
      name: lengthError(t, cleanName(name), 1, 40),
      description: lengthError(t, description, 20, 1024),
      goal: maxError(t, goal, 500),
    };
    setErrors(next);
    if (hasErrors(next)) return;
    const value: AgentSpec["identity"] = { ...spec.identity, name: cleanName(name), description: description.trim() };
    if (goal.trim()) value.goal = goal.trim();
    else delete value.goal;
    onSave(value);
  }

  return (
    <EditorForm label={label} busy={busy} errors={errors} onSubmit={submit} onCancel={onCancel}>
      <Field label={t("builder.field.name")} error={errors.name} required>
        {(a11y) => <Input {...a11y} value={name} maxLength={40} autoComplete="off" onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field
        label={t("builder.field.description")}
        hint={t("builder.error.length", { min: 20, max: formatNumber(1024, locale) })}
        error={errors.description}
        required
      >
        {(a11y) => <Textarea {...a11y} value={description} rows={4} maxLength={1024} onChange={(e) => setDescription(e.target.value)} />}
      </Field>
      <Field label={t("builder.field.goal")} optionalLabel={t("builder.edit.optional")} error={errors.goal}>
        {(a11y) => <Textarea {...a11y} value={goal} rows={2} maxLength={500} onChange={(e) => setGoal(e.target.value)} />}
      </Field>
    </EditorForm>
  );
}

// ── Cómo habla ──────────────────────────────────────────────────────────────

const REGISTERS: readonly ("" | Register)[] = ["", "tu", "usted", "vos"];

function VoiceEditor({ spec, busy, label, onSave, onCancel }: EditorProps<"voice">) {
  const t = useT();
  const base = React.useId();
  const voice = spec.voice ?? {};
  const [tone, setTone] = React.useState(voice.tone ?? "");
  const [languages, setLanguages] = React.useState((voice.languages ?? []).join(", "));
  const [register, setRegister] = React.useState<"" | Register>(voice.register ?? "");
  const [greeting, setGreeting] = React.useState(voice.greeting ?? "");
  const [errors, setErrors] = React.useState<Errors>({});

  function submit() {
    const codes = parseLanguages(languages);
    const next: Errors = {
      tone: maxError(t, tone, 200),
      languages: codes === null ? t("builder.error.languages") : undefined,
      greeting: maxError(t, greeting, 300),
    };
    setErrors(next);
    if (hasErrors(next) || codes === null) return;
    const value: NonNullable<AgentSpec["voice"]> = {};
    if (tone.trim()) value.tone = tone.trim();
    if (codes.length) value.languages = codes;
    if (register) value.register = register;
    if (greeting.trim()) value.greeting = greeting.trim();
    onSave(value);
  }

  return (
    <EditorForm label={label} busy={busy} errors={errors} onSubmit={submit} onCancel={onCancel}>
      <Field label={t("builder.field.tone")} optionalLabel={t("builder.edit.optional")} error={errors.tone}>
        {(a11y) => (
          <Input {...a11y} value={tone} maxLength={200} placeholder={t("builder.field.tone.placeholder")} autoComplete="off" onChange={(e) => setTone(e.target.value)} />
        )}
      </Field>
      <Field label={t("builder.field.languages")} hint={t("builder.field.languages.hint")} error={errors.languages}>
        {(a11y) => <Input {...a11y} value={languages} maxLength={60} autoComplete="off" onChange={(e) => setLanguages(e.target.value)} />}
      </Field>
      <fieldset className="grid min-w-0 gap-2">
        <legend className="mb-1 text-sm font-medium">{t("builder.field.register")}</legend>
        <div className="flex min-w-0 flex-wrap gap-4">
          {REGISTERS.map((r) => (
            <label key={r || "none"} className="flex min-h-6 items-center gap-2 text-sm">
              <input type="radio" name={`${base}-register`} className="size-4 accent-primary" checked={register === r} onChange={() => setRegister(r)} />
              {r ? t(`builder.register.${r}` as MessageKey) : t("builder.field.register.none")}
            </label>
          ))}
        </div>
      </fieldset>
      <Field label={t("builder.field.greeting")} optionalLabel={t("builder.edit.optional")} error={errors.greeting}>
        {(a11y) => <Textarea {...a11y} value={greeting} rows={2} maxLength={300} onChange={(e) => setGreeting(e.target.value)} />}
      </Field>
    </EditorForm>
  );
}

// ── Instrucciones ───────────────────────────────────────────────────────────

function InstructionsEditor({ spec, busy, label, onSave, onCancel }: EditorProps<"instructions">) {
  const t = useT();
  const locale = useLocale();
  const legacy = spec.mode === "instructions" || (spec.instructions?.legacy_text !== undefined && !spec.instructions?.sections?.length);
  const [text, setText] = React.useState(spec.instructions?.legacy_text ?? "");
  const [sections, setSections] = React.useState<SpecSection[]>(() => spec.instructions?.sections?.map((s) => ({ ...s })) ?? []);
  const [errors, setErrors] = React.useState<Errors>({});
  const total = sectionsChars(sections);

  function submit() {
    if (legacy) {
      const next: Errors = { legacy: text.trim() ? undefined : t("builder.error.required") };
      setErrors(next);
      if (!hasErrors(next)) onSave({ ...spec.instructions, legacy_text: text });
      return;
    }
    const next: Errors = { total: total > INSTRUCTIONS_MAX ? t("builder.error.total", { max: formatNumber(INSTRUCTIONS_MAX, locale) }) : undefined };
    sections.forEach((s, i) => {
      next[`title-${i}`] = lengthError(t, s.title, 1, 80);
      next[`body-${i}`] = lengthError(t, s.body, 1, INSTRUCTIONS_MAX);
    });
    setErrors(next);
    if (hasErrors(next)) return;
    onSave({ ...spec.instructions, sections: sections.map((s) => ({ title: s.title.trim(), body: s.body.trim() })) });
  }

  function update(i: number, patch: Partial<SpecSection>) {
    setSections((prev) => prev.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  }

  if (legacy) {
    return (
      <EditorForm label={label} busy={busy} errors={errors} onSubmit={submit} onCancel={onCancel}>
        <Field label={t("builder.field.legacy")} error={errors.legacy} required>
          {(a11y) => <Textarea {...a11y} value={text} rows={12} className="font-mono text-xs" onChange={(e) => setText(e.target.value)} />}
        </Field>
      </EditorForm>
    );
  }

  return (
    <EditorForm label={label} busy={busy} errors={errors} onSubmit={submit} onCancel={onCancel}>
      <ol className="grid min-w-0 gap-4">
        {sections.map((s, i) => (
          <li key={i} className="grid min-w-0 gap-2 rounded-md border border-border p-3">
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground">{t("builder.field.section", { n: i + 1 })}</span>
              <RemoveButton what={t("builder.field.section", { n: i + 1 })} onClick={() => setSections((prev) => prev.filter((_, j) => j !== i))} />
            </div>
            <Field label={t("builder.field.section.title", { n: i + 1 })} error={errors[`title-${i}`]} required>
              {(a11y) => <Input {...a11y} value={s.title} maxLength={80} autoComplete="off" onChange={(e) => update(i, { title: e.target.value })} />}
            </Field>
            <Field label={t("builder.field.section.body", { n: i + 1 })} error={errors[`body-${i}`]} required>
              {(a11y) => <Textarea {...a11y} value={s.body} rows={5} maxLength={INSTRUCTIONS_MAX} onChange={(e) => update(i, { body: e.target.value })} />}
            </Field>
          </li>
        ))}
      </ol>
      <p className={`text-xs tabular-nums ${total > INSTRUCTIONS_MAX ? "text-destructive" : "text-muted-foreground"}`} role={errors.total ? "alert" : undefined}>
        {errors.total ?? t("builder.field.section.total", { n: formatNumber(total, locale), max: formatNumber(INSTRUCTIONS_MAX, locale) })}
      </p>
      {sections.length < 20 ? (
        <AddButton label={t("builder.field.section.add")} onClick={() => setSections((prev) => [...prev, { title: "", body: "" }])} />
      ) : null}
    </EditorForm>
  );
}

// ── Procedimientos ──────────────────────────────────────────────────────────

type DraftProcedure = Omit<SpecProcedure, "id"> & { id: string | null };

function ProceduresEditor({ spec, busy, label, onSave, onCancel }: EditorProps<"procedures">) {
  const t = useT();
  const [items, setItems] = React.useState<DraftProcedure[]>(() => (spec.procedures ?? []).map((p) => ({ ...p })));
  const [errors, setErrors] = React.useState<Errors>({});

  function submit() {
    const next: Errors = {};
    items.forEach((p, i) => {
      next[`title-${i}`] = lengthError(t, p.title, 1, 80);
      next[`when-${i}`] = lengthError(t, p.when, 1, 300);
      next[`steps-${i}`] = lengthError(t, p.steps, 1, 2000);
    });
    setErrors(next);
    if (hasErrors(next)) return;
    const taken = new Set(items.flatMap((p) => (p.id ? [p.id] : [])));
    const value: SpecProcedure[] = items.map((p) => {
      const id = p.id ?? procedureId(p.title, taken);
      taken.add(id);
      const out: SpecProcedure = { id, title: p.title.trim(), when: p.when.trim(), steps: p.steps.trim() };
      if (p.tools?.length) out.tools = p.tools;
      return out;
    });
    onSave(value);
  }

  function update(i: number, patch: Partial<DraftProcedure>) {
    setItems((prev) => prev.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  }

  return (
    <EditorForm label={label} busy={busy} errors={errors} onSubmit={submit} onCancel={onCancel}>
      <ol className="grid min-w-0 gap-4">
        {items.map((p, i) => (
          <li key={p.id ?? `new-${i}`} className="grid min-w-0 gap-2 rounded-md border border-border p-3">
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground">{t("builder.field.procedure", { n: i + 1 })}</span>
              <RemoveButton what={t("builder.field.procedure", { n: i + 1 })} onClick={() => setItems((prev) => prev.filter((_, j) => j !== i))} />
            </div>
            <Field label={t("builder.field.procedure.title", { n: i + 1 })} error={errors[`title-${i}`]} required>
              {(a11y) => <Input {...a11y} value={p.title} maxLength={80} autoComplete="off" onChange={(e) => update(i, { title: e.target.value })} />}
            </Field>
            <Field label={t("builder.field.procedure.when", { n: i + 1 })} error={errors[`when-${i}`]} required>
              {(a11y) => <Input {...a11y} value={p.when} maxLength={300} autoComplete="off" onChange={(e) => update(i, { when: e.target.value })} />}
            </Field>
            <Field label={t("builder.field.procedure.steps", { n: i + 1 })} error={errors[`steps-${i}`]} required>
              {(a11y) => <Textarea {...a11y} value={p.steps} rows={4} maxLength={2000} onChange={(e) => update(i, { steps: e.target.value })} />}
            </Field>
          </li>
        ))}
      </ol>
      {items.length < 30 ? (
        <AddButton
          label={t("builder.field.procedure.add")}
          onClick={() => setItems((prev) => [...prev, { id: null, title: "", when: "", steps: "" }])}
        />
      ) : null}
    </EditorForm>
  );
}

// ── Cuándo pasa a una persona ───────────────────────────────────────────────

const TRIGGER_LABEL: Record<EscalationCode, MessageKey> = {
  asks_for_human: "builder.block.escalation.asks_for_human",
  failed_attempts: "builder.block.escalation.failed_attempts",
  complaint: "builder.block.escalation.complaint",
  payment_issue: "builder.block.escalation.payment_issue",
  emergency: "builder.block.escalation.emergency",
  out_of_scope: "builder.block.escalation.out_of_scope",
};

function EscalationEditor({ spec, busy, label, onSave, onCancel }: EditorProps<"escalation">) {
  const t = useT();
  const base = React.useId();
  const triggers = spec.escalation?.triggers ?? [];
  const [codes, setCodes] = React.useState<Set<EscalationCode>>(() => new Set(triggers.filter((tr): tr is EscalationCode => !isCustomTrigger(tr))));
  const [custom, setCustom] = React.useState<string[]>(() => triggers.filter(isCustomTrigger).map((tr) => tr.custom));
  const [attempts, setAttempts] = React.useState(spec.escalation?.failed_attempts ?? 2);
  const [message, setMessage] = React.useState(spec.escalation?.message ?? "");
  const [errors, setErrors] = React.useState<Errors>({});

  function toggle(code: EscalationCode, on: boolean) {
    setCodes((prev) => {
      const next = new Set(prev);
      if (on) next.add(code);
      else next.delete(code);
      return next;
    });
  }

  function submit() {
    const kept = custom.map((c) => c.trim()).filter(Boolean);
    const next: Errors = { message: maxError(t, message, 500) };
    kept.forEach((c, i) => {
      next[`custom-${i}`] = c.length > 300 ? t("builder.error.max", { max: 300 }) : undefined;
    });
    setErrors(next);
    if (hasErrors(next)) return;
    const value: NonNullable<AgentSpec["escalation"]> = {
      ...spec.escalation,
      triggers: [...ESCALATION_CODES.filter((c) => codes.has(c)), ...[...new Set(kept)].map((c): EscalationTrigger => ({ custom: c }))].slice(0, 20),
      failed_attempts: attempts,
    };
    if (message.trim()) value.message = message.trim();
    else delete value.message;
    onSave(value);
  }

  return (
    <EditorForm label={label} busy={busy} errors={errors} onSubmit={submit} onCancel={onCancel}>
      <fieldset className="grid min-w-0 gap-2">
        <legend className="mb-1 text-sm font-medium">{t("builder.field.triggers")}</legend>
        {ESCALATION_CODES.map((code) => (
          <label key={code} className="flex min-h-6 min-w-0 items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 size-4 shrink-0 accent-primary" checked={codes.has(code)} onChange={(e) => toggle(code, e.target.checked)} />
            <span className="min-w-0 text-pretty">{t(TRIGGER_LABEL[code], { n: attempts })}</span>
          </label>
        ))}
      </fieldset>
      {codes.has("failed_attempts") ? (
        <div className="grid min-w-0 gap-1">
          <label htmlFor={`${base}-attempts`} className="text-sm font-medium">
            {t("builder.field.attempts")}
          </label>
          <NativeSelect id={`${base}-attempts`} value={attempts} onChange={(e) => setAttempts(Number(e.target.value))} wrapperClassName="w-24">
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </NativeSelect>
        </div>
      ) : null}
      <ul className="grid min-w-0 gap-2">
        {custom.map((c, i) => (
          <li key={i} className="flex min-w-0 items-end gap-2">
            <Field label={t("builder.field.custom", { n: i + 1 })} error={errors[`custom-${i}`]} className="flex-1">
              {(a11y) => (
                <Input
                  {...a11y}
                  value={c}
                  maxLength={300}
                  autoComplete="off"
                  onChange={(e) => setCustom((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                />
              )}
            </Field>
            <RemoveButton what={t("builder.field.custom", { n: i + 1 })} onClick={() => setCustom((prev) => prev.filter((_, j) => j !== i))} />
          </li>
        ))}
      </ul>
      {codes.size + custom.length < 20 ? <AddButton label={t("builder.field.custom.add")} onClick={() => setCustom((prev) => [...prev, ""])} /> : null}
      <Field label={t("builder.field.message")} optionalLabel={t("builder.edit.optional")} error={errors.message}>
        {(a11y) => <Textarea {...a11y} value={message} rows={2} maxLength={500} onChange={(e) => setMessage(e.target.value)} />}
      </Field>
    </EditorForm>
  );
}

// ── Reglas ──────────────────────────────────────────────────────────────────

function RulesEditor({ spec, busy, label, onSave, onCancel }: EditorProps<"rules">) {
  const t = useT();
  const [rules, setRules] = React.useState<string[]>(() => [...(spec.rules ?? [])]);
  const [errors, setErrors] = React.useState<Errors>({});

  function submit() {
    const next: Errors = {};
    rules.forEach((r, i) => {
      next[`rule-${i}`] = r.trim().length > 300 ? t("builder.error.max", { max: 300 }) : undefined;
    });
    setErrors(next);
    if (hasErrors(next)) return;
    // Una regla vacía no es una regla: se quita sin preguntar.
    onSave(rules.map((r) => r.trim()).filter(Boolean));
  }

  return (
    <EditorForm label={label} busy={busy} errors={errors} onSubmit={submit} onCancel={onCancel}>
      <ol className="grid min-w-0 gap-2">
        {rules.map((r, i) => (
          <li key={i} className="flex min-w-0 items-end gap-2">
            <Field label={t("builder.field.rule", { n: i + 1 })} error={errors[`rule-${i}`]} className="flex-1">
              {(a11y) => (
                <Input
                  {...a11y}
                  value={r}
                  maxLength={300}
                  autoComplete="off"
                  onChange={(e) => setRules((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                />
              )}
            </Field>
            <RemoveButton what={t("builder.field.rule", { n: i + 1 })} onClick={() => setRules((prev) => prev.filter((_, j) => j !== i))} />
          </li>
        ))}
      </ol>
      {rules.length < 30 ? <AddButton label={t("builder.field.rule.add")} onClick={() => setRules((prev) => [...prev, ""])} /> : null}
    </EditorForm>
  );
}

// ── piezas ──────────────────────────────────────────────────────────────────

function AddButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <div>
      <Button type="button" variant="outline" size="sm" onClick={onClick}>
        <Plus aria-hidden="true" />
        {label}
      </Button>
    </div>
  );
}

function RemoveButton({ what, onClick }: { what: string; onClick: () => void }) {
  const t = useT();
  return (
    <Button type="button" variant="ghost" size="icon-sm" onClick={onClick} aria-label={t("builder.edit.remove", { what })} className="shrink-0">
      <X aria-hidden="true" />
    </Button>
  );
}
