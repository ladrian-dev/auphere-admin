import type { Meta, StoryObj } from "@storybook/react-vite";

import { BlockChart, type BlockChartCopy } from "../components/block-chart";
import { StackedBarChart } from "../components/chart-bars";
import { ProjectionLineChart } from "../components/chart-line";
import { Meter } from "../components/meter";

const meta = { title: "Charts" } satisfies Meta;
export default meta;
type Story = StoryObj;

const days = Array.from({ length: 14 }, (_, i) => `2026-08-${String(i + 1).padStart(2, "0")}`);
const bars = days.map((d, i) => ({ day: d, "channel.message": 120 + (i % 5) * 20, "llm.input_tokens": 40 + (i % 3) * 15, "media.image": 5 + (i % 4) }));

export const StackedBars: Story = {
  render: () => (
    <StackedBarChart
      ariaLabel="Unidades por día y medidor"
      data={bars}
      xKey="day"
      series={[
        { key: "channel.message", label: "Mensajes" },
        { key: "llm.input_tokens", label: "Tokens entrada (k)" },
        { key: "media.image", label: "Imágenes" },
      ]}
      formatX={(d) => d.slice(5)}
    />
  ),
};

let acc = 0;
const line = days.map((d, i) => {
  acc += 130;
  return i < 9 ? { x: d, actual: acc, projected: i === 8 ? acc : null } : { x: d, actual: null, projected: acc };
});
export const Projection: Story = {
  render: () => (
    <ProjectionLineChart
      ariaLabel="Proyección de fin de mes"
      data={line}
      labels={{ actual: "Consumido", projected: "Proyección", cap: "Tope" }}
      cap={1600}
      formatX={(d) => d.slice(5)}
    />
  ),
};

export const Gauge: Story = {
  render: () => (
    <div className="grid max-w-md gap-6">
      <Meter label="Mensajes del mes" value={1204} max={5000} valueLabel="1.204 / 5.000 · 24 %" />
      <Meter label="Mensajes del mes" value={4300} max={5000} valueLabel="4.300 / 5.000 · 86 %" />
      <Meter label="Mensajes del mes" value={5200} max={5000} valueLabel="5.200 / 5.000 · 104 %" />
      <Meter label="Mensajes del mes" value={900} max={null} valueLabel="900" noMaxLabel="Sin tope configurado" />
    </div>
  ),
};

/* Spec 072 §5 — barras macizas: una por día, el eje en enteros y hoy con borde. */
const blockCopy: BlockChartCopy = {
  column: "Día",
  total: "Total",
  top: "Con más actividad",
  noData: "Sin datos",
  empty: "Aún no hay conversaciones en estos días.",
  totalOf: (n) => `${n} conversaciones`,
};
const weekLabels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Hoy"];

export const DailyBars: Story = {
  render: () => (
    <BlockChart
      title="Conversaciones por día"
      series={[
        { key: "resolved", label: "Resueltas sin persona" },
        { key: "handed", label: "Pasadas a una persona" },
      ]}
      columns={weekLabels.map((label, i) => ({
        key: String(i),
        label,
        title: `${label} ${16 + i} nov`,
        values: [[1, 0, 2, 0, 1, 0, 1][i] ?? 0, [0, 0, 0, 1, 0, 0, 0][i] ?? 0],
      }))}
      copy={blockCopy}
    />
  ),
};

export const DailySpend: Story = {
  render: () => (
    <BlockChart
      title="Gasto por día"
      series={[{ key: "conversations", label: "Conversaciones" }]}
      columns={Array.from({ length: 30 }, (_, i) => ({
        key: String(i),
        label: i === 29 ? "Hoy" : String(i + 1),
        title: `${i + 1} nov`,
        values: [((i * 37) % 90) * 10_000],
      }))}
      copy={{ ...blockCopy, totalOf: (n) => n }}
      minStep={1_000}
      formatValue={(v) => `${(v / 100_000).toFixed(2).replace(".", ",")} USD`}
    />
  ),
};
