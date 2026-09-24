import type { Meta, StoryObj } from "@storybook/react-vite";
import { MoreHorizontal } from "lucide-react";
import { useState } from "react";

import { Button } from "../../components/button";
import { Callout } from "../../components/callout";
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
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "../../components/sheet";
import { StatusBadge } from "../../components/status-badge";
import { StatusDot } from "../../components/status-dot";
import { Stepper } from "../../components/stepper";

/**
 * Prototipo · iteración 1 (spec 017, R1–R3): la cabecera de la ficha, la
 * navegación en tres grupos y la barra de borrador. Solo forma: los textos
 * son los de la consola en español, pero nada aquí importa i18n ni router.
 *
 * Reglas que fija (tras la crítica del 2026-09-24, 20/40):
 *   - la ficha tiene dos vidas: mientras falta algo, «Puesta en marcha» es un
 *     stepper con UN botón; cuando ya atiende, el stepper desaparece y su
 *     sitio lo ocupan Crédito y Actividad;
 *   - un cliente archivado o en pausa no tiene «pasos pendientes»: tiene un
 *     aviso de estado con una sola salida («Reactivar»);
 *   - un solo botón primario por vista; el segundo pasa a outline;
 *   - la barra de Crédito y su cifra dicen lo mismo («Quedan 3 800 de 5 000»);
 *   - las pestañas con cambios sin publicar llevan un punto; la hoja de
 *     diferencias publica desde su pie;
 *   - en pantalla se dice «crédito», nunca «cupo» (owner, 2026-09-24).
 */
const meta = { title: "Prototipos/Ficha de cliente", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj;

type StepKey = "agent" | "channel" | "quota" | "activation";
type Setup = { agent: boolean; channel: boolean; quota: boolean; active: boolean; next: StepKey | null };
type Status = "active" | "paused" | "archived";
type Role = "owner" | "analyst";

const STEP_LABEL: Record<StepKey, string> = { agent: "Agente", channel: "Canal", quota: "Crédito", activation: "En marcha" };
const NEXT_ACTION: Record<StepKey, string> = {
  agent: "Preparar el agente",
  channel: "Conectar un canal",
  quota: "Asignar crédito",
  activation: "Activar el cliente",
};
const STEP_ORDER: StepKey[] = ["agent", "channel", "quota", "activation"];

// ── Cabecera ────────────────────────────────────────────────────────────

function Header({ status, phone, serving, role }: { status: Status; phone?: string; serving: boolean; role: Role }) {
  const canWrite = role === "owner";
  const tone = status === "active" ? "positive" : status === "paused" ? "warning" : "muted";
  const label = status === "active" ? "Activo" : status === "paused" ? "En pausa" : "Archivado";
  return (
    <header className="flex flex-col gap-(--space-stack)">
      <nav aria-label="Migas" className="text-xs text-muted-foreground">
        Clientes <span aria-hidden="true">/</span> <span className="text-foreground">Panadería La Espiga</span>
      </nav>
      <div className="flex flex-wrap items-start justify-between gap-(--space-stack)">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-balance">Panadería La Espiga</h1>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <StatusBadge tone={tone}>{label}</StatusBadge>
            {serving ? <span className="text-status-positive-text">Atendiendo desde el 23 sept 2026</span> : null}
            {phone ? (
              <span className="text-muted-foreground">WhatsApp {phone}</span>
            ) : status === "active" ? (
              <span className="text-muted-foreground">Sin canal conectado</span>
            ) : null}
          </div>
        </div>
        {canWrite ? (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant="outline" size="sm" aria-label="Más acciones">
                  <MoreHorizontal aria-hidden="true" /> Más
                </Button>
              }
            />
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
    </header>
  );
}

// ── Bloques de la primera fila ──────────────────────────────────────────

/** Mientras falta algo: stepper + un solo botón, pegado a su frase. */
function SetupCard({ setup, role }: { setup: Setup; role: Role }) {
  const current = setup.next ? STEP_ORDER.indexOf(setup.next) : STEP_ORDER.length;
  return (
    <Section title="Puesta en marcha" description="Lo que falta para que el agente atienda." className="min-w-0">
      <Stepper variant="line" ariaLabel="Puesta en marcha" current={current} steps={STEP_ORDER.map((k) => ({ key: k, label: STEP_LABEL[k] }))} stepOfLabel={(n, t) => `Paso ${n} de ${t}`} />
      {setup.next ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-1">
          <span className="text-sm text-muted-foreground">Siguiente paso</span>
          {role === "owner" ? (
            <Button size="sm">{NEXT_ACTION[setup.next]}</Button>
          ) : (
            <span className="text-sm">
              {NEXT_ACTION[setup.next]} <span className="text-muted-foreground">(lo hace el propietario)</span>
            </span>
          )}
        </div>
      ) : null}
    </Section>
  );
}

function CreditCard({ quota, status, pendingIsQuota }: { quota: { cap: number; remaining: number } | null; status: Status; pendingIsQuota: boolean }) {
  const consumed = quota ? quota.cap - quota.remaining : 0;
  return (
    <Section title="Crédito" className="min-w-0">
      {quota ? (
        <Meter
          label="Crédito"
          labelHidden
          value={consumed}
          max={quota.cap}
          valueLabel={`Quedan ${quota.remaining.toLocaleString("es")} de ${quota.cap.toLocaleString("es")} créditos`}
          hint={status === "active" ? `${consumed.toLocaleString("es")} consumidos este mes · se renueva el 1 de octubre.` : `${consumed.toLocaleString("es")} consumidos este mes.`}
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          Sin crédito asignado.{pendingIsQuota ? " El agente no puede atender hasta que se le asigne." : ""}
        </p>
      )}
    </Section>
  );
}

/** Cuando ya atiende: lo que cambia cada día ocupa el sitio del stepper. */
function ActivityCard() {
  return (
    <Section title="Actividad" className="min-w-0">
      <DescriptionList
        layout="inline"
        dense
        items={[
          { key: "conv", term: "Conversaciones (7 días)", detail: "12" },
          { key: "last", term: "Último mensaje", detail: "hace 2 h" },
          { key: "esc", term: "Escaladas a una persona", detail: "1" },
        ]}
      />
    </Section>
  );
}

function LifecycleNotice({ status }: { status: Exclude<Status, "active"> }) {
  const isArchived = status === "archived";
  return (
    <Callout tone={isArchived ? "neutral" : "warning"} title={isArchived ? "Archivado el 12 sept 2026" : "En pausa desde el 12 sept 2026"} action={<Button size="sm" variant="outline">Reactivar</Button>}>
      El agente no atiende {isArchived ? "y el canal sigue reservado para este cliente" : "mientras el cliente esté en pausa"}.
    </Callout>
  );
}

// ── Navegación ──────────────────────────────────────────────────────────

const GROUPS = [
  { label: "Configurar", items: ["Agente", "Ajustes", "Capacidades", "Conocimiento"] },
  { label: "Conectar", items: ["Canales", "Integraciones", "Puesto de trabajo"] },
  { label: "Observar", items: ["Resumen", "Conversaciones", "Playground"] },
];

function Nav({ current, compact, hide = [], marked = [] }: { current: string; compact?: boolean; hide?: string[]; marked?: string[] }) {
  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => !hide.includes(i)) })).filter((g) => g.items.length);
  if (compact) {
    return (
      <NativeSelect aria-label="Sección de la ficha" defaultValue={current} wrapperClassName="w-full">
        {groups.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.items.map((i) => (
              <option key={i}>{marked.includes(i) ? `${i} · sin publicar` : i}</option>
            ))}
          </optgroup>
        ))}
      </NativeSelect>
    );
  }
  return (
    <nav aria-label="Sección de la ficha" className="flex flex-wrap gap-x-10 gap-y-2 border-b border-border">
      {groups.map((g) => (
        <div key={g.label} className="flex flex-col gap-1">
          <span className="px-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{g.label}</span>
          <ul className="flex gap-1">
            {g.items.map((i) => (
              <li key={i}>
                <a
                  href="#"
                  aria-current={i === current ? "page" : undefined}
                  className={[
                    "-mb-px inline-flex items-center gap-2 border-b-2 px-2 py-2 text-sm",
                    i === current ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                  ].join(" ")}
                >
                  {i}
                  {marked.includes(i) ? <StatusDot tone="info" label="cambios sin publicar" /> : null}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

// ── Borrador ────────────────────────────────────────────────────────────

function DraftBar({ screens, canPublish, primary }: { screens: string[]; canPublish: boolean; primary: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-status-info-border bg-status-info-bg px-3 py-2 text-sm">
      <span>
        Cambios sin publicar en <strong>{screens.join(" y ")}</strong>
        {canPublish ? null : " · Puede publicar: propietario, administrador o builder"}
      </span>
      <span className="flex gap-2">
        <Button size="sm" variant={canPublish ? "ghost" : "outline"} onClick={() => setOpen(true)}>
          Ver diferencias
        </Button>
        {canPublish ? (
          <Button size="sm" variant={primary ? "default" : "outline"} onClick={() => setOpen(true)}>
            Publicar…
          </Button>
        ) : null}
      </span>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="flex flex-col gap-(--space-block) overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Cambios sin publicar</SheetTitle>
            <SheetDescription>Borrador v4 frente a la versión activa v3. Publicar los aplica al agente al instante.</SheetDescription>
          </SheetHeader>
          <Section title="Ajustes" headingLevel={3} flat>
            <DescriptionList layout="inline" items={[{ term: "Horario", detail: "Atiende siempre → L–V 9–18" }, { term: "Idiomas", detail: "español → español, inglés" }]} />
          </Section>
          <Section title="Capacidades" headingLevel={3} flat>
            <DescriptionList layout="inline" items={[{ term: "Reservas", detail: "apagada → activada" }, { term: "Consultar pedido", detail: "modo siempre → nunca" }]} />
          </Section>
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground">Prompt completo</summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-muted p-3 font-mono text-xs">Eres el asistente de Panadería La Espiga…</pre>
          </details>
          <SheetFooter className="flex-row justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cerrar
            </Button>
            {canPublish ? <Button onClick={() => setOpen(false)}>Publicar v4</Button> : null}
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  );
}

// ── Página ──────────────────────────────────────────────────────────────

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
  status?: Status;
  phone?: string;
  role?: Role;
  draft?: string[];
  compact?: boolean;
}) {
  const canWrite = role === "owner";
  const serving = status === "active" && setup.next === null;
  const pending = status === "active" && setup.next !== null;
  return (
    <div className={compact ? "mx-auto flex w-96 flex-col gap-(--space-section) p-4" : "mx-auto flex max-w-(--width-content) flex-col gap-(--space-section) p-8"}>
      <Header status={status} phone={phone} serving={serving} role={role} />

      {status !== "active" ? <LifecycleNotice status={status} /> : null}
      <div className={compact ? "flex flex-col gap-(--space-block)" : "grid gap-(--space-block) lg:grid-cols-[2fr_1fr]"}>
        {pending ? <SetupCard setup={setup} role={role} /> : <ActivityCard />}
        <CreditCard quota={quota} status={status} pendingIsQuota={setup.next === "quota"} />
      </div>

      <div className="flex flex-col gap-(--space-block)">
        <Nav current="Resumen" compact={compact} hide={role === "analyst" ? ["Playground"] : []} marked={draft} />
        {draft.length ? <DraftBar screens={draft} canPublish={canWrite} primary={!pending} /> : null}
        <Section title="Resumen">
          <p className="text-sm text-muted-foreground">(contenido de la pestaña)</p>
        </Section>
      </div>
    </div>
  );
}

const QUOTA = { cap: 5000, remaining: 3800 };

export const FaltaCanal: Story = {
  render: () => <Page setup={{ agent: true, channel: false, quota: true, active: true, next: "channel" }} quota={QUOTA} />,
};
export const Atendiendo: Story = {
  render: () => <Page setup={{ agent: true, channel: true, quota: true, active: true, next: null }} quota={QUOTA} phone="+34 653 32 16 93" />,
};
export const SinCreditoAsignado: Story = {
  render: () => <Page setup={{ agent: true, channel: true, quota: false, active: true, next: "quota" }} quota={null} phone="+34 653 32 16 93" />,
};
export const ConBorrador: Story = {
  render: () => <Page setup={{ agent: true, channel: true, quota: true, active: true, next: null }} quota={QUOTA} phone="+34 653 32 16 93" draft={["Ajustes", "Capacidades"]} />,
};
export const Analyst: Story = {
  render: () => <Page role="analyst" setup={{ agent: true, channel: false, quota: true, active: true, next: "channel" }} quota={QUOTA} draft={["Ajustes"]} />,
};
export const Archivado: Story = {
  render: () => <Page status="archived" setup={{ agent: true, channel: true, quota: true, active: false, next: "activation" }} quota={QUOTA} phone="+34 653 32 16 93" />,
};
export const Movil: Story = {
  render: () => <Page compact setup={{ agent: true, channel: false, quota: true, active: true, next: "channel" }} quota={QUOTA} draft={["Ajustes"]} />,
};
