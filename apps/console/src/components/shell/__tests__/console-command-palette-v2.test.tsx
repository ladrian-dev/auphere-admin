import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { SearchResult } from "@/lib/backend";

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/" }));
// La paleta de hoy (v1) busca con una acción de servidor; la nueva no la usa.
vi.mock("@/app/(console)/notifications/actions", () => ({ searchClientsAction: vi.fn() }));

const { ConsoleCommandPaletteV2 } = await import("../console-command-palette");

/**
 * Spec 047 (R47.2, escenario 2 de la historia 27): ⌘K encuentra, por nombre o
 * por nicho, clientes con sus pestañas, agentes con su cliente, pantallas y
 * solo las acciones que la persona puede hacer. Las flechas mueven la
 * selección, Intro abre y Escape cierra.
 *
 * La respuesta imita a la API (`GET /console/search?q=`, `api/console/search.py`):
 * clientes y agentes solo con texto; pantallas y acciones, todas las permitidas
 * y como claves, y es la consola la que las empareja con lo escrito.
 */
const WORLD: SearchResult = {
  clients: [
    { ref: "flor", name: "Flor y Encanto", niche: "Floristería" },
    { ref: "clinica", name: "Clínica Dental Sonrisa", niche: "Clínica dental" },
  ],
  agents: [
    { agent_id: "a-1", name: "Recepción", client_ref: "flor", client_name: "Flor y Encanto" },
    { agent_id: "a-2", name: "Recepcionista", client_ref: "clinica", client_name: "Clínica Dental Sonrisa" },
    { agent_id: "a-3", name: "Recordatorios", client_ref: "clinica", client_name: "Clínica Dental Sonrisa" },
  ],
  screens: [
    { key: "home", href: "/" },
    { key: "team", href: "/team" },
    { key: "keys", href: "/keys" },
  ],
  actions: [
    { key: "new_client", href: "/clients/new" },
    { key: "invite_member", href: "/team?invite=1" },
    // Una clave que esta consola todavía no conoce no se pinta como texto crudo.
    { key: "something_new", href: "/x" },
  ],
};

const fold = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
function searchFor(q: string): SearchResult {
  const needle = fold(q.trim());
  const base = { screens: WORLD.screens, actions: WORLD.actions };
  if (!needle) return { clients: [], agents: [], ...base };
  return {
    clients: WORLD.clients.filter((c) => fold(`${c.name} ${c.niche ?? ""}`).includes(needle)),
    agents: WORLD.agents.filter((a) => fold(a.name).includes(needle)),
    ...base,
  };
}

const fetchMock = vi.fn();

/** Lo que oye un lector de pantalla en cada opción. */
const spoken = (options: HTMLElement[]) => options.map((o) => o.getAttribute("aria-label") ?? o.textContent);

function respond(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}
const asTheApi = (url: string) => respond(searchFor(new URL(url, "http://console.test").searchParams.get("q") ?? ""));

function Palette() {
  return (
    <LocaleProvider locale="es">
      <ConsoleCommandPaletteV2 />
    </LocaleProvider>
  );
}

async function openAndType(text: string) {
  const user = userEvent.setup();
  render(<Palette />);
  await user.click(screen.getByRole("button", { name: "Buscar…" }));
  const input = await screen.findByRole("combobox", { name: "Buscar y navegar" });
  input.focus();
  if (text) await user.type(input, text);
  return { user, input };
}

describe("ConsoleCommandPaletteV2", () => {
  beforeEach(() => {
    router.push.mockReset();
    fetchMock.mockReset().mockImplementation(asTheApi);
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("«Recep» trae los agentes que se llaman así, con su cliente, y nada que no coincida", async () => {
    await openAndType("Recep");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/search?q=Recep", expect.anything()));
    const list = screen.getByRole("listbox");
    const agents = await within(list).findByRole("group", { name: "Agentes" });
    expect(spoken(within(agents).getAllByRole("option"))).toEqual([
      "Recepción, Flor y Encanto",
      "Recepcionista, Clínica Dental Sonrisa",
    ]);
    expect(within(list).queryByRole("group", { name: "Clientes" })).toBeNull();
    expect(within(list).queryByRole("group", { name: "Pantallas" })).toBeNull();
    expect(within(list).queryByRole("group", { name: "Acciones" })).toBeNull();
  });

  it("sin escribir: las pantallas y las acciones permitidas; con texto, las que coinciden por su nombre", async () => {
    const { user, input } = await openAndType("");
    const list = screen.getByRole("listbox");
    const screens = await within(list).findByRole("group", { name: "Pantallas" });
    expect(spoken(within(screens).getAllByRole("option"))).toEqual(["Panel", "Equipo", "API"]);
    const actions = within(list).getByRole("group", { name: "Acciones" });
    expect(spoken(within(actions).getAllByRole("option"))).toEqual(["Nuevo cliente", "Invitar a alguien al equipo"]);
    expect(list).not.toHaveTextContent("something_new");
    await user.type(input, "equi");
    await waitFor(() =>
      expect(spoken(within(screen.getByRole("group", { name: "Pantallas" })).getAllByRole("option"))).toEqual(["Equipo"]),
    );
    expect(spoken(within(screen.getByRole("group", { name: "Acciones" })).getAllByRole("option"))).toEqual(["Invitar a alguien al equipo"]);
  });

  it("las flechas mueven, Intro abre el agente y la paleta se cierra", async () => {
    const { user } = await openAndType("Recep");
    await screen.findByRole("group", { name: "Agentes" });
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: /Recepcionista/ })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Enter}");
    expect(router.push).toHaveBeenCalledWith("/clients/clinica/agents/a-2");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("un cliente por su nombre o por su nicho, con sus pestañas, que abren su pantalla", async () => {
    const { user } = await openAndType("flori");
    const clients = await screen.findByRole("group", { name: "Clientes" });
    expect(spoken(within(clients).getAllByRole("option"))).toEqual([
      "Flor y Encanto, Floristería",
      "Flor y Encanto · Negocio",
      "Flor y Encanto · Agentes",
    ]);
    await user.click(within(clients).getByRole("option", { name: /Flor y Encanto · Negocio/ }));
    expect(router.push).toHaveBeenCalledWith("/clients/flor/business");
  });

  it("Escape cierra", async () => {
    const { user } = await openAndType("Re");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("⌘K y Ctrl+K la abren desde cualquier pantalla", async () => {
    const user = userEvent.setup();
    render(<Palette />);
    await user.keyboard("{Meta>}k{/Meta}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  describe("los cinco estados", () => {
    it("cargando: lo dice mientras busca", async () => {
      fetchMock.mockImplementation(() => new Promise(() => {}));
      await openAndType("Recep");
      await waitFor(() => expect(screen.getByRole("listbox")).toHaveAttribute("aria-busy", "true"));
    });

    it("vacío: «Sin resultados para…», también cuando ninguna pantalla ni acción coincide", async () => {
      await openAndType("zzz");
      await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Sin resultados para «zzz»"));
    });

    it("error: lo dice y no inventa resultados", async () => {
      fetchMock.mockImplementation(() => respond({ detail: "boom" }, 502));
      await openAndType("Recep");
      expect(await screen.findByRole("alert")).toHaveTextContent("La búsqueda falló. Inténtalo de nuevo.");
      expect(screen.queryAllByRole("option")).toHaveLength(0);
    });

    it("parcial: mientras busca lo siguiente, se quedan los resultados anteriores", async () => {
      let release: (r: Response) => void = () => {};
      const { user } = await openAndType("Recep");
      await screen.findByRole("group", { name: "Agentes" });
      fetchMock.mockImplementation(() => new Promise<Response>((r) => (release = r)));
      await user.type(screen.getByRole("combobox"), "c");
      await waitFor(() => expect(screen.getByRole("listbox")).toHaveAttribute("aria-busy", "true"));
      expect(screen.getAllByRole("option").length).toBeGreaterThan(0);
      await act(async () => {
        release(new Response(JSON.stringify({ ...searchFor("Recepc"), agents: [WORLD.agents[0]] }), { status: 200 }));
      });
      await waitFor(() => expect(screen.getByRole("listbox")).not.toHaveAttribute("aria-busy"));
      expect(within(screen.getByRole("group", { name: "Agentes" })).getAllByRole("option")).toHaveLength(1);
    });
  });

  it("pasa axe con resultados", async () => {
    await openAndType("Recep");
    await screen.findByRole("group", { name: "Agentes" });
    expect(await axeViolations()).toEqual([]);
  });
});
