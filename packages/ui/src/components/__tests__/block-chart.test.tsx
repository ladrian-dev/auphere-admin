import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "../../test/axe";
import {
  BlockChart,
  blockChartCells,
  blockChartLabelIndices,
  blockChartRows,
  blockChartScale,
  type BlockChartColumn,
  type BlockChartCopy,
} from "../block-chart";

/**
 * Spec 047 (R47.10, R46.3) — la gráfica de bloques, con el cálculo de `01` §12:
 * - 12 filas; 16 con más de 60 columnas;
 * - el máximo del eje es un paso «bonito» (1, 2, 2,5, 5 o 10 × 10ⁿ) ≥ pico × 1,04 / 4, por 4;
 * - celdas llenas = máx(1 si hay dato, redondeo(valor / máximo × filas)), repartidas
 *   entre las series de abajo arriba;
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

function week(): BlockChartColumn[] {
  return WEEK.map((label, i) => ({
    key: `d${i}`,
    label,
    title: `${label} ${20 + i} oct`,
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

describe("el cálculo (01 §12)", () => {
  it("el máximo del eje es un paso redondo por 4, con un 4 % de aire", () => {
    expect(blockChartScale(120)).toEqual({ step: 50, max: 200 });
    expect(blockChartScale(875)).toEqual({ step: 250, max: 1000 });
    expect(blockChartScale(96)).toEqual({ step: 25, max: 100 });
    expect(blockChartScale(100)).toEqual({ step: 50, max: 200 });
    expect(blockChartScale(3)).toEqual({ step: 1, max: 4 });
    expect(blockChartScale(0)).toEqual({ step: 1, max: 4 });
  });

  it("12 filas; 16 si hay más de 60 columnas", () => {
    expect(blockChartRows(7)).toBe(12);
    expect(blockChartRows(60)).toBe(12);
    expect(blockChartRows(61)).toBe(16);
    expect(blockChartRows(90)).toBe(16);
  });

  it("los cuadros llenos: al menos uno si hay dato, repartidos de abajo arriba", () => {
    expect(blockChartCells([0, 0], 200, 12)).toEqual([0, 0]);
    expect(blockChartCells([1, 0], 200, 12)).toEqual([1, 0]);
    expect(blockChartCells([150, 50], 200, 12)).toEqual([9, 3]);
    // Una serie con dato nunca desaparece si hay sitio para las dos.
    expect(blockChartCells([100, 2], 200, 12)).toEqual([5, 1]);
    expect(blockChartCells([200, 0], 200, 12)).toEqual([12, 0]);
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
  it("es una rejilla continua: una columna por día, cada una con sus filas", () => {
    render(<Chart />);
    const plot = screen.getByRole("listbox", { name: "Conversaciones por día" });
    const columns = within(plot).getAllByRole("option");
    expect(columns).toHaveLength(7);
    for (const col of columns) expect(col.querySelectorAll("[data-cell]")).toHaveLength(12);
    // Los cuadros vacíos dibujan la pista.
    expect(columns[0]!.querySelectorAll('[data-cell="track"]').length).toBeGreaterThan(0);
  });

  it("dos series en dos tonos, con su leyenda", () => {
    render(<Chart />);
    const legend = document.querySelector<HTMLElement>("[data-slot=block-chart-legend]")!;
    expect(within(legend).getByText("Resueltas sin persona")).toBeVisible();
    expect(within(legend).getByText("Pasadas a una persona")).toBeVisible();
    const first = screen.getAllByRole("option")[0]!;
    expect(first.querySelector('[data-cell="0"]')!.className).toMatch(/\bbg-series-1\b/);
    expect(first.querySelector('[data-cell="1"]')!.className).toMatch(/\bbg-series-2\b/);
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
    expect(within(rows[1]!).getByRole("rowheader")).toHaveTextContent("Mar 20 oct");
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
    expect(first).toHaveAccessibleName("Mar 20 oct: 110 conversaciones");
    const tip = screen.getByRole("tooltip");
    expect(first).toHaveAttribute("aria-describedby", tip.id);
    expect(tip).toHaveTextContent("Mar 20 oct");
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
    expect(screen.getByRole("tooltip")).toHaveTextContent("Mié 21 oct");
    await user.keyboard("{End}");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Hoy 26 oct");
    await user.keyboard("{Home}");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Mar 20 oct");
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
    expect(screen.getByRole("tooltip")).toHaveTextContent("Vie 23 oct");
    fireEvent.click(screen.getAllByRole("option")[4]!);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Sáb 24 oct");
  });

  it("90 días: 16 filas, etiquetas espaciadas y desplazamiento lateral dentro de su caja", () => {
    render(<Chart columns={days(90)} />);
    const columns = screen.getAllByRole("option");
    expect(columns).toHaveLength(90);
    expect(columns[0]!.querySelectorAll("[data-cell]")).toHaveLength(16);
    const scroller = screen.getByRole("listbox", { name: "Conversaciones por día" }).closest("[data-scroll-x]");
    expect(scroller).not.toBeNull();
    expect(scroller!.className).toMatch(/\boverflow-x-auto\b/);
    expect(document.querySelectorAll("[data-axis-label]")).toHaveLength(8);
  });

  it("30 días: 12 filas y una etiqueta de cada cinco más «Hoy»", () => {
    render(<Chart columns={days(30)} />);
    expect(screen.getAllByRole("option")[0]!.querySelectorAll("[data-cell]")).toHaveLength(12);
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

    it("vacío: dibuja la pista y lo dice", () => {
      render(<Chart columns={week().map((c) => ({ ...c, values: [0, 0] }))} />);
      expect(screen.getByRole("status")).toHaveTextContent("Aún no hay conversaciones en estos días.");
      expect(document.querySelectorAll('[data-cell="track"]').length).toBe(7 * 12);
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
