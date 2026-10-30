"use client";

import { OctagonAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button, Callout, Field, Section, StatusBadge, Textarea } from "@nexus/ui";
import type { ClientDataFinding, GeneratedGuide } from "@/lib/backend-sector-guides";

import { DATE } from "../labels";
import { TestEditor } from "../sector-tests/sector-editor";
import {
  TESTS_PER_SECTOR,
  blankTest,
  formFromTest,
  testsFromForms,
  testsWithErrors,
  type CriterionForm,
  type TestForm,
} from "../sector-tests/sector-tests";
import { reviewGeneratedGuideAction } from "./actions";
import { GeneratedTests } from "./generated-tests";
import { GuideEditor } from "./guide-editor";
import { GuideView } from "./guide-view";
import { PromoteDialog } from "./promote-dialog";
import {
  GUIDE_STATUS,
  KIND_LABEL,
  LIST_PATH,
  NOTE_MAX,
  buildReviewBody,
  fieldPath,
  findingAnchor,
  findingErrors,
  findingPlace,
  findingsByField,
  formFromGuide,
  guideFromForm,
  noteError,
  plural,
  promoteBlockers,
  whoLabel,
  type GuideForm,
} from "./sector-guides";

type Props = {
  guide: GeneratedGuide;
  /** The operator looking, to say «por ti». */
  operatorEmail: string;
  /** Keys that already have a guide, and `otro`. */
  takenKeys: readonly string[];
};

/** Hide the errors under a key the person has just changed: `ask.1`, or a whole list (`ask`). */
function without(errors: Record<string, string>, touched: ReadonlySet<string>): Record<string, string> {
  if (!touched.size) return errors;
  if (touched.has("*")) return {};
  return Object.fromEntries(
    Object.entries(errors).filter(([key]) => ![...touched].some((t) => key === t || key.startsWith(`${t}.`))),
  );
}

const add = (set: ReadonlySet<string>, key: string) => new Set(set).add(key);

/**
 * Spec 047 (T201, 58.5): one guide generated for a client, to review it — with
 * the client's data marked where it is — and, reviewed and clean, to convert
 * it into an Auphere guide. The guide and its tests belong to the client until
 * then.
 */
export function GeneratedGuideView({ guide: g, operatorEmail, takenKeys }: Props) {
  const router = useRouter();
  const open = g.status === "generated" || g.status === "reviewed";

  const [findings, setFindings] = useState<ClientDataFinding[]>(g.client_data);
  const [editing, setEditing] = useState(false);
  const [guideForm, setGuideForm] = useState<GuideForm>(() => formFromGuide(g.guide));
  const [testForms, setTestForms] = useState<TestForm[]>(() => g.tests.map(formFromTest));
  const [openTests, setOpenTests] = useState<Set<string>>(() => new Set());
  const [guideErrors, setGuideErrors] = useState<Record<string, string>>({});
  const [testErrors, setTestErrors] = useState<Record<string, string>>({});
  const [touchedGuide, setTouchedGuide] = useState<ReadonlySet<string>>(() => new Set());
  const [touchedTests, setTouchedTests] = useState<ReadonlySet<string>>(() => new Set());
  const [note, setNote] = useState("");
  const [noteProblem, setNoteProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const busy = useRef(false);

  const marks = useMemo(() => findingsByField(findings), [findings]);
  const fromFindings = useMemo(() => findingErrors(findings), [findings]);
  const shownGuideErrors = { ...without(fromFindings.guide, touchedGuide), ...guideErrors };
  const shownTestErrors = { ...without(fromFindings.tests, touchedTests), ...testErrors };
  const wrongTests = testsWithErrors(shownTestErrors);

  function startEditing() {
    setGuideForm(formFromGuide(g.guide));
    setTestForms(g.tests.map(formFromTest));
    // Open the tests the API marked, so their fields show where the data is.
    const marked = testsWithErrors(fromFindings.tests);
    setOpenTests(new Set(g.tests.map((_, i) => i).filter((i) => marked.has(i)).map(String)));
    setGuideErrors({});
    setTestErrors({});
    setTouchedGuide(new Set());
    setTouchedTests(new Set());
    setFailure(null);
    setEditing(true);
  }

  function stopEditing() {
    setEditing(false);
    setGuideErrors({});
    setTestErrors({});
    setFailure(null);
  }

  // The «open» set goes by index, like the errors of `testsFromForms`;
  // removing a test moves the indexes, so it starts again.
  const testKey = (i: number) => String(i);
  const toggleTest = (i: number) =>
    setOpenTests((s) => {
      const next = new Set(s);
      if (next.has(testKey(i))) next.delete(testKey(i));
      else next.add(testKey(i));
      return next;
    });
  const touchTest = (key: string) => {
    setTouchedTests((s) => add(s, key));
    setTestErrors((e) => without(e, new Set([key])));
  };
  const updateTest = (uid: string, i: number, patch: Partial<TestForm>) => {
    setTestForms((all) => all.map((f) => (f.uid === uid ? { ...f, ...patch } : f)));
    for (const field of Object.keys(patch)) touchTest(`${i}.${field}`);
  };
  const updateCriteria = (uid: string, i: number, change: (c: CriterionForm[]) => CriterionForm[]) => {
    setTestForms((all) => all.map((f) => (f.uid === uid ? { ...f, criteria: change(f.criteria) } : f)));
    touchTest(`${i}.criteria`);
  };
  const removeTest = (uid: string) => {
    // The indexes move: the old errors would point at the wrong test.
    setTestForms((all) => all.filter((f) => f.uid !== uid));
    setTestErrors({});
    setTouchedTests(new Set(["*"]));
    setOpenTests(new Set());
  };
  const addTest = () => {
    const i = testForms.length;
    setTestForms((all) => [...all, blankTest()]);
    setOpenTests((s) => new Set(s).add(testKey(i)));
  };

  async function review() {
    if (busy.current) return;
    setFailure(null);
    const problem = noteError(note);
    setNoteProblem(problem);
    let edited = null;
    if (editing) {
      const checkedGuide = guideFromForm(guideForm);
      const checkedTests = testsFromForms(testForms);
      setGuideErrors(checkedGuide.ok ? {} : checkedGuide.errors);
      setTestErrors(checkedTests.ok ? {} : checkedTests.errors);
      if (!checkedTests.ok) {
        const wrong = testsWithErrors(checkedTests.errors);
        setOpenTests((s) => new Set([...s, ...[...wrong].map(testKey)]));
      }
      if (!checkedGuide.ok || !checkedTests.ok) {
        setFailure("Hay campos por corregir: están marcados en la guía y en las pruebas.");
        return;
      }
      edited = { guide: checkedGuide.guide, tests: checkedTests.tests };
    }
    if (problem) return;

    busy.current = true;
    setPending(true);
    try {
      const result = await reviewGeneratedGuideAction(g.tenant_id, g.guide_id, buildReviewBody(g, edited, note));
      if (!result.ok) {
        setFailure(result.error);
        if (result.findings) {
          // What the API found on what would have been saved: mark it again.
          setFindings(result.findings);
          setTouchedGuide(new Set());
          setTouchedTests(new Set());
        }
        return;
      }
      toast.success("Guía revisada");
      setFindings(result.data.client_data ?? []);
      setEditing(false);
      setNote("");
      router.refresh();
    } finally {
      busy.current = false;
      setPending(false);
    }
  }

  const status = GUIDE_STATUS[g.status];
  const blockers = promoteBlockers({ ...g, client_data: findings });
  const reviewLabel = editing ? "Guardar las correcciones y marcar como revisada" : g.status === "reviewed" ? "Volver a marcar como revisada" : "Marcar como revisada";

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
        <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
        <p className="min-w-0 flex-1 text-sm text-muted-foreground text-pretty">
          Generada el {DATE.format(new Date(g.created_at))}
          {g.reviewed_at ? ` · Revisada por ${whoLabel(g.reviewed_by, operatorEmail)} el ${DATE.format(new Date(g.reviewed_at))}` : ""}
        </p>
        {open ? (
          <Button type="button" size="sm" variant="outline" onClick={editing ? stopEditing : startEditing} disabled={pending}>
            {editing ? "Descartar las correcciones" : "Corregir la guía y las pruebas"}
          </Button>
        ) : null}
      </div>

      <Notices guide={g} findings={findings} editing={editing} />

      <Section title="La guía" description="Lo que el constructor recibe como ejemplo de oficio para los agentes de este cliente.">
        {editing ? (
          <GuideEditor
            form={guideForm}
            errors={shownGuideErrors}
            onChange={(next, touched) => {
              setGuideForm(next);
              setTouchedGuide((s) => add(s, touched));
              setGuideErrors((e) => without(e, new Set([touched])));
            }}
          />
        ) : (
          <GuideView guide={g.guide} marks={marks} />
        )}
      </Section>

      <Section
        title="Las pruebas"
        description={`Las ${TESTS_PER_SECTOR} pruebas del sector que se generaron con la guía. Al convertirla, pasan a ser la versión 1 del catálogo de su clave.`}
      >
        {editing ? (
          <div className="flex flex-col gap-3">
            <p className={testForms.length === TESTS_PER_SECTOR ? "text-sm text-muted-foreground tabular-nums" : "text-sm font-medium tabular-nums"}>
              {testForms.length} de {TESTS_PER_SECTOR} pruebas
            </p>
            <ol className="flex flex-col gap-3">
              {testForms.map((f, i) => (
                <TestEditor
                  key={f.uid}
                  form={f}
                  index={i}
                  open={openTests.has(testKey(i))}
                  hasErrors={wrongTests.has(i)}
                  errors={shownTestErrors}
                  onToggle={() => toggleTest(i)}
                  onChange={(patch) => updateTest(f.uid, i, patch)}
                  onCriteria={(change) => updateCriteria(f.uid, i, change)}
                  onRemove={() => removeTest(f.uid)}
                />
              ))}
            </ol>
            <div>
              <Button type="button" size="sm" variant="outline" onClick={addTest} disabled={testForms.length >= TESTS_PER_SECTOR}>
                Añadir prueba
              </Button>
            </div>
            {shownTestErrors.count ? (
              <p role="alert" className="text-sm text-destructive text-pretty">
                {shownTestErrors.count}
              </p>
            ) : null}
          </div>
        ) : (
          <GeneratedTests tests={g.tests} marks={marks} />
        )}
      </Section>

      {open ? (
        <Section
          title="Revisión"
          description="Al marcarla como revisada, la API vuelve a buscar datos del cliente en lo que queda guardado. Si encuentra alguno no guarda nada y dice dónde está."
        >
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void review();
            }}
          >
            <Field
              label="Nota"
              optionalLabel="Opcional"
              hint={`Queda en la auditoría. Hasta ${NOTE_MAX} caracteres. Por ejemplo, «Quitado el teléfono del paso 2».`}
              error={noteProblem ?? undefined}
            >
              {(a11y) => <Textarea {...a11y} rows={2} maxLength={NOTE_MAX} value={note} onChange={(e) => setNote(e.target.value)} />}
            </Field>
            {failure ? (
              <p role="alert" className="text-sm text-destructive text-pretty">
                {failure}
              </p>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2">
              <Button type="submit" disabled={pending} aria-busy={pending || undefined}>
                {pending ? "Revisando…" : reviewLabel}
              </Button>
            </div>
          </form>
        </Section>
      ) : null}

      {open ? (
        <Section
          title="Convertir en guía de Auphere"
          description={`Desde entonces, cada cliente de «Otro» con la etiqueta «${g.sector_label}» recibe esta guía en lugar de generar la suya.`}
        >
          {editing ? (
            <p className="text-sm text-muted-foreground text-pretty">
              Guarda o descarta las correcciones antes de convertirla. Lo que se convierte es la guía guardada.
            </p>
          ) : g.promotable && !blockers.length ? (
            <div>
              <PromoteDialog guide={g} takenKeys={takenKeys} onFindings={(f) => setFindings(f)} />
            </div>
          ) : (
            <div className="flex flex-col gap-2 text-sm">
              <p className="text-muted-foreground">Para convertirla le falta:</p>
              <ul aria-label="Lo que le falta para convertirla" className="flex list-disc flex-col gap-1 pl-5">
                {blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </div>
          )}
        </Section>
      ) : null}
    </div>
  );
}

/** What the guide needs, in the order it matters: the client's data first. */
function Notices({ guide: g, findings, editing }: { guide: GeneratedGuide; findings: ClientDataFinding[]; editing: boolean }) {
  const titleId = "client-data-title";
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {findings.length ? (
        <section
          aria-labelledby={titleId}
          className="flex min-w-0 flex-col gap-2 rounded-md border border-status-danger-border bg-status-danger-bg px-3 py-2 text-sm"
        >
          <h2 id={titleId} className="flex items-center gap-2 font-medium text-balance">
            <OctagonAlert className="size-4 shrink-0 text-destructive" aria-hidden="true" />
            Lleva {plural(findings.length, "dato", "datos")} del cliente
          </h2>
          <p className="text-pretty text-muted-foreground">
            Una guía de Auphere no puede llevar el nombre del cliente, su web, teléfonos, correos, direcciones, sedes ni personas del
            equipo. Corrígela y vuelve a marcarla como revisada.
          </p>
          <ul className="flex flex-col gap-1">
            {findings.map((f, i) => {
              const path = fieldPath(f.pointer);
              const place = findingPlace(f.pointer);
              return (
                <li key={`${f.pointer}:${i}`} className="min-w-0 text-pretty break-words">
                  {path && !editing ? (
                    <a href={`#${findingAnchor(path)}`} className="font-medium underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring">
                      {place}
                    </a>
                  ) : (
                    <span className="font-medium">{place}</span>
                  )}
                  {` · ${KIND_LABEL[f.kind] ?? f.kind} «${f.excerpt}»`}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
      {g.tests.length !== TESTS_PER_SECTOR ? (
        <Callout tone="warning" title={`Tiene ${g.tests.length} de ${TESTS_PER_SECTOR} pruebas`}>
          Para revisarla y convertirla tienen que quedar exactamente {TESTS_PER_SECTOR}. Corrígelas.
        </Callout>
      ) : null}
      {g.status === "generated" && !findings.length ? (
        <Callout tone="info" title="Falta revisarla">
          Léela, corrige lo que haga falta y márcala como revisada. Es del cliente: nadie más la ve hasta que se convierta.
        </Callout>
      ) : null}
      {g.status === "reviewed" && g.promotable && !findings.length ? (
        <Callout tone="positive" title="Lista para convertir">
          Revisada, sin datos del cliente y con sus {TESTS_PER_SECTOR} pruebas.
        </Callout>
      ) : null}
      {g.status === "promoted" ? (
        <Callout tone="positive" title="Convertida en guía de Auphere">
          Con la clave «{g.promoted_to}»{g.promoted_at ? ` desde el ${DATE.format(new Date(g.promoted_at))}` : ""}. Los clientes de «Otro»
          con la etiqueta «{g.sector_label}» la reciben en lugar de generar la suya. <Link href={LIST_PATH}>Ver las guías de Auphere</Link>
        </Callout>
      ) : null}
      {g.status === "archived" ? (
        <Callout tone="neutral" title="Archivada">
          Ya no se puede revisar ni convertir.
        </Callout>
      ) : null}
    </div>
  );
}
