import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentConnector } from "@/lib/backend/agent-connectors-types";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";
import type { AgentSpec } from "@/lib/backend/builder-types";

import { AGENT, CONN_COBRO, CONN_GCAL, CONN_WOO, REF, catalog, connector, fail, ok } from "./connector-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/connector-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/integrations/actions", () => ({}));

const { AgentConnectorsPanel } = await import("../agent-connectors");
type Actions = NonNullable<React.ComponentProps<typeof AgentConnectorsPanel>["actions"]>;

/**
 * Spec 047 (historia 21; T129; requisitos 35.2, 35.3, 35.5 y 35.7) — la
 * sección Conectores de un agente, como el prototipo aprobado (`agente.md` §9,
 * hueco H10; requisitos 62.5 y 63.3): una sola tarjeta con filas, el buscador
 * sin etiqueta visible, el filtro segmentado con recuentos, lo que piden las
 * habilidades primero; «Conectar» con el permiso (activa sin pedir de nuevo,
 * abre la autorización o pide la clave); «Conectado» con «Ajustes» (el
 * permiso y los ajustes del catálogo) y «Quitar» con confirmación; y sus
 * estados de carga, error y vacío.
 */

const SPEC = { skills: [{ key: "pedidos.consultar", enabled: true, integration: "woocommerce" }] } as unknown as AgentSpec;

/** `"lazy"`: sin datos del servidor, la sección los lee al montar. */
function panel(data: AgentConnector[] | null | "lazy" = catalog(), over: Partial<Actions> = {}, { canWrite = true } = {}) {
  const actions: Actions = {
    load: vi.fn(async () => ok(catalog())),
    connect: vi.fn(async () => ok({ status: "activated" as const, connection_id: CONN_COBRO })),
    activate: vi.fn(async ({ permission, settings }) => ok({ permission, settings })),
    remove: vi.fn(async () => ok({ skills: ["pedidos.consultar"], procedures: ["Ver un pedido"] })),
    reconnect: vi.fn(async () => ok({ slug: "hubspot", signed_consent_url: "https://auth.example/hubspot", expires_at: "2026-10-28T12:00:00Z" })),
    saveKey: vi.fn(async () => ok({ last_sync: { status: "ok", added: 3, deprecated: 0, reason: null, at: "2026-10-28T10:00:00Z" } } as unknown as ConnectorOut)),
    open: vi.fn(),
    ...over,
  };
  const view = render(
    <LocaleProvider locale="es">
      <AgentConnectorsPanel refId={REF} agentId={AGENT} connectors={data === "lazy" ? undefined : data} canWrite={canWrite} spec={SPEC} actions={actions} />
    </LocaleProvider>,
  );
  return { ...view, actions };
}

const row = (name: string) => screen.getAllByRole("listitem").find((li) => within(li).queryByRole("heading", { name })) as HTMLElement;
const names = () =>
  within(screen.getByRole("list", { name: "Conectores para este agente" }))
    .getAllByRole("heading", { level: 3 })
    .map((h) => h.textContent);

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("la sección Conectores · leer (H10)", () => {
  it("una sola tarjeta con filas: logo, nombre con su categoría, la nota y su acción; el permiso no está a la vista; pasa axe", async () => {
    const { container } = panel();
    const list = screen.getByRole("list", { name: "Conectores para este agente" });
    expect(list.className).toMatch(/divide-y/);
    expect(container.querySelectorAll("[data-slot=agent-connector-list]")).toHaveLength(1);
    expect(names()).toEqual(["WooCommerce", "Google Calendar", "Amigable Cobro", "HubSpot"]);
    // Conectado: la insignia, «Ajustes» y «Quitar».
    expect(within(row("WooCommerce")).getByText("Tienda")).toBeVisible();
    expect(within(row("WooCommerce")).getByText("Conectado")).toBeVisible();
    expect(within(row("WooCommerce")).getByText(/lo necesita una habilidad de este agente/)).toBeVisible();
    expect(within(row("WooCommerce")).getByRole("button", { name: "Ajustes de WooCommerce" })).toBeVisible();
    expect(within(row("WooCommerce")).getByRole("button", { name: "Quitar WooCommerce" })).toBeVisible();
    // Sin conectar: la nota dice que lo pide una habilidad y cómo se autoriza; «Conectar» es el principal.
    const gcal = row("Google Calendar");
    expect(within(gcal).getByText("Calendario")).toBeVisible();
    expect(within(gcal).getByText(/lo necesita una habilidad de este agente · Se autoriza con la cuenta del servicio/)).toBeVisible();
    expect(within(gcal).getByRole("button", { name: "Conectar Google Calendar" }).className).toMatch(/(^|\s)bg-primary(\s|$)/);
    // Conectado al cliente y sin usar aquí: lo dice, y «Conectar» lo activa.
    expect(within(row("Amigable Cobro")).getByText(/Conectado, sin usar en este agente/)).toBeVisible();
    expect(within(row("Amigable Cobro")).getByRole("button", { name: "Conectar Amigable Cobro" }).className).not.toMatch(/(^|\s)bg-primary(\s|$)/);
    // Rota: lo dice, con «Reconectar» y su página.
    expect(within(row("HubSpot")).getByText("Hay que volver a autorizar")).toBeVisible();
    expect(within(row("HubSpot")).getByRole("button", { name: "Reconectar HubSpot" })).toBeVisible();
    expect(within(row("HubSpot")).getByRole("link", { name: "Ver su página de HubSpot" })).toHaveAttribute("href", `/clients/${REF}/integrations/${CONN_GCAL}?agent=${AGENT}`);
    // 63.3: el permiso se ajusta dentro de «Ajustes», no en la fila.
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("lo que piden las habilidades va primero, y después lo conectado, aunque la API lo mande en otro orden (62.5)", () => {
    const [woo, gcal, cobro, hubspot] = catalog();
    panel([hubspot!, cobro!, woo!, gcal!]);
    expect(names()).toEqual(["WooCommerce", "Google Calendar", "HubSpot", "Amigable Cobro"]);
  });

  it("el buscador no lleva etiqueta a la vista pero sí nombre; el filtro segmentado cuenta Todos, Conectados y cada categoría", async () => {
    const user = userEvent.setup();
    panel();
    expect(screen.queryByText("Buscar un conector")).not.toBeInTheDocument();
    const search = screen.getByRole("searchbox", { name: "Buscar conector" });
    const filter = screen.getByRole("group", { name: "Categoría" });
    expect(within(filter).getAllByRole("button").map((b) => b.textContent)).toEqual(["Todos 4", "Conectados 1", "Tienda 1", "Calendario 1", "Cobros 1", "Clientes 1"]);
    expect(within(filter).getByRole("button", { name: "Todos 4" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(filter).getByRole("button", { name: "Conectados 1" }));
    expect(within(filter).getByRole("button", { name: "Conectados 1" })).toHaveAttribute("aria-pressed", "true");
    expect(names()).toEqual(["WooCommerce"]);
    await user.click(within(filter).getByRole("button", { name: "Cobros 1" }));
    expect(names()).toEqual(["Amigable Cobro"]);
    await user.click(within(filter).getByRole("button", { name: "Todos 4" }));
    await user.type(search, "cal");
    expect(names()).toEqual(["Google Calendar"]);
    expect(search).toHaveFocus();
    await user.clear(search);
    await user.type(search, "nada");
    expect(screen.getByText("Ningún conector coincide con «nada».")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Quitar los filtros" }));
    expect(names()).toHaveLength(4);
  });

  it("quien solo lee ve el permiso como texto y solo el camino a cada página", () => {
    panel(catalog(), {}, { canWrite: false });
    expect(screen.getByText("Tu rol puede ver los conectores, no cambiarlos.")).toBeVisible();
    expect(within(row("WooCommerce")).getByText(/Solo leer/)).toBeVisible();
    expect(within(row("WooCommerce")).getByRole("link", { name: "Ver su página de WooCommerce" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Conectar|Ajustes|Quitar|Reconectar/ })).not.toBeInTheDocument();
  });
});

describe("la sección Conectores · los estados", () => {
  it("sin datos del servidor, carga al montar y lo dice mientras tanto", async () => {
    let resolve: (v: ReturnType<typeof ok<AgentConnector[]>>) => void = () => {};
    const load = vi.fn(() => new Promise<ReturnType<typeof ok<AgentConnector[]>>>((r) => (resolve = r)));
    panel("lazy", { load });
    expect(screen.getByText("Cargando los conectores…")).toBeVisible();
    expect(load).toHaveBeenCalledWith({ ref: REF, agent: AGENT });
    resolve(ok(catalog()));
    expect(await screen.findByRole("list", { name: "Conectores para este agente" })).toBeVisible();
  });

  it("si no se pudo leer lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    const load = vi.fn(async () => fail(503));
    panel(null, { load });
    expect(screen.getByText("No se pudieron cargar los conectores de este agente. Lo que ya usa sigue funcionando.")).toBeVisible();
    load.mockResolvedValueOnce(ok(catalog()) as never);
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("list", { name: "Conectores para este agente" })).toBeVisible();
  });

  it("un catálogo vacío", () => {
    panel([]);
    expect(screen.getByText("Todavía no hay conectores disponibles para este cliente.")).toBeVisible();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
  });
});

describe("la sección Conectores · conectar (35.3, 35.4)", () => {
  it("ya autorizado para el cliente: se activa con el permiso elegido, sin pedir nada más", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(screen.getByRole("button", { name: "Conectar Google Calendar" }));
    const dialog = await screen.findByRole("dialog", { name: "Conectar Google Calendar" });
    await user.click(within(dialog).getByRole("radio", { name: /Preguntar antes de escribir/ }));
    await user.click(within(dialog).getByRole("button", { name: "Conectar" }));
    await waitFor(() => expect(actions.connect).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "googlecalendar", permission: "ask_before_write" }));
    expect(toast.success).toHaveBeenCalledWith("Google Calendar conectado y activado en este agente.");
    await waitFor(() => expect(actions.load).toHaveBeenCalled());
  });

  it("conectado al cliente y sin usar aquí: «Conectar» lo activa en este agente con su permiso", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(screen.getByRole("button", { name: "Conectar Amigable Cobro" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Conectar Amigable Cobro" })).getByRole("button", { name: "Conectar" }));
    await waitFor(() => expect(actions.connect).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "amigable_cobro", permission: "read" }));
  });

  it("OAuth: abre la autorización, deja el enlace por si se bloqueó y vuelve a leer al terminar", async () => {
    const user = userEvent.setup();
    const connect = vi.fn(async () => ok({ slug: "googlecalendar", signed_consent_url: "https://auth.example/gcal", expires_at: "2026-10-28T12:00:00Z" }));
    const { actions } = panel(catalog(), { connect });
    await user.click(screen.getByRole("button", { name: "Conectar Google Calendar" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Conectar" }));
    await waitFor(() => expect(actions.open).toHaveBeenCalledWith("https://auth.example/gcal"));
    expect(screen.getByText(/Se abrió la autorización de Google Calendar/)).toBeVisible();
    expect(screen.getByRole("link", { name: /Si no se abrió, ábrela aquí/ })).toHaveAttribute("href", "https://auth.example/gcal");
    await user.click(screen.getByRole("button", { name: "Ya la terminé" }));
    await waitFor(() => expect(actions.load).toHaveBeenCalled());
  });

  it("con clave: la pide, la guarda y después activa con el permiso elegido", async () => {
    const user = userEvent.setup();
    const connect = vi.fn(async () =>
      fail(409, "authorize_with_form", { auth_kind: "api_key", form: [{ field: "token", label: "Token", secret: true, required: true }] }),
    );
    const list = [connector({ slug: "amigable_venta", name: "Amigable Venta", category: "catalog" })];
    const { actions } = panel(list, { connect });
    await user.click(screen.getByRole("button", { name: "Conectar Amigable Venta" }));
    let dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: /Leer y escribir/ }));
    await user.click(within(dialog).getByRole("button", { name: "Conectar" }));
    dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/se conecta con una clave/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Guardar y conectar" }));
    expect(within(dialog).getByText("Campo obligatorio.")).toBeVisible();
    await user.type(within(dialog).getByLabelText(/Clave de la API/), "secreto");
    await user.click(within(dialog).getByRole("button", { name: "Guardar y conectar" }));
    await waitFor(() =>
      expect(actions.saveKey).toHaveBeenCalledWith({ ref: REF, slug: "amigable_venta", secrets: { token: "secreto" }, endpoint_meta: {} }),
    );
    await waitFor(() => expect(actions.activate).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "amigable_venta", permission: "read_write", settings: {} }));
    expect(toast.success).toHaveBeenCalledWith("Amigable Venta conectado y activado en este agente.");
  });

  it("una clave que el proveedor rechaza no activa nada", async () => {
    const user = userEvent.setup();
    const connect = vi.fn(async () => fail(409, "authorize_with_form", { form: [{ field: "token", secret: true }] }));
    const saveKey = vi.fn(async () => ok({ last_sync: { status: "error", reason: "auth_rejected" } } as unknown as ConnectorOut));
    const { actions } = panel([connector({ slug: "amigable_venta", name: "Amigable Venta" })], { connect, saveKey });
    await user.click(screen.getByRole("button", { name: "Conectar Amigable Venta" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Conectar" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Clave de la API/), "mala");
    await user.click(within(dialog).getByRole("button", { name: "Guardar y conectar" }));
    expect(await within(dialog).findByText("Amigable Venta rechazó la clave. Revísala y vuelve a intentarlo.")).toBeVisible();
    expect(actions.activate).not.toHaveBeenCalled();
  });

  it("sin formulario en el catálogo, lleva a los Conectores del cliente", async () => {
    const user = userEvent.setup();
    const connect = vi.fn(async () => fail(409, "authorize_with_form", { auth_kind: "browser_credentials", form: null }));
    panel([connector({ slug: "mi_agenda", name: "Mi Agenda", auth_kind: "browser_credentials" })], { connect });
    await user.click(screen.getByRole("button", { name: "Conectar Mi Agenda" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Conectar" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Mi Agenda se conecta desde los Conectores del cliente/)).toBeVisible();
    expect(within(dialog).getByText("Ir a los Conectores del cliente").closest("a")).toHaveAttribute("href", `/clients/${REF}/integrations`);
  });

  it("una conexión rota se reconecta y conserva las activaciones", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(screen.getByRole("button", { name: "Reconectar HubSpot" }));
    await waitFor(() => expect(actions.reconnect).toHaveBeenCalledWith({ ref: REF, connection: expect.any(String) }));
    expect(actions.open).toHaveBeenCalledWith("https://auth.example/hubspot");
    expect(screen.getByText(/Se abrió la autorización de HubSpot/)).toBeVisible();
  });
});

describe("la sección Conectores · «Ajustes» y «Quitar» (35.5, 35.7; 63.3)", () => {
  it("el permiso se cambia dentro de «Ajustes» y se guarda con sus ajustes", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(screen.getByRole("button", { name: "Ajustes de WooCommerce" }));
    const dialog = await screen.findByRole("dialog", { name: "Ajustes de WooCommerce en este agente" });
    const group = within(dialog).getByRole("radiogroup", { name: "Permiso en este agente" });
    expect(within(group).getByRole("radio", { name: /Solo leer/ })).toBeChecked();
    expect(within(dialog).getByRole("link", { name: "Ver su página de WooCommerce" })).toHaveAttribute("href", `/clients/${REF}/integrations/${CONN_WOO}?agent=${AGENT}`);
    await user.click(within(group).getByRole("radio", { name: /Leer y escribir/ }));
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(actions.activate).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "woocommerce", permission: "read_write", settings: { store_url: "https://tienda.example" } }),
    );
    expect(toast.success).toHaveBeenCalledWith("WooCommerce: Leer y escribir.");
  });

  it("«Quitar» pide confirmación con las habilidades que lo piden, y al quitarlo dice lo que pierde", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(screen.getByRole("button", { name: "Quitar WooCommerce" }));
    const dialog = await screen.findByRole("dialog", { name: "Quitar WooCommerce de este agente" });
    expect(within(dialog).getByText("Se quedan sin él estas habilidades: Pedidos consultar.")).toBeVisible();
    expect(actions.remove).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Quitar de este agente" }));
    await waitFor(() => expect(actions.remove).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "woocommerce" }));
    expect(toast.success).toHaveBeenCalledWith("Este agente ya no usa WooCommerce. Se quedan sin él: Pedidos consultar, Ver un pedido.");
    expect(within(row("WooCommerce")).getByRole("button", { name: "Conectar WooCommerce" })).toBeVisible();
  });

  it("un error de la API se dice en la fila", async () => {
    const user = userEvent.setup();
    panel(catalog(), { remove: vi.fn(async () => fail(409, "connection_not_authorized")) });
    await user.click(screen.getByRole("button", { name: "Quitar WooCommerce" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Quitar de este agente" }));
    expect(await within(row("WooCommerce")).findByRole("alert")).toHaveTextContent("La conexión no está autorizada. Vuelve a conectarla.");
  });

  it("los ajustes del catálogo se editan, se validan y lo que la API marca vuelve a su campo", async () => {
    const user = userEvent.setup();
    const activate = vi.fn().mockResolvedValueOnce(fail(422, "invalid_settings", { errors: [{ field: "store_url", message: "bad" }] }));
    activate.mockImplementation(async ({ permission, settings }) => ok({ permission, settings }));
    const { actions } = panel(catalog(), { activate });
    await user.click(screen.getByRole("button", { name: "Ajustes de WooCommerce" }));
    const dialog = await screen.findByRole("dialog", { name: "Ajustes de WooCommerce en este agente" });
    const field = within(dialog).getByRole("textbox", { name: "Dirección de la tienda" });
    expect(field).toHaveValue("https://tienda.example");
    await user.clear(field);
    await user.type(field, "http://tienda");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(within(dialog).getByText("Tiene que empezar por https://")).toBeVisible();
    expect(actions.activate).not.toHaveBeenCalled();
    await user.clear(field);
    await user.type(field, "https://otra.example");
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(await within(dialog).findByText("Revisa los ajustes marcados.")).toBeVisible();
    expect(within(dialog).getByText("Revisa este valor.")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(actions.activate).toHaveBeenLastCalledWith({ ref: REF, agent: AGENT, slug: "woocommerce", permission: "read", settings: { store_url: "https://otra.example" } }),
    );
    expect(toast.success).toHaveBeenCalledWith("Ajustes de WooCommerce guardados.");
  });
});

it("el catálogo de este agente también existe con conexión de otro estado: pendiente se vuelve a autorizar", () => {
  const list = [connector({ slug: "googlecalendar", name: "Google Calendar", auth_kind: "oauth_composio", connection: { id: CONN_COBRO, status: "pending", last_checked_at: null } })];
  panel(list);
  expect(screen.getByText("Pendiente de consentimiento")).toBeVisible();
  expect(screen.getByRole("button", { name: "Conectar Google Calendar" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Ver su página de Google Calendar" })).toBeVisible();
});
