import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChevronDown, MoreHorizontal } from "lucide-react";
import { useState } from "react";

import { Button } from "../../components/button";
import { DescriptionList } from "../../components/description-list";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/dropdown-menu";
import { Meter } from "../../components/meter";
import { NativeSelect } from "../../components/native-select";
import { Section } from "../../components/section";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "../../components/sheet";
import { StatusBadge } from "../../components/status-badge";
import { StatusDot } from "../../components/status-dot";

/**
 * Prototipo · iteración 1 (spec 017, R1–R3): la cabecera de la ficha, la
 * navegación en tres grupos y la barra de borrador. Solo forma: los textos
 * son los de la consola en español, pero nada aquí importa i18n ni router.
 * Lo que este prototipo fija y el código tendrá que respetar:
 *   - cuatro puntos de puesta en marcha con nombre, y UN botón (el del primero pendiente);
 *   - el cupo como barra en la cabecera, o «Sin cupo asignado»;
 *   - ciclo de vida en «Más»; Eliminar solo archivado;
 *   - tres grupos con nombre; a menos de 768 px, un selector con optgroup;
 *   - la barra de borrador pegada bajo la navegación, con «Ver diferencias» y «Publicar».
 */
const meta = { title: "Prototipos/Ficha de cliente", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj;

type StepKey = "agent" | "channel" | "quota" | "activation";
type Setup = { agent: boolean; channel: boolean; quota: boolean; active: boolean; next: StepKey | null };

const STEP_LABEL: Record<StepKey, string> = { agent: "Agente", channel: "Canal", quota: "Cupo", activation: "Activo" };
const NEXT_ACTION: Record<StepKey, string> = {
  agent: "Preparar el agente",
  channel: "Conectar un canal",
  quota: "Asignar cupo",
  activation: "Activar",
};

function SetupSteps({ setup, canAct }: { setup: Setup; canAct: boolean }) {
  const done: Record<StepKey, boolean> = { agent: setup.agent, channel: setup.channel, quota: setup.quota, activation: setup.active };
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <ol aria-label="Puesta en marcha" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        {(Object.keys(STEP_LABEL) as StepKey[]).map((k) => (
          <li key={k} className="inline-flex items-center gap-2" aria-current={setup.next === k ? "step" : undefined}>
            <StatusDot tone={done[k] ? "positive" : k === setup.next ? "warning" : "muted"} label={done[k] ? "hecho" : "pendiente"} />
            <span className={done[k] ? "text-muted-foreground" : "font-medium"}>{STEP_LABEL[k]}</span>
          </li>
        ))}
      </ol>
      {setup.next && canAct ? <Button size="sm">{NEXT_ACTION[setup.next]}</Button> : null}
      {setup.next === null ? <span className="text-sm text-status-positive-text">Atendiendo desde el 23 sept 2026</span> : null}
    </div>
  );
}

function Header({
  setup,
  quota,
  status,
  phone,
  role,
}: {
  setup: Setup;
  quota: { cap: number; remaining: number } | null;
  status: "active" | "paused" | "archived";
  phone?: string;
  role: "owner" | "analyst";
}) {
  const canWrite = role === "owner";
  const tone = status === "active" ? "positive" : status === "paused" ? "warning" : "muted";
  const label = status === "active" ? "Activo" : status === "paused" ? "En pausa" : "Archivado";
  return (
    <header className="flex flex-col gap-(--space-stack) border-b border-border pb-4">
      <nav aria-label="Migas" className="text-xs text-muted-foreground">
        Clientes <span aria-hidden="true">/</span> <span className="text-foreground">Panadería La Espiga</span>
      </nav>
      <div className="flex flex-wrap items-start justify-between gap-(--space-stack)">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-balance">Panadería La Espiga</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <StatusBadge tone={tone}>{label}</StatusBadge>
            {phone ? <span className="text-muted-foreground">{phone}</span> : null}
          </div>
        </div>
        {canWrite ? (
          <DropdownMenu>
            <DropdownMenuTrigger className="inline-flex h-8 items-center gap-1 rounded-sm border border-border px-3 text-sm hover:bg-muted" aria-label="Más acciones">
              <MoreHorizontal className="size-4" aria-hidden="true" /> Más
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {status === "active" ? <DropdownMenuItem>Pausar</DropdownMenuItem> : <DropdownMenuItem>Reactivar</DropdownMenuItem>}
              {status !== "archived" ? <DropdownMenuItem>Archivar</DropdownMenuItem> : null}
              {status === "archived" ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive">Eliminar…</DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
      <div className="grid gap-(--space-stack) md:grid-cols-[1fr_minmax(16rem,20rem)] md:items-center">
        <SetupSteps setup={setup} canAct={canWrite} />
        {quota ? (
          <Meter label="Cupo" value={quota.cap - quota.remaining} max={quota.cap} valueLabel={`${quota.remaining.toLocaleString("es")} de ${quota.cap.toLocaleString("es")} créditos`} />
        ) : (
          <p className="text-sm text-muted-foreground">Sin cupo asignado{canWrite ? " · Asignar cupo" : ""}</p>
        )}
      </div>
    </header>
  );
}

const GROUPS = [
  { label: "Configurar", items: ["Agente", "Ajustes", "Capacidades", "Conocimiento"] },
  { label: "Conectar", items: ["Canales", "Integraciones", "Puesto de trabajo"] },
  { label: "Observar", items: ["Resumen", "Conversaciones", "Playground"] },
];

function Nav({ current, compact, hide = [] }: { current: string; compact?: boolean; hide?: string[] }) {
  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => !hide.includes(i)) })).filter((g) => g.items.length);
  if (compact) {
    return (
      <NativeSelect aria-label="Sección de la ficha" defaultValue={current} wrapperClassName="w-full">
        {groups.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.items.map((i) => (
              <option key={i}>{i}</option>
            ))}
          </optgroup>
        ))}
      </NativeSelect>
    );
  }
  return (
    <nav aria-label="Sección de la ficha" className="flex flex-wrap gap-x-6 gap-y-2 border-b border-border">
      {groups.map((g) => (
        <div key={g.label} className="flex items-baseline gap-3">
          <span className="text-xs font-medium text-muted-foreground">{g.label}</span>
          <ul className="flex gap-1">
            {g.items.map((i) => (
              <li key={i}>
                <a
                  href="#"
                  aria-current={i === current ? "page" : undefined}
                  className={[
                    "-mb-px inline-block border-b-2 px-2 py-2 text-sm",
                    i === current ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                  ].join(" ")}
                >
                  {i}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function DraftBar({ screens, canPublish }: { screens: string[]; canPublish: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-status-info-border bg-status-info-bg px-3 py-2 text-sm">
      <span>
        Cambios sin publicar en <strong>{screens.join(" y ")}</strong>
        {canPublish ? null : " · Puede publicar: propietario, administrador o builder"}
      </span>
      <span className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          Ver diferencias
        </Button>
        {canPublish ? <Button size="sm">Publicar</Button> : null}
      </span>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="flex flex-col gap-(--space-block) overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Diferencias entre el borrador y la versión activa</SheetTitle>
            <SheetDescription>Borrador v4 · activa v3</SheetDescription>
          </SheetHeader>
          <Section title="Ajustes" headingLevel={3} flat>
            <DescriptionList layout="inline" items={[{ term: "Horario", detail: "Atiende siempre → L–V 9–18" }, { term: "Idiomas", detail: "español → español, inglés" }]} />
          </Section>
          <Section title="Capacidades" headingLevel={3} flat>
            <DescriptionList layout="inline" items={[{ term: "Reservas", detail: "activada" }, { term: "Consultar pedido", detail: "modo: siempre → nunca" }]} />
          </Section>
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground">
              <ChevronDown className="mr-1 inline size-4" aria-hidden="true" /> Prompt completo
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-muted p-3 font-mono text-xs">Eres el asistente de Panadería La Espiga…</pre>
          </details>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function Page({
  setup,
  quota,
  status = "active",
  phone,
  role = "owner",
  draft = [],
  compact,
}: {
  setup: Setup;
  quota: { cap: number; remaining: number } | null;
  status?: "active" | "paused" | "archived";
  phone?: string;
  role?: "owner" | "analyst";
  draft?: string[];
  compact?: boolean;
}) {
  return (
    <div className={compact ? "mx-auto flex w-96 flex-col gap-(--space-block) p-4" : "mx-auto flex max-w-(--width-content) flex-col gap-(--space-block) p-6"}>
      <Header setup={setup} quota={quota} status={status} phone={phone} role={role} />
      <Nav current="Resumen" compact={compact} hide={role === "analyst" ? ["Playground"] : []} />
      {draft.length ? <DraftBar screens={draft} canPublish={role === "owner"} /> : null}
      <Section title="Resumen" description="Lo esencial de este cliente.">
        <p className="text-sm text-muted-foreground">(contenido de la pestaña)</p>
      </Section>
    </div>
  );
}

export const FaltaCanal: Story = {
  render: () => <Page setup={{ agent: true, channel: false, quota: true, active: true, next: "channel" }} quota={{ cap: 5000, remaining: 3800 }} />,
};
export const Atendiendo: Story = {
  render: () => <Page setup={{ agent: true, channel: true, quota: true, active: true, next: null }} quota={{ cap: 5000, remaining: 3800 }} phone="+34 653 32 16 93" />,
};
export const SinCupoAsignado: Story = {
  render: () => <Page setup={{ agent: true, channel: true, quota: false, active: true, next: "quota" }} quota={null} phone="+34 653 32 16 93" />,
};
export const ConBorrador: Story = {
  render: () => <Page setup={{ agent: true, channel: true, quota: true, active: true, next: null }} quota={{ cap: 5000, remaining: 3800 }} phone="+34 653 32 16 93" draft={["Ajustes", "Capacidades"]} />,
};
export const Analyst: Story = {
  render: () => <Page role="analyst" setup={{ agent: true, channel: false, quota: true, active: true, next: "channel" }} quota={{ cap: 5000, remaining: 3800 }} draft={["Ajustes"]} />,
};
export const Archivado: Story = {
  render: () => <Page status="archived" setup={{ agent: true, channel: true, quota: true, active: false, next: "activation" }} quota={{ cap: 5000, remaining: 3800 }} />,
};
export const Movil: Story = {
  render: () => <Page compact setup={{ agent: true, channel: false, quota: true, active: true, next: "channel" }} quota={{ cap: 5000, remaining: 3800 }} draft={["Ajustes"]} />,
};
