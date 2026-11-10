"use client";

import { Button, Field, Input, Textarea } from "@nexus/ui";

import {
  GUIDE_LIMITS,
  blankItem,
  blankProcedure,
  type GuideForm,
  type ProcedureForm,
  type TextItem,
} from "./sector-guides";

type ListKey = "ask" | "risks" | "tools";

type Props = {
  form: GuideForm;
  /** Validation and client-data errors by key (`ask.1`, `procedures.0.steps`…). */
  errors: Record<string, string>;
  onChange: (next: GuideForm, touched: string) => void;
};

/**
 * Spec 047 (T201, 58.5): the corrections of a generated guide — what to ask,
 * the procedures, what goes to a person and the tools — with the limits of
 * `contracts/admin-sector-guides.md`. The client's data found by the API shows
 * as the error of the field it is in.
 */
export function GuideEditor({ form, errors, onChange }: Props) {
  const setList = (key: ListKey, items: TextItem[], touched: string) => onChange({ ...form, [key]: items }, touched);
  const setProcedures = (procedures: ProcedureForm[], touched: string) => onChange({ ...form, procedures }, touched);
  const L = GUIDE_LIMITS;

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <TextList
        legend="Qué preguntar al negocio"
        hint={`De 1 a ${L.ask.max} frases, cada una de hasta ${L.ask.length} caracteres.`}
        listKey="ask"
        items={form.ask}
        max={L.ask.max}
        maxLength={L.ask.length}
        itemLabel={(n) => `Frase ${n} de qué preguntar`}
        removeLabel={(n) => `Quitar la frase ${n} de qué preguntar`}
        addLabel="Añadir frase"
        errors={errors}
        onChange={(items, touched) => setList("ask", items, touched)}
      />

      <fieldset className="flex min-w-0 flex-col gap-3">
        <legend className="text-sm font-medium">Procedimientos típicos</legend>
        <p className="text-xs text-muted-foreground text-pretty">
          Hasta {L.procedures.max}. Cada uno con su título, cuándo aplica y sus pasos.
        </p>
        {errors.procedures ? (
          <p role="alert" className="text-xs text-destructive">
            {errors.procedures}
          </p>
        ) : null}
        <ol className="flex flex-col gap-3">
          {form.procedures.map((p, i) => {
            const n = i + 1;
            const err = (field: string) => errors[`procedures.${i}.${field}`];
            const set = (patch: Partial<ProcedureForm>, field: string) =>
              setProcedures(
                form.procedures.map((x) => (x.uid === p.uid ? { ...x, ...patch } : x)),
                `procedures.${i}.${field}`,
              );
            return (
              <li key={p.uid} className="rounded-md ring-1 ring-foreground/10">
                <fieldset className="grid min-w-0 grid-cols-1 gap-3 px-4 py-4 sm:grid-cols-2">
                  <legend className="sr-only">Procedimiento {n}</legend>
                  <div className="flex min-w-0 items-center justify-between gap-2 sm:col-span-2">
                    <p aria-hidden="true" className="text-sm font-medium">
                      Procedimiento {n}
                    </p>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      aria-label={`Quitar el procedimiento ${n}`}
                      onClick={() => setProcedures(form.procedures.filter((x) => x.uid !== p.uid), "procedures")}
                    >
                      Quitar
                    </Button>
                  </div>
                  <Field label="Título" required requiredLabel="Obligatorio" error={err("title")}>
                    {(a11y) => (
                      <Input {...a11y} maxLength={L.procedures.title} value={p.title} onChange={(e) => set({ title: e.target.value }, "title")} />
                    )}
                  </Field>
                  <Field label="Cuándo" optionalLabel="Opcional" error={err("when")}>
                    {(a11y) => (
                      <Input {...a11y} maxLength={L.procedures.when} value={p.when} onChange={(e) => set({ when: e.target.value }, "when")} />
                    )}
                  </Field>
                  <Field label="Pasos" required requiredLabel="Obligatorio" className="sm:col-span-2" error={err("steps")}>
                    {(a11y) => (
                      <Textarea
                        {...a11y}
                        rows={3}
                        maxLength={L.procedures.steps}
                        value={p.steps}
                        onChange={(e) => set({ steps: e.target.value }, "steps")}
                      />
                    )}
                  </Field>
                </fieldset>
              </li>
            );
          })}
        </ol>
        <div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={form.procedures.length >= L.procedures.max}
            onClick={() => setProcedures([...form.procedures, blankProcedure()], "procedures")}
          >
            Añadir procedimiento
          </Button>
        </div>
      </fieldset>

      <TextList
        legend="Lo que hay que pasar a una persona"
        hint={`Hasta ${L.risks.max} frases, cada una de hasta ${L.risks.length} caracteres.`}
        listKey="risks"
        items={form.risks}
        max={L.risks.max}
        maxLength={L.risks.length}
        itemLabel={(n) => `Frase ${n} de lo que hay que pasar a una persona`}
        removeLabel={(n) => `Quitar la frase ${n} de lo que hay que pasar a una persona`}
        addLabel="Añadir frase"
        errors={errors}
        onChange={(items, touched) => setList("risks", items, touched)}
      />

      <TextList
        legend="Herramientas que suele necesitar"
        hint={`Hasta ${L.tools.max} nombres del catálogo, como reservas.find_slots. Nunca booking.*.`}
        listKey="tools"
        items={form.tools}
        max={L.tools.max}
        mono
        itemLabel={(n) => `Herramienta ${n}`}
        removeLabel={(n) => `Quitar la herramienta ${n}`}
        addLabel="Añadir herramienta"
        errors={errors}
        onChange={(items, touched) => setList("tools", items, touched)}
      />
    </div>
  );
}

type TextListProps = {
  legend: string;
  hint: string;
  listKey: ListKey;
  items: TextItem[];
  max: number;
  maxLength?: number;
  mono?: boolean;
  itemLabel: (n: number) => string;
  removeLabel: (n: number) => string;
  addLabel: string;
  errors: Record<string, string>;
  onChange: (items: TextItem[], touched: string) => void;
};

/** A list of sentences (or names), one input each, with «Quitar» and «Añadir». */
function TextList({ legend, hint, listKey, items, max, maxLength, mono, itemLabel, removeLabel, addLabel, errors, onChange }: TextListProps) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="text-sm font-medium">{legend}</legend>
      <p className="text-xs text-muted-foreground text-pretty">{hint}</p>
      {errors[listKey] ? (
        <p role="alert" className="text-xs text-destructive">
          {errors[listKey]}
        </p>
      ) : null}
      <ol className="flex flex-col gap-2">
        {items.map((item, i) => {
          const n = i + 1;
          const error = errors[`${listKey}.${i}`];
          const errorId = `${listKey}-${item.uid}-error`;
          return (
            <li key={item.uid} className="flex min-w-0 flex-col gap-1">
              <div className="flex min-w-0 items-start gap-2">
                <Input
                  aria-label={itemLabel(n)}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? errorId : undefined}
                  maxLength={maxLength}
                  spellCheck={mono ? false : undefined}
                  className={mono ? "min-w-0 flex-1 font-mono text-xs" : "min-w-0 flex-1"}
                  value={item.text}
                  onChange={(e) =>
                    onChange(
                      items.map((x) => (x.uid === item.uid ? { ...x, text: e.target.value } : x)),
                      `${listKey}.${i}`,
                    )
                  }
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  aria-label={removeLabel(n)}
                  onClick={() => onChange(items.filter((x) => x.uid !== item.uid), listKey)}
                >
                  Quitar
                </Button>
              </div>
              {error ? (
                <p id={errorId} className="text-xs text-destructive text-pretty break-words">
                  {error}
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
      <div>
        <Button type="button" size="sm" variant="outline" disabled={items.length >= max} onClick={() => onChange([...items, blankItem()], listKey)}>
          {addLabel}
        </Button>
      </div>
    </fieldset>
  );
}
