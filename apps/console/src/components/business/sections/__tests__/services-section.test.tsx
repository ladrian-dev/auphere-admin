import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Service, Services } from "@/lib/backend/business-sections";

vi.mock("@/app/(console)/clients/[ref]/business/actions", () => ({
  createServiceAction: vi.fn(),
  updateServiceAction: vi.fn(),
  archiveServiceAction: vi.fn(),
  duplicateServiceAction: vi.fn(),
  setServiceAgentsAction: vi.fn(),
}));

const { ServicesSection } = await import("../services-section");

/**
 * Spec 047 (T060, historia 6) — Servicios en Negocio: reservable o no, el
 * precio con los decimales de su moneda, «Lo usan», duplicar y archivar, quién
 * lo ofrece, y sus estados (vacío, solo lectura).
 */

const RECEPCION = { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", name: "Recepción", serves_all: true };
const VENTAS = { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", name: "Ventas mayoristas", serves_all: false };
const svc = (over: Partial<Service>): Service => ({
  id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  name: "Ramo grande",
  description: null,
  bookable: false,
  duration_min: null,
  price: { kind: "amount", amount_minor: 15000 },
  currency: "CLP",
  staff: "all",
  agents: { mode: "all_agents", agent_ids: [] },
  used_by: [{ id: RECEPCION.id, name: RECEPCION.name }],
  archived: false,
  ...over,
});
const SERVICES: Services = {
  revision: 2,
  state: "complete",
  allowed: ["edit"],
  currency: "CLP",
  exponent: 0,
  created_id: null,
  agents: [RECEPCION, VENTAS],
  items: [
    svc({}),
    svc({ id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", name: "Corte", bookable: true, duration_min: 30, price: { kind: "free" } }),
    svc({
      id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      name: "Pedido mayorista",
      price: { kind: "none" },
      agents: { mode: "list", agent_ids: [VENTAS.id] },
      used_by: [
        { id: RECEPCION.id, name: RECEPCION.name },
        { id: VENTAS.id, name: VENTAS.name },
      ],
    }),
  ],
};

type R = { ok: true; data: Services } | { ok: false; status: number; message: string; code?: string | null };

function section(props: Partial<React.ComponentProps<typeof ServicesSection>> = {}) {
  const ok = async (): Promise<R> => ({ ok: true, data: SERVICES });
  const actions = {
    create: vi.fn(ok),
    update: vi.fn(ok),
    archive: vi.fn(ok),
    duplicate: vi.fn(ok),
    setAgents: vi.fn(ok),
  };
  const view = render(
    <LocaleProvider locale="es">
      <ServicesSection refId="flor" services={SERVICES} canWrite actions={actions} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions };
}

describe("ServicesSection", () => {
  it("lists each service with its price in its currency and who uses it", async () => {
    const { container } = section();
    const ramo = screen.getByRole("row", { name: /Ramo grande/ });
    expect(within(ramo).getByText("15.000 CLP")).toBeVisible();
    expect(within(ramo).getByText("No se reserva")).toBeVisible();
    expect(within(ramo).getByText("Recepción")).toBeVisible();
    const corte = screen.getByRole("row", { name: /Corte/ });
    expect(within(corte).getByText("30 min")).toBeVisible();
    expect(within(corte).getByText("Gratis")).toBeVisible();
    const mayor = screen.getByRole("row", { name: /Pedido mayorista/ });
    expect(within(mayor).getByText("Sin precio")).toBeVisible();
    expect(within(mayor).getByText("Recepción, Ventas mayoristas")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("duplicates and archives with the revision it read", async () => {
    const user = userEvent.setup();
    const { actions } = section();
    const ramo = () => screen.getByRole("row", { name: /Ramo grande/ });
    await user.click(within(ramo()).getByRole("button", { name: "Acciones de Ramo grande" }));
    await user.click(await screen.findByRole("menuitem", { name: "Duplicar" }));
    expect(actions.duplicate).toHaveBeenCalledWith(expect.objectContaining({ ref: "flor", id: SERVICES.items[0]?.id, revision: 2 }));
    await user.click(within(ramo()).getByRole("button", { name: "Acciones de Ramo grande" }));
    await user.click(await screen.findByRole("menuitem", { name: "Archivar" }));
    expect(actions.archive).toHaveBeenCalledWith(expect.objectContaining({ id: SERVICES.items[0]?.id }));
  });

  it("folds four actions into «⋯», editing first (regla de los tres puntos)", async () => {
    const user = userEvent.setup();
    section();
    const ramo = screen.getByRole("row", { name: /Ramo grande/ });
    expect(within(ramo).queryByRole("button", { name: /^Editar|^Duplicar|^Archivar|^Quién/ })).toBeNull();
    await user.click(within(ramo).getByRole("button", { name: "Acciones de Ramo grande" }));
    const items = (await screen.findAllByRole("menuitem")).map((i) => i.textContent);
    expect(items).toEqual(["Editar", "Quién lo ofrece", "Duplicar", "Archivar"]);
    await user.click(screen.getByRole("menuitem", { name: "Editar" }));
    expect(await screen.findByRole("dialog", { name: /Editar|Ramo grande/ })).toBeTruthy();
  });

  it("with two actions (the client's console) they stay as buttons", () => {
    const ok = async (): Promise<R> => ({ ok: true, data: SERVICES });
    section({ actions: { create: vi.fn(ok), update: vi.fn(ok), archive: vi.fn(ok) } });
    const ramo = screen.getByRole("row", { name: /Ramo grande/ });
    expect(within(ramo).getByRole("button", { name: "Editar Ramo grande" })).toBeVisible();
    expect(within(ramo).getByRole("button", { name: "Archivar Ramo grande" })).toBeVisible();
    expect(within(ramo).queryByRole("button", { name: "Acciones de Ramo grande" })).toBeNull();
  });

  it("adds a bookable service with its duration and price", async () => {
    const user = userEvent.setup();
    const { actions } = section();
    await user.click(screen.getByRole("button", { name: "Añadir servicio" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir servicio" });
    await user.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Boda");
    await user.click(within(dialog).getByRole("checkbox", { name: "Se reserva" }));
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Duración" }), "90");
    await user.click(within(dialog).getByRole("radio", { name: "Importe" }));
    await user.type(within(dialog).getByRole("textbox", { name: "Importe en CLP" }), "45.000");
    await user.click(within(dialog).getByRole("button", { name: "Guardar servicio" }));
    expect(actions.create).toHaveBeenCalledWith({
      ref: "flor",
      revision: 2,
      body: { name: "Boda", description: null, bookable: true, duration_min: 90, price: { kind: "amount", amount_minor: 45000 }, category: null },
    });
  });

  it("spec 055: each row uses the decimals of its own currency", () => {
    section({ services: { ...SERVICES, currency: "USD", exponent: 2, items: [svc({ exponent: 0 })] } });
    expect(screen.getByText("15.000 CLP")).toBeVisible();
  });

  it("spec 055: without a business currency it asks for one and invents none", async () => {
    const user = userEvent.setup();
    const { actions } = section({ services: { ...SERVICES, currency: "XXX", currency_set: false, exponent: 2, items: [] } });
    await user.click(screen.getByRole("button", { name: "Añadir servicio" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir servicio" });
    await user.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Boda");
    await user.click(within(dialog).getByRole("radio", { name: "Importe" }));
    await user.type(within(dialog).getByRole("textbox", { name: "Importe" }), "15,50");
    await user.click(within(dialog).getByRole("button", { name: "Guardar servicio" }));
    expect(await within(dialog).findByText("Elige la moneda de los precios.")).toBeVisible();
    expect(actions.create).not.toHaveBeenCalled();
    await user.selectOptions(within(dialog).getByRole("combobox", { name: /Moneda de los precios/ }), "USD");
    expect(within(dialog).getByRole("textbox", { name: "Importe en USD" })).toHaveValue("15,50");
    await user.click(within(dialog).getByRole("button", { name: "Guardar servicio" }));
    expect(actions.create).toHaveBeenCalledWith({
      ref: "flor",
      revision: 2,
      body: { name: "Boda", description: null, bookable: false, duration_min: null, price: { kind: "amount", amount_minor: 1550 }, price_currency: "USD", category: null },
    });
  });

  it("spec 055: groups by category, alphabetically, with «Sin categoría» last", () => {
    section({
      services: {
        ...SERVICES,
        items: [
          svc({ id: "11111111-1111-4111-8111-111111111111", name: "Consulta", category: null }),
          svc({ id: "22222222-2222-4222-8222-222222222222", name: "Tinte", category: "Color" }),
          svc({ id: "33333333-3333-4333-8333-333333333333", name: "Básico", category: "Corte" }),
          svc({ id: "44444444-4444-4444-8444-444444444444", name: "Heavy", category: "Corte" }),
        ],
      },
    });
    const rows = screen
      .getAllByRole("row")
      .slice(1)
      .map((r) => (r.querySelector("th") ?? r.querySelector("td span"))?.textContent);
    expect(rows).toEqual(["Color", "Tinte", "Corte", "Básico", "Heavy", "Sin categoría", "Consulta"]);
  });

  it("spec 055: without any category the list looks as it always did", () => {
    section();
    expect(screen.queryByText("Sin categoría")).toBeNull();
  });

  it("spec 055: the dialog suggests the categories in use and sends the one written", async () => {
    const user = userEvent.setup();
    const { actions } = section({ services: { ...SERVICES, items: [svc({ category: "Corte" })] } });
    await user.click(screen.getByRole("button", { name: "Añadir servicio" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir servicio" });
    const box = within(dialog).getByRole("combobox", { name: /Categoría/ });
    expect([...document.querySelectorAll(`#${box.getAttribute("list")} option`)].map((o) => o.getAttribute("value"))).toEqual(["Corte"]);
    await user.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Heavy");
    await user.type(box, " Corte ");
    await user.click(within(dialog).getByRole("button", { name: "Guardar servicio" }));
    expect(actions.create).toHaveBeenCalledWith(expect.objectContaining({ body: expect.objectContaining({ name: "Heavy", category: "Corte" }) }));
  });

  it("spec 055: the client's console shows the groups but does not edit the category", async () => {
    const user = userEvent.setup();
    section({ categorizable: false, services: { ...SERVICES, items: [svc({ category: "Corte" })] } });
    expect(screen.getByText("Corte")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Añadir servicio" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir servicio" });
    expect(within(dialog).queryByRole("combobox", { name: /Categoría/ })).toBeNull();
  });

  it("chooses who offers a service; those that serve all are always in", async () => {
    const user = userEvent.setup();
    const { actions } = section();
    const ramo = screen.getByRole("row", { name: /Ramo grande/ });
    await user.click(within(ramo).getByRole("button", { name: "Acciones de Ramo grande" }));
    await user.click(await screen.findByRole("menuitem", { name: "Quién lo ofrece" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: "Solo algunos agentes" }));
    const recepcion = within(dialog).getByRole("checkbox", { name: /Recepción/ });
    expect(recepcion).toBeChecked();
    expect(recepcion).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox", { name: /Ventas mayoristas/ }));
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(actions.setAgents).toHaveBeenCalledWith(
      expect.objectContaining({ id: SERVICES.items[0]?.id, revision: 2, body: { mode: "list", agent_ids: [VENTAS.id] } }),
    );
  });

  it("says when there is nothing yet, and is read-only without permission", () => {
    section({ services: { ...SERVICES, items: [] } });
    expect(screen.getByText(/Todavía no hay servicios/)).toBeVisible();
  });

  it("hides every action without permission", () => {
    section({ canWrite: false });
    expect(screen.queryByRole("button", { name: "Añadir servicio" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Duplicar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Archivar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Acciones de/ })).toBeNull();
  });
});
