import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { ClientAgent } from "@/lib/backend";
import type { ChannelDetail } from "@/lib/backend/channels";

/**
 * Spec 030, iteration 3 (R14.1, 14.2, 14.5 · T096): a client with more than
 * one agent, from the partner console. The selector lives only on the tabs
 * of one agent and keeps its choice in `?agent=`; «Nuevo agente» asks for a
 * name, a template and only what the template needs; the draft bar is the
 * one of the chosen agent; and each number says which agent answers on it.
 * With one agent none of this is in the way.
 */

const nav = vi.hoisted(() => ({ pathname: "/clients/demo/agent", search: "", push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ push: nav.push, refresh: nav.refresh, replace: vi.fn() }),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const agentsActions = vi.hoisted(() => ({
  createAgentAction: vi.fn(),
  renameAgentAction: vi.fn(),
  archiveAgentAction: vi.fn(),
  assignChannelAgentAction: vi.fn(),
}));
vi.mock("@/app/(console)/clients/[ref]/agents/actions", () => agentsActions);
const listSeedTemplatesAction = vi.hoisted(() => vi.fn());
vi.mock("@/app/(console)/clients/new/actions", () => ({ listSeedTemplatesAction }));
const draftActions = vi.hoisted(() => ({ draftDiffAction: vi.fn(), publishFromBarAction: vi.fn() }));
vi.mock("@/app/(console)/clients/[ref]/agent/actions", () => draftActions);
vi.mock("@/app/(console)/clients/actions", () => ({ rollbackAgentAction: vi.fn() }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  setChannelRoleAction: vi.fn(),
  disconnectChannelAction: vi.fn(),
  listCatalogsAction: vi.fn().mockResolvedValue({ ok: true, data: { items: [], linked_id: null } }),
  setCatalogAction: vi.fn(),
  clearCatalogAction: vi.fn(),
}));

const { AgentSwitcher } = await import("@/components/clients/agent-switcher");
const { AgentDraftBars } = await import("@/components/clients/agent-draft-bars");
const { ClientNav } = await import("@/components/clients/client-nav");
const { ChannelCard } = await import("@/components/channels/channel-card");

const MAIN = "11111111-1111-4111-8111-111111111111";
const SALES = "22222222-2222-4222-8222-222222222222";
const DRAFT = "33333333-3333-4333-8333-333333333333";
const agent = (o: Partial<ClientAgent>): ClientAgent => ({
  id: MAIN,
  name: "Agente principal",
  status: "active",
  is_principal: true,
  channels: [],
  active_version: 3,
  draft_version: null,
  ...o,
});
const MANY = [
  agent({}),
  agent({ id: SALES, name: "Ventas", is_principal: false, active_version: 5 }),
  agent({ id: DRAFT, name: "Soporte", is_principal: false, active_version: null, draft_version: 6 }),
];

function es(ui: React.ReactNode) {
  return render(<LocaleProvider locale="es">{ui}</LocaleProvider>);
}

beforeEach(() => {
  nav.pathname = "/clients/demo/agent";
  nav.search = "";
  vi.clearAllMocks();
});

describe("el selector de agente", () => {
  it("no está fuera de las pestañas de un agente", () => {
    nav.pathname = "/clients/demo/channels";
    const { container } = es(<AgentSwitcher refId="demo" agents={MANY} canWrite />);
    expect(container).toBeEmptyDOMElement();
  });

  it("con un agente solo ofrece crear otro — y nada a quien no puede", () => {
    const { unmount } = es(<AgentSwitcher refId="demo" agents={[agent({})]} canWrite />);
    expect(screen.queryByRole("combobox", { name: "Agente" })).toBeNull();
    expect(screen.getByRole("button", { name: "Nuevo agente" })).toBeInTheDocument();
    unmount();
    const { container } = es(<AgentSwitcher refId="demo" agents={[agent({})]} canWrite={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lista los agentes, dice cuál está sin publicar y lleva la elección a la URL", async () => {
    nav.search = "tab=x";
    es(<AgentSwitcher refId="demo" agents={MANY} canWrite />);
    const select = screen.getByRole("combobox", { name: "Agente" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Agente principal",
      "Ventas",
      "Soporte · sin publicar",
    ]);
    await userEvent.selectOptions(select, SALES);
    expect(nav.push).toHaveBeenLastCalledWith(`/clients/demo/agent?tab=x&agent=${SALES}`);
    await userEvent.selectOptions(select, MAIN);
    expect(nav.push).toHaveBeenLastCalledWith("/clients/demo/agent?tab=x");
  });

  it("renombrar y archivar solo aparecen sobre un agente que no es el principal", () => {
    const { unmount } = es(<AgentSwitcher refId="demo" agents={MANY} canWrite />);
    expect(screen.queryByRole("button", { name: "Archivar" })).toBeNull();
    unmount();
    nav.search = `agent=${SALES}`;
    es(<AgentSwitcher refId="demo" agents={MANY} canWrite />);
    expect(screen.getByRole("combobox", { name: "Agente" })).toHaveValue(SALES);
    expect(screen.getByRole("button", { name: "Renombrar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archivar" })).toBeInTheDocument();
  });

  it("archivar un agente que contesta en un número lo dice con palabras", async () => {
    nav.search = `agent=${SALES}`;
    agentsActions.archiveAgentAction.mockResolvedValue({ ok: false, status: 409, message: "", code: "agent_has_channels" });
    es(<AgentSwitcher refId="demo" agents={MANY} canWrite />);
    await userEvent.click(screen.getByRole("button", { name: "Archivar" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Archivar" }));
    await waitFor(() => expect(agentsActions.archiveAgentAction).toHaveBeenCalledWith({ ref: "demo", agent: SALES }));
    // The reason stays in the dialog, next to the decision.
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Este agente contesta en algún número. Dale ese número a otro agente antes de archivarlo.",
    );
  });

  it("un agente con números dice por qué no se archiva antes de confirmar, y no llama a nadie", async () => {
    nav.search = `agent=${SALES}`;
    const withNumber = MANY.map((a) => (a.id === SALES ? { ...a, channels: [{ id: "c1", display: "+34600000000" }] } : a));
    es(<AgentSwitcher refId="demo" agents={withNumber} canWrite />);
    await userEvent.click(screen.getByRole("button", { name: "Archivar" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Este agente contesta en algún número.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Archivar" }));
    expect(agentsActions.archiveAgentAction).not.toHaveBeenCalled();
  });

  it("renombrar con un nombre que ya existe deja el diálogo abierto con el motivo", async () => {
    nav.search = `agent=${SALES}`;
    agentsActions.renameAgentAction.mockResolvedValue({ ok: false, status: 409, message: "", code: "name_taken" });
    es(<AgentSwitcher refId="demo" agents={MANY} canWrite />);
    await userEvent.click(screen.getByRole("button", { name: "Renombrar" }));
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByRole("textbox", { name: "Nombre" });
    await userEvent.clear(input);
    await userEvent.type(input, "Soporte");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(await within(dialog).findByText("Ya hay un agente con ese nombre.")).toBeInTheDocument();
    expect(agentsActions.renameAgentAction).toHaveBeenCalledWith({ ref: "demo", agent: SALES, name: "Soporte" });

    agentsActions.renameAgentAction.mockResolvedValue({ ok: true, data: agent({ id: SALES, name: "Soporte web", is_principal: false }) });
    await userEvent.type(input, " web");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Ahora se llama «Soporte web»."));
  });
});

describe("«Nuevo agente»", () => {
  const TEMPLATES = [
    {
      name: "generic_v1",
      display_name: "Genérico",
      version: "1",
      vertical: "generic",
      tools_count: 3,
      placeholders: [
        { key: "tenant.address", required: true, secret: false, kind: "text" as const, example: null },
        { key: "agent.name", required: false, secret: false, kind: "text" as const, example: null },
      ],
    },
  ];

  it("pide nombre, plantilla y solo lo que la plantilla necesita; luego abre el agente nuevo", async () => {
    listSeedTemplatesAction.mockResolvedValue({ ok: true, data: TEMPLATES });
    agentsActions.createAgentAction.mockResolvedValue({ ok: true, data: agent({ id: SALES, name: "Ventas", is_principal: false }) });
    es(<AgentSwitcher refId="demo" agents={[agent({})]} canWrite />);
    await userEvent.click(screen.getByRole("button", { name: "Nuevo agente" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/no contesta en ningún número hasta que lo publiques/)).toBeInTheDocument();

    // Nothing filled: it says what is missing and calls nobody.
    await userEvent.click(await within(dialog).findByRole("button", { name: "Crear agente" }));
    expect(within(dialog).getAllByText("Este campo es obligatorio.").length).toBe(2);
    expect(agentsActions.createAgentAction).not.toHaveBeenCalled();
    // The optional placeholder is not asked for here.
    expect(within(dialog).getAllByRole("textbox")).toHaveLength(2);

    await userEvent.type(within(dialog).getByRole("textbox", { name: "Nombre" }), "  Ventas ");
    const [, address] = within(dialog).getAllByRole("textbox");
    await userEvent.type(address!, "Calle Mayor 1");
    await userEvent.click(within(dialog).getByRole("button", { name: "Crear agente" }));
    await waitFor(() =>
      expect(agentsActions.createAgentAction).toHaveBeenCalledWith({
        ref: "demo",
        name: "Ventas",
        seed_template: "generic_v1",
        placeholders: { "tenant.address": "Calle Mayor 1" },
      }),
    );
    expect(nav.push).toHaveBeenCalledWith(`/clients/demo/agent?agent=${SALES}`);
    expect(toast.success).toHaveBeenCalledWith("«Ventas» creado. Revisa su borrador y publícalo.");
  });

  it("un nombre repetido se dice junto al campo", async () => {
    listSeedTemplatesAction.mockResolvedValue({ ok: true, data: [{ ...TEMPLATES[0]!, placeholders: [] }] });
    agentsActions.createAgentAction.mockResolvedValue({ ok: false, status: 409, message: "", code: "name_taken" });
    es(<AgentSwitcher refId="demo" agents={[agent({})]} canWrite />);
    await userEvent.click(screen.getByRole("button", { name: "Nuevo agente" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(await within(dialog).findByRole("textbox", { name: "Nombre" }), "Agente principal");
    await userEvent.click(within(dialog).getByRole("button", { name: "Crear agente" }));
    expect(await within(dialog).findByText("Ya hay un agente con ese nombre.")).toBeInTheDocument();
  });

  it("si las plantillas no se pueden leer, lo dice y deja reintentar", async () => {
    listSeedTemplatesAction.mockResolvedValueOnce({ ok: false, status: 503, message: "" });
    listSeedTemplatesAction.mockResolvedValueOnce({ ok: true, data: TEMPLATES });
    es(<AgentSwitcher refId="demo" agents={[agent({})]} canWrite />);
    await userEvent.click(screen.getByRole("button", { name: "Nuevo agente" }));
    expect(await screen.findByText("No pudimos cargar las plantillas. Cierra y vuelve a intentarlo.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("button", { name: "Crear agente" })).toBeInTheDocument();
    expect(listSeedTemplatesAction).toHaveBeenCalledTimes(2);
  });
});

describe("la barra del borrador y las pestañas siguen al agente", () => {
  const drafts = [
    { agentId: MAIN, isPrincipal: true, screens: [], version: 3, activeVersion: 3 },
    { agentId: SALES, isPrincipal: false, screens: ["prompt" as const], version: 6, activeVersion: 5 },
  ];

  it("la barra es la del agente de la URL — y la del principal sin él", async () => {
    nav.search = `agent=${SALES}`;
    draftActions.draftDiffAction.mockResolvedValue({ ok: false, status: 503, message: "" });
    const { unmount } = es(<AgentDraftBars refId="demo" drafts={drafts} canPublish />);
    expect(screen.getByText(/Cambios sin publicar en/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Revisar y publicar" }));
    await waitFor(() => expect(draftActions.draftDiffAction).toHaveBeenCalledWith({ ref: "demo", agent: SALES }));
    unmount();
    // The principal has nothing unpublished: no bar.
    nav.search = "";
    es(<AgentDraftBars refId="demo" drafts={drafts} canPublish />);
    expect(screen.queryByText(/Cambios sin publicar en/)).toBeNull();
  });

  it("moverse entre las pestañas de un agente conserva el agente; las del cliente, no", () => {
    nav.search = `agent=${SALES}`;
    es(<ClientNav refId="demo" role="owner" />);
    const links = screen.getAllByRole("link");
    const href = (label: RegExp) => links.find((l) => label.test(l.textContent ?? ""))?.getAttribute("href");
    expect(href(/^Habilidades/)).toBe(`/clients/demo/capabilities?agent=${SALES}`);
    expect(href(/^Canales/)).toBe("/clients/demo/channels");
  });
});

describe("el agente de cada número", () => {
  const CHANNEL: ChannelDetail = {
    logo_url: null,
    id: "9f1b4e8a-6f3c-4c2a-9a6d-2f7e5c1b3d40",
    type: "whatsapp",
    provider: "meta",
    agent_enabled: true,
    provider_identifier: "+34653321693",
    status: "active",
    role: null,
    verified_name: "Flor",
    quality_rating: "GREEN",
    messaging_tier: "TIER_250",
    mode: "cloud_api",
    unlink_pending: [],
    catalog: null,
    catalog_state: "none",
    catalog_error: null,
    last_health_check_at: null,
    created_at: "2026-09-23T20:27:00Z",
  };
  const card = (o: { agents?: ClientAgent[]; manage?: boolean; channel?: Partial<ChannelDetail> } = {}) =>
    es(
      <ul>
        <ChannelCard
          refId="demo"
          channel={{ ...CHANNEL, ...o.channel }}
          manage={o.manage ?? true}
          showRoles={false}
          agents={o.agents ?? MANY}
          agentId={MAIN}
        />
      </ul>,
    );

  it("con un agente no hay nada que elegir", () => {
    card({ agents: [agent({})] });
    expect(screen.queryByRole("combobox", { name: "Contesta" })).toBeNull();
  });

  it("elegir otro agente no cambia nada hasta confirmarlo; luego vale desde el próximo mensaje", async () => {
    agentsActions.assignChannelAgentAction.mockResolvedValue({ ok: true, data: { channel_id: CHANNEL.id, agent_id: SALES } });
    card();
    const select = screen.getByRole("combobox", { name: "Contesta" });
    expect(select).toHaveValue(MAIN);
    expect(within(select).getByRole("option", { name: "Soporte · sin publicar" })).toBeDisabled();
    // One arrow key on a closed select is a change event: it must not move a live number.
    await userEvent.selectOptions(select, SALES);
    expect(agentsActions.assignChannelAgentAction).not.toHaveBeenCalled();
    expect(select).toHaveValue(MAIN);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("¿Que conteste Ventas en +34653321693?")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cambiar agente" }));
    await waitFor(() =>
      expect(agentsActions.assignChannelAgentAction).toHaveBeenCalledWith({ ref: "demo", channel: CHANNEL.id, agent: SALES }),
    );
    expect(toast.success).toHaveBeenCalledWith("Desde el próximo mensaje contesta Ventas.");
  });

  it("cancelar deja el número como estaba", async () => {
    card();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Contesta" }), SALES);
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(agentsActions.assignChannelAgentAction).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: "Contesta" })).toHaveValue(MAIN);
  });

  it("una negativa de la API se dice con palabras, dentro del diálogo", async () => {
    agentsActions.assignChannelAgentAction.mockResolvedValue({ ok: false, status: 409, message: "", code: "agent_not_published" });
    card();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Contesta" }), SALES);
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cambiar agente" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Ese agente aún no está publicado. Publícalo antes de darle un número.",
    );
  });

  it("un número solo de avisos no tiene agente, y quien solo mira lee el nombre", () => {
    const { unmount } = card({ channel: { agent_enabled: false } });
    expect(screen.queryByText("Contesta")).toBeNull();
    unmount();
    card({ manage: false });
    expect(screen.queryByRole("combobox", { name: "Contesta" })).toBeNull();
    expect(screen.getByText("Agente principal")).toBeInTheDocument();
  });
});
