import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as fs from "node:fs";
import * as path from "node:path";
import { describe, expect, it, vi } from "vitest";

import { CatalogBrowser, type CatalogBrowserProps, type CatalogItem } from "../catalog-browser";

/**
 * El patrón de catálogo (spec 018, R4), aprobado por el owner el 2026-09-28.
 *
 * Lo que estos tests fijan es la promesa del componente: **tres gestos
 * —buscar, activos/todo, categoría— que funcionan igual vengan de donde
 * vengan los elementos**. Y la frontera que lo hace posible: el patrón
 * navega, no actúa, y no sabe qué es una habilidad.
 */

type Item = CatalogItem & { nota?: string };

const ITEMS: Item[] = [
  { id: "book", name: "Reservar una cita", search: "propone huecos", category: "citas", active: true },
  { id: "cancel", name: "Cancelar una cita", search: "anula la reserva", category: "citas", active: false },
  { id: "order", name: "Tomar un pedido", search: "recoge productos", category: "pedidos", active: true },
  { id: "track", name: "Seguir un pedido", search: "en qué estado", category: "pedidos", active: false },
  // Sin categoría: R4.5 — va a un grupo con nombre propio, no a uno inventado.
  { id: "human", name: "Pasar a una persona", search: "escala al equipo", category: null, active: true },
];

const LABELS: CatalogBrowserProps<Item>["labels"] = {
  title: "Habilidades",
  search: "Buscar habilidades",
  searchPlaceholder: "Buscar…",
  tabs: "Qué se ve",
  active: "Activos",
  all: "Todo",
  count: (shown, active) => `${shown} habilidades · ${active} activas`,
  uncategorized: "Otras",
  category: (k) => ({ citas: "Citas", pedidos: "Pedidos" })[k] ?? k,
  noResults: "Nada coincide",
  filtersInUse: ({ query, tab, category }) =>
    `Estás viendo ${tab === "active" ? "solo lo activo" : "todo"}${category ? `, en «${category}»` : ""}${query ? `, buscando «${query}»` : ""}.`,
  clear: "Quitar los filtros",
};

function props(over: Partial<CatalogBrowserProps<Item>> = {}): CatalogBrowserProps<Item> {
  return {
    items: ITEMS,
    tab: "all",
    category: null,
    query: "",
    onQueryChange: vi.fn(),
    onClear: vi.fn(),
    hrefFor: (next) => {
      const p = new URLSearchParams();
      const tab = next.tab ?? "all";
      if (tab === "active") p.set("tab", "active");
      const cat = next.category === undefined ? null : next.category;
      if (cat) p.set("cat", cat);
      const qs = p.toString();
      return qs ? `/catalogo?${qs}` : "/catalogo";
    },
    renderItem: (item) => <li key={item.id}>{item.name}</li>,
    empty: <p>No hay nada publicado todavía.</p>,
    labels: LABELS,
    ...over,
  };
}

function mount(over: Partial<CatalogBrowserProps<Item>> = {}) {
  return render(<CatalogBrowser {...props(over)} />);
}

describe("CatalogBrowser · buscar", () => {
  it("reduce la lista y el contador lo dice", () => {
    const { rerender } = mount();
    expect(screen.getByText("5 habilidades · 3 activas")).toBeInTheDocument();

    rerender(<CatalogBrowser {...props({ query: "pedido" })} />);
    const nombres = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(nombres).toEqual(["Tomar un pedido", "Seguir un pedido"]);
    expect(screen.getByText("2 habilidades · 1 activas")).toBeInTheDocument();
  });

  it("busca también en lo que no se ve: la descripción cuenta", () => {
    mount({ query: "huecos" });
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Reservar una cita"]);
  });

  it("lo tecleado sale del componente, no se queda dentro", async () => {
    const onQueryChange = vi.fn();
    const user = userEvent.setup();
    mount({ onQueryChange });
    await user.type(screen.getByRole("searchbox", { name: "Buscar habilidades" }), "a");
    // Controlado: el estado vive en la dirección de la página, no aquí.
    expect(onQueryChange).toHaveBeenCalledWith("a");
  });
});

describe("CatalogBrowser · activos y todo", () => {
  it("la pestaña de activos enseña solo lo activo, y se puede volver", () => {
    mount({ tab: "active" });
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Reservar una cita",
      "Tomar un pedido",
      "Pasar a una persona",
    ]);
    // El camino de vuelta existe y es una dirección, no un estado interno:
    // por eso compartir el enlace lleva a lo mismo (R4.4).
    expect(screen.getByRole("link", { name: "Todo" })).toHaveAttribute("href", "/catalogo");
    expect(screen.getByRole("link", { name: "Activos" })).toHaveAttribute("href", "/catalogo?tab=active");
  });

  it("la pestaña puesta se anuncia, no solo se pinta", () => {
    mount({ tab: "active" });
    expect(screen.getByRole("link", { name: "Activos" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("link", { name: "Todo" })).not.toHaveAttribute("aria-current");
  });
});

describe("CatalogBrowser · categorías", () => {
  it("agrupa, y cada pastilla lleva su cuenta", () => {
    mount();
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Citas",
      "Pedidos",
      "Otras",
    ]);
    expect(screen.getByRole("link", { name: "Citas · 2" })).toHaveAttribute("href", "/catalogo?cat=citas");
  });

  it("un elemento sin categoría cae en un grupo con nombre propio", () => {
    mount();
    const otras = screen.getByRole("region", { name: "Otras" });
    expect(within(otras).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Pasar a una persona"]);
  });

  it("filtrar por categoría deja solo ese grupo, y la pastilla dice que está puesta", () => {
    mount({ category: "pedidos" });
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Pedidos"]);
    expect(screen.getByRole("link", { name: "Pedidos · 2" })).toHaveAttribute("aria-current", "true");
    // Pulsarla otra vez la quita: el enlace vuelve al catálogo sin filtro.
    expect(screen.getByRole("link", { name: "Pedidos · 2" })).toHaveAttribute("href", "/catalogo");
  });

  it("un grupo por elemento no es una agrupación: se calla el encabezado, no la categoría", () => {
    // Cuatro conectores en cuatro categorías daban cuatro títulos y cuatro
    // tarjetas solas en su fila (owner, 2026-09-28). Las pastillas siguen
    // ahí y siguen filtrando: lo único que desaparece es el encabezado.
    const sueltos = ITEMS.map((i, n) => ({ ...i, category: `cat${n}` }));
    mount({ items: sueltos });
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
    expect(screen.getAllByRole("listitem")).toHaveLength(sueltos.length);
    expect(screen.getByRole("link", { name: "cat0 · 1" })).toBeInTheDocument();
  });

  it("en cuanto un grupo tiene dos, se agrupa", () => {
    mount();
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThan(0);
  });

  it("con una sola categoría no se pintan: no filtrarían nada", () => {
    mount({ items: [ITEMS[0]!, { ...ITEMS[1]!, category: "citas" }] });
    expect(screen.queryByRole("link", { name: /Citas/ })).toBeNull();
  });
});

describe("CatalogBrowser · los dos vacíos no son el mismo", () => {
  it("sin nada que enseñar, el cartel lo pone la pantalla", () => {
    mount({ items: [] });
    expect(screen.getByText("No hay nada publicado todavía.")).toBeInTheDocument();
    // Y **no** ofrece quitar filtros: no hay filtro que quitar, y ofrecerlo
    // mandaría a buscar una causa que no existe.
    expect(screen.queryByRole("button", { name: "Quitar los filtros" })).toBeNull();
    // Ni buscador ni pestañas: tres controles que no pueden hacer nada sobre
    // una lista vacía. Se callan solos, igual que las pastillas.
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.queryByRole("group", { name: "Qué se ve" })).toBeNull();
  });

  it("vacío por filtro dice con qué se filtró y ofrece quitarlo", async () => {
    const onClear = vi.fn();
    const user = userEvent.setup();
    mount({ query: "devolución", category: "citas", onClear });
    expect(screen.getByText("Nada coincide")).toBeInTheDocument();
    expect(screen.getByText("Estás viendo todo, en «citas», buscando «devolución».")).toBeInTheDocument();
    // Y el cartel del catálogo vacío no aparece: son dos cosas distintas.
    expect(screen.queryByText("No hay nada publicado todavía.")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Quitar los filtros" }));
    expect(onClear).toHaveBeenCalled();
  });
});

describe("CatalogBrowser · lo que NO hace", () => {
  it("no sabe qué es una habilidad, un conector ni un canal", () => {
    // La frontera del patrón, comprobada en la fuente y no solo en lo
    // pintado: en cuanto el componente nombre uno de los tres catálogos,
    // deja de servir para los otros dos. Es exactamente lo que le pasó a
    // Herramientas y Habilidades antes de la spec 017.
    const src = fs.readFileSync(
      path.join(__dirname, "..", "catalog-browser.tsx"),
      "utf8",
    );
    const prohibidas = /habilidad|capacidad|conector|integraci|canal|skill|connector|channel|whatsapp/i;
    const culpables = src
      .split("\n")
      .map((line, i) => [i + 1, line] as const)
      .filter(([, line]) => prohibidas.test(line));
    expect(culpables.map(([n, l]) => `${n}: ${l.trim()}`)).toEqual([]);
  });

  it("no decide qué se hace al pulsar: la tarjeta la pinta la pantalla", () => {
    mount({ renderItem: (item) => <li key={item.id}>ficha de {item.name}</li> });
    expect(screen.getByText("ficha de Reservar una cita")).toBeInTheDocument();
  });
});
