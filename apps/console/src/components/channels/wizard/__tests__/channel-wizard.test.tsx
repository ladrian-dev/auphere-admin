import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { t as translate } from "@/i18n/messages";
import type { ChannelCatalogEntry } from "@/lib/backend/channels";

/**
 * Spec 046 (T004): «Añadir canal» in the partner console — the same four
 * steps as the operator panel. What is pinned here: which step a path is
 * on, that only what can start is a link (constitution §V, 1.2.0), and that
 * step 3 always says what the number is for before giving it an agent.
 */

const nav = vi.hoisted(() => ({ pathname: "/clients/demo/channels/new", push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: nav.push, refresh: nav.refresh, replace: vi.fn() }),
}));
const agentsActions = vi.hoisted(() => ({ assignChannelAgentAction: vi.fn() }));
vi.mock("@/app/(console)/clients/[ref]/agents/actions", () => agentsActions);
const channelActions = vi.hoisted(() => ({ setChannelRoleAction: vi.fn() }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => channelActions);

const { stepOf, wizardPaths } = await import("../steps");
const { ChannelTile } = await import("../channel-tile");
const { WizardSteps } = await import("../wizard-steps");
const { AssignStepForm, assignPlan } = await import("../assign-step-form");

const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate("es", key, vars);
const mount = (ui: React.ReactElement) => render(<LocaleProvider locale="es">{ui}</LocaleProvider>);

const entry = (key: string, availability: ChannelCatalogEntry["availability"], note: string | null = null): ChannelCatalogEntry => ({
  key,
  name: key === "whatsapp" ? "WhatsApp" : key,
  description: `Descripción de ${key}`,
  availability,
  note,
});

describe("los pasos del asistente", () => {
  it("la ruta dice el paso", () => {
    expect(stepOf("/clients/demo/channels/new")).toBe(0);
    expect(stepOf("/clients/demo/channels/new/whatsapp")).toBe(1);
    expect(stepOf("/clients/demo/channels/new/whatsapp/agent")).toBe(2);
    expect(stepOf("/clients/demo/channels/new/whatsapp/done")).toBe(3);
  });

  it("las rutas llevan el número y su papel", () => {
    const p = wizardPaths("la espiga");
    expect(p.agent("whatsapp", "c1")).toBe("/clients/la%20espiga/channels/new/whatsapp/agent?channel=c1");
    expect(p.done("whatsapp", "c1", "agent")).toBe("/clients/la%20espiga/channels/new/whatsapp/done?channel=c1");
    expect(p.done("whatsapp", "c1", "notifications")).toContain("&role=notifications");
  });

  it("el carril marca el paso actual y da por hechos los anteriores", () => {
    nav.pathname = "/clients/demo/channels/new/whatsapp/agent";
    mount(<WizardSteps />);
    const current = screen.getByText("Asignar agente").closest("li");
    expect(current).toHaveAttribute("aria-current", "step");
    expect(screen.queryByText("1")).toBeNull();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
});

describe("el catálogo (§V, enmienda 1.2.0)", () => {
  it("solo lo que se puede conectar es un enlace", () => {
    const { container } = mount(
      <ul>
        <li>
          <ChannelTile entry={entry("whatsapp", "available")} href="/x/whatsapp" t={t} />
        </li>
        <li>
          <ChannelTile entry={entry("tiktok", "pending", "Esperando la aprobación del proveedor.")} href="/x/tiktok" t={t} />
        </li>
        <li>
          <ChannelTile entry={entry("telegram", "coming_soon", "Todavía no se puede conectar.")} href="/x/telegram" t={t} />
        </li>
      </ul>,
    );
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/x/whatsapp");
    expect(screen.getByText("Pendiente")).toBeInTheDocument();
    expect(screen.getByText("Próximamente")).toBeInTheDocument();
    expect(container.querySelectorAll("[aria-disabled=true]")).toHaveLength(2);
  });
});

describe("paso 3 · para qué es el número y quién contesta", () => {
  const n = { id: "c1", label: "Panadería · +34600000001", agentId: null, agentEnabled: true };
  const numbers = [n];
  const agents = [{ id: "a1", name: "Recepción", published: true }];

  beforeEach(() => {
    nav.push.mockReset();
    channelActions.setChannelRoleAction.mockReset().mockResolvedValue({ ok: true, data: {} });
    agentsActions.assignChannelAgentAction.mockReset().mockResolvedValue({ ok: true, data: {} });
  });

  it("el plan siempre escribe el papel y solo asigna agente a un número que atiende", () => {
    expect(assignPlan({ purpose: "agent", number: n, agentId: "a1" })).toEqual({ role: "agent", assign: "a1" });
    expect(assignPlan({ purpose: "notifications", number: n, agentId: "a1" })).toEqual({ role: "notifications", assign: null });
    expect(assignPlan({ purpose: "agent", number: { ...n, agentEnabled: false }, agentId: "a1" })).toEqual({ role: "agent", assign: null });
  });

  it("guardar escribe el papel, asigna el agente y pasa a ¡Listo!", async () => {
    mount(<AssignStepForm refId="demo" channel="whatsapp" numbers={numbers} agents={agents} defaultNumber="c1" defaultAgent="a1" />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/clients/demo/channels/new/whatsapp/done?channel=c1"));
    expect(channelActions.setChannelRoleAction).toHaveBeenCalledWith({ ref: "demo", channelId: "c1", role: "agent" });
    expect(agentsActions.assignChannelAgentAction).toHaveBeenCalledWith({ ref: "demo", channel: "c1", agent: "a1" });
  });

  it("una línea de avisos no recibe agente", async () => {
    mount(<AssignStepForm refId="demo" channel="whatsapp" numbers={numbers} agents={agents} defaultNumber="c1" defaultAgent="a1" />);
    await userEvent.click(screen.getByRole("radio", { name: /Solo envía avisos/ }));
    expect(screen.queryByText(/Agente que contesta/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalled());
    expect(agentsActions.assignChannelAgentAction).not.toHaveBeenCalled();
    expect(String(nav.push.mock.calls[0]?.[0])).toContain("role=notifications");
  });

  it("un agente sin publicar no se puede guardar, y se dice por qué", () => {
    mount(
      <AssignStepForm
        refId="demo"
        channel="whatsapp"
        numbers={numbers}
        agents={[{ id: "a1", name: "Recepción", published: false }]}
        defaultNumber="c1"
        defaultAgent="a1"
      />,
    );
    expect(screen.getByText(/todavía no está publicado/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar y terminar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ir al agente" })).toHaveAttribute("href", "/clients/demo/agent?agent=a1");
  });

  it("el rechazo de la API sale en palabras, junto al botón", async () => {
    agentsActions.assignChannelAgentAction.mockResolvedValue({ ok: false, status: 409, message: "", code: "channel_send_only" });
    mount(<AssignStepForm refId="demo" channel="whatsapp" numbers={numbers} agents={agents} defaultNumber="c1" defaultAgent="a1" />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ese número solo envía avisos");
    expect(nav.push).not.toHaveBeenCalled();
  });
});
