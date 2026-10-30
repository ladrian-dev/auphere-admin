import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ClientAgent } from "@/lib/backend";
import type { SuggestedAgent } from "@/lib/backend/suggested-agents";

const dismissAction = vi.hoisted(() => vi.fn());
vi.mock("@/app/(console)/clients/[ref]/agents/suggested-actions", () => ({ dismissSuggestedAgentAction: dismissAction }));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const { AgentCards } = await import("../agent-cards");

/**
 * Spec 047 (historia 7, escenario 6; requisito 17.2) — la pestaña Agentes: una
 * tarjeta por agente con si está publicado o solo en borrador y sus canales,
 * que lleva a la pantalla del agente. «Nuevo agente» solo para quien puede
 * crear agentes (§V).
 */

const REF = "barberia-cultor";
const agent = (over: Partial<ClientAgent>): ClientAgent => ({
  id: "11111111-1111-4111-8111-111111111111",
  name: "Recepción",
  status: "active",
  is_principal: true,
  channels: [{ id: "c1", display: "+34 600 000 000" }],
  active_version: 3,
  draft_version: null,
  ...over,
});
const AGENTS: ClientAgent[] = [
  agent({}),
  agent({ id: "22222222-2222-4222-8222-222222222222", name: "Ventas", is_principal: false, channels: [], active_version: null, draft_version: 4 }),
  agent({
    id: "33333333-3333-4333-8333-333333333333",
    name: "Cobros",
    is_principal: false,
    channels: [
      { id: "c2", display: "+34 600 000 001" },
      { id: "c3", display: "+34 600 000 002" },
    ],
    active_version: 2,
    draft_version: 5,
  }),
];

function cards(agents: ClientAgent[] | null, canWrite = true, suggested: SuggestedAgent[] | null = null) {
  return render(
    <LocaleProvider locale="es">
      <AgentCards refId={REF} agents={agents} canWrite={canWrite} suggested={suggested} />
    </LocaleProvider>,
  );
}

describe("la pestaña Agentes", () => {
  it("dice de cada agente si está publicado o en borrador y cuántos canales tiene, y pasa axe", async () => {
    const { container } = cards(AGENTS);
    const list = screen.getByRole("list", { name: "Agentes del cliente" });
    const [recepcion, ventas, cobros] = within(list).getAllByRole("link");
    expect(recepcion).toHaveAttribute("href", `/clients/${REF}/agents/11111111-1111-4111-8111-111111111111`);
    expect(within(recepcion!).getByText("Publicado")).toBeVisible();
    expect(within(recepcion!).getByText("1 canal")).toBeVisible();
    expect(within(recepcion!).getByText("Por defecto")).toBeVisible();
    expect(within(ventas!).getByText("Borrador")).toBeVisible();
    expect(within(ventas!).getByText("Sin canal")).toBeVisible();
    expect(within(cobros!).getByText("Con cambios sin publicar")).toBeVisible();
    expect(within(cobros!).getByText("2 canales")).toBeVisible();
    // Un solo botón primario por vista: «Nuevo agente» está en la cabecera del cliente (Andrés, 2026-10-28).
    expect(screen.queryByRole("link", { name: "Nuevo agente" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin agentes, el vacío lo dice (el botón está en la cabecera); sin permiso, solo lo dice", async () => {
    const { container, unmount } = cards([]);
    expect(screen.getByText("Este cliente aún no tiene agentes")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Nuevo agente" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
    unmount();
    cards([], false);
    expect(screen.getByText("Cuando alguien de tu equipo cree uno, aparecerá aquí.")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Nuevo agente" })).toBeNull();
  });

  it("con el estado visible de la API: el mismo texto en todas partes, y abre la pestaña que le toca (25.5, 26.1)", () => {
    cards([
      agent({ name: "Recepción", is_default: true, visible_state: { code: "serving", tone: "positive", reason: null }, opens: "overview" }),
      agent({
        id: "44444444-4444-4444-8444-444444444444",
        name: "Cobros",
        is_principal: false,
        is_default: false,
        visible_state: { code: "paused", tone: "warn", reason: "no_balance" },
        opens: "overview",
      }),
      agent({
        id: "55555555-5555-4555-8555-555555555555",
        name: "Ventas",
        is_principal: false,
        is_default: false,
        visible_state: { code: "ready_no_channel", tone: "info", reason: null },
        opens: "channels",
      }),
    ]);
    const list = screen.getByRole("list", { name: "Agentes del cliente" });
    const [recepcion, cobros, ventas] = within(list).getAllByRole("link");
    expect(within(recepcion!).getByText("Atendiendo")).toBeVisible();
    expect(within(recepcion!).getByText("Por defecto")).toBeVisible();
    expect(within(cobros!).getByText("Pausado · sin saldo")).toBeVisible();
    expect(within(cobros!).queryByText("Por defecto")).toBeNull();
    expect(within(ventas!).getByText("Listo · sin canal")).toBeVisible();
    expect(ventas).toHaveAttribute("href", `/clients/${REF}/channels`);
    expect(cobros).toHaveAttribute("href", `/clients/${REF}/agents/44444444-4444-4444-8444-444444444444`);
  });

  it("si no se pudieron leer, lo dice", () => {
    cards(null);
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos cargar los agentes");
  });
});

/**
 * Enmienda del 2026-10-29 (T210, requisito 60.6) — los agentes que el sistema
 * sugiere para el cliente salen como tarjetas «Sugerido», detrás de los suyos,
 * con «Crear este agente» (abre «Nuevo agente» con nombre y descripción, no
 * crea nada) y «Descartar». Nunca se crean solos.
 */
describe("la pestaña Agentes · los sugeridos (60.6)", () => {
  const SUGGESTED: SuggestedAgent[] = [
    { id: "s1", name: "Cobros", description: "Envía el enlace de pago de la señal y confirma cuando llega.", role: "billing" },
    { id: "s2", name: "Dudas & preguntas", description: "Responde a lo que preguntan sobre precios y horarios.", role: null },
  ];

  it("cada uno es una tarjeta «Sugerido» con «Crear este agente», que abre «Nuevo agente» relleno, y pasa axe", async () => {
    const { container } = cards(AGENTS, true, SUGGESTED);
    const list = screen.getByRole("list", { name: "Agentes sugeridos" });
    const [cobros, dudas] = within(list).getAllByRole("listitem");
    expect(within(cobros!).getByText("Sugerido")).toBeVisible();
    expect(within(cobros!).getByText("Cobros")).toBeVisible();
    expect(within(cobros!).getByText("Para cobros")).toBeVisible();
    expect(within(cobros!).getByText(SUGGESTED[0]!.description)).toBeVisible();
    expect(within(cobros!).getByRole("link", { name: "Crear este agente: Cobros" })).toHaveAttribute(
      "href",
      `/clients/${REF}/agents/new?name=Cobros&description=${encodeURIComponent(SUGGESTED[0]!.description)}`,
    );
    expect(within(dudas!).getByRole("link", { name: "Crear este agente: Dudas & preguntas" })).toHaveAttribute(
      "href",
      expect.stringContaining("name=Dudas%20%26%20preguntas"),
    );
    // Los suyos siguen igual, primero.
    expect(within(screen.getByRole("list", { name: "Agentes del cliente" })).getAllByRole("link")).toHaveLength(3);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«Descartar» lo quita y no lo crea", async () => {
    const user = userEvent.setup();
    dismissAction.mockResolvedValue({ ok: true, data: null });
    cards(AGENTS, true, SUGGESTED);
    await user.click(screen.getByRole("button", { name: "Descartar la sugerencia Cobros" }));
    expect(dismissAction).toHaveBeenCalledWith({ ref: REF, id: "s1" });
    await waitFor(() => expect(screen.queryByRole("link", { name: "Crear este agente: Cobros" })).toBeNull());
    expect(screen.getByRole("link", { name: "Crear este agente: Dudas & preguntas" })).toBeVisible();
    expect(toast.success).toHaveBeenCalledWith("Sugerencia descartada.");
  });

  it("si no se puede descartar, lo dice y la deja", async () => {
    const user = userEvent.setup();
    dismissAction.mockResolvedValue({ ok: false, status: 500, message: "x" });
    cards(AGENTS, true, SUGGESTED);
    await user.click(screen.getByRole("button", { name: "Descartar la sugerencia Cobros" }));
    expect(await screen.findByText("No se pudo descartar. Inténtalo de nuevo.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Crear este agente: Cobros" })).toBeVisible();
  });

  it("sin agentes, el vacío y debajo los sugeridos", () => {
    cards([], true, SUGGESTED);
    expect(screen.getByText("Este cliente aún no tiene agentes")).toBeVisible();
    expect(screen.getByRole("list", { name: "Agentes sugeridos" })).toBeVisible();
  });

  it("el nombre accesible de «Crear este agente» empieza por lo que se ve (WCAG 2.5.3); un papel que no conoce no se pinta", () => {
    cards(AGENTS, true, [{ ...SUGGESTED[0]!, role: "marketing" as SuggestedAgent["role"] }]);
    const link = screen.getByRole("link", { name: "Crear este agente: Cobros" });
    expect(link).toHaveTextContent("Crear este agente");
    expect(link.getAttribute("aria-label")).toMatch(/^Crear este agente/);
    expect(screen.queryByText(/builder\.suggested\.role/)).toBeNull();
  });

  it("quien solo lee los ve sin botones; sin sugeridos (o si no cargaron) no hay lista", () => {
    const { unmount } = cards(AGENTS, false, SUGGESTED);
    expect(screen.getByRole("list", { name: "Agentes sugeridos" })).toBeVisible();
    expect(screen.queryByRole("link", { name: /Crear este agente/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Descartar/ })).toBeNull();
    unmount();
    const second = cards(AGENTS, true, []);
    expect(screen.queryByRole("list", { name: "Agentes sugeridos" })).toBeNull();
    second.unmount();
    cards(AGENTS, true, null);
    expect(screen.queryByRole("list", { name: "Agentes sugeridos" })).toBeNull();
  });
});

/**
 * Spec 047, enmienda del 2026-10-30 (T228; requisito 65.7;
 * `contracts/console-api.md` §11 «Sugerencias de agentes»): no hay papeles
 * fijos. `role` es opcional: `null` es lo normal, puede no venir y cualquier
 * valor que la consola no conozca cuenta como `null`. Nada falla y no se pinta
 * ningún papel.
 */
describe("la pestaña Agentes · los sugeridos sin papel obligatorio (65.7)", () => {
  it("sin papel, sin el campo o con uno desconocido: la tarjeta sale entera y sin papel; pasa axe", async () => {
    const free = [
      { id: "s1", name: "Atiende y pasa las citas", description: "Responde dudas y pasa las citas al equipo.", role: null },
      { id: "s2", name: "Encargos de tartas", description: "Toma nota de los encargos y los pasa al obrador." } as unknown as SuggestedAgent,
      { id: "s3", name: "Avisos de stock", description: "Dice qué hay disponible esta semana.", role: "inventory" } as unknown as SuggestedAgent,
    ];
    const { container } = cards(AGENTS, true, free);
    const list = screen.getByRole("list", { name: "Agentes sugeridos" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    for (const [i, li] of items.entries()) {
      expect(within(li).getByText("Sugerido")).toBeVisible();
      expect(within(li).getByText(free[i]!.description)).toBeVisible();
      expect(within(li).queryByText(/^Para /)).toBeNull();
      expect(within(li).getByRole("link", { name: `Crear este agente: ${free[i]!.name}` })).toBeVisible();
    }
    expect(await axeViolations(container)).toEqual([]);
  });
});
