import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Basics, Faqs, Hours, Locations, Policies, Sector, Services, SpecialDates } from "@/lib/backend/business-sections";
import type { BusinessRecord, Suggestion } from "@/lib/backend/client-records";

const biz = vi.hoisted(() => ({
  saveBasicsAction: vi.fn(),
  savePoliciesAction: vi.fn(),
  createFaqAction: vi.fn(),
  updateFaqAction: vi.fn(),
  archiveFaqAction: vi.fn(),
  reloadSectionAction: vi.fn(),
}));
vi.mock("@/app/(console)/clients/[ref]/business/actions", () => ({
  ...biz,
  saveHoursAction: vi.fn(),
  loadHoursAction: vi.fn(),
  createLocationAction: vi.fn(),
  updateLocationAction: vi.fn(),
  archiveLocationAction: vi.fn(),
  createSpecialDateAction: vi.fn(),
  archiveSpecialDateAction: vi.fn(),
  createServiceAction: vi.fn(),
  updateServiceAction: vi.fn(),
  archiveServiceAction: vi.fn(),
  duplicateServiceAction: vi.fn(),
  setServiceAgentsAction: vi.fn(),
}));
const decide = vi.hoisted(() => vi.fn());
vi.mock("@/app/(console)/clients/[ref]/client-v2-actions", () => ({
  decideSuggestionAction: decide,
  confirmSectionAction: vi.fn(),
  putLinksAction: vi.fn(),
  listSourcesAction: vi.fn(),
  uploadSourceAction: vi.fn(),
  addSourceUrlAction: vi.fn(),
  rereadSourceAction: vi.fn(),
  removeSourceAction: vi.fn(),
  restoreSourceAction: vi.fn(),
}));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const { BusinessSectionsView } = await import("../business-sections");

/**
 * Spec 047, enmienda del 2026-10-29 (T209; requisitos 57.5, 60.4 y 60.5) — en
 * Negocio, el sector en «Datos básicos» (con «Con guía» o «Generada», el
 * selector de los sectores con guía más «Otro», y la propuesta del sistema al
 * lado del valor), y dos secciones nuevas, «Políticas» y «Preguntas
 * frecuentes», que enseñan y editan lo que entra en el prompt de todos los
 * agentes, con lo sugerido marcado «Sugerido · confirma» y aceptar, editar o
 * descartar cada cosa. Sus cinco estados: vacío, error, parcial, ideal (el de
 * carga es `loading.tsx`).
 */

const REF = "barberia-cultor";
const meta = { allowed: ["edit" as const] };
const BARBERIA: Sector = { key: "barberia_peluqueria", label: "Barbería", confidence: 0.92, source: "niche", decided_by: "system", has_guide: true };
const BASICS: Basics = {
  ...meta,
  revision: 4,
  state: "complete",
  name: "Barbería Cultor",
  niche: "Barbería de barrio",
  info: null,
  website: null,
  country: "ES",
  timezone: "Europe/Madrid",
  price_currency: "EUR",
  eu_only: true,
  sector: BARBERIA,
};
const EMPTY_DAYS = { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] };
const HOURS: Hours = { ...meta, revision: 0, state: "pending", location_id: null, inherits: false, layout: null, days: EMPTY_DAYS, label: null };
const LOCATIONS: Locations = { ...meta, revision: 0, state: "pending", items: [], created_id: null };
const SPECIAL: SpecialDates = { ...meta, revision: 0, state: "optional", items: [], created_id: null };
const SERVICES: Services = { ...meta, revision: 0, state: "complete", currency: "EUR", exponent: 2, items: [], agents: [], created_id: null };
const POLICIES: Policies = {
  ...meta,
  revision: 2,
  state: "complete",
  cancellation: null,
  payments: "Efectivo, tarjeta y Bizum.",
  deposit: null,
  no_show: null,
};
const FAQS: Faqs = {
  ...meta,
  revision: 5,
  state: "complete",
  created_id: null,
  items: [
    { id: "f0000000-0000-4000-8000-000000000001", q: "¿Hay aparcamiento?", a: "Sí, en la calle de atrás.", suggested: false },
    { id: "f0000000-0000-4000-8000-000000000002", q: "¿Aceptáis niños?", a: "Sí, desde los 4 años.", suggested: true },
  ],
};
const SECTORS = [
  { key: "barberia_peluqueria", label: "Barbería" },
  { key: "clinica", label: "Clínica" },
  { key: "restaurante", label: "Restaurante" },
];

function suggestion(over: Partial<Suggestion>): Suggestion {
  return {
    id: "50000000-0000-4000-8000-000000000001",
    pointer: "/policies/cancellation",
    section: "policies",
    proposed_value: "Avisa con 24 horas de antelación.",
    current_value: null,
    source: "builder",
    source_url: null,
    translated_from: null,
    created_at: "2026-10-29T10:00:00Z",
    ...over,
  };
}
function record(suggestions: Suggestion[] = []): BusinessRecord {
  return { spec: {}, valid: true, problems: [], sections: [], provenance: {}, suggestions, allowed: ["edit", "decide"] };
}
const POLICY_SUGGESTION = suggestion({});
const FAQ_SUGGESTION = suggestion({
  id: "50000000-0000-4000-8000-000000000002",
  pointer: "/faqs/-",
  section: "faqs",
  proposed_value: { q: "¿Se puede pagar con tarjeta?", a: "Sí, con todas." },
  source: "web",
  source_url: "https://cultorbarber.com/faq",
});
const SECTOR_SUGGESTION = suggestion({
  id: "50000000-0000-4000-8000-000000000003",
  pointer: "/business/sector",
  section: "basics",
  proposed_value: { key: "clinica", label: "Clínica" },
  current_value: { key: "barberia_peluqueria", label: "Barbería" },
  source: "web",
});

const ok = <T,>(data: T) => ({ ok: true as const, data });
const failed = { ok: false as const, status: 503, message: "down" };

type Data = React.ComponentProps<typeof BusinessSectionsView>["data"];
function page(over: Partial<Data> = {}, canWrite = true) {
  return render(
    <LocaleProvider locale="es">
      <BusinessSectionsView
        refId={REF}
        canWrite={canWrite}
        data={{
          basics: ok(BASICS),
          locations: ok(LOCATIONS),
          hours: ok(HOURS),
          specialDates: ok(SPECIAL),
          services: ok(SERVICES),
          policies: ok(POLICIES),
          faqs: ok(FAQS),
          sectors: ok(SECTORS),
          record: ok(record([POLICY_SUGGESTION, FAQ_SUGGESTION])),
          ...over,
        }}
      />
    </LocaleProvider>,
  );
}

const region = (name: string) => screen.getByRole("region", { name });

beforeEach(() => {
  vi.clearAllMocks();
  decide.mockResolvedValue(ok({ decision: "accept" }));
});

describe("Negocio · Políticas y Preguntas frecuentes en el índice (60.4)", () => {
  it("van después de Servicios, cada una con su tarjeta, y pasan axe", async () => {
    const { container } = page();
    const index = screen.getByRole("navigation", { name: "Secciones de Negocio" });
    const names = within(index)
      .getAllByRole("link")
      .map((a) => a.textContent?.replace(/(Completa|Pendiente|Opcional|Leída · revísala)$/, ""));
    expect(names.slice(0, 6)).toEqual(["Datos básicos", "Sedes", "Horarios", "Servicios", "Políticas", "Preguntas frecuentes"]);
    expect(region("Políticas")).toBeVisible();
    expect(region("Preguntas frecuentes")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("Negocio · el sector en Datos básicos (57.5)", () => {
  it("dice el sector y si tiene guía de Auphere", () => {
    page();
    const basics = region("Datos básicos");
    expect(within(basics).getByText("Sector")).toBeVisible();
    expect(within(basics).getByText("Barbería")).toBeVisible();
    expect(within(basics).getByText("Con guía")).toBeVisible();
  });

  it("uno sin guía dice «Generada»; mientras se identifica, lo dice; sin el dato en la API, no habla del sector", () => {
    const { unmount } = page({ basics: ok({ ...BASICS, sector: { ...BARBERIA, key: "otro", label: "Gimnasio", has_guide: false } }) });
    expect(within(region("Datos básicos")).getByText("Gimnasio")).toBeVisible();
    expect(within(region("Datos básicos")).getByText("Generada")).toBeVisible();
    unmount();
    const second = page({ basics: ok({ ...BASICS, sector: null }) });
    expect(within(region("Datos básicos")).getByText("Identificando el sector…")).toBeVisible();
    second.unmount();
    const old: Basics = { ...BASICS };
    delete old.sector;
    page({ basics: ok(old) });
    expect(within(region("Datos básicos")).queryByText("Sector")).toBeNull();
  });

  it("la propuesta del sistema sale al lado del valor y se acepta o se descarta", async () => {
    const user = userEvent.setup();
    biz.reloadSectionAction.mockResolvedValue(ok({ ...BASICS, revision: 5, sector: { ...BARBERIA, key: "clinica", label: "Clínica", decided_by: "person" } }));
    page({ record: ok(record([SECTOR_SUGGESTION])) });
    const basics = region("Datos básicos");
    expect(within(basics).getByText("Propuesto: Clínica")).toBeVisible();
    await user.click(within(basics).getByRole("button", { name: "Aceptar el sector Clínica" }));
    expect(decide).toHaveBeenCalledWith({ ref: REF, id: SECTOR_SUGGESTION.id, decision: "accept" });
    await waitFor(() => expect(biz.reloadSectionAction).toHaveBeenCalledWith({ ref: REF, section: "basics" }));
    expect(await within(basics).findByText("Clínica")).toBeVisible();
    expect(within(basics).queryByText("Propuesto: Clínica")).toBeNull();
  });

  it("descartar la propuesta la quita sin tocar el sector", async () => {
    const user = userEvent.setup();
    page({ record: ok(record([SECTOR_SUGGESTION])) });
    const basics = region("Datos básicos");
    await user.click(within(basics).getByRole("button", { name: "Descartar el sector Clínica" }));
    expect(decide).toHaveBeenCalledWith({ ref: REF, id: SECTOR_SUGGESTION.id, decision: "discard" });
    await waitFor(() => expect(within(basics).queryByText("Propuesto: Clínica")).toBeNull());
    expect(within(basics).getByText("Barbería")).toBeVisible();
  });

  it("se corrige eligiendo un sector con guía", async () => {
    const user = userEvent.setup();
    biz.saveBasicsAction.mockResolvedValue(ok({ ...BASICS, revision: 5, sector: { ...BARBERIA, key: "clinica", label: "Clínica", decided_by: "person" } }));
    page();
    const basics = region("Datos básicos");
    await user.click(within(basics).getByRole("button", { name: "Editar Datos básicos" }));
    const select = within(basics).getByRole("combobox", { name: /Sector/ });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Barbería", "Clínica", "Restaurante", "Otro"]);
    await user.selectOptions(select, "clinica");
    await user.click(within(basics).getByRole("button", { name: "Guardar datos básicos" }));
    expect(biz.saveBasicsAction).toHaveBeenCalledWith({ ref: REF, revision: 4, body: { sector: { key: "clinica", label: "Clínica" } } });
  });

  it("o con «Otro» y una etiqueta libre de hasta 40 caracteres, que es obligatoria", async () => {
    const user = userEvent.setup();
    biz.saveBasicsAction.mockResolvedValue(ok(BASICS));
    page();
    const basics = region("Datos básicos");
    await user.click(within(basics).getByRole("button", { name: "Editar Datos básicos" }));
    await user.selectOptions(within(basics).getByRole("combobox", { name: /Sector/ }), "otro");
    const label = within(basics).getByRole("textbox", { name: /Cómo se llama el sector/ });
    expect(label).toHaveAttribute("maxLength", "40");
    await user.click(within(basics).getByRole("button", { name: "Guardar datos básicos" }));
    expect(within(basics).getByText("Escribe cómo se llama el sector.")).toBeVisible();
    expect(biz.saveBasicsAction).not.toHaveBeenCalled();
    await user.type(label, "Gimnasio");
    await user.click(within(basics).getByRole("button", { name: "Guardar datos básicos" }));
    expect(biz.saveBasicsAction).toHaveBeenCalledWith({ ref: REF, revision: 4, body: { sector: { key: "otro", label: "Gimnasio" } } });
  });

  it("si la API no conoce la clave, lo dice; si la lista no carga, se puede escribir en «Otro»", async () => {
    const user = userEvent.setup();
    biz.saveBasicsAction.mockResolvedValue({ ok: false, status: 422, message: "x", code: "sector_unknown" });
    page({ sectors: failed });
    const basics = region("Datos básicos");
    await user.click(within(basics).getByRole("button", { name: "Editar Datos básicos" }));
    expect(within(basics).getByText(/No pudimos cargar la lista de sectores/)).toBeVisible();
    const select = within(basics).getByRole("combobox", { name: /Sector/ });
    // El actual sigue en la lista aunque no cargue el resto.
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Barbería", "Otro"]);
    await user.selectOptions(select, "otro");
    await user.type(within(basics).getByRole("textbox", { name: /Cómo se llama el sector/ }), "Óptica");
    await user.click(within(basics).getByRole("button", { name: "Guardar datos básicos" }));
    expect(await within(basics).findByText("Ese sector ya no está en la lista. Elige otro.")).toBeVisible();
  });
});

describe("Negocio · Políticas (60.4, 60.5)", () => {
  it("enseña las cuatro, con lo que falta dicho, y la sugerida con su marca y su procedencia", () => {
    page();
    const policies = region("Políticas");
    expect(within(policies).getByText("Pagos")).toBeVisible();
    expect(within(policies).getByText("Efectivo, tarjeta y Bizum.")).toBeVisible();
    expect(within(policies).getAllByText("Sin escribir")).toHaveLength(3);
    const proposal = within(policies).getByRole("listitem", { name: "Cancelación" });
    expect(within(proposal).getByText("Sugerido · confirma")).toBeVisible();
    expect(within(proposal).getByText("Propuesto a partir de la ficha")).toBeVisible();
    expect(within(proposal).getByText("Avisa con 24 horas de antelación.")).toBeVisible();
  });

  it("aceptar la guarda en la ficha y vuelve a leer la sección", async () => {
    const user = userEvent.setup();
    biz.reloadSectionAction.mockResolvedValue(ok({ ...POLICIES, revision: 3, cancellation: "Avisa con 24 horas de antelación." }));
    page();
    const policies = region("Políticas");
    await user.click(within(policies).getByRole("button", { name: "Aceptar Cancelación" }));
    expect(decide).toHaveBeenCalledWith({ ref: REF, id: POLICY_SUGGESTION.id, decision: "accept" });
    await waitFor(() => expect(biz.reloadSectionAction).toHaveBeenCalledWith({ ref: REF, section: "policies" }));
    await waitFor(() => expect(within(policies).queryByText("Sugerido · confirma")).toBeNull());
    expect(within(policies).getByText("Avisa con 24 horas de antelación.")).toBeVisible();
    expect(toast.success).toHaveBeenCalledWith("Añadido a la ficha.");
  });

  it("editarla antes de aceptar manda el texto nuevo", async () => {
    const user = userEvent.setup();
    biz.reloadSectionAction.mockResolvedValue(ok(POLICIES));
    page();
    const policies = region("Políticas");
    await user.click(within(policies).getByRole("button", { name: "Editar Cancelación" }));
    const text = within(policies).getByRole("textbox", { name: /Texto/ });
    expect(text).toHaveValue("Avisa con 24 horas de antelación.");
    await user.clear(text);
    await user.type(text, "Avisa con 48 horas.");
    await user.click(within(policies).getByRole("button", { name: "Guardar en la ficha" }));
    expect(decide).toHaveBeenCalledWith({ ref: REF, id: POLICY_SUGGESTION.id, decision: "edit", value: "Avisa con 48 horas." });
  });

  it("descartarla la quita y no la vuelve a leer", async () => {
    const user = userEvent.setup();
    page();
    const policies = region("Políticas");
    await user.click(within(policies).getByRole("button", { name: "Descartar Cancelación" }));
    expect(decide).toHaveBeenCalledWith({ ref: REF, id: POLICY_SUGGESTION.id, decision: "discard" });
    await waitFor(() => expect(within(policies).queryByText("Avisa con 24 horas de antelación.")).toBeNull());
    expect(biz.reloadSectionAction).not.toHaveBeenCalled();
  });

  it("si otra persona ya la decidió, lo dice", async () => {
    const user = userEvent.setup();
    decide.mockResolvedValue({ ok: false, status: 409, message: "x", code: "already_decided" });
    page();
    const policies = region("Políticas");
    await user.click(within(policies).getByRole("button", { name: "Aceptar Cancelación" }));
    expect(await within(policies).findByText("Ya lo decidió otra persona.")).toBeVisible();
  });

  it("«Editar» escribe las cuatro y manda la revisión leída", async () => {
    const user = userEvent.setup();
    biz.savePoliciesAction.mockResolvedValue(ok({ ...POLICIES, revision: 3, no_show: "Se cobra la mitad." }));
    page({ record: ok(record()) });
    const policies = region("Políticas");
    await user.click(within(policies).getByRole("button", { name: "Editar Políticas" }));
    await user.type(within(policies).getByRole("textbox", { name: "No presentarse" }), "Se cobra la mitad.");
    await user.click(within(policies).getByRole("button", { name: "Guardar políticas" }));
    expect(biz.savePoliciesAction).toHaveBeenCalledWith({
      ref: REF,
      revision: 2,
      body: { cancellation: null, payments: "Efectivo, tarjeta y Bizum.", deposit: null, no_show: "Se cobra la mitad." },
    });
    expect(await within(policies).findByText("Se cobra la mitad.")).toBeVisible();
  });

  it("un 412 dice que alguien la cambió mientras tanto", async () => {
    const user = userEvent.setup();
    biz.savePoliciesAction.mockResolvedValue({ ok: false, status: 412, message: "x", code: "revision_conflict" });
    page();
    const policies = region("Políticas");
    await user.click(within(policies).getByRole("button", { name: "Editar Políticas" }));
    await user.click(within(policies).getByRole("button", { name: "Guardar políticas" }));
    expect(await within(policies).findByRole("alert")).toHaveTextContent(/Alguien cambió esta sección/);
  });
});

describe("Negocio · Preguntas frecuentes (60.4, 60.5)", () => {
  it("enseña las confirmadas y las sugeridas aparte, con su marca", () => {
    page();
    const faqs = region("Preguntas frecuentes");
    expect(within(faqs).getByText("¿Hay aparcamiento?")).toBeVisible();
    expect(within(faqs).getByText("Sí, en la calle de atrás.")).toBeVisible();
    const fromRow = within(faqs).getByRole("listitem", { name: "¿Aceptáis niños?" });
    expect(within(fromRow).getByText("Sugerido · confirma")).toBeVisible();
    const fromWeb = within(faqs).getByRole("listitem", { name: "¿Se puede pagar con tarjeta?" });
    expect(within(fromWeb).getByText("Sugerido · confirma")).toBeVisible();
    expect(within(fromWeb).getByText("Leído de la web")).toBeVisible();
  });

  it("aceptar una pregunta sugerida de la ficha la confirma (deja de ser sugerida)", async () => {
    const user = userEvent.setup();
    biz.updateFaqAction.mockResolvedValue(ok({ ...FAQS, revision: 6, items: FAQS.items.map((f) => ({ ...f, suggested: false })) }));
    page();
    const faqs = region("Preguntas frecuentes");
    await user.click(within(faqs).getByRole("button", { name: "Aceptar ¿Aceptáis niños?" }));
    expect(biz.updateFaqAction).toHaveBeenCalledWith({ ref: REF, revision: 5, id: FAQS.items[1]!.id, body: { suggested: false } });
    await waitFor(() => expect(within(faqs).queryByRole("listitem", { name: "¿Aceptáis niños?" })).toBeNull());
    expect(within(faqs).getByText("¿Aceptáis niños?")).toBeVisible();
  });

  it("descartar una sugerida de la ficha la archiva", async () => {
    const user = userEvent.setup();
    biz.archiveFaqAction.mockResolvedValue(ok({ ...FAQS, revision: 6, items: [FAQS.items[0]!] }));
    page();
    const faqs = region("Preguntas frecuentes");
    await user.click(within(faqs).getByRole("button", { name: "Descartar ¿Aceptáis niños?" }));
    expect(biz.archiveFaqAction).toHaveBeenCalledWith({ ref: REF, revision: 5, id: FAQS.items[1]!.id });
    await waitFor(() => expect(within(faqs).queryByText("¿Aceptáis niños?")).toBeNull());
  });

  it("editar una propuesta pendiente manda pregunta y respuesta", async () => {
    const user = userEvent.setup();
    biz.reloadSectionAction.mockResolvedValue(ok(FAQS));
    page();
    const faqs = region("Preguntas frecuentes");
    await user.click(within(faqs).getByRole("button", { name: "Editar ¿Se puede pagar con tarjeta?" }));
    const answer = within(faqs).getByRole("textbox", { name: /Respuesta/ });
    await user.clear(answer);
    await user.type(answer, "Sí, menos American Express.");
    await user.click(within(faqs).getByRole("button", { name: "Guardar en la ficha" }));
    expect(decide).toHaveBeenCalledWith({
      ref: REF,
      id: FAQ_SUGGESTION.id,
      decision: "edit",
      value: { q: "¿Se puede pagar con tarjeta?", a: "Sí, menos American Express." },
    });
    await waitFor(() => expect(biz.reloadSectionAction).toHaveBeenCalledWith({ ref: REF, section: "faqs" }));
  });

  it("«Añadir pregunta» crea una con la revisión leída", async () => {
    const user = userEvent.setup();
    biz.createFaqAction.mockResolvedValue(ok({ ...FAQS, revision: 6, items: [...FAQS.items, { id: "f3", q: "¿Abrís en agosto?", a: "Solo por las mañanas.", suggested: false }] }));
    page();
    const faqs = region("Preguntas frecuentes");
    await user.click(within(faqs).getByRole("button", { name: "Añadir pregunta" }));
    await user.click(within(faqs).getByRole("button", { name: "Guardar pregunta" }));
    expect(within(faqs).getByText("Escribe la pregunta y la respuesta.")).toBeVisible();
    await user.type(within(faqs).getByRole("textbox", { name: /^Pregunta/ }), "¿Abrís en agosto?");
    await user.type(within(faqs).getByRole("textbox", { name: /^Respuesta/ }), "Solo por las mañanas.");
    await user.click(within(faqs).getByRole("button", { name: "Guardar pregunta" }));
    expect(biz.createFaqAction).toHaveBeenCalledWith({ ref: REF, revision: 5, body: { q: "¿Abrís en agosto?", a: "Solo por las mañanas." } });
    expect(await within(faqs).findByText("¿Abrís en agosto?")).toBeVisible();
  });

  it("una confirmada se edita y se quita", async () => {
    const user = userEvent.setup();
    biz.updateFaqAction.mockResolvedValue(ok({ ...FAQS, revision: 6, items: [{ ...FAQS.items[0]!, a: "Sí, gratis." }, FAQS.items[1]!] }));
    biz.archiveFaqAction.mockResolvedValue(ok({ ...FAQS, revision: 7, items: [FAQS.items[1]!] }));
    page();
    const faqs = region("Preguntas frecuentes");
    await user.click(within(faqs).getByRole("button", { name: "Editar ¿Hay aparcamiento?" }));
    const answer = within(faqs).getByRole("textbox", { name: /^Respuesta/ });
    await user.clear(answer);
    await user.type(answer, "Sí, gratis.");
    await user.click(within(faqs).getByRole("button", { name: "Guardar pregunta" }));
    expect(biz.updateFaqAction).toHaveBeenCalledWith({ ref: REF, revision: 5, id: FAQS.items[0]!.id, body: { q: "¿Hay aparcamiento?", a: "Sí, gratis." } });
    expect(await within(faqs).findByText("Sí, gratis.")).toBeVisible();
    await user.click(within(faqs).getByRole("button", { name: "Quitar ¿Hay aparcamiento?" }));
    expect(biz.archiveFaqAction).toHaveBeenCalledWith({ ref: REF, revision: 6, id: FAQS.items[0]!.id });
  });
});

/**
 * T218 (puertas de UI, 2026-10-29): un error nunca es un callejón sin salida.
 * Un 412 en Políticas o en Preguntas frecuentes deja «Recargar» en el sitio, y
 * la propuesta de sector no se manda dos veces con un doble clic.
 */
describe("Negocio · recuperarse de un error (T218)", () => {
  it("Políticas: tras un 412, «Recargar» lee lo nuevo y deja volver a guardar con su revisión", async () => {
    const user = userEvent.setup();
    biz.savePoliciesAction
      .mockResolvedValueOnce({ ok: false, status: 412, message: "x", code: "revision_conflict" })
      .mockResolvedValueOnce(ok({ ...POLICIES, revision: 4, deposit: "10 €" }));
    biz.reloadSectionAction.mockResolvedValue(ok({ ...POLICIES, revision: 3, cancellation: "Avisa con 12 horas." }));
    page();
    const policies = region("Políticas");
    await user.click(within(policies).getByRole("button", { name: "Editar Políticas" }));
    await user.click(within(policies).getByRole("button", { name: "Guardar políticas" }));
    await user.click(await within(policies).findByRole("button", { name: "Recargar" }));
    expect(biz.reloadSectionAction).toHaveBeenCalledWith({ ref: REF, section: "policies" });
    expect(await within(policies).findByRole("textbox", { name: "Cancelación" })).toHaveValue("Avisa con 12 horas.");
    expect(within(policies).queryByRole("alert")).toBeNull();
    await user.type(within(policies).getByRole("textbox", { name: "Señal" }), "10 €");
    await user.click(within(policies).getByRole("button", { name: "Guardar políticas" }));
    expect(biz.savePoliciesAction).toHaveBeenLastCalledWith(expect.objectContaining({ revision: 3 }));
  });

  it("Preguntas frecuentes: tras un 412, «Recargar» lee la lista y conserva lo escrito", async () => {
    const user = userEvent.setup();
    biz.createFaqAction
      .mockResolvedValueOnce({ ok: false, status: 412, message: "x", code: "revision_conflict" })
      .mockResolvedValueOnce(ok({ ...FAQS, revision: 7, items: [...FAQS.items, { id: "f3", q: "¿Abrís en agosto?", a: "Por las mañanas.", suggested: false }] }));
    biz.reloadSectionAction.mockResolvedValue(ok({ ...FAQS, revision: 6 }));
    page();
    const faqs = region("Preguntas frecuentes");
    await user.click(within(faqs).getByRole("button", { name: "Añadir pregunta" }));
    await user.type(within(faqs).getByRole("textbox", { name: /^Pregunta/ }), "¿Abrís en agosto?");
    await user.type(within(faqs).getByRole("textbox", { name: /^Respuesta/ }), "Por las mañanas.");
    await user.click(within(faqs).getByRole("button", { name: "Guardar pregunta" }));
    await user.click(await within(faqs).findByRole("button", { name: "Recargar" }));
    expect(biz.reloadSectionAction).toHaveBeenCalledWith({ ref: REF, section: "faqs" });
    await waitFor(() => expect(within(faqs).queryByRole("alert")).toBeNull());
    expect(within(faqs).getByRole("textbox", { name: /^Pregunta/ })).toHaveValue("¿Abrís en agosto?");
    await user.click(within(faqs).getByRole("button", { name: "Guardar pregunta" }));
    expect(biz.createFaqAction).toHaveBeenLastCalledWith({ ref: REF, revision: 6, body: { q: "¿Abrís en agosto?", a: "Por las mañanas." } });
  });

  it("el sector: mientras se decide la propuesta, sus botones esperan y un doble clic no la manda dos veces", async () => {
    const user = userEvent.setup();
    let release: (v: unknown) => void = () => undefined;
    decide.mockImplementation(() => new Promise((r) => (release = r)));
    biz.reloadSectionAction.mockResolvedValue(ok(BASICS));
    page({ record: ok(record([SECTOR_SUGGESTION])) });
    const basics = region("Datos básicos");
    const accept = within(basics).getByRole("button", { name: "Aceptar el sector Clínica" });
    await user.dblClick(accept);
    expect(decide).toHaveBeenCalledTimes(1);
    expect(within(basics).getByRole("button", { name: "Descartar el sector Clínica" })).toBeDisabled();
    release(ok({ decision: "accept" }));
    await waitFor(() => expect(within(basics).queryByText("Propuesto: Clínica")).toBeNull());
  });
});

describe("Negocio · los cinco estados de las secciones nuevas", () => {
  it("vacío: sin políticas ni preguntas, lo dice", () => {
    page({
      policies: ok({ ...POLICIES, payments: null, state: "optional" }),
      faqs: ok({ ...FAQS, items: [], state: "optional" }),
      record: ok(record()),
    });
    expect(within(region("Políticas")).getAllByText("Sin escribir")).toHaveLength(4);
    expect(within(region("Preguntas frecuentes")).getByText("Todavía no hay preguntas frecuentes.")).toBeVisible();
  });

  it("error: una sección que no cargó lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    biz.reloadSectionAction.mockResolvedValue(ok(POLICIES));
    page({ policies: failed, faqs: failed });
    const policies = region("Políticas");
    expect(within(policies).getByText("No se pudo cargar esta sección.")).toBeVisible();
    expect(within(region("Preguntas frecuentes")).getByText("No se pudo cargar esta sección.")).toBeVisible();
    await user.click(within(policies).getByRole("button", { name: "Reintentar" }));
    expect(biz.reloadSectionAction).toHaveBeenCalledWith({ ref: REF, section: "policies" });
    expect(await within(region("Políticas")).findByText("Efectivo, tarjeta y Bizum.")).toBeVisible();
  });

  it("parcial: sin la ficha, se ve lo escrito y se avisa de que lo sugerido no cargó", () => {
    page({ record: failed });
    expect(within(region("Políticas")).getByText("Efectivo, tarjeta y Bizum.")).toBeVisible();
    expect(within(region("Políticas")).getByText("No pudimos cargar lo sugerido para esta sección.")).toBeVisible();
    expect(within(region("Preguntas frecuentes")).getByText("No pudimos cargar lo sugerido para esta sección.")).toBeVisible();
  });

  it("solo lectura: lo sugerido se ve sin botones", () => {
    page({}, false);
    const policies = region("Políticas");
    expect(within(policies).getByText("Sugerido · confirma")).toBeVisible();
    expect(within(policies).queryByRole("button", { name: /Aceptar|Descartar|Editar/ })).toBeNull();
    expect(within(region("Preguntas frecuentes")).queryByRole("button", { name: /Aceptar|Añadir pregunta|Quitar/ })).toBeNull();
  });

  it("textos largos: las tarjetas no se desbordan", () => {
    const long = "Las cancelaciones con menos de veinticuatro horas de antelación se cobran enteras ".repeat(4);
    page({ policies: ok({ ...POLICIES, cancellation: long }) });
    const policies = region("Políticas");
    expect(policies.className).toMatch(/min-w-0/);
    expect(within(policies).getByText(long.trim()).className).toMatch(/break-words/);
  });
});
