/**
 * Spec 047 (T090, 21.2, 54.10): the sector catalog as the editor shows it —
 * one form per test — and back. Pure, so it is tested on its own. The rules
 * are those of `services/testing/sector_catalog.py` (`SectorTest`), which the
 * API checks again: exactly 12 tests, unique keys, and each one with name,
 * first message and between 1 and 6 criteria.
 */
import type { SectorCriterion, SectorTest } from "@/lib/backend-builder";

export const TESTS_PER_SECTOR = 12;
export const MAX_CRITERIA = 6;

const KEY = /^[a-z0-9_]{1,40}$/;
const LIMITS = { name: 120, persona: 500, first_message: 2000, plan: 1000, criterion: 300 } as const;

export type CriterionForm = { uid: string; key: string; text: string };

export type TestForm = {
  /** Stable identity for React; never sent. */
  uid: string;
  key: string;
  name: string;
  persona: string;
  first_message: string;
  plan: string;
  /** The JSON of `expected_state`, as typed. */
  expected_state: string;
  criteria: CriterionForm[];
  critical: boolean;
};

let seq = 0;
const nextUid = () => `t${++seq}`;

export function formFromTest(test: SectorTest): TestForm {
  const state = test.expected_state ?? {};
  return {
    uid: nextUid(),
    key: test.key,
    name: test.name,
    persona: test.persona ?? "",
    first_message: test.first_message,
    plan: test.plan ?? "",
    expected_state: Object.keys(state).length ? JSON.stringify(state, null, 2) : "",
    criteria: (test.criteria ?? []).map((c) => ({ uid: nextUid(), key: c.key, text: c.text })),
    critical: Boolean(test.critical),
  };
}

export function blankCriterion(): CriterionForm {
  return { uid: nextUid(), key: "", text: "" };
}

export function blankTest(): TestForm {
  return {
    uid: nextUid(),
    key: "",
    name: "",
    persona: "",
    first_message: "",
    plan: "",
    expected_state: "",
    criteria: [blankCriterion()],
    critical: false,
  };
}

/** The forms to start editing from: the version in force, or 12 empty tests. */
export function formsFromCatalog(tests: SectorTest[]): TestForm[] {
  return tests.length ? tests.map(formFromTest) : Array.from({ length: TESTS_PER_SECTOR }, blankTest);
}

export type CheckedTests = { ok: true; tests: SectorTest[] } | { ok: false; errors: Record<string, string> };

const KEY_RULE = "Minúsculas, cifras y «_», hasta 40 caracteres.";

function parseState(raw: string): Record<string, unknown> | null {
  if (!raw.trim()) return {};
  try {
    const value: unknown = JSON.parse(raw);
    return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/**
 * The tests to publish, or what is wrong with them. Error keys: `count`,
 * `{i}.{field}`, `{i}.criteria` and `{i}.criteria.{j}.{key|text}`.
 */
export function testsFromForms(forms: TestForm[]): CheckedTests {
  const errors: Record<string, string> = {};
  if (forms.length !== TESTS_PER_SECTOR) {
    errors.count = `Cada sector lleva exactamente ${TESTS_PER_SECTOR} pruebas; ahora hay ${forms.length}.`;
  }
  const seen = new Map<string, number>();
  const tests: SectorTest[] = forms.map((f, i) => {
    const key = f.key.trim();
    const name = f.name.trim();
    const persona = f.persona.trim();
    const first = f.first_message.trim();
    const plan = f.plan.trim();
    if (!KEY.test(key)) errors[`${i}.key`] = key ? KEY_RULE : "Hace falta la clave.";
    else if (seen.has(key)) errors[`${i}.key`] = `La clave «${key}» ya la usa la prueba ${seen.get(key)! + 1}.`;
    else seen.set(key, i);
    if (!name) errors[`${i}.name`] = "Hace falta el nombre.";
    else if (name.length > LIMITS.name) errors[`${i}.name`] = `Como mucho ${LIMITS.name} caracteres.`;
    if (persona.length > LIMITS.persona) errors[`${i}.persona`] = `Como mucho ${LIMITS.persona} caracteres.`;
    if (!first) errors[`${i}.first_message`] = "Hace falta el primer mensaje.";
    else if (first.length > LIMITS.first_message) errors[`${i}.first_message`] = `Como mucho ${LIMITS.first_message} caracteres.`;
    if (plan.length > LIMITS.plan) errors[`${i}.plan`] = `Como mucho ${LIMITS.plan} caracteres.`;
    const state = parseState(f.expected_state);
    if (state === null) errors[`${i}.expected_state`] = "Tiene que ser un objeto JSON, por ejemplo {\"booking\": {\"created\": true}}.";
    if (f.criteria.length < 1 || f.criteria.length > MAX_CRITERIA) {
      errors[`${i}.criteria`] = `Entre 1 y ${MAX_CRITERIA} criterios.`;
    }
    const criterionKeys = new Set<string>();
    const criteria: SectorCriterion[] = f.criteria.map((c, j) => {
      const ckey = c.key.trim();
      const text = c.text.trim();
      if (!KEY.test(ckey)) errors[`${i}.criteria.${j}.key`] = ckey ? KEY_RULE : "Hace falta la clave.";
      else if (criterionKeys.has(ckey)) errors[`${i}.criteria.${j}.key`] = "Repetida en esta prueba: el juez da un veredicto por clave.";
      criterionKeys.add(ckey);
      if (!text) errors[`${i}.criteria.${j}.text`] = "Hace falta el criterio.";
      else if (text.length > LIMITS.criterion) errors[`${i}.criteria.${j}.text`] = `Como mucho ${LIMITS.criterion} caracteres.`;
      return { key: ckey, text };
    });
    return {
      key,
      name,
      persona,
      first_message: first,
      plan,
      expected_state: state ?? {},
      criteria,
      critical: f.critical,
    };
  });
  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, tests };
}

/** Which tests have something to fix, by index. */
export function testsWithErrors(errors: Record<string, string>): Set<number> {
  const out = new Set<number>();
  for (const key of Object.keys(errors)) {
    const index = Number(key.split(".")[0]);
    if (Number.isInteger(index)) out.add(index);
  }
  return out;
}

/** `sector_catalog.SectorCatalogError` codes, in words. */
export const PUBLISH_ERRORS: Record<string, string> = {
  twelve_tests_required: `Cada sector lleva exactamente ${TESTS_PER_SECTOR} pruebas.`,
  duplicate_key: "Dos pruebas tienen la misma clave.",
  invalid_test: "La API rechaza el formato de alguna prueba: revisa claves, nombres, primeros mensajes y criterios.",
  unknown_sector: "Ese sector no existe.",
};
