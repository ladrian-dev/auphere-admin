import type { Meta, StoryObj } from "@storybook/react-vite";

import { StackedBarChart } from "../components/chart-bars";
import { CapGauge } from "../components/chart-gauge";
import { ProjectionLineChart } from "../components/chart-line";

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
      <CapGauge label="Mensajes del mes" value={1204} max={5000} valueLabel="1.204 / 5.000" percentLabel="24 %" noCapLabel="Sin tope" />
      <CapGauge label="Mensajes del mes" value={4300} max={5000} valueLabel="4.300 / 5.000" percentLabel="86 %" noCapLabel="Sin tope" />
      <CapGauge label="Mensajes del mes" value={5200} max={5000} valueLabel="5.200 / 5.000" percentLabel="104 %" noCapLabel="Sin tope" />
      <CapGauge label="Mensajes del mes" value={900} max={null} valueLabel="900" noCapLabel="Sin tope configurado" />
    </div>
  ),
};
