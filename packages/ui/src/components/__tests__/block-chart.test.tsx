import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "../../test/axe";
import {
  BlockChart,
  blockChartBar,
  blockChartLabelIndices,
  blockChartScale,
  blockChartTicks,
  type BlockChartColumn,
  type BlockChartCopy,
} from "../block-chart";

/**
 * Spec 047 (R47.10, R46.3) y spec 072 §5 («Barras macizas»):
 * - una barra maciza por día; las series se apilan dentro de la barra (5.1);
 * - el eje va en pasos enteros de su unidad: 1, 2 o 5 × 10ⁿ, nunca por debajo
 *   del paso mínimo (una conversación, un céntimo), con un 4 % de aire (5.2);
 * - hoy se marca con un borde y dice «hoy» en su nombre accesible (5.3);
 * - las barras crecen al entrar, y con «Reducir movimiento» salen quietas (5.4);
 * - la tabla para lectores de pantalla se mantiene (5.5);
 * - etiquetas: todas hasta 14 columnas; si no, una de cada ⌈n/7⌉ y siempre la última.
 */

const SERIES = [
  { key: "solved", label: "Resueltas sin persona" },
  { key: "handed", label: "Pasadas a una persona" },
];

const COPY: BlockChartCopy = {
  column: "Día",
  total: "Total",
  top: "Con más actividad",
  noData: "Sin datos",
  empty: "Aún no hay conversaciones en estos días.",
  totalOf: (n) => `${n} conversaciones`,
};

const WEEK = ["Mar", "Mié", "Jue", "Vie", "Sáb", "Dom", "Hoy"];
const WEEK_TITLE = ["Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo", "Lunes"];

function week(): BlockChartColumn[] {
  return WEEK.map((label, i) => ({
    key: `d${i}`,
    label,
    title: `${WEEK_TITLE[i]} ${20 + i} oct`,
    values: [100 + i * 10, 10 + i],
    top: [
      { label: "Flor y Encanto", share: 0.46 },
      { label: "ADSL System", share: 0.31 },
      { label: "Clínica Dental Sonrisa", share: 0.17 },
      { label: "Café Origen", share: 0.06 },
    ],
  }));
}

function days(n: number): BlockChartColumn[] {
  return Array.from({ length: n }, (_, i) => ({
    key: `d${i}`,
    label: i === n - 1 ? "Hoy" : String(i + 1),
    title: `Día ${i + 1}`,
    values: [i % 5, i % 2],
  }));
}

function Chart(props: Partial<React.ComponentProps<typeof BlockChart>>) {
  return <BlockChart title="Conversaciones por día" series={SERIES} columns={week()} copy={COPY} {...props} />;
}

const ticks = () => Array.from(document.querySelectorAll("[data-axis-tick]")).map((t) => t.textContent);

describe("el cálculo", () => {
  it("el eje sube en pasos de 1, 2 o 5 × 10ⁿ, con un 4 % de aire y como mucho cuatro tramos (cinco marcas)", () => {
    expect(blockChartScale(120)).toEqual({ step: 50, max: 150 });
    expect(blockChartScale(875)).toEqual({ step: 500, max: 1000 });
    expect(blockChartScale(96)).toEqual({ step: 50, max: 100 });
    expect(blockChartScale(100)).toEqual({ step: 50, max: 150 });
    expect(blockChartScale(3)).toEqual({ step: 1, max: 4 });
    expect(blockChartScale(0)).toEqual({ step: 1, max: 4 });
  });

  it("conversaciones enteras: nunca 0,5 ni 1,5 (072 §5.2)", () => {
    expect(blockChartScale(1)).toEqual({ step: 1, max: 2 });
    expect(blockChartScale(2)).toEqual({ step: 1, max: 3 });
    expect(blockChartTicks(1)).toEqual([0, 1, 2]);
    for (let peak = 1; peak <= 40; peak++) {
      for (const tick of blockChartTicks(peak)) expect(Number.isInteger(tick)).toBe(true);
    }
  });

  it("dinero en pasos redondos, nunca por debajo del paso mínimo (072 §5.2)", () => {
    // 7,30 USD en cien milésimas, con un céntimo de paso mínimo: 0 · 2 · 4 · 6 · 8 USD.
    expect(blockChartTicks(730_000, 1_000)).toEqual([0, 200_000, 400_000, 600_000, 800_000]);
    // 9 USD: 0 · 5 · 10 USD.
    expect(blockChartTicks(900_000, 1_000)).toEqual([0, 500_000, 1_000_000]);
    // Menos de un céntimo no baja del céntimo.
    expect(blockChartScale(200, 1_000)).toEqual({ step: 1_000, max: 1_000 });
  });

  it("una barra: su alto sobre el máximo y el reparto de sus series, de abajo arriba", () => {
    expect(blockChartBar([0, 0], 200)).toEqual({ height: 0, parts: [0, 0] });
    expect(blockChartBar([150, 50], 200)).toEqual({ height: 1, parts: [0.75, 0.25] });
    expect(blockChartBar([50, 0], 200)).toEqual({ height: 0.25, parts: [1, 0] });
    // Nada se sale del gráfico, y un valor raro cuenta como cero.
    expect(blockChartBar([400, Number.NaN], 200)).toEqual({ height: 1, parts: [1, 0] });
  });

  it("etiquetas: todas hasta 14 columnas; si no, una de cada ⌈n/7⌉ y siempre la última", () => {
    expect(blockChartLabelIndices(7)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(blockChartLabelIndices(14)).toHaveLength(14);
    expect(blockChartLabelIndices(30)).toEqual([0, 5, 10, 15, 20, 25, 29]);
    expect(blockChartLabelIndices(28)).toEqual([0, 4, 8, 12, 16, 20, 24, 27]);
    expect(blockChartLabelIndices(90)).toEqual([0, 13, 26, 39, 52, 65, 78, 89]);
  });
});

describe("<BlockChart>", () => {
  it("una barra maciza por día, con las series apiladas dentro (072 §5.1)", () => {
    render(<Chart />);
    const plot = screen.getByRole("listbox", { name: "Conversaciones por día" });
    const columns = within(plot).getAllByRole("option");
    expect(columns).toHaveLength(7);
    for (const col of columns) {
      expect(col.querySelectorAll("[data-bar]")).toHaveLength(1);
      expect(col.querySelectorAll("[data-series]")).toHaveLength(2);
    }
    // Ya no hay rejilla de cuadros.
    expect(document.querySelector("[data-cell]")).toBeNull();
    // La barra más alta (Hoy: 176 de un eje de 200) mide su parte del alto.
    expect(within(plot).getAllByRole("option")[6]!.querySelector<HTMLElement>("[data-bar]")!.style.height).toBe("88%");
  });

  it("el eje de conversaciones va en enteros: 0 · 1 · 2, nunca 0,5 ni 1,5 (072 §5.2)", () => {
    const cols = week().map((c, i) => ({ ...c, values: i === 3 ? [1, 0] : [0, 0] }));
    render(<Chart columns={cols} />);
    expect(ticks()).toEqual(["0", "1", "2"]);
  });

  it("el eje de dinero va en pasos redondos con su unidad (072 §5.2)", () => {
    const cols = week().map((c, i) => ({ ...c, values: [i === 6 ? 900_000 : 100_000, 0] }));
    render(<Chart columns={cols} minStep={1_000} formatValue={(v) => `${v / 100_000} USD`} />);
    expect(ticks()).toEqual(["0 USD", "5 USD", "10 USD"]);
  });

  it("hoy se marca con un borde y dice «hoy» en su nombre accesible (072 §5.3)", () => {
    render(<Chart />);
    const columns = screen.getAllByRole("option");
    const today = columns[6]!;
    expect(today).toHaveAttribute("data-today", "true");
    expect(today.querySelector("[data-bar]")!.className).toMatch(/\boutline-2\b/);
    expect(today).toHaveAccessibleName("Lunes 26 oct (hoy): 176 conversaciones");
    for (const col of columns.slice(0, 6)) {
      expect(col).not.toHaveAttribute("data-today");
      expect(col.querySelector("[data-bar]")!.className).not.toMatch(/\boutline-2\b/);
    }
    // La tabla también lo dice.
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(within(rows[7]!).getByRole("rowheader")).toHaveTextContent("Lunes 26 oct (hoy)");
  });

  it("hoy en inglés, o con la palabra que pase la pantalla", () => {
    const { unmount } = render(<Chart locale="en" />);
    expect(screen.getAllByRole("option")[6]).toHaveAccessibleName("Lunes 26 oct (today): 176 conversaciones");
    unmount();
    render(<Chart copy={{ ...COPY, today: "ahora" }} />);
    expect(screen.getAllByRole("option")[6]).toHaveAccessibleName("Lunes 26 oct (ahora): 176 conversaciones");
  });

  it("una columna dice si es hoy; si ninguna lo dice, hoy es la última", () => {
    const cols = week().map((c, i) => ({ ...c, today: i === 2 }));
    render(<Chart columns={cols} />);
    const columns = screen.getAllByRole("option");
    expect(columns[2]).toHaveAttribute("data-today", "true");
    expect(columns[6]).not.toHaveAttribute("data-today");
  });

  it("hoy sin nada aún sigue marcado, con una barra mínima", () => {
    const cols = week();
    cols[6] = { ...cols[6]!, values: [0, 0] };
    render(<Chart columns={cols} />);
    const bar = screen.getAllByRole("option")[6]!.querySelector<HTMLElement>("[data-bar]")!;
    expect(bar.className).toMatch(/\boutline-2\b/);
    expect(bar.className).toMatch(/\bmin-h-1\b/);
  });

  it("las barras crecen al entrar, y con «Reducir movimiento» salen quietas (072 §5.4)", () => {
    render(<Chart />);
    for (const bar of document.querySelectorAll<HTMLElement>("[data-bar]")) {
      // Solo con movimiento: la animación va detrás de `motion-safe:`.
      expect(bar.className).toMatch(/(^|\s)motion-safe:animate-bar-grow(\s|$)/);
      expect(bar.className).not.toMatch(/(^|\s)animate-bar-grow(\s|$)/);
      expect(bar.className).toMatch(/\borigin-bottom\b/);
    }
  });

  it("con pocas columnas (una semana) cada una ocupa su parte del ancho, sin huecos grandes (Andrés, 2026-10-28)", () => {
    render(<Chart />);
    const grid = screen.getByRole("listbox");
    expect(grid.style.gridTemplateColumns).toBe("repeat(7, minmax(0, 1fr))");
    expect(grid.style.justifyContent).not.toBe("space-between");
  });

  it("dos series en dos tonos, con su leyenda", () => {
    render(<Chart />);
    const legend = document.querySelector<HTMLElement>("[data-slot=block-chart-legend]")!;
    expect(within(legend).getByText("Resueltas sin persona")).toBeVisible();
    expect(within(legend).getByText("Pasadas a una persona")).toBeVisible();
    const first = screen.getAllByRole("option")[0]!;
    expect(first.querySelector('[data-series="0"]')!.className).toMatch(/\bbg-series-1\b/);
    expect(first.querySelector('[data-series="1"]')!.className).toMatch(/\bbg-series-2\b/);
  });

  it("tiene una tabla equivalente para los lectores de pantalla", () => {
    render(<Chart />);
    const table = screen.getByRole("table", { name: "Conversaciones por día" });
    expect(table.className).toMatch(/\bsr-only\b/);
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(8);
    expect(within(rows[0]!).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "Día",
      "Resueltas sin persona",
      "Pasadas a una persona",
      "Total",
    ]);
    expect(within(rows[1]!).getByRole("rowheader")).toHaveTextContent("Martes 20 oct");
    expect(rows[1]).toHaveTextContent("110");
  });

  it("el tooltip dice el total, el reparto y los 3 primeros, y se abre con el teclado", async () => {
    const user = userEvent.setup();
    render(<Chart />);
    await user.tab();
    const plot = screen.getByRole("listbox", { name: "Conversaciones por día" });
    expect(plot).toHaveFocus();
    const first = screen.getAllByRole("option")[0]!;
    expect(plot).toHaveAttribute("aria-activedescendant", first.id);
    expect(first).toHaveAttribute("aria-selected", "true");
    // Cada columna se nombra con su día y su total: es lo que lee el lector al moverse.
    expect(first).toHaveAccessibleName("Martes 20 oct: 110 conversaciones");
    const tip = screen.getByRole("tooltip");
    expect(first).toHaveAttribute("aria-describedby", tip.id);
    expect(tip).toHaveTextContent("Martes 20 oct");
    expect(tip).toHaveTextContent("110 conversaciones");
    expect(tip).toHaveTextContent("Resueltas sin persona");
    expect(tip).toHaveTextContent("91 %");
    expect(tip).toHaveTextContent("Con más actividad");
    expect(tip).toHaveTextContent("Flor y Encanto");
    expect(tip).toHaveTextContent("46 %");
    expect(tip).toHaveTextContent("Clínica Dental Sonrisa");
    expect(tip).not.toHaveTextContent("Café Origen");

    await user.keyboard("{ArrowRight}");
    expect(plot).toHaveAttribute("aria-activedescendant", screen.getAllByRole("option")[1]!.id);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Miércoles 21 oct");
    await user.keyboard("{End}");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Lunes 26 oct");
    await user.keyboard("{Home}");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Martes 20 oct");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(plot).toHaveFocus();
  });

  it("una sola parada de Tab: las columnas no son focos sueltos, las flechas las recorren", () => {
    render(<Chart />);
    expect(screen.getByRole("listbox")).toHaveAttribute("tabindex", "0");
    for (const option of screen.getAllByRole("option")) expect(option).not.toHaveAttribute("tabindex");
  });

  it("el ratón también abre el tooltip, y el toque en móvil", () => {
    render(<Chart />);
    fireEvent.mouseEnter(screen.getAllByRole("option")[3]!);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Viernes 23 oct");
    fireEvent.click(screen.getAllByRole("option")[4]!);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Sábado 24 oct");
  });

  it("90 días: una barra por día, etiquetas espaciadas y desplazamiento lateral dentro de su caja", () => {
    render(<Chart columns={days(90)} />);
    const columns = screen.getAllByRole("option");
    expect(columns).toHaveLength(90);
    expect(document.querySelectorAll("[data-bar]")).toHaveLength(90);
    const scroller = screen.getByRole("listbox", { name: "Conversaciones por día" }).closest("[data-scroll-x]");
    expect(scroller).not.toBeNull();
    expect(scroller!.className).toMatch(/\boverflow-x-auto\b/);
    expect(document.querySelectorAll("[data-axis-label]")).toHaveLength(8);
  });

  it("30 días: una barra por día y una etiqueta de cada cinco más «Hoy»", () => {
    render(<Chart columns={days(30)} />);
    expect(document.querySelectorAll("[data-bar]")).toHaveLength(30);
    const labels = Array.from(document.querySelectorAll("[data-axis-label]")).map((l) => l.textContent);
    expect(labels).toEqual(["1", "6", "11", "16", "21", "26", "Hoy"]);
  });

  describe("los cinco estados", () => {
    it("cargando: un esqueleto del mismo tamaño, sin datos inventados", () => {
      render(<Chart loading />);
      const chart = document.querySelector("[data-slot=block-chart]")!;
      expect(chart).toHaveAttribute("aria-busy", "true");
      expect(screen.getByRole("status")).toBeInTheDocument();
      expect(screen.queryByRole("table")).toBeNull();
      expect(screen.queryAllByRole("option")).toHaveLength(0);
    });

    it("vacío: lo dice, sin barras y sin una escala inventada", () => {
      render(<Chart columns={week().map((c) => ({ ...c, values: [0, 0] }))} />);
      expect(screen.getByRole("status")).toHaveTextContent("Aún no hay conversaciones en estos días.");
      expect(document.querySelectorAll("[data-bar]")).toHaveLength(0);
      expect(document.querySelectorAll("[data-gridline]").length).toBeGreaterThan(0);
      expect(ticks()).toEqual([]);
    });

    it("vacío de 90 días: la pista no desliza, porque el teclado no llegaría (recorrido UI, axe)", () => {
      // Solo hay decoración oculta: una caja deslizable sin nada enfocable era
      // `scrollable-region-focusable` (serio) en la pantalla del agente.
      render(<Chart columns={days(90).map((c) => ({ ...c, values: [0, 0] }))} />);
      const scroller = document.querySelector("[data-slot=block-chart] [data-scroll-x]");
      expect(scroller).not.toBeNull();
      expect(scroller!.className).not.toMatch(/\boverflow-x-auto\b/);
    });

    it("error: lo dice y deja reintentar", () => {
      const onRetry = vi.fn();
      render(<Chart error="No se pudo cargar la actividad." onRetry={onRetry} />);
      expect(screen.getByRole("alert")).toHaveTextContent("No se pudo cargar la actividad.");
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      expect(onRetry).toHaveBeenCalled();
    });

    it("parcial: un día sin datos dice «Sin datos» y no se pinta como cero", () => {
      const cols = week();
      cols[2] = { ...cols[2]!, values: null };
      render(<Chart columns={cols} />);
      const col = screen.getAllByRole("option")[2]!;
      expect(col).toHaveAttribute("data-missing", "true");
      // Sin barra: una pista discontinua, que no se lee como un cero.
      expect(col.querySelector("[data-bar]")).toBeNull();
      expect(col.querySelector("[data-placeholder]")).not.toBeNull();
      fireEvent.mouseEnter(col);
      expect(screen.getByRole("tooltip")).toHaveTextContent("Sin datos");
      const row = within(screen.getByRole("table")).getAllByRole("row")[3]!;
      expect(row).toHaveTextContent("Sin datos");
    });
  });

  it("pasa axe, también con el tooltip abierto", async () => {
    const user = userEvent.setup();
    render(<Chart />);
    expect(await axeViolations()).toEqual([]);
    await user.tab();
    expect(await axeViolations()).toEqual([]);
  });
});
