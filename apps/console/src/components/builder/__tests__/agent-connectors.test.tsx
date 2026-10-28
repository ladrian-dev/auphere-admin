import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentConnector } from "@/lib/backend/agent-connectors-types";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";
import type { AgentSpec } from "@/lib/backend/builder-types";

import { AGENT, CONN_COBRO, CONN_WOO, REF, catalog, connector, fail, ok } from "./connector-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/connector-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/integrations/actions", () => ({}));

const { AgentConnectorsPanel } = await import("../agent-connectors");
type Actions = NonNullable<React.ComponentProps<typeof AgentConnectorsPanel>["actions"]>;

/**
 * Spec 047 (historia 21; T129; requisitos 35.2, 35.3, 35.5 y 35.7) — la
 * sección Conectores de un agente: el catálogo con lo que piden las
 * habilidades primero, el buscador y la categoría; «Conectar» con el permiso
 * (activa sin pedir de nuevo, abre la autorización o pide la clave); el permiso
 * en la fila; quitarlo con confirmación y las habilidades afectadas; la regla
 * de los tres puntos; y sus estados de carga, error y vacío.
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

async function openMenu(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole("button", { name: `Más acciones de ${name}` }));
  return screen.findByRole("menu");
}

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("la sección Conectores · leer", () => {
  it("el catálogo en el orden de la API, cada fila con su estado, quién la pide y cómo se autoriza, y pasa axe", async () => {
    const { container } = panel();
    const list = screen.getByRole("list", { name: "Conectores para este agente" });
    const names = within(list)
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(names).toEqual(["WooCommerce", "Google Calendar", "Amigable Cobro", "HubSpot"]);
    expect(within(row("WooCommerce")).getByText("Lo usa este agente")).toBeVisible();
    expect(within(row("WooCommerce")).getByText("Lo pide una habilidad")).toBeVisible();
    expect(within(row("WooCommerce")).getByText("Se conecta con una clave")).toBeVisible();
    expect(within(row("Google Calendar")).getByText("Sin conectar")).toBeVisible();
    expect(within(row("Google Calendar")).getByText("Se autoriza con la cuenta del servicio")).toBeVisible();
    expect(within(row("Amigable Cobro")).getByText("Conectado, sin usar en este agente")).toBeVisible();
    expect(within(row("HubSpot")).getByText("Hay que volver a autorizar")).toBeVisible();
    // El permiso de la fila, con lo que significa.
    expect(within(row("WooCommerce")).getByRole("combobox", { name: "Permiso de WooCommerce en este agente" })).toHaveValue("read");
    expect(within(row("WooCommerce")).getByText("Consulta, nunca cambia nada.")).toBeVisible();
    expect(within(row("Amigable Cobro")).getByRole("combobox", { name: "Permiso de Amigable Cobro en este agente" })).toHaveValue("off");
    expect(screen.getByText("Se ven 4 de 4")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("busca por nombre y filtra por categoría, y sin resultados deja quitar los filtros", async () => {
    const user = userEvent.setup();
    panel();
    await user.type(screen.getByRole("searchbox", { name: "Buscar un conector" }), "cal");
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Google Calendar"]);
    expect(screen.getByText("Se ven 1 de 4")).toBeVisible();
    await user.clear(screen.getByRole("searchbox", { name: "Buscar un conector" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Categoría" }), "Cobros");
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Amigable Cobro"]);
    await user.type(screen.getByRole("searchbox", { name: "Buscar un conector" }), "nada");
    expect(screen.getByText("Ningún conector coincide con la búsqueda.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Quitar los filtros" }));
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(4);
  });

  it("con más de dos acciones en la lista, cada fila las lleva en su ⋯, la principal primero", async () => {
    const user = userEvent.setup();
    panel();
    const menu = await openMenu(user, "WooCommerce");
    const items = within(menu).getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toEqual(["Ver su página", "Ajustes", "Quitar de este agente"]);
    expect(within(menu).getByRole("menuitem", { name: "Ver su página" })).toHaveAttribute("href", `/clients/${REF}/integrations/${CONN_WOO}?agent=${AGENT}`);
  });

  it("con una sola acción, el botón lleva el nombre del conector", () => {
    panel([connector({ slug: "googlecalendar", name: "Google Calendar", auth_kind: "oauth_composio" })]);
    expect(screen.getByRole("button", { name: "Conectar Google Calendar" })).toBeVisible();
    expect(screen.queryByRole("combobox", { name: "Categoría" })).not.toBeInTheDocument();
  });

  it("quien solo lee ve los permisos sin cambiarlos y solo el camino a cada página", async () => {
    const user = userEvent.setup();
    panel(catalog(), {}, { canWrite: false });
    expect(screen.getByText("Tu rol puede ver los conectores, no cambiarlos.")).toBeVisible();
    expect(screen.queryByRole("combobox", { name: /Permiso de/ })).not.toBeInTheDocument();
    expect(within(row("WooCommerce")).getByText("Solo leer")).toBeVisible();
    const menu = await openMenu(user, "WooCommerce");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Ver su página"]);
    expect(screen.queryByRole("button", { name: /Conectar/ })).not.toBeInTheDocument();
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

  it("si no se pudo leer lo dice y deja reintentar, y un catálogo vacío lo dice también", async () => {
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
    const menu = await openMenu(user, "Google Calendar");
    await user.click(within(menu).getByRole("menuitem", { name: "Conectar" }));
    const dialog = await screen.findByRole("dialog", { name: "Conectar Google Calendar" });
    await user.click(within(dialog).getByRole("radio", { name: /Preguntar antes de escribir/ }));
    await user.click(within(dialog).getByRole("button", { name: "Conectar" }));
    await waitFor(() => expect(actions.connect).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "googlecalendar", permission: "ask_before_write" }));
    expect(toast.success).toHaveBeenCalledWith("Google Calendar conectado y activado en este agente.");
    await waitFor(() => expect(actions.load).toHaveBeenCalled());
  });

  it("OAuth: abre la autorización, deja el enlace por si se bloqueó y vuelve a leer al terminar", async () => {
    const user = userEvent.setup();
    const connect = vi.fn(async () => ok({ slug: "googlecalendar", signed_consent_url: "https://auth.example/gcal", expires_at: "2026-10-28T12:00:00Z" }));
    const { actions } = panel(catalog(), { connect });
    await user.click(within(await openMenu(user, "Google Calendar")).getByRole("menuitem", { name: "Conectar" }));
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
    panel([connector({ slug: "agendapro", name: "AgendaPro", auth_kind: "browser_credentials" })], { connect });
    await user.click(screen.getByRole("button", { name: "Conectar AgendaPro" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Conectar" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/AgendaPro se conecta desde los Conectores del cliente/)).toBeVisible();
    expect(within(dialog).getByText("Ir a los Conectores del cliente").closest("a")).toHaveAttribute("href", `/clients/${REF}/integrations`);
  });

  it("una conexión rota se reconecta y conserva las activaciones", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(within(await openMenu(user, "HubSpot")).getByRole("menuitem", { name: "Reconectar" }));
    await waitFor(() => expect(actions.reconnect).toHaveBeenCalledWith({ ref: REF, connection: expect.any(String) }));
    expect(actions.open).toHaveBeenCalledWith("https://auth.example/hubspot");
    expect(screen.getByText(/Se abrió la autorización de HubSpot/)).toBeVisible();
  });
});

describe("la sección Conectores · el permiso y quitarlo (35.5, 35.7)", () => {
  it("cambiar el permiso lo guarda con sus ajustes; activarlo en un conectado sin uso también", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.selectOptions(within(row("WooCommerce")).getByRole("combobox"), "read_write");
    await waitFor(() =>
      expect(actions.activate).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "woocommerce", permission: "read_write", settings: { store_url: "https://tienda.example" } }),
    );
    expect(toast.success).toHaveBeenCalledWith("WooCommerce: Leer y escribir.");
    await user.selectOptions(within(row("Amigable Cobro")).getByRole("combobox"), "read");
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Amigable Cobro activado en este agente con «Solo leer»."));
    expect(within(row("Amigable Cobro")).getByText("Lo usa este agente")).toBeVisible();
  });

  it("un error de la API se dice en la fila", async () => {
    const user = userEvent.setup();
    panel(catalog(), { activate: vi.fn(async () => fail(409, "connection_not_authorized")) });
    await user.selectOptions(within(row("WooCommerce")).getByRole("combobox"), "read_write");
    expect(await within(row("WooCommerce")).findByRole("alert")).toHaveTextContent("La conexión no está autorizada. Vuelve a conectarla.");
  });

  it("«Sin usar» pide confirmación con las habilidades que lo piden, y al quitarlo dice lo que pierde", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.selectOptions(within(row("WooCommerce")).getByRole("combobox"), "off");
    const dialog = await screen.findByRole("dialog", { name: "Quitar WooCommerce de este agente" });
    expect(within(dialog).getByText("Se quedan sin él estas habilidades: Pedidos consultar.")).toBeVisible();
    expect(actions.remove).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Quitar de este agente" }));
    await waitFor(() => expect(actions.remove).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "woocommerce" }));
    expect(toast.success).toHaveBeenCalledWith("Este agente ya no usa WooCommerce. Se quedan sin él: Pedidos consultar, Ver un pedido.");
    expect(within(row("WooCommerce")).getByText("Conectado, sin usar en este agente")).toBeVisible();
  });

  it("los ajustes del catálogo se editan, se validan y lo que la API marca vuelve a su campo", async () => {
    const user = userEvent.setup();
    const activate = vi.fn().mockResolvedValueOnce(fail(422, "invalid_settings", { errors: [{ field: "store_url", message: "bad" }] }));
    activate.mockImplementation(async ({ permission, settings }) => ok({ permission, settings }));
    const { actions } = panel(catalog(), { activate });
    await user.click(within(await openMenu(user, "WooCommerce")).getByRole("menuitem", { name: "Ajustes" }));
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

it("el catálogo de este agente también existe con conexión de otro estado: pendiente se vuelve a autorizar", async () => {
  const user = userEvent.setup();
  const list = [connector({ slug: "googlecalendar", name: "Google Calendar", auth_kind: "oauth_composio", connection: { id: CONN_COBRO, status: "pending", last_checked_at: null } })];
  panel(list);
  expect(screen.getByText("Pendiente de consentimiento")).toBeVisible();
  const menu = await openMenu(user, "Google Calendar");
  expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Conectar", "Ver su página"]);
});
