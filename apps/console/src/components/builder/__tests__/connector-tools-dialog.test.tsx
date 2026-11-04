import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import { t as translate } from "@/i18n/messages";
import type { ConnectorTool, ConnectorTools } from "@/lib/backend/agent-connectors-types";
import type { CapabilityUpdated } from "@/lib/backend/capabilities";

import { TOOLS_FOLD_FROM, hasTools, toolFailure, toolsView } from "../connector-model";
import { AGENT, REF, catalog, connector, fail, ok } from "./connector-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/connector-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/integrations/actions", () => ({}));

const { ConnectorToolsDialog } = await import("../connector-tools-dialog");
const { AgentConnectorsPanel } = await import("../agent-connectors");

/**
 * «Herramientas» de un conector: dos grupos, lo recomendado primero, cada
 * interruptor es una escritura que se ve al momento y vuelve atrás con palabras, y
 * lo que no se puede tocar dice por qué. Sus cinco estados: carga, vacío, error,
 * parcial e ideal.
 */

const translated = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate("es", key, vars);

function tool(over: Partial<ConnectorTool> & { name: string }): ConnectorTool {
  return {
    title: over.name,
    description: "Lo que hace.",
    read_only: true,
    enabled: false,
    enabled_in_active: false,
    locked: false,
    locked_by: null,
    needs_write_permission: false,
    suggested: false,
    ...over,
  };
}

const FREE = tool({ name: "GCAL_FREE", title: "Ver huecos libres", enabled: true, enabled_in_active: true, suggested: true });
const BOOK = tool({ name: "GCAL_BOOK", title: "Crear una cita", read_only: false, enabled: true, enabled_in_active: true, suggested: true });
const DROP = tool({ name: "GCAL_DROP", title: "Calendar list delete", read_only: false });

function tools(list: ConnectorTool[], permission: ConnectorTools["permission"] = "read_write"): ConnectorTools {
  return { slug: "googlecalendar", name: "Google Calendar", permission, tools: list };
}

const updated = (enabled: boolean) => ok({ capability: { enabled }, draft_created: false, version: 2 } as unknown as CapabilityUpdated);

function dialog(
  data: ConnectorTools | ReturnType<typeof fail> = tools([FREE, BOOK, DROP]),
  over: { save?: (key: string, enabled: boolean) => Promise<unknown>; canWrite?: boolean } = {},
) {
  const load = vi.fn(async () => ("ok" in data ? data : ok(data)));
  const save = vi.fn(over.save ?? (async (_key: string, enabled: boolean) => updated(enabled)));
  const onClose = vi.fn();
  const onChanged = vi.fn();
  const onOpenSettings = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <ConnectorToolsDialog
        connector={connector({ slug: "googlecalendar", name: "Google Calendar" })}
        canWrite={over.canWrite ?? true}
        load={load as never}
        save={save as never}
        onClose={onClose}
        onChanged={onChanged}
        onOpenSettings={onOpenSettings}
      />
    </LocaleProvider>,
  );
  return { ...view, load, save, onClose, onChanged, onOpenSettings };
}

const row = (name: string) => screen.getByText(name).closest("li") as HTMLElement;
const switchOf = (name: string) => screen.getByRole("switch", { name });

beforeEach(() => {
  toast.success.mockClear();
});

describe("Herramientas · los cinco estados", () => {
  it("cargando: el aviso y filas con la forma de lo que llega", async () => {
    let resolve: (v: unknown) => void = () => {};
    const load = vi.fn(() => new Promise((r) => (resolve = r)));
    const view = render(
      <LocaleProvider locale="es">
        <ConnectorToolsDialog connector={connector()} canWrite load={load as never} save={vi.fn() as never} onClose={vi.fn()} onChanged={vi.fn()} onOpenSettings={vi.fn()} />
      </LocaleProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Cargando las herramientas");
    expect(document.querySelector("[data-slot=connector-tools-loading]")).toHaveAttribute("aria-busy", "true");
    resolve(ok(tools([FREE])));
    expect(await screen.findByRole("switch", { name: "Ver huecos libres" })).toBeVisible();
    view.unmount();
  });

  it("ideal: dos grupos, cada fila con qué hace y su interruptor, y dice que va al borrador; pasa axe", async () => {
    dialog();
    await screen.findByRole("switch", { name: "Ver huecos libres" });
    const dialogEl = screen.getByRole("dialog", { name: "Herramientas de Google Calendar" });
    expect(dialogEl).toHaveTextContent("Los cambios van al borrador y se aplican al guardarlo");
    expect(dialogEl).toHaveTextContent("desactualizadas las pruebas");
    expect(within(dialogEl).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Consulta1", "Cambia2"]);
    expect(within(row("Ver huecos libres")).getByText("Recomendada")).toBeVisible();
    expect(within(row("Ver huecos libres")).getByText(/Solo consulta datos/)).toBeVisible();
    expect(within(row("Calendar list delete")).getByText(/Puede cambiar datos/)).toBeVisible();
    expect(within(row("Ver huecos libres")).getByText("Lo que hace.")).toBeVisible();
    expect(switchOf("Ver huecos libres")).toBeChecked();
    expect(switchOf("Calendar list delete")).not.toBeChecked();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(await axeViolations(dialogEl)).toEqual([]);
  });

  it("vacío: lo dice, sin grupos ni buscador", async () => {
    dialog(tools([]));
    expect(await screen.findByText(/todavía no trae herramientas/)).toBeVisible();
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
  });

  it("error: lo dice con un reintento que vuelve a leer", async () => {
    const user = userEvent.setup();
    const { load } = dialog(fail(500));
    expect(await screen.findByText(/No se pudieron cargar las herramientas/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });

  it("error de rol: no le echa la culpa a la conexión", async () => {
    dialog(fail(403));
    expect(await screen.findByText("Tu rol no permite esta acción.")).toBeVisible();
  });

  it("parcial: con muchas se ve lo recomendado, lo encendido y lo que no se apaga, y «Ver todas» lleva al resto", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 50 }, (_, i) => tool({ name: `T_${i}`, title: `Herramienta ${i}`, read_only: i % 2 === 0 }));
    const on = tool({ name: "ON", title: "Encendida a mano", enabled: true, enabled_in_active: true });
    dialog(tools([FREE, BOOK, on, ...many]));
    await screen.findByRole("switch", { name: "Ver huecos libres" });
    expect(screen.getAllByRole("switch")).toHaveLength(3);
    expect(screen.getByRole("status")).toHaveTextContent("Se ven 3 de 53.");
    const more = screen.getByRole("button", { name: "Ver todas (53)" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await user.click(more);
    expect(screen.getAllByRole("switch")).toHaveLength(53);
    expect(screen.getByRole("button", { name: "Ver menos" })).toHaveAttribute("aria-expanded", "true");
    // No hay encendido en bloque (owner, 2026-09-28).
    expect(screen.queryByRole("button", { name: /todas.*encender|encender todas|activar todas/i })).not.toBeInTheDocument();
  });

  it("parcial sin nada recomendado: las primeras, no una pantalla vacía", async () => {
    const many = Array.from({ length: 40 }, (_, i) => tool({ name: `T_${i}`, title: `Herramienta ${i}` }));
    dialog(tools(many));
    await screen.findByRole("switch", { name: "Herramienta 0" });
    expect(screen.getAllByRole("switch")).toHaveLength(TOOLS_FOLD_FROM);
  });

  it("parcial de búsqueda: busca en todas y, sin nada, lo dice y deja quitarla", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 30 }, (_, i) => tool({ name: `T_${i}`, title: `Herramienta ${i}` }));
    dialog(tools([FREE, ...many]));
    const search = await screen.findByRole("searchbox", { name: "Buscar herramienta" });
    await user.type(search, "Herramienta 29");
    expect(screen.getAllByRole("switch")).toHaveLength(1);
    expect(switchOf("Herramienta 29")).toBeVisible();
    expect(search).toHaveFocus();
    await user.clear(search);
    await user.type(search, "nada de nada");
    expect(screen.getByText("Ninguna herramienta coincide con «nada de nada».")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Quitar la búsqueda" }));
    expect(switchOf("Ver huecos libres")).toBeVisible();
  });
});

describe("Herramientas · encender y apagar", () => {
  it("se ve al momento, sale una llamada por herramienta y al cerrar la pantalla relee el borrador", async () => {
    const user = userEvent.setup();
    let finish: (v: unknown) => void = () => {};
    const { save, onClose, onChanged, load } = dialog(undefined, { save: () => new Promise((r) => (finish = r)) });
    const sw = await screen.findByRole("switch", { name: "Calendar list delete" });
    await user.click(sw);
    expect(sw).toBeChecked();
    expect(save).toHaveBeenCalledWith("GCAL_DROP", true);
    expect(save).toHaveBeenCalledTimes(1);
    finish(updated(true));
    // Apagar una puede dejar a otra como la última: se vuelve a leer.
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(onChanged).not.toHaveBeenCalled();
    await user.click(screen.getAllByRole("button", { name: "Cerrar" }).at(-1)!);
    expect(onClose).toHaveBeenCalled();
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it("cerrar sin haber cambiado nada no relee el borrador", async () => {
    const user = userEvent.setup();
    const { onClose, onChanged } = dialog();
    await screen.findByRole("switch", { name: "Ver huecos libres" });
    const footer = screen.getAllByRole("button", { name: "Cerrar" }).at(-1)!;
    await user.click(footer);
    expect(onClose).toHaveBeenCalled();
    await new Promise((r) => setTimeout(r, 0));
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("si la API no lo acepta vuelve atrás y lo dice con palabras, en su fila", async () => {
    const user = userEvent.setup();
    const { onChanged } = dialog(undefined, {
      save: async () => fail(422, "spec_invalid", { problems: [{ code: "end_customer_argument", pointer: "/tools/0", message: "x" }] }),
    });
    const sw = await screen.findByRole("switch", { name: "Calendar list delete" });
    await user.click(sw);
    const alert = await within(row("Calendar list delete")).findByRole("alert");
    expect(alert).toHaveTextContent("deja elegir a qué cliente consultar");
    expect(sw).not.toBeChecked();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("si la llamada ni llega, también vuelve atrás", async () => {
    const user = userEvent.setup();
    dialog(undefined, { save: () => Promise.reject(new Error("network")) });
    const sw = await screen.findByRole("switch", { name: "Ver huecos libres" });
    await user.click(sw);
    expect(await within(row("Ver huecos libres")).findByRole("alert")).toHaveTextContent("No se pudo cambiar");
    expect(sw).toBeChecked();
  });

  it("la respuesta manda: si la API lo deja apagado, se queda apagado y se dice", async () => {
    const user = userEvent.setup();
    dialog(undefined, { save: async () => updated(false) });
    const sw = await screen.findByRole("switch", { name: "Calendar list delete" });
    await user.click(sw);
    expect(await within(row("Calendar list delete")).findByRole("alert")).toHaveTextContent("sigue apagada");
    expect(sw).not.toBeChecked();
  });

  it("dos seguidas salen una detrás de otra, en el orden en que se pulsaron", async () => {
    const user = userEvent.setup();
    const order: string[] = [];
    let release: () => void = () => {};
    const { save } = dialog(undefined, {
      save: async (key, enabled) => {
        order.push(key);
        if (key === "GCAL_DROP") await new Promise<void>((r) => (release = r));
        return updated(enabled);
      },
    });
    await user.click(await screen.findByRole("switch", { name: "Calendar list delete" }));
    await user.click(switchOf("Crear una cita"));
    expect(save).toHaveBeenCalledTimes(1);
    release();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(order).toEqual(["GCAL_DROP", "GCAL_BOOK"]);
  });

  it("lo que no se puede apagar lo dice y no deja tocarlo", async () => {
    const locked = tool({ ...BOOK, locked: true, locked_by: "promise" });
    const { save } = dialog(tools([FREE, locked]));
    const sw = await screen.findByRole("switch", { name: "Crear una cita" });
    expect(sw).toHaveAttribute("aria-disabled", "true");
    expect(within(row("Crear una cita")).getByText(/las instrucciones de este agente prometen/)).toBeVisible();
    expect(save).not.toHaveBeenCalled();
  });

  it("una de escritura con «Solo leer» dice lo que necesita y lleva a Ajustes", async () => {
    const user = userEvent.setup();
    const blocked = tool({ ...BOOK, needs_write_permission: true });
    const off = tool({ ...DROP, needs_write_permission: true });
    const { onOpenSettings, onClose } = dialog(tools([FREE, blocked, off], "read"));
    await screen.findByRole("switch", { name: "Crear una cita" });
    expect(screen.getByText(/Este agente tiene el permiso «Solo leer»/)).toBeVisible();
    expect(within(row("Crear una cita")).getByText(/Necesita el permiso «Leer y escribir»/)).toBeVisible();
    expect(within(row("Calendar list delete")).getByText(/Necesita el permiso «Leer y escribir»/)).toBeVisible();
    expect(within(row("Calendar list delete")).queryByRole("button")).not.toBeInTheDocument();
    await user.click(within(row("Crear una cita")).getByRole("button", { name: "Cambiar en Ajustes" }));
    expect(onOpenSettings).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("quien solo puede leer ve el estado con palabras, sin interruptores", async () => {
    const blocked = tool({ ...BOOK, needs_write_permission: true });
    dialog(tools([FREE, blocked, DROP], "read"), { canWrite: false });
    expect(await screen.findByText(/Tu rol puede ver estas herramientas/)).toBeVisible();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(within(row("Ver huecos libres")).getByText("Encendida")).toBeVisible();
    expect(within(row("Calendar list delete")).getByText("Apagada")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Cambiar en Ajustes" })).not.toBeInTheDocument();
  });

  it("un nombre largo no rompe la fila", async () => {
    const long = "Donaudampfschifffahrtsgesellschaftskapitänsmützenherstellungsbetrieb";
    dialog(tools([tool({ name: "LONG", title: long, description: long.repeat(8) })]));
    await screen.findByRole("switch", { name: long });
    expect(screen.getByText(long).className).toMatch(/min-w-0/);
    expect(screen.getByText(long).className).toMatch(/break-words/);
    expect(row(long).querySelector("div")?.className).toMatch(/min-w-0/);
  });
});

describe("Herramientas · lo que decide sin pintar", () => {
  it("una fila no desaparece bajo el dedo de quien la acaba de apagar", () => {
    const many = Array.from({ length: 30 }, (_, i) => tool({ name: `T_${i}` }));
    const list = [tool({ name: "ON", enabled: false }), ...many];
    const view = toolsView(list, { q: "", all: false, pinned: new Set(["ON"]) });
    expect(view.read.map((t) => t.name)).toEqual(["ON"]);
    expect(view.foldable).toBe(true);
  });

  it("lo que está encendido siempre se ve, aunque se encendiera después de abrir", () => {
    const many = Array.from({ length: 30 }, (_, i) => tool({ name: `T_${i}` }));
    const view = toolsView([tool({ name: "LATER", enabled: true }), ...many], { q: "", all: false, pinned: new Set() });
    expect(view.read.map((t) => t.name)).toEqual(["LATER"]);
  });

  it("con pocas no hay nada que plegar, y buscar no pliega", () => {
    const few = [FREE, BOOK, DROP];
    expect(toolsView(few, { q: "", all: false, pinned: new Set() })).toMatchObject({ shown: 3, foldable: false });
    const many = Array.from({ length: 30 }, (_, i) => tool({ name: `T_${i}`, title: `Uno ${i}` }));
    expect(toolsView(many, { q: "uno 1", all: false, pinned: new Set() })).toMatchObject({ foldable: false, shown: 11 });
  });

  it("cada código de la API tiene su frase", () => {
    expect(toolFailure(translated, { status: 403 })).toBe("Tu rol no permite esta acción.");
    expect(toolFailure(translated, { status: 422, code: "tool_in_use", info: { locked_by: "task" } })).toMatch(/una tarea de este agente/);
    expect(toolFailure(translated, { status: 422, code: "tool_in_use", info: { locked_by: "test" } })).toMatch(/una prueba de este agente/);
    expect(toolFailure(translated, { status: 422, code: "too_many_tools", info: { max: 60 } })).toMatch(/ya lleva 60 herramientas/);
    expect(toolFailure(translated, { status: 404, code: null })).toMatch(/ya no está disponible/);
    expect(toolFailure(translated, { status: 422, code: "spec_invalid", info: { problems: [{ code: "tool_not_allowed" }] } })).toMatch(/ya no está disponible/);
    expect(toolFailure(translated, { status: 422, code: "spec_invalid", info: { problems: [] } })).toMatch(/sin poder funcionar/);
    expect(toolFailure(translated, { status: 500 })).toMatch(/se queda como estaba/);
  });
});

describe("Herramientas · la fila del conector", () => {
  function panel({ canWrite = true } = {}) {
    const actions = {
      tools: vi.fn(async () => ok(tools([FREE, BOOK]))),
      setTool: vi.fn(async ({ enabled }: { enabled: boolean }) => updated(enabled)),
    };
    const onConnected = vi.fn();
    render(
      <LocaleProvider locale="es">
        <AgentConnectorsPanel refId={REF} agentId={AGENT} connectors={catalog()} canWrite={canWrite} onConnected={onConnected} actions={actions as never} />
      </LocaleProvider>,
    );
    return { actions, onConnected };
  }

  it("solo en lo que este agente usa, también para quien solo lee", () => {
    panel({ canWrite: false });
    expect(screen.getByRole("button", { name: "Herramientas de WooCommerce" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Herramientas de Google Calendar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Herramientas de HubSpot" })).not.toBeInTheDocument();
    expect(catalog().filter(hasTools).map((c) => c.slug)).toEqual(["woocommerce"]);
  });

  it("abre el diálogo de ese conector, cambia en el agente de la ruta y avisa a la pantalla al cerrar", async () => {
    const user = userEvent.setup();
    const { actions, onConnected } = panel();
    await user.click(screen.getByRole("button", { name: "Herramientas de WooCommerce" }));
    expect(actions.tools).toHaveBeenCalledWith({ ref: REF, agent: AGENT, slug: "woocommerce", lang: "es" });
    await user.click(await screen.findByRole("switch", { name: "Ver huecos libres" }));
    await waitFor(() => expect(actions.setTool).toHaveBeenCalledWith({ ref: REF, agent: AGENT, key: "GCAL_FREE", enabled: false }));
    await waitFor(() => expect(actions.tools).toHaveBeenCalledTimes(2));
    await user.click(screen.getAllByRole("button", { name: "Cerrar" }).at(-1)!);
    await waitFor(() => expect(onConnected).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("«Cambiar en Ajustes» cierra este diálogo y abre los ajustes del conector", async () => {
    const user = userEvent.setup();
    const actions = {
      tools: vi.fn(async () => ok(tools([tool({ ...BOOK, needs_write_permission: true })], "read"))),
      setTool: vi.fn(),
    };
    render(
      <LocaleProvider locale="es">
        <AgentConnectorsPanel refId={REF} agentId={AGENT} connectors={catalog()} canWrite actions={actions as never} />
      </LocaleProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Herramientas de WooCommerce" }));
    await user.click(await within(await screen.findByRole("dialog")).findAllByRole("button", { name: "Cambiar en Ajustes" }).then((b) => b[0]!));
    expect(await screen.findByRole("dialog", { name: /Ajustes de WooCommerce/ })).toBeVisible();
  });
});
