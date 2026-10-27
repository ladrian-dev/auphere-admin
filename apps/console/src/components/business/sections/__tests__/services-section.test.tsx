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
    const ramo = screen.getByRole("row", { name: /Ramo grande/ });
    await user.click(within(ramo).getByRole("button", { name: "Duplicar Ramo grande" }));
    expect(actions.duplicate).toHaveBeenCalledWith(expect.objectContaining({ ref: "flor", id: SERVICES.items[0]?.id, revision: 2 }));
    await user.click(within(ramo).getByRole("button", { name: "Archivar Ramo grande" }));
    expect(actions.archive).toHaveBeenCalledWith(expect.objectContaining({ id: SERVICES.items[0]?.id }));
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
      body: { name: "Boda", description: null, bookable: true, duration_min: 90, price: { kind: "amount", amount_minor: 45000 } },
    });
  });

  it("chooses who offers a service; those that serve all are always in", async () => {
    const user = userEvent.setup();
    const { actions } = section();
    const ramo = screen.getByRole("row", { name: /Ramo grande/ });
    await user.click(within(ramo).getByRole("button", { name: "Quién ofrece Ramo grande" }));
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
  });
});
