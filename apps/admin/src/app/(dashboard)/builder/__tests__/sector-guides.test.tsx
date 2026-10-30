import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SectorTest } from "@/lib/backend-builder";
import type {
  GeneratedGuide,
  GeneratedGuideSummary,
  Guide,
  MissingSectors,
  SectorGuide,
} from "@/lib/backend-sector-guides";

const h = vi.hoisted(() => ({ review: vi.fn(), promote: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../sector-guides/actions", () => ({
  reviewGeneratedGuideAction: (...a: unknown[]) => h.review(...a),
  promoteGeneratedGuideAction: (...a: unknown[]) => h.promote(...a),
}));
vi.mock("../actions", () => ({
  publishSectorTestsAction: vi.fn(),
  calibrateJudgeAction: vi.fn(),
  runEvalAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const {
  buildReviewBody,
  checkPromote,
  findingErrors,
  findingPlace,
  formFromGuide,
  guideFailure,
  guideFromForm,
  loadErrorCopy,
  parseLimit,
  promoteBlockers,
  suggestKey,
} = await import("../sector-guides/sector-guides");
const { MissingLabels } = await import("../sector-guides/missing-labels");
const { AuphereGuides } = await import("../sector-guides/auphere-guides");
const { GeneratedGuideView } = await import("../sector-guides/generated-guide");
const { SectionError } = await import("../sector-guides/section-error");
const { SectorGuidesSkeleton, GeneratedGuideSkeleton } = await import("../sector-guides/skeletons");
const { BuilderTabs } = await import("../builder-tabs");

// ── fixtures, in the contract's shapes ─────────────────────────────────────

function test(i: number, o: Partial<SectorTest> = {}): SectorTest {
  return {
    key: `t${i}`,
    name: `Prueba ${i}`,
    persona: "Socio nuevo",
    first_message: `Hola ${i}`,
    plan: "Pregunta y acepta lo primero.",
    expected_state: {},
    criteria: [{ key: "ok", text: "Responde con lo de la ficha." }],
    critical: false,
    ...o,
  };
}

const TWELVE = Array.from({ length: 12 }, (_, i) => test(i));

const GUIDE: Guide = {
  ask: ["¿Atendéis sin cita?", "¿Qué horario tenéis?"],
  procedures: [
    {
      title: "Llegar sin cita",
      when: "Alguien pregunta si puede pasarse ya",
      steps: "Mira el hueco más cercano y, si no hay, llama al 612 345 678.",
    },
  ],
  risks: ["Una lesión durante el entrenamiento"],
  tools: ["reservas.find_slots", "escalate.escalate_to_human"],
};

const TENANT = "aaaaaaaa-0000-0000-0000-000000000001";
const GUIDE_ID = "bbbbbbbb-0000-0000-0000-000000000002";
const PHONE = { pointer: "/guide/procedures/0/steps", kind: "phone" as const, excerpt: "…si no hay, llama al 612 345 678." };

const GENERATED: GeneratedGuide = {
  guide_id: GUIDE_ID,
  tenant_id: TENANT,
  client_name: "Gimnasio Norte",
  sector_label: "Gimnasio",
  label_key: "gimnasio",
  status: "generated",
  guide: GUIDE,
  tests: TWELVE,
  client_data: [PHONE],
  promotable: false,
  reviewed_by: null,
  reviewed_at: null,
  promoted_to: null,
  promoted_at: null,
  created_at: "2026-10-30T09:12:00+00:00",
};

const CLEAN_GUIDE: Guide = {
  ...GUIDE,
  procedures: [{ ...GUIDE.procedures[0]!, steps: "Mira el hueco más cercano." }],
};

const REVIEWED: GeneratedGuide = {
  ...GENERATED,
  guide: CLEAN_GUIDE,
  status: "reviewed",
  client_data: [],
  promotable: true,
  reviewed_by: "operator:ana@auphere.com",
  reviewed_at: "2026-10-30T11:00:00+00:00",
};

function summary(o: Partial<GeneratedGuideSummary> = {}): GeneratedGuideSummary {
  return {
    tenant_id: TENANT,
    client_name: "Gimnasio Norte",
    guide_id: GUIDE_ID,
    status: "generated",
    tests: 12,
    created_at: "2026-10-30T09:12:00+00:00",
    reviewed_at: null,
    reviewed_by: null,
    ...o,
  };
}

const MISSING: MissingSectors = {
  items: [
    {
      label_key: "gimnasio",
      label: "Gimnasio",
      clients: 7,
      guides: { generated: 3, reviewed: 1 },
      candidates: [
        summary({
          guide_id: "g-reviewed",
          client_name: "Box Crossfit Sur",
          status: "reviewed",
          reviewed_by: "operator:ana@auphere.com",
          reviewed_at: "2026-10-30T11:00:00+00:00",
        }),
        summary({ guide_id: "g-new", tests: 11 }),
      ],
    },
    { label_key: "escape_room", label: "Escape room", clients: 2, guides: { generated: 0, reviewed: 0 }, candidates: [] },
    {
      label_key: "tatuajes",
      label: "Tatuajes",
      clients: 0,
      guides: { generated: 1, reviewed: 0 },
      candidates: [summary({ guide_id: "g-old", client_name: "Tinta Fina" })],
    },
  ],
  clients_scanned: 54,
  generated_at: "2026-10-30T10:00:00+00:00",
};

const BARBER: SectorGuide = {
  key: "barberia_peluqueria",
  label: "Barbería y peluquería",
  label_key: "barberia_y_peluqueria",
  source: "template",
  templates: ["barbershop_v1"],
  version: 1,
  tests: 12,
  published_by: null,
  published_at: null,
  guide: GUIDE,
};
const YOGA: SectorGuide = {
  key: "yoga",
  label: "Yoga",
  label_key: "yoga",
  source: "promoted",
  templates: [],
  version: 1,
  tests: 12,
  published_by: "operator:ana@auphere.com",
  published_at: "2026-10-29T08:00:00+00:00",
  guide: { ask: ["¿Qué estilos dais?"], procedures: [], risks: [], tools: [] },
};
const TAKEN = ["barberia_peluqueria", "yoga", "otro"];

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

// ── the rules, pure ────────────────────────────────────────────────────────

/** Spec 047 (T201, 58.5): the screen's rules, from `contracts/admin-sector-guides.md`. */
describe("the rules of a generated guide", () => {
  it("says where each finding is, in words", () => {
    expect(findingPlace("/guide/ask/1")).toBe("Qué preguntar · frase 2");
    expect(findingPlace("/guide/procedures/0/steps")).toBe("Procedimiento 1 · Pasos");
    expect(findingPlace("/guide/procedures/2/when")).toBe("Procedimiento 3 · Cuándo");
    expect(findingPlace("/guide/risks/0")).toBe("Riesgos · frase 1");
    expect(findingPlace("/guide/tools/3")).toBe("Herramientas · 4");
    expect(findingPlace("/tests/3/first_message")).toBe("Prueba 4 · Primer mensaje");
    expect(findingPlace("/tests/0/criteria/1/text")).toBe("Prueba 1 · Criterio 2");
    expect(findingPlace("/tests/5/expected_state/booking/note")).toBe("Prueba 6 · Estado esperado");
    expect(findingPlace("/guide")).toBe("La guía");
  });

  it("turns the findings into errors on the fields the editors show", () => {
    const errors = findingErrors([
      PHONE,
      { pointer: "/guide/ask/1", kind: "email", excerpt: "…hola@gimnasionorte.es…" },
      { pointer: "/tests/3/criteria/0/text", kind: "staff", excerpt: "…pregunta por Marta…" },
      { pointer: "/tests/5/expected_state/booking", kind: "client_name", excerpt: "…Gimnasio Norte…" },
    ]);
    expect(errors.guide["procedures.0.steps"]).toBe("Dato del cliente · Teléfono: «…si no hay, llama al 612 345 678.»");
    expect(errors.guide["ask.1"]).toMatch(/^Dato del cliente · Correo: /);
    expect(errors.tests["3.criteria.0.text"]).toMatch(/^Dato del cliente · Persona del equipo: /);
    expect(errors.tests["5.expected_state"]).toMatch(/^Dato del cliente · Nombre del cliente: /);
  });

  it("goes to the form and back without changing a guide", () => {
    expect(guideFromForm(formFromGuide(GUIDE))).toEqual({ ok: true, guide: GUIDE });
  });

  it("checks the guide like the API does", () => {
    const form = formFromGuide(GUIDE);
    form.ask = [{ uid: "a", text: " " }];
    form.procedures = [{ uid: "p", title: "", when: "x".repeat(301), steps: "" }];
    form.risks = Array.from({ length: 11 }, (_, i) => ({ uid: `r${i}`, text: "Algo" }));
    form.tools = [
      { uid: "x", text: "booking.create" },
      { uid: "y", text: "" },
    ];
    const checked = guideFromForm(form);
    expect(checked.ok).toBe(false);
    if (checked.ok) return;
    expect(checked.errors["ask.0"]).toBe("Escribe la frase o quítala.");
    expect(checked.errors["procedures.0.title"]).toBe("Hace falta el título.");
    expect(checked.errors["procedures.0.when"]).toMatch(/como mucho 300/i);
    expect(checked.errors["procedures.0.steps"]).toBe("Hacen falta los pasos.");
    expect(checked.errors.risks).toMatch(/como mucho 10/i);
    expect(checked.errors["tools.0"]).toMatch(/booking/);
    expect(checked.errors["tools.1"]).toBe("Escribe el nombre o quítala.");

    const none = formFromGuide({ ...GUIDE, ask: [] });
    const noAsk = guideFromForm(none);
    expect(noAsk.ok).toBe(false);
    if (!noAsk.ok) expect(noAsk.errors.ask).toMatch(/al menos una/i);
  });

  it("sends only what changed, so the audit says whether it was edited", () => {
    expect(buildReviewBody(GENERATED, null, "")).toEqual({});
    expect(buildReviewBody(GENERATED, null, "  Leída entera ")).toEqual({ note: "Leída entera" });
    expect(buildReviewBody(GENERATED, { guide: GUIDE, tests: TWELVE }, "")).toEqual({});
    expect(buildReviewBody(GENERATED, { guide: CLEAN_GUIDE, tests: TWELVE }, "Quitado el teléfono")).toEqual({
      guide: CLEAN_GUIDE,
      note: "Quitado el teléfono",
    });
    const renamed = TWELVE.map((t, i) => (i === 2 ? { ...t, name: "Otra" } : t));
    expect(buildReviewBody(GENERATED, { guide: GUIDE, tests: renamed }, "")).toEqual({ tests: renamed });
  });

  it("says what a guide still needs to be converted", () => {
    expect(promoteBlockers(GENERATED)).toEqual(["Revisarla.", "Quitar 1 dato del cliente."]);
    expect(promoteBlockers({ ...REVIEWED, promotable: false, tests: TWELVE.slice(0, 11) })).toEqual([
      "Completar las pruebas: tiene 11 de 12.",
    ]);
    expect(promoteBlockers(REVIEWED)).toEqual([]);
    expect(promoteBlockers({ ...REVIEWED, status: "promoted", promotable: false })).toEqual(["Ya se convirtió."]);
    expect(promoteBlockers({ ...REVIEWED, status: "archived", promotable: false })).toEqual(["Está archivada."]);
  });

  it("checks the conversion like the API does", () => {
    const ok = { key: "gimnasio", label: " Gimnasio ", reason: " Siete clientes " };
    expect(checkPromote(ok, TAKEN)).toEqual({ ok: true, body: { key: "gimnasio", label: "Gimnasio", reason: "Siete clientes" } });
    const bad = checkPromote({ key: "Gym24", label: "", reason: "ok" }, TAKEN);
    expect(bad.ok).toBe(false);
    if (!bad.ok) {
      expect(bad.errors.key).toMatch(/minúsculas y «_»/i);
      expect(bad.errors.label).toBe("Hace falta la etiqueta.");
      expect(bad.errors.reason).toMatch(/al menos 3/);
    }
    for (const key of ["otro", "barberia_peluqueria", "yoga"]) {
      const taken = checkPromote({ ...ok, key }, TAKEN);
      expect(taken.ok).toBe(false);
      if (!taken.ok) expect(taken.errors.key).toBe("Esa clave ya es de un sector o de otra guía de Auphere.");
    }
    const long = checkPromote({ ...ok, label: "x".repeat(41) }, TAKEN);
    expect(long.ok).toBe(false);
    if (!long.ok) expect(long.errors.label).toMatch(/como mucho 40/i);
  });

  it("suggests a key the API accepts from the label", () => {
    expect(suggestKey("gimnasio")).toBe("gimnasio");
    expect(suggestKey("peluquería canina")).toBe("peluqueria_canina");
    expect(suggestKey("crossfit-24h")).toBe("crossfit_h");
    expect(suggestKey("7")).toBe("");
  });

  it("says the API's refusals in words, findings included", () => {
    const findings = [PHONE];
    expect(guideFailure(422, { detail: { code: "client_data_found", findings } }, "review")).toEqual({
      ok: false,
      code: "client_data_found",
      error: "Quedan datos del cliente. Corrígelos y vuelve a marcarla como revisada. No se ha guardado nada.",
      findings,
    });
    expect(guideFailure(409, { detail: { code: "guide_key_taken" } }, "promote").error).toBe(
      "Esa clave ya es de un sector o de otra guía de Auphere.",
    );
    expect(guideFailure(409, { detail: { code: "guide_label_taken" } }, "promote").error).toBe("Esa etiqueta ya tiene guía de Auphere.");
    expect(guideFailure(409, { detail: { code: "guide_not_reviewed" } }, "promote").error).toMatch(/revisarla/);
    expect(guideFailure(409, { detail: { code: "guide_not_reviewable" } }, "review").error).toMatch(/convertida o archivada/);
    expect(guideFailure(404, { detail: { code: "unknown_guide" } }, "review").error).toMatch(/no existe/);
    expect(guideFailure(422, { detail: { code: "twelve_tests_required" } }, "review").error).toMatch(/exactamente 12/);
    expect(guideFailure(400, { detail: "operator required" }, "review").error).toMatch(/sesión de operador/);
    expect(guideFailure(422, { detail: [{ loc: ["body", "key"], msg: "bad" }] }, "promote").error).toMatch(
      /clave, la etiqueta y el motivo/,
    );
    expect(guideFailure(503, null, "review").error).toBe("La API respondió 503. Vuelve a intentarlo en un momento.");
  });

  it("reads the limit of the list between 1 and 100, 20 by default", () => {
    expect(parseLimit(undefined)).toBe(20);
    expect(parseLimit("100")).toBe(100);
    expect(parseLimit("0")).toBe(20);
    expect(parseLimit("500")).toBe(20);
    expect(parseLimit("abc")).toBe(20);
  });

  it("says why a read failed: the panel's token or the API", () => {
    expect(loadErrorCopy(401)).toMatch(/token del panel/);
    expect(loadErrorCopy(503)).toBe("La API no respondió. Vuelve a intentarlo en un momento.");
    expect(loadErrorCopy(null)).toBe("La API no respondió. Vuelve a intentarlo en un momento.");
  });
});

// ── the list ───────────────────────────────────────────────────────────────

describe("the labels without a guide", () => {
  it("shows each label with its clients, its generated guides and «Revisar» on each one", () => {
    render(<MissingLabels data={MISSING} limit={20} />);
    expect(screen.getByText(/54 clientes leídos/)).toBeTruthy();
    const gym = screen.getByRole("article", { name: "Gimnasio" });
    expect(within(gym).getByText("7 clientes")).toBeTruthy();
    expect(within(gym).getByText("3 generadas · 1 revisada")).toBeTruthy();
    const list = within(gym).getByRole("list", { name: "Guías generadas con la etiqueta Gimnasio" });
    expect(list.children).toHaveLength(2);
    const reviewed = within(list).getAllByRole("listitem")[0]!;
    expect(within(reviewed).getByText("Revisada")).toBeTruthy();
    expect(within(reviewed).getByText(/revisada por ana@auphere\.com/)).toBeTruthy();
    const link = within(reviewed).getByRole("link", { name: "Revisar la guía de Box Crossfit Sur" });
    expect(link.getAttribute("href")).toBe(`/builder/sector-guides/${TENANT}/g-reviewed`);
    // The visible text is part of the accessible name (WCAG 2.5.3).
    expect(link.textContent).toBe("Revisar");
    const fresh = within(list).getAllByRole("listitem")[1]!;
    expect(within(fresh).getByText("Sin revisar")).toBeTruthy();
    expect(within(fresh).getByText("11 de 12 pruebas")).toBeTruthy();
    // 4 live guides, 2 shown.
    expect(within(gym).getByText("Se enseñan 2 de 4.")).toBeTruthy();
  });

  it("partial: a label with clients and nothing generated has nothing to convert", () => {
    render(<MissingLabels data={MISSING} limit={20} />);
    const escape = screen.getByRole("article", { name: "Escape room" });
    expect(within(escape).getByText("2 clientes")).toBeTruthy();
    expect(within(escape).getByText(/no hay nada que convertir/)).toBeTruthy();
    expect(within(escape).queryByRole("link")).toBeNull();
  });

  it("a label nobody has today keeps its guides, and says why", () => {
    render(<MissingLabels data={MISSING} limit={20} />);
    const tattoo = screen.getByRole("article", { name: "Tatuajes" });
    expect(within(tattoo).getByText("Ningún cliente hoy")).toBeTruthy();
    expect(within(tattoo).getByRole("link", { name: "Revisar la guía de Tinta Fina" })).toBeTruthy();
  });

  it("empty: says there are no sectors without a guide", () => {
    render(<MissingLabels data={{ ...MISSING, items: [] }} limit={20} />);
    expect(screen.getByRole("status").textContent).toMatch(/No hay sectores sin guía/);
  });

  it("offers more labels when the list is cut at the limit", () => {
    const { rerender } = render(<MissingLabels data={MISSING} limit={3} />);
    expect(screen.getByRole("link", { name: "Ver hasta 100 etiquetas" }).getAttribute("href")).toBe("/builder/sector-guides?limit=100");
    rerender(<MissingLabels data={MISSING} limit={20} />);
    expect(screen.queryByRole("link", { name: "Ver hasta 100 etiquetas" })).toBeNull();
  });
});

describe("Auphere's guides", () => {
  it("lists the template ones and the converted ones, with their version and tests", async () => {
    render(<AuphereGuides guides={[BARBER, YOGA, { ...BARBER, key: "clinica", label: "Clínica", tests: 0 }]} />);
    const list = screen.getByRole("list", { name: "Guías de Auphere" });
    expect(list.children).toHaveLength(3);
    // Each guide holds lists of its own: the rows are the list's children.
    const [barber, yoga, clinic] = Array.from(list.children) as HTMLElement[];
    expect(within(barber!).getByText("Plantilla")).toBeTruthy();
    expect(within(barber!).getByText("versión 1 · 12 pruebas")).toBeTruthy();
    expect(within(yoga!).getByText("Convertida")).toBeTruthy();
    expect(within(clinic!).getByText("Sin pruebas")).toBeTruthy();
    await userEvent.click(within(barber!).getByText("Barbería y peluquería"));
    expect(within(barber!).getByText(/Sale de la plantilla barbershop_v1/)).toBeTruthy();
    expect(within(barber!).getByText("¿Atendéis sin cita?")).toBeTruthy();
    await userEvent.click(within(yoga!).getByText("Yoga"));
    expect(within(yoga!).getByText(/Convertida por ana@auphere\.com/)).toBeTruthy();
    expect(within(yoga!).getAllByText("Ninguno.").length).toBeGreaterThan(0);
  });

  it("empty: says so", () => {
    render(<AuphereGuides guides={[]} />);
    expect(screen.getByRole("status").textContent).toMatch(/No hay guías de Auphere/);
  });
});

describe("loading and error", () => {
  it("loading: skeletons that say what they wait for", () => {
    const { unmount } = render(<SectorGuidesSkeleton />);
    expect(screen.getByRole("status", { name: "Cargando los sectores sin guía" }).getAttribute("aria-busy")).toBe("true");
    unmount();
    render(<GeneratedGuideSkeleton />);
    expect(screen.getByRole("status", { name: "Cargando la guía generada" })).toBeTruthy();
  });

  it("error: says why, and retries by reading again", async () => {
    render(<SectionError title="No se pudieron leer los sectores sin guía" status={401} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch(/token del panel/);
    await userEvent.click(within(alert).getByRole("button", { name: "Reintentar" }));
    expect(h.refresh).toHaveBeenCalled();
  });

  it("the Constructor has the tab", () => {
    render(<BuilderTabs current="/builder/sector-guides" />);
    expect(screen.getByRole("link", { name: "Sectores sin guía" }).getAttribute("aria-current")).toBe("page");
  });
});

// ── one generated guide ────────────────────────────────────────────────────

describe("a generated guide", () => {
  it("marks the client's data where it is, and does not offer to convert it", () => {
    render(<GeneratedGuideView guide={GENERATED} operatorEmail="luis@auphere.com" takenKeys={TAKEN} />);
    const summary = screen.getByRole("region", { name: "Lleva 1 dato del cliente" });
    const place = within(summary).getByRole("link", { name: "Procedimiento 1 · Pasos" });
    const target = document.getElementById(place.getAttribute("href")!.slice(1));
    expect(target).not.toBeNull();
    expect(target!.textContent).toContain("llama al 612 345 678");
    expect(target!.textContent).toContain("Dato del cliente · Teléfono");
    expect(screen.queryByRole("button", { name: "Convertir en guía de Auphere" })).toBeNull();
    const why = screen.getByRole("list", { name: "Lo que le falta para convertirla" });
    expect(within(why).getByText("Revisarla.")).toBeTruthy();
    expect(within(why).getByText("Quitar 1 dato del cliente.")).toBeTruthy();
  });

  it("partial: says when it does not have its 12 tests", () => {
    render(<GeneratedGuideView guide={{ ...GENERATED, tests: TWELVE.slice(0, 10) }} operatorEmail="x" takenKeys={TAKEN} />);
    expect(screen.getByText("Tiene 10 de 12 pruebas")).toBeTruthy();
  });

  it("marks it reviewed with a note, and waits while it does so nobody sends it twice", async () => {
    let finish: (v: unknown) => void = () => {};
    h.review.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    render(<GeneratedGuideView guide={GENERATED} operatorEmail="x" takenKeys={TAKEN} />);
    await userEvent.type(screen.getByRole("textbox", { name: /Nota/ }), "Leída entera");
    await userEvent.click(screen.getByRole("button", { name: "Marcar como revisada" }));
    const busy = screen.getByRole("button", { name: /Revisando/ }) as HTMLButtonElement;
    expect(busy.disabled).toBe(true);
    await userEvent.click(busy);
    expect(h.review).toHaveBeenCalledTimes(1);
    expect(h.review).toHaveBeenCalledWith(TENANT, GUIDE_ID, { note: "Leída entera" });
    finish({ ok: true, data: { ...GENERATED, status: "reviewed" } });
    await screen.findByRole("button", { name: "Marcar como revisada" });
    expect(h.success).toHaveBeenCalledWith("Guía revisada");
    expect(h.refresh).toHaveBeenCalled();
  });

  it("corrects the guide in place, the finding on its field, and sends only the guide", async () => {
    h.review.mockResolvedValue({ ok: true, data: REVIEWED });
    render(<GeneratedGuideView guide={GENERATED} operatorEmail="x" takenKeys={TAKEN} />);
    await userEvent.click(screen.getByRole("button", { name: "Corregir la guía y las pruebas" }));
    const procedure = screen.getByRole("group", { name: "Procedimiento 1" });
    const steps = within(procedure).getByRole("textbox", { name: /Pasos/ });
    expect(steps.getAttribute("aria-invalid")).toBe("true");
    expect(within(procedure).getByText(/Dato del cliente · Teléfono/)).toBeTruthy();
    // The converted guide is the saved one: not while editing.
    await userEvent.clear(steps);
    await userEvent.type(steps, "Mira el hueco más cercano.");
    await userEvent.click(screen.getByRole("button", { name: "Guardar las correcciones y marcar como revisada" }));
    expect(h.review).toHaveBeenCalledWith(TENANT, GUIDE_ID, { guide: CLEAN_GUIDE });
    expect(h.refresh).toHaveBeenCalled();
  });

  it("does not send a guide the API would refuse", async () => {
    render(<GeneratedGuideView guide={GENERATED} operatorEmail="x" takenKeys={TAKEN} />);
    await userEvent.click(screen.getByRole("button", { name: "Corregir la guía y las pruebas" }));
    await userEvent.clear(screen.getByRole("textbox", { name: "Frase 1 de qué preguntar" }));
    await userEvent.click(screen.getByRole("button", { name: "Guardar las correcciones y marcar como revisada" }));
    expect(h.review).not.toHaveBeenCalled();
    expect(screen.getByText("Escribe la frase o quítala.")).toBeTruthy();
  });

  it("when the API still finds client data, says where and saves nothing", async () => {
    h.review.mockResolvedValue({
      ok: false,
      code: "client_data_found",
      error: "Quedan datos del cliente. Corrígelos y vuelve a marcarla como revisada. No se ha guardado nada.",
      findings: [{ pointer: "/guide/ask/1", kind: "email", excerpt: "…hola@gimnasionorte.es…" }],
    });
    render(<GeneratedGuideView guide={GENERATED} operatorEmail="x" takenKeys={TAKEN} />);
    await userEvent.click(screen.getByRole("button", { name: "Corregir la guía y las pruebas" }));
    await userEvent.click(screen.getByRole("button", { name: "Guardar las correcciones y marcar como revisada" }));
    expect(screen.getByText(/Quedan datos del cliente/)).toBeTruthy();
    const ask = screen.getByRole("textbox", { name: "Frase 2 de qué preguntar" });
    expect(ask.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText(/Dato del cliente · Correo: «…hola@gimnasionorte\.es…»/)).toBeTruthy();
    expect(h.refresh).not.toHaveBeenCalled();
  });

  it("converts a reviewed guide without client data, with key, label and reason", async () => {
    h.promote.mockResolvedValue({ ok: true, data: { ...YOGA, key: "gimnasio", label: "Gimnasio" } });
    render(<GeneratedGuideView guide={REVIEWED} operatorEmail="ana@auphere.com" takenKeys={TAKEN} />);
    expect(screen.getByText(/Revisada por ti/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Convertir en guía de Auphere" }));
    const dialog = screen.getByRole("dialog");
    const key = within(dialog).getByRole("textbox", { name: /Clave/ }) as HTMLInputElement;
    expect(key.value).toBe("gimnasio");
    expect((within(dialog).getByRole("textbox", { name: /Etiqueta/ }) as HTMLInputElement).value).toBe("Gimnasio");
    await userEvent.clear(key);
    await userEvent.type(key, "barberia_peluqueria");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Siete clientes, revisada por Ana");
    await userEvent.click(within(dialog).getByRole("button", { name: "Convertir" }));
    expect(h.promote).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Esa clave ya es de un sector o de otra guía de Auphere.")).toBeTruthy();
    await userEvent.clear(key);
    await userEvent.type(key, "gimnasio");
    await userEvent.click(within(dialog).getByRole("button", { name: "Convertir" }));
    expect(h.promote).toHaveBeenCalledWith(TENANT, GUIDE_ID, {
      key: "gimnasio",
      label: "Gimnasio",
      reason: "Siete clientes, revisada por Ana",
    });
    expect(h.success).toHaveBeenCalledWith("«Gimnasio» ya es guía de Auphere");
    expect(h.refresh).toHaveBeenCalled();
  });

  it("says the API's refusal of a conversion by its code", async () => {
    h.promote.mockResolvedValue({ ok: false, code: "guide_label_taken", error: "Esa etiqueta ya tiene guía de Auphere." });
    render(<GeneratedGuideView guide={REVIEWED} operatorEmail="x" takenKeys={TAKEN} />);
    await userEvent.click(screen.getByRole("button", { name: "Convertir en guía de Auphere" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Siete clientes");
    await userEvent.click(within(dialog).getByRole("button", { name: "Convertir" }));
    expect(within(dialog).getByRole("alert").textContent).toBe("Esa etiqueta ya tiene guía de Auphere.");
    expect(h.refresh).not.toHaveBeenCalled();
  });

  it("does not offer to convert while there are corrections not saved", async () => {
    render(<GeneratedGuideView guide={REVIEWED} operatorEmail="x" takenKeys={TAKEN} />);
    await userEvent.click(screen.getByRole("button", { name: "Corregir la guía y las pruebas" }));
    expect(screen.queryByRole("button", { name: "Convertir en guía de Auphere" })).toBeNull();
    expect(screen.getByText(/Guarda o descarta las correcciones/)).toBeTruthy();
  });

  it("a converted guide is read only, and says its key", () => {
    render(
      <GeneratedGuideView
        guide={{ ...REVIEWED, status: "promoted", promotable: false, promoted_to: "gimnasio", promoted_at: "2026-10-30T12:00:00+00:00" }}
        operatorEmail="x"
        takenKeys={TAKEN}
      />,
    );
    expect(screen.getByText("Convertida en guía de Auphere")).toBeTruthy();
    expect(screen.getByText(/«gimnasio»/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Marcar como revisada/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Convertir en guía de Auphere" })).toBeNull();
  });
});
