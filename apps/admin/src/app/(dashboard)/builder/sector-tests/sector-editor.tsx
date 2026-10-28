"use client";

import { ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button, Callout, Field, Input, StatusBadge, Textarea, cn } from "@nexus/ui";
import type { SectorCatalog } from "@/lib/backend-builder";

import { publishSectorTestsAction } from "../actions";
import {
  MAX_CRITERIA,
  TESTS_PER_SECTOR,
  blankCriterion,
  blankTest,
  formsFromCatalog,
  testsFromForms,
  testsWithErrors,
  type CriterionForm,
  type TestForm,
} from "./sector-tests";

type Props = { sector: SectorCatalog; onDone: () => void };

/**
 * Spec 047 (T090, 21.2, 54.10): a new version of a sector, starting from the
 * one in force. Each test with its name, simulated persona, first message,
 * plan, expected state and criteria, critical or normal. Exactly 12, checked
 * here and again by the API.
 */
export function SectorEditor({ sector, onDone }: Props) {
  const router = useRouter();
  const [forms, setForms] = useState<TestForm[]>(() => formsFromCatalog(sector.tests));
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const nextVersion = (sector.version ?? 0) + 1;

  const update = (uid: string, patch: Partial<TestForm>) =>
    setForms((all) => all.map((f) => (f.uid === uid ? { ...f, ...patch } : f)));
  const updateCriteria = (uid: string, change: (criteria: CriterionForm[]) => CriterionForm[]) =>
    setForms((all) => all.map((f) => (f.uid === uid ? { ...f, criteria: change(f.criteria) } : f)));
  const toggle = (uid: string) =>
    setOpen((s) => {
      const next = new Set(s);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });

  function addTest() {
    const test = blankTest();
    setForms((all) => [...all, test]);
    setOpen((s) => new Set(s).add(test.uid));
  }

  function removeTest(uid: string) {
    // The indexes move: the old errors would point at the wrong test.
    setErrors({});
    setForms((all) => all.filter((f) => f.uid !== uid));
  }

  async function publish() {
    setFailure(null);
    const checked = testsFromForms(forms);
    if (!checked.ok) {
      setErrors(checked.errors);
      const wrong = testsWithErrors(checked.errors);
      setOpen((s) => new Set([...s, ...forms.filter((_, i) => wrong.has(i)).map((f) => f.uid)]));
      return;
    }
    setErrors({});
    setPending(true);
    try {
      const result = await publishSectorTestsAction(sector.sector, checked.tests);
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(`${sector.name}: versión ${result.data.version ?? nextVersion} publicada`);
      router.refresh();
      onDone();
    } finally {
      setPending(false);
    }
  }

  const wrong = testsWithErrors(errors);
  const fieldErrors = Object.keys(errors).filter((k) => k !== "count").length;

  return (
    <form
      aria-label={`Versión nueva de ${sector.name}`}
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        void publish();
      }}
    >
      <Callout tone="info" title={`Versión ${nextVersion} de ${sector.name}`}>
        Los agentes que ya existen siguen con sus pruebas: cada una recuerda de qué versión salió. Los agentes nuevos de este
        sector nacen con estas {TESTS_PER_SECTOR}.
      </Callout>
      <p className={cn("text-sm tabular-nums", forms.length === TESTS_PER_SECTOR ? "text-muted-foreground" : "font-medium")}>
        {forms.length} de {TESTS_PER_SECTOR} pruebas
      </p>
      <ol className="flex flex-col gap-3">
        {forms.map((f, i) => (
          <TestEditor
            key={f.uid}
            form={f}
            index={i}
            open={open.has(f.uid)}
            hasErrors={wrong.has(i)}
            errors={errors}
            onToggle={() => toggle(f.uid)}
            onChange={(patch) => update(f.uid, patch)}
            onCriteria={(change) => updateCriteria(f.uid, change)}
            onRemove={() => removeTest(f.uid)}
          />
        ))}
      </ol>
      <div>
        <Button type="button" size="sm" variant="outline" onClick={addTest} disabled={forms.length >= TESTS_PER_SECTOR}>
          Añadir prueba
        </Button>
      </div>
      {errors.count || fieldErrors ? (
        <div role="alert" className="flex flex-col gap-1 text-sm text-destructive text-pretty">
          {errors.count ? <p>{errors.count}</p> : null}
          {fieldErrors ? (
            <p>
              {fieldErrors === 1 ? "Hay 1 campo por corregir" : `Hay ${fieldErrors} campos por corregir`} en{" "}
              {wrong.size === 1 ? "la prueba" : "las pruebas"} {[...wrong].sort((a, b) => a - b).map((i) => i + 1).join(", ")}.
            </p>
          ) : null}
        </div>
      ) : null}
      {failure ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {failure}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone} disabled={pending}>
          Cancelar
        </Button>
        <Button type="submit" disabled={pending}>
          {pending ? "Publicando…" : `Publicar la versión ${nextVersion}`}
        </Button>
      </div>
    </form>
  );
}

type TestEditorProps = {
  form: TestForm;
  index: number;
  open: boolean;
  hasErrors: boolean;
  errors: Record<string, string>;
  onToggle: () => void;
  onChange: (patch: Partial<TestForm>) => void;
  onCriteria: (change: (criteria: CriterionForm[]) => CriterionForm[]) => void;
  onRemove: () => void;
};

function TestEditor({ form, index, open, hasErrors, errors, onToggle, onChange, onCriteria, onRemove }: TestEditorProps) {
  const n = index + 1;
  const bodyId = `sector-test-${form.uid}`;
  const err = (field: string) => errors[`${index}.${field}`];
  return (
    <li className="rounded-md ring-1 ring-foreground/10">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={onToggle}
          className="flex min-h-8 min-w-0 flex-1 items-center gap-3 rounded-sm px-1 text-left text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} aria-hidden="true" />
          <span className="w-6 shrink-0 text-xs text-muted-foreground tabular-nums">{n}</span>
          <span className="min-w-0 flex-1 truncate font-medium">{form.name.trim() || "Prueba sin nombre"}</span>
          {form.key ? <code className="hidden text-xs text-muted-foreground sm:inline">{form.key}</code> : null}
          {hasErrors ? <StatusBadge tone="danger">Por corregir</StatusBadge> : null}
          {form.critical ? <StatusBadge tone="warning">Crítica</StatusBadge> : null}
        </button>
        <Button type="button" size="sm" variant="ghost" onClick={onRemove} aria-label={`Quitar la prueba ${n}`}>
          Quitar
        </Button>
      </div>
      {open ? (
        <fieldset id={bodyId} className="grid grid-cols-1 gap-3 border-t border-border px-4 py-4 sm:grid-cols-2">
          <legend className="sr-only">Prueba {n}</legend>
          <Field label="Clave" required requiredLabel="Obligatoria" hint="Minúsculas, cifras y «_». Única en el sector." error={err("key")}>
            {(a11y) => <Input {...a11y} value={form.key} onChange={(e) => onChange({ key: e.target.value })} spellCheck={false} />}
          </Field>
          <Field label="Nombre" required requiredLabel="Obligatorio" error={err("name")}>
            {(a11y) => <Input {...a11y} maxLength={120} value={form.name} onChange={(e) => onChange({ name: e.target.value })} />}
          </Field>
          <Field label="Persona simulada" className="sm:col-span-2" error={err("persona")}>
            {(a11y) => <Input {...a11y} maxLength={500} value={form.persona} onChange={(e) => onChange({ persona: e.target.value })} />}
          </Field>
          <Field label="Primer mensaje" required requiredLabel="Obligatorio" className="sm:col-span-2" error={err("first_message")}>
            {(a11y) => (
              <Textarea {...a11y} rows={2} maxLength={2000} value={form.first_message} onChange={(e) => onChange({ first_message: e.target.value })} />
            )}
          </Field>
          <Field label="Plan" hint="Cómo sigue la conversación la persona simulada." className="sm:col-span-2" error={err("plan")}>
            {(a11y) => <Textarea {...a11y} rows={2} maxLength={1000} value={form.plan} onChange={(e) => onChange({ plan: e.target.value })} />}
          </Field>
          <Field
            label="Estado esperado (JSON)"
            hint="Lo que tiene que quedar hecho en el mundo simulado. Vacío: no se comprueba y lo decide el juez."
            className="sm:col-span-2"
            error={err("expected_state")}
          >
            {(a11y) => (
              <Textarea
                {...a11y}
                rows={3}
                spellCheck={false}
                className="font-mono text-xs"
                placeholder='{"booking": {"created": true}}'
                value={form.expected_state}
                onChange={(e) => onChange({ expected_state: e.target.value })}
              />
            )}
          </Field>
          <fieldset className="flex flex-col gap-2 sm:col-span-2">
            <legend className="text-sm font-medium">Criterios del juez</legend>
            <p className="text-xs text-muted-foreground text-pretty">
              Entre 1 y {MAX_CRITERIA}. El juez da un veredicto por criterio: pasa, falla o «No sé».
            </p>
            {err("criteria") ? (
              <p role="alert" className="text-xs text-destructive">
                {err("criteria")}
              </p>
            ) : null}
            <ul className="flex flex-col gap-2">
              {form.criteria.map((c, j) => (
                <li key={c.uid} className="flex flex-col gap-2 sm:flex-row sm:items-start">
                  <div className="flex flex-col gap-1 sm:w-48">
                    <Input
                      aria-label={`Clave del criterio ${j + 1} de la prueba ${n}`}
                      aria-invalid={err(`criteria.${j}.key`) ? true : undefined}
                      placeholder="clave"
                      spellCheck={false}
                      value={c.key}
                      onChange={(e) => onCriteria((all) => all.map((x) => (x.uid === c.uid ? { ...x, key: e.target.value } : x)))}
                    />
                    {err(`criteria.${j}.key`) ? <p className="text-xs text-destructive text-pretty">{err(`criteria.${j}.key`)}</p> : null}
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <Input
                      aria-label={`Criterio ${j + 1} de la prueba ${n}`}
                      aria-invalid={err(`criteria.${j}.text`) ? true : undefined}
                      maxLength={300}
                      value={c.text}
                      onChange={(e) => onCriteria((all) => all.map((x) => (x.uid === c.uid ? { ...x, text: e.target.value } : x)))}
                    />
                    {err(`criteria.${j}.text`) ? <p className="text-xs text-destructive text-pretty">{err(`criteria.${j}.text`)}</p> : null}
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={form.criteria.length <= 1}
                    aria-label={`Quitar el criterio ${j + 1} de la prueba ${n}`}
                    onClick={() => onCriteria((all) => all.filter((x) => x.uid !== c.uid))}
                  >
                    Quitar
                  </Button>
                </li>
              ))}
            </ul>
            <div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={form.criteria.length >= MAX_CRITERIA}
                onClick={() => onCriteria((all) => [...all, blankCriterion()])}
              >
                Añadir criterio
              </Button>
            </div>
          </fieldset>
          <label className="flex min-h-6 items-center gap-2 text-sm sm:col-span-2">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={form.critical}
              onChange={(e) => onChange({ critical: e.target.checked })}
            />
            Crítica: si no pasa, se señala aparte en cada pasada
          </label>
        </fieldset>
      ) : null}
    </li>
  );
}
