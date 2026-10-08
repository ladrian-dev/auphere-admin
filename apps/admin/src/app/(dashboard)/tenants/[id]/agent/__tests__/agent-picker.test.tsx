import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TenantAgent } from "@/lib/backend";

/**
 * Spec 030, iteration 3 (R14.1, R14.5 · T102): the agent tab of the admin
 * says which of the client's agents it edits and keeps it in `?agent=`;
 * «Nuevo agente» asks only for a name and keeps it when the API refuses.
 */

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  usePathname: () => "/tenants/t1/agent",
  useRouter: () => ({ push, refresh: vi.fn() }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const createTenantAgentAction = vi.hoisted(() => vi.fn());
vi.mock("../actions", () => ({ createTenantAgentAction }));

const { AgentPicker } = await import("../agent-picker");

const MAIN = "11111111-1111-4111-8111-111111111111";
const SALES = "22222222-2222-4222-8222-222222222222";
const agent = (o: Partial<TenantAgent>): TenantAgent => ({
  id: MAIN,
  name: "Agente principal",
  status: "active",
  is_principal: true,
  channels: [],
  active_version: 3,
  draft_version: null,
  ...o,
});
const TWO = [agent({}), agent({ id: SALES, name: "Ventas", is_principal: false, active_version: null })];

beforeEach(() => vi.clearAllMocks());

describe("AgentPicker", () => {
  it("con un agente no hay selector, solo «Nuevo agente»", () => {
    render(<AgentPicker tenantId="t1" agents={[agent({})]} selectedId={MAIN} />);
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.getByRole("button", { name: "Nuevo agente" })).toBeInTheDocument();
  });

  it("con varios dice cuál es el principal y cuál está sin publicar, y lleva la elección a la URL", async () => {
    render(<AgentPicker tenantId="t1" agents={TWO} selectedId={MAIN} />);
    const select = screen.getByRole("combobox", { name: "Agente" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Agente principal · principal",
      "Ventas · sin publicar",
    ]);
    await userEvent.selectOptions(select, SALES);
    expect(push).toHaveBeenLastCalledWith(`/tenants/t1/agent?agent=${SALES}`);
    await userEvent.selectOptions(select, MAIN);
    expect(push).toHaveBeenLastCalledWith("/tenants/t1/agent");
  });

  it("crea un agente y lo abre; un nombre repetido se dice junto al campo sin borrarlo", async () => {
    createTenantAgentAction.mockResolvedValueOnce({ ok: false, error: "name_taken" });
    render(<AgentPicker tenantId="t1" agents={TWO} selectedId={MAIN} />);
    await userEvent.click(screen.getByRole("button", { name: "Nuevo agente" }));
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByRole("textbox", { name: "Nombre" });
    await userEvent.type(input, "Ventas");
    await userEvent.click(within(dialog).getByRole("button", { name: "Crear agente" }));
    expect(await within(dialog).findByText("Ya hay un agente activo con ese nombre.")).toBeInTheDocument();
    expect(input).toHaveValue("Ventas");

    createTenantAgentAction.mockResolvedValueOnce({ ok: true, data: agent({ id: "33333333-3333-4333-8333-333333333333", name: "Soporte", is_principal: false }) });
    await userEvent.clear(input);
    await userEvent.type(input, "Soporte");
    await userEvent.click(within(dialog).getByRole("button", { name: "Crear agente" }));
    await waitFor(() => expect(createTenantAgentAction).toHaveBeenLastCalledWith("t1", "Soporte"));
    expect(push).toHaveBeenLastCalledWith("/tenants/t1/agent?agent=33333333-3333-4333-8333-333333333333");
  });

  it("sin nombre no llama a nadie", async () => {
    render(<AgentPicker tenantId="t1" agents={TWO} selectedId={MAIN} />);
    await userEvent.click(screen.getByRole("button", { name: "Nuevo agente" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Crear agente" }));
    expect(await within(dialog).findByText("Poné un nombre.")).toBeInTheDocument();
    expect(createTenantAgentAction).not.toHaveBeenCalled();
  });
});
