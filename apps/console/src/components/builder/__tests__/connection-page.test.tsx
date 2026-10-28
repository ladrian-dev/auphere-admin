import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ConnectionPage } from "@/lib/backend/agent-connectors-types";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";

import { AGENT, CONN_WOO, OTHER_AGENT, REF, connectionPage, fail, ok } from "./connector-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/app/(console)/clients/[ref]/agents/connector-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/integrations/actions", () => ({}));

const { ConnectionPageView } = await import("../connection-page");
type Actions = NonNullable<React.ComponentProps<typeof ConnectionPageView>["actions"]>;

/**
 * Spec 047 (historia 21; T129; requisitos 36.1, 36.3 y 36.4) — la página de
 * cada conector: la cuenta, el estado con la última comprobación, los agentes
 * con su permiso y sus ajustes, «Reconectar» (OAuth o clave) y «Desconectar
 * para todos», que primero dice a quién afecta.
 */

const KEY_CONNECTOR = {
  slug: "woocommerce",
  auth_kind: "api_key",
  credentials_form: [
    { field: "store_url", secret: false, required: true },
    { field: "consumer_key", secret: true, required: true },
  ],
} as unknown as ConnectorOut;

function view(page: ConnectionPage = connectionPage(), over: Partial<Actions> = {}, { canWrite = true, fromAgent = AGENT as string | null, connector = null as ConnectorOut | null } = {}) {
  const actions: Actions = {
    reload: vi.fn(async () => ok(connectionPage())),
    activate: vi.fn(async ({ permission, settings }) => ok({ permission, settings })),
    remove: vi.fn(async () => ok({ skills: [], procedures: [] })),
    reconnect: vi.fn(async () => ok({ slug: "woocommerce", signed_consent_url: "https://auth.example/woo", expires_at: "2026-10-28T12:00:00Z" })),
    disconnect: vi.fn(async ({ confirm }) =>
      confirm
        ? ok({ status: "disconnected" as const, affected: [] })
        : fail(409, "confirm_required", {
            affected: [
              { agent_id: AGENT, name: "Recepción", skills: ["pedidos.consultar"], procedures: [] },
              { agent_id: OTHER_AGENT, name: "Ventas", skills: [], procedures: [] },
            ],
          }),
    ),
    saveKey: vi.fn(async () => ok({ last_sync: null } as unknown as ConnectorOut)),
    open: vi.fn(),
    ...over,
  };
  const out = render(
    <LocaleProvider locale="es">
      <ConnectionPageView refId={REF} page={page} connector={connector} fromAgent={fromAgent} canWrite={canWrite} actions={actions} />
    </LocaleProvider>,
  );
  return { ...out, actions };
}

const agentRow = (name: string) => screen.getAllByRole("listitem").find((li) => within(li).queryByRole("heading", { name })) as HTMLElement;

beforeEach(() => {
  toast.success.mockClear();
  router.push.mockClear();
});

describe("la página de un conector · leer (36.1)", () => {
  it("la cuenta, el estado, la última comprobación y los agentes con su permiso y sus ajustes, y pasa axe", async () => {
    const { container } = view();
    expect(screen.getByRole("heading", { level: 2, name: "WooCommerce" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Volver al agente" })).toHaveAttribute("href", `/clients/${REF}/agents/${AGENT}?tab=integrations`);
    const details = screen.getByRole("region", { name: "La conexión" });
    expect(within(details).getByText("https://tienda.example")).toBeVisible();
    expect(within(details).getByText("Última comprobación")).toBeVisible();
    expect(within(details).queryByText("Aún sin comprobar")).not.toBeInTheDocument();
    expect(within(agentRow("Recepción")).getByRole("combobox", { name: "Permiso de Recepción con WooCommerce" })).toHaveValue("read");
    expect(within(agentRow("Recepción")).getByText("Dirección de la tienda: https://tienda.example")).toBeVisible();
    expect(within(agentRow("Ventas")).getByRole("combobox")).toHaveValue("read_write");
    expect(within(agentRow("Ventas")).getByText("Sin ajustes")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin cuenta, sin comprobar y sin agentes lo dice; desde fuera de un agente vuelve a Conectores", () => {
    view(connectionPage({ account: null, last_checked_at: null, agents: [] }), {}, { fromAgent: null });
    expect(screen.getByText("El servicio no dice qué cuenta es")).toBeVisible();
    expect(screen.getByText("Aún sin comprobar")).toBeVisible();
    expect(screen.getByText("Ningún agente lo usa todavía. Se activa desde la sección Conectores de cada agente.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Volver a los Conectores" })).toHaveAttribute("href", `/clients/${REF}/integrations`);
  });

  it("caducada: «Hay que volver a autorizar», arriba y con su arreglo (36.3)", () => {
    view(connectionPage({ needs_reauth: true, status: "needs_reauth" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Hay que volver a autorizar WooCommerce.");
    expect(screen.getAllByRole("button", { name: "Reconectar" })).toHaveLength(2);
  });

  it("quien solo lee no ve botones ni selectores", () => {
    view(connectionPage(), {}, { canWrite: false });
    expect(screen.getByText("Tu rol puede ver este conector, no cambiarlo.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Desconectar para todos" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(within(agentRow("Recepción")).getByText("Solo leer")).toBeVisible();
    // Dos agentes, una acción cada uno: los dos enlaces a la vista.
    expect(within(agentRow("Recepción")).getByText("Abrir el agente").closest("a")).toHaveAttribute("href", `/clients/${REF}/agents/${AGENT}?tab=integrations`);
  });
});

describe("la página de un conector · cambiar", () => {
  it("el permiso de un agente se cambia en su fila y sus ajustes en su ⋯", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.selectOptions(within(agentRow("Ventas")).getByRole("combobox"), "ask_before_write");
    await waitFor(() => expect(actions.activate).toHaveBeenCalledWith({ ref: REF, agent: OTHER_AGENT, slug: "woocommerce", permission: "ask_before_write", settings: {} }));
    expect(toast.success).toHaveBeenCalledWith("Ventas: Preguntar antes de escribir.");
    await user.click(screen.getByRole("button", { name: "Más acciones de Recepción" }));
    await user.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Ajustes" }));
    const dialog = await screen.findByRole("dialog");
    await user.clear(within(dialog).getByRole("textbox", { name: "Dirección de la tienda" }));
    await user.type(within(dialog).getByRole("textbox", { name: "Dirección de la tienda" }), "https://nueva.example");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(actions.activate).toHaveBeenLastCalledWith({ ref: REF, agent: AGENT, slug: "woocommerce", permission: "read", settings: { store_url: "https://nueva.example" } }),
    );
    expect(await screen.findByText("Dirección de la tienda: https://nueva.example")).toBeVisible();
  });

  it("quitarlo de un agente pide confirmación y lo saca de la lista", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.selectOptions(within(agentRow("Ventas")).getByRole("combobox"), "off");
    const dialog = await screen.findByRole("dialog", { name: "Quitar WooCommerce de Ventas" });
    await user.click(within(dialog).getByRole("button", { name: "Quitar de este agente" }));
    await waitFor(() => expect(actions.remove).toHaveBeenCalledWith({ ref: REF, agent: OTHER_AGENT, slug: "woocommerce" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Ventas" })).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith("Ventas ya no usa WooCommerce.");
  });

  it("«Reconectar» con OAuth abre la autorización y deja el enlace", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(screen.getByRole("button", { name: "Reconectar" }));
    await waitFor(() => expect(actions.reconnect).toHaveBeenCalledWith({ ref: REF, connection: CONN_WOO }));
    expect(actions.open).toHaveBeenCalledWith("https://auth.example/woo");
    expect(screen.getByText("Se abrió la autorización de WooCommerce. Los agentes conservan su permiso.")).toBeVisible();
  });

  it("«Reconectar» con clave pide la del catálogo y vuelve a leer la página", async () => {
    const user = userEvent.setup();
    const { actions } = view(connectionPage(), { reconnect: vi.fn(async () => fail(409, "authorize_with_form", { auth_kind: "api_key" })) }, { connector: KEY_CONNECTOR });
    await user.click(screen.getByRole("button", { name: "Reconectar" }));
    const dialog = await screen.findByRole("dialog", { name: "Conectar WooCommerce" });
    await user.type(within(dialog).getByLabelText(/Dirección de la tienda/), "https://tienda.example");
    await user.type(within(dialog).getByLabelText(/Clave de consumidor/), "ck_1");
    await user.click(within(dialog).getByRole("button", { name: "Guardar y conectar" }));
    await waitFor(() =>
      expect(actions.saveKey).toHaveBeenCalledWith({ ref: REF, slug: "woocommerce", secrets: { consumer_key: "ck_1" }, endpoint_meta: { store_url: "https://tienda.example" } }),
    );
    await waitFor(() => expect(actions.reload).toHaveBeenCalledWith({ ref: REF, connection: CONN_WOO }));
  });

  it("«Desconectar para todos» primero dice a quién afecta, y solo con la confirmación desconecta (36.4)", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(screen.getByRole("button", { name: "Desconectar para todos" }));
    const dialog = await screen.findByRole("dialog", { name: "Desconectar WooCommerce para todos los agentes" });
    expect(actions.disconnect).toHaveBeenCalledWith({ ref: REF, connection: CONN_WOO, confirm: false });
    expect(within(dialog).getByText("Recepción, pierde Pedidos consultar")).toBeVisible();
    expect(within(dialog).getByText("Ventas, ninguna habilidad lo pide")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Desconectar para todos" }));
    await waitFor(() => expect(actions.disconnect).toHaveBeenLastCalledWith({ ref: REF, connection: CONN_WOO, confirm: true }));
    expect(toast.success).toHaveBeenCalledWith("WooCommerce desconectado para todos.");
    expect(router.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${AGENT}?tab=integrations`);
  });
});
