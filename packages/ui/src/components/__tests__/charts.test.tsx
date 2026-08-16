import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StackedBarChart } from "../chart-bars";
import { CapGauge } from "../chart-gauge";
import { ProjectionLineChart } from "../chart-line";
import { CHART_SERIES_COLORS } from "../chart-theme";

describe("CapGauge", () => {
  it("renders a native progress with the tone by threshold", () => {
    const { rerender } = render(<CapGauge label="Mensajes" value={20} max={100} valueLabel="20 / 100" percentLabel="20 %" noCapLabel="Sin tope" />);
    const bar = screen.getByRole("progressbar", { name: "Mensajes" });
    expect(bar).toHaveAttribute("value", "20");
    expect(bar).toHaveAttribute("data-tone", "positive");
    rerender(<CapGauge label="Mensajes" value={85} max={100} valueLabel="85 / 100" noCapLabel="Sin tope" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("data-tone", "warning");
    rerender(<CapGauge label="Mensajes" value={130} max={100} valueLabel="130 / 100" noCapLabel="Sin tope" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("data-tone", "danger");
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "100");
  });
  it("renders the no-cap state without a bar", () => {
    render(<CapGauge label="Mensajes" value={20} max={null} valueLabel="20" noCapLabel="Sin tope configurado" />);
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText("Sin tope configurado")).toBeInTheDocument();
  });
});

describe("chart theme", () => {
  it("only uses CSS tokens for series colours", () => {
    for (const c of CHART_SERIES_COLORS) expect(c).toMatch(/^var\(--color-/);
  });
});

describe("Recharts wrappers", () => {
  it("mount with an accessible label (jsdom has no layout, so no SVG assertions)", () => {
    render(
      <>
        <StackedBarChart ariaLabel="Barras" data={[{ d: "2026-08-01", a: 1 }]} xKey="d" series={[{ key: "a", label: "A" }]} />
        <ProjectionLineChart ariaLabel="Línea" data={[{ x: "2026-08-01", actual: 1 }]} labels={{ actual: "Real", projected: "Proyección" }} />
      </>,
    );
    expect(screen.getByRole("img", { name: "Barras" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Línea" })).toBeInTheDocument();
  });
});
