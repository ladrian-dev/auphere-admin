import type {
  AgentReview,
  AgentTest,
  HistoryEntry,
  PlaygroundSession,
  PublishPreview,
  QualityJob,
  TestSuite,
} from "@/lib/backend/agent-quality-types";

/** Spec 047 (T089, T094) — los datos de prueba del probador, las pruebas, la revisión y «Guardar». */

export const REF = "barberia-cultor";
export const AGENT = "11111111-1111-4111-8111-111111111111";
export const SESSION = "55555555-5555-4555-8555-555555555555";
export const JOB = "66666666-6666-4666-8666-666666666666";

export const ok = <T,>(data: T) => ({ ok: true as const, data });
export const fail = (status: number, code: string | null = null, info?: Record<string, unknown>) => ({
  ok: false as const,
  status,
  message: "",
  code,
  ...(info ? { info } : {}),
});
/** Una espera que no espera: los trabajos se consultan en seguida. */
export const noWait = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

export function session(over: Partial<PlaygroundSession> = {}): PlaygroundSession {
  return {
    session_id: SESSION,
    version_number: 3,
    is_draft: true,
    timezone: "Europe/Madrid",
    now: "2026-10-27T11:20:00+01:00",
    agenda: [{ id: "b1", service: "Corte", when: "28/10/2026 a las 10:00", status: "confirmed" }],
    services: [{ name: "Corte", bookable: true, duration_min: 30, price: "15 €" }],
    transcript: [],
    created_by: "console:luis@ladrian.studio",
    allowed: ["send", "set_time", "close"],
    ...over,
  };
}

export function test(over: Partial<AgentTest> = {}): AgentTest {
  return {
    id: "77777777-7777-4777-8777-000000000001",
    kind: "case",
    name: "Pregunta el horario",
    persona: "Cliente habitual",
    first_message: "¿A qué hora abrís mañana?",
    plan: "",
    expected_state: {},
    criteria: [],
    critical: false,
    not_applicable_reason: null,
    sector_test_ref: null,
    stale: false,
    status: "passed",
    passes: 3,
    decided: 3,
    why_failed: null,
    ...over,
  };
}

export const TESTS: AgentTest[] = [
  test({}),
  test({
    id: "77777777-7777-4777-8777-000000000002",
    name: "Reserva una cita",
    critical: true,
    status: "failed",
    passes: 0,
    decided: 3,
    why_failed: "La cita no existe en la agenda al terminar.",
  }),
  test({ id: "77777777-7777-4777-8777-000000000003", name: "Pide un descuento", status: "flaky", passes: 2, decided: 3, stale: true }),
  test({
    id: "77777777-7777-4777-8777-000000000004",
    kind: "sector",
    name: "Pregunta por aparcamiento",
    status: "not_run",
    passes: 0,
    decided: 0,
    sector_test_ref: "barber.parking",
  }),
  test({
    id: "77777777-7777-4777-8777-000000000005",
    kind: "sector",
    name: "Pide cita para un perro",
    status: "not_applicable",
    not_applicable_reason: "No atendemos mascotas",
    passes: 0,
    decided: 0,
  }),
  test({ id: "77777777-7777-4777-8777-000000000006", kind: "person", name: "Pregunta por la tarjeta regalo", status: "unknown", passes: 1, decided: 2 }),
];

export function suite(over: Partial<TestSuite> = {}): TestSuite {
  return {
    summary: {
      passed: 1,
      flaky: 1,
      failed: 1,
      unknown: 1,
      not_run: 1,
      not_applicable: 1,
      total: 6,
      stale: 1,
      critical_failed: ["77777777-7777-4777-8777-000000000002"],
      rate: 61.11,
    },
    tests: TESTS,
    judge_calibrated: true,
    allowed: ["add", "edit", "run"],
    ...over,
  };
}

export const REVIEW: AgentReview = {
  version_number: 3,
  findings: [
    {
      code: "skill_without_integration",
      severity: "block",
      message: "La habilidad Reservas necesita Google Calendar y no está conectada.",
      fix: { kind: "link", target: "integrations", integration: "googlecalendar" },
    },
    {
      code: "contradicts_hours",
      severity: "warn",
      message: "Contradice la ficha: horario del domingo.",
      pointer: "/instructions/sections/0/body",
      fix: { kind: "edit", pointer: "/instructions/sections/0/body" },
    },
    {
      code: "unknown_tool",
      severity: "block",
      message: "Cita una herramienta que no existe: reservas.borrar.",
      fix: { kind: "proposal", proposal_id: "88888888-8888-4888-8888-888888888888" },
    },
    { code: "service_without_price", severity: "warn", message: "El servicio Tinte no tiene precio.", fix: { kind: "link", target: "business/services" } },
  ],
  checks: [
    { check: "skills_integrations", ok: false, findings: 1 },
    { check: "services", ok: false, findings: 1 },
    { check: "hours", ok: true, findings: 0 },
    { check: "contradictions", ok: false, findings: 1 },
    { check: "promises", ok: true, findings: 0 },
    { check: "tools_exist", ok: false, findings: 1 },
    { check: "escalation_recipients", ok: true, findings: 0 },
    { check: "ai_disclosure", ok: true, findings: 0 },
  ],
  blocking: 2,
};

export function preview(over: Partial<PublishPreview> = {}): PublishPreview {
  return {
    action: "save",
    has_draft: true,
    has_channels: false,
    diff: [],
    gate: null,
    can_override: false,
    ...over,
  };
}

export function job(over: Partial<QualityJob> = {}): QualityJob {
  return {
    job_id: JOB,
    kind: "publish",
    status: "running",
    agent_id: AGENT,
    progress: { step: "testing", blocks: [] },
    result: null,
    error_code: null,
    created_at: "2026-10-27T10:00:00Z",
    finished_at: null,
    ...over,
  };
}

export const HISTORY: HistoryEntry[] = [
  {
    number: 3,
    status: "active",
    author: "console:luis@ladrian.studio",
    created_at: "2026-10-27T09:00:00Z",
    published_at: "2026-10-27T09:30:00Z",
    published_by: "console:luis@ladrian.studio",
    note: "Respuestas más cortas",
    changed: ["instructions", "rules"],
    model_policy: null,
    tests: { rate: 95, conditions: [] },
    override_reason: "El cliente abre mañana y la prueba de aparcamiento no aplica",
  },
  {
    number: 2,
    status: "archived",
    author: "console:lucia@ladrian.studio",
    created_at: "2026-10-20T09:00:00Z",
    published_at: "2026-10-20T09:30:00Z",
    published_by: "console:lucia@ladrian.studio",
    note: null,
    changed: ["voice"],
    model_policy: null,
    tests: null,
    override_reason: null,
  },
];
