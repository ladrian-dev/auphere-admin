import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";

import { Button } from "../components/button";
import { Callout } from "../components/callout";
import { Checklist, type ChecklistItem } from "../components/checklist";
import { DescriptionList } from "../components/description-list";
import { DraftBadge } from "../components/draft-badge";
import { Field } from "../components/field";
import { HelpHint } from "../components/help-hint";
import { Input } from "../components/input";
import { Meter } from "../components/meter";
import { NativeSelect } from "../components/native-select";
import { Section } from "../components/section";
import { Stepper } from "../components/stepper";

const meta = { title: "Building blocks" } satisfies Meta;
export default meta;
type Story = StoryObj;

export const Meters: Story = {
  render: () => (
    <div className="flex max-w-md flex-col gap-6">
      <Meter label="Créditos del mes" value={1204} max={5000} valueLabel="1 204 / 5 000 · 24 %" hint="Se reinicia el día 1." />
      <Meter label="Créditos del mes" value={4300} max={5000} valueLabel="4 300 / 5 000 · 86 %" />
      <Meter label="Créditos del mes" value={5000} max={5000} valueLabel="5 000 / 5 000 · 100 %" hint="El agente no responde hasta que asignes más crédito." />
      <Meter label="Créditos del mes" value={1204} max={null} valueLabel="1 204" noMaxLabel="Sin tope: consume del saldo del partner." />
      <Meter label="Conocimiento" value={3} max={20} tone="info" size="sm" valueLabel="3 de 20 documentos" />
      <Meter label="Cargando" value={0} max={100} loading />
    </div>
  ),
};

const steps: ChecklistItem[] = [
  { key: "create", label: "Crear el cliente", status: "done" },
  { key: "seed", label: "Preparar el agente", status: "done" },
  { key: "publish", label: "Publicar la primera versión", status: "running", detail: "Publicando…" },
  { key: "channel", label: "Conectar WhatsApp", status: "failed", detail: "Meta no devolvió el código de autorización.", onRetry: () => {}, retryLabel: "Reintentar" },
  { key: "activate", label: "Activar el cliente", status: "current", href: "#activate" },
  { key: "tools", label: "Conectar la tienda", status: "todo", href: "#tools" },
  { key: "skip", label: "Importar el catálogo", status: "skipped", detail: "Este negocio no tiene catálogo." },
];

export const Checklists: Story = {
  render: () => (
    <Section title="Puesta en marcha" description="Lo que falta para que el agente atienda." className="max-w-md">
      <Checklist ariaLabel="Puesta en marcha" items={steps} />
    </Section>
  ),
};

export const Steppers: Story = {
  render: () => (
    <div className="flex flex-col gap-6">
      <Stepper ariaLabel="Alta de cliente" current={1} steps={[{ key: "a", label: "Negocio" }, { key: "b", label: "Agente" }, { key: "c", label: "Canal" }, { key: "d", label: "Listo" }]} stepOfLabel={(n, t) => `Paso ${n} de ${t}`} />
      <Stepper variant="line" ariaLabel="Alta de cliente" current={2} steps={[{ key: "a", label: "Negocio" }, { key: "b", label: "Agente" }, { key: "c", label: "Canal" }, { key: "d", label: "Listo" }]} stepOfLabel={(n, t) => `Paso ${n} de ${t}`} />
    </div>
  ),
};

export const Callouts: Story = {
  render: () => (
    <div className="flex max-w-lg flex-col gap-3">
      <Callout title="Sin novedades">Nada que hacer por aquí.</Callout>
      <Callout tone="info" title="Versión 3 en borrador">Publica para que el agente use los cambios.</Callout>
      <Callout tone="positive" title="WhatsApp conectado">El agente ya atiende en +34 653 32 16 93.</Callout>
      <Callout tone="warning" title="Queda un 14 % del cupo" action={<Button size="sm">Asignar crédito</Button>}>
        Cuando se agote el agente dejará de responder.
      </Callout>
      <Callout tone="danger" title="No se pudo publicar" dismissible dismissLabel="Cerrar">
        Error hablando con el backend.
      </Callout>
    </div>
  ),
};

function FieldsDemo() {
  const [name, setName] = useState("");
  return (
    <form className="flex max-w-sm flex-col gap-4" onSubmit={(e) => e.preventDefault()}>
      <Field label="Nombre del negocio" required requiredLabel="Obligatorio" hint="Como lo verán tus clientes." error={name.length === 0 ? "Escribe un nombre." : undefined}>
        {(a11y) => <Input {...a11y} value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Idioma" optionalLabel="Opcional" hint="El del negocio, no el tuyo.">
        {(a11y) => (
          <NativeSelect {...a11y} defaultValue="es">
            <option value="es">Español</option>
            <option value="en">English</option>
            <option value="hu">Magyar</option>
          </NativeSelect>
        )}
      </Field>
      <div className="flex items-center gap-1 text-sm">
        Tope mensual <HelpHint>Créditos que este cliente puede gastar al mes. Sin tope consume del saldo del partner.</HelpHint>
      </div>
      <div className="flex gap-2">
        <Button type="submit">Guardar</Button>
        <Button type="button" loading>
          Guardando
        </Button>
      </div>
    </form>
  );
}
export const Fields: Story = { render: () => <FieldsDemo /> };

export const Descriptions: Story = {
  render: () => (
    <Section title="Resumen" actions={<DraftBadge draft={4} active={3} draftLabel={(v) => `Borrador v${v}`} activeLabel={(v) => `Activa v${v}`} />} className="max-w-lg">
      <DescriptionList
        columns={2}
        items={[
          { term: "Referencia", detail: "panaderia-la-espiga", mono: true, truncate: true },
          { term: "Plantilla", detail: "Comercio genérico" },
          { term: "Modelo", detail: "Sol · ×17 créditos" },
          { term: "Creado", detail: "22 sep 2026" },
        ]}
      />
      <DraftBadge draft={null} active={null} draftLabel={(v) => `Borrador v${v}`} activeLabel={(v) => `Activa v${v}`} noneLabel="Sin publicar" />
    </Section>
  ),
};
