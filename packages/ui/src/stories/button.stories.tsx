import type { Meta, StoryObj } from "@storybook/react-vite";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "../components/button";

const meta = {
  title: "Primitives/Button",
  component: Button,
  args: { children: "Nuevo cliente" },
} satisfies Meta<typeof Button>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Variants: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-2">
      <Button>Default</Button>
      <Button variant="outline">Outline</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="destructive">Destructive</Button>
      <Button variant="link">Link</Button>
    </div>
  ),
};
export const Sizes: Story = {
  name: "Sizes — 24 / 28 / 32 / 36 px, next to an Input",
  render: () => (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="xs">xs</Button>
      <Button size="sm">sm</Button>
      <Button size="default">default</Button>
      <Button size="lg">lg</Button>
      <Button size="icon" aria-label="Add">
        <Plus />
      </Button>
      <input className="h-8 rounded-md border border-input px-3 text-sm" placeholder="Input h-8" />
    </div>
  ),
};
export const WithIcon: Story = {
  render: () => (
    <Button variant="destructive">
      <Trash2 data-icon="inline-start" /> Eliminar cliente
    </Button>
  ),
};
export const Disabled: Story = { args: { disabled: true } };
export const LongLabel: Story = {
  name: "Overflow — German string",
  render: () => (
    <div className="w-40">
      <Button className="max-w-full">
        <span className="truncate">Kundenverwaltungseinstellungen speichern</span>
      </Button>
    </div>
  ),
};
