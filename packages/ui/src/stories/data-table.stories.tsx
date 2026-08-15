import type { Meta, StoryObj } from "@storybook/react-vite";
import { Users } from "lucide-react";

import { Button } from "../components/button";
import { DataTable, type ColumnDef, type DataTableProps } from "../components/data-table";
import { EmptyState } from "../components/empty-state";
import { StatusBadge } from "../components/status-badge";

type Row = { ref: string; name: string; status: "active" | "paused" | "provisioning"; conversations: number };

const rows: Row[] = [
  { ref: "clinica-x", name: "Clínica X", status: "active", conversations: 1204 },
  { ref: "barber-y", name: "Barbería Y — nombre extraordinariamente largo para probar el truncado", status: "paused", conversations: 12 },
  { ref: "shop-z", name: "Tienda Z", status: "provisioning", conversations: 0 },
];

const columns: ColumnDef<Row, unknown>[] = [
  { accessorKey: "name", header: "Cliente" },
  { accessorKey: "ref", header: "Ref", cell: (c) => <span className="font-mono text-xs">{String(c.getValue())}</span> },
  {
    accessorKey: "status",
    header: "Estado",
    cell: (c) => {
      const s = c.getValue() as Row["status"];
      const tone = s === "active" ? "positive" : s === "paused" ? "warning" : "info";
      return <StatusBadge tone={tone}>{s}</StatusBadge>;
    },
  },
  { accessorKey: "conversations", header: "Conversaciones", meta: { align: "right" }, cell: (c) => new Intl.NumberFormat("es").format(c.getValue() as number) },
];

type Props = DataTableProps<Row, unknown>;
const meta = {
  title: "Data/DataTable",
  render: (args: Props) => <DataTable {...args} />,
} satisfies Meta<Props>;
export default meta;
type Story = StoryObj<Props>;

export const Ideal: Story = { args: { columns, data: rows, sortable: true, label: "Clientes" } };
export const Loading: Story = { args: { columns, data: [], loading: true } };
export const Empty: Story = {
  args: {
    columns,
    data: [],
    empty: <EmptyState icon={Users} title="Todavía no hay clientes" action={<Button>Nuevo cliente</Button>} />,
  },
};
export const ErrorState: Story = { args: { columns, data: [], error: "No se pudieron cargar los clientes", onRetry: () => {} } };
export const Partial: Story = {
  name: "Partial — one row, missing values",
  args: { columns, data: [{ ref: "solo", name: "Único", status: "provisioning", conversations: 0 }] },
};
export const Narrow: Story = {
  name: "Overflow — 360 px container scrolls inside",
  render: (args) => (
    <div className="w-[360px]">
      <DataTable {...args} />
    </div>
  ),
  args: { columns, data: rows },
};
