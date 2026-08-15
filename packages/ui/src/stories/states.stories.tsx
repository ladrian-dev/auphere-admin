import type { Meta, StoryObj } from "@storybook/react-vite";
import { Users } from "lucide-react";

import { Button } from "../components/button";
import { EmptyState } from "../components/empty-state";
import { ErrorState } from "../components/error-state";
import { Metric } from "../components/metric";
import { CardSkeleton, HeaderSkeleton, TableSkeleton } from "../components/skeleton";
import { StatusBadge } from "../components/status-badge";

const meta = { title: "States" } satisfies Meta;
export default meta;
type Story = StoryObj;

export const Empty: Story = {
  render: () => (
    <EmptyState
      icon={Users}
      title="Todavía no hay clientes"
      description="Crea el primero: en menos de tres minutos tendrás un agente borrador listo."
      action={<Button>Nuevo cliente</Button>}
    />
  ),
};
export const EmptyReadonly: Story = {
  render: () => <EmptyState title="Sin actividad en el periodo" readonly />,
};
export const Error: Story = {
  render: () => (
    <ErrorState
      title="No se pudieron cargar los clientes"
      description="Error hablando con el backend."
      onRetry={() => {}}
      retryLabel="Reintentar"
    />
  ),
};
export const Loading: Story = {
  render: () => (
    <div className="space-y-6">
      <HeaderSkeleton />
      <div className="grid gap-4 md:grid-cols-3">
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </div>
      <TableSkeleton rows={4} columns={5} />
    </div>
  ),
};
export const Metrics: Story = {
  render: () => (
    <div className="grid gap-4 md:grid-cols-4">
      <Metric label="Clientes activos" value="12" hint="de 18" href="#" />
      <Metric label="Conversaciones" value="1.204" hint="82 % del tope" href="#" />
      <Metric label="Con incidencia" value="2" hint="agentes" href="#" />
      <Metric label="Cargando" value="" loading hint="…" />
    </div>
  ),
};
export const Badges: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <StatusBadge tone="positive">Activo</StatusBadge>
      <StatusBadge tone="warning">Aprovisionando</StatusBadge>
      <StatusBadge tone="danger">Con errores</StatusBadge>
      <StatusBadge tone="info" pulse>
        En vivo
      </StatusBadge>
      <StatusBadge tone="muted">Archivado</StatusBadge>
      <div className="w-32">
        <StatusBadge tone="muted">Nombre larguísimo que se trunca con title</StatusBadge>
      </div>
    </div>
  ),
};
