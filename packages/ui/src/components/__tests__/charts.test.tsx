import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StackedBarChart } from "../chart-bars";
import { ProjectionLineChart } from "../chart-line";
import { CHART_SERIES_COLORS } from "../chart-theme";

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
