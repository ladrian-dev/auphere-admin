import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChevronLeft, ChevronRight, MoreHorizontal } from "lucide-react";
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
import { HelpHint } from "../../components/help-hint";
import { Kbd } from "../../components/kbd";
import { Meter } from "../../components/meter";
import { NativeSelect } from "../../components/native-select";
import { Section } from "../../components/section";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "../../components/sheet";
import { CardSkeleton, Skeleton } from "../../components/skeleton";
import { StatusBadge } from "../../components/status-badge";
import { StatusDot } from "../../components/status-dot";
import { Stepper } from "../../components/stepper";
import { TooltipProvider } from "../../components/tooltip";

/**
 * Prototipo · iteración 1 (spec 017, R1–R3): la cabecera de la ficha, la
 * navegación en tres grupos y la barra de borrador. Solo forma: los textos
 * son los de la consola en español, pero nada aquí importa i18n ni router.
 *
 * Reglas que fija (crítica del 2026-09-24 y segunda vuelta):
 *   - la ficha tiene dos vidas: mientras falta algo, «Puesta en marcha» es un
 *     stepper con UN botón; cuando ya atiende, el stepper desaparece y su
 *     sitio lo ocupan Actividad y Crédito;
 *   - un cliente archivado o en pausa no tiene «pasos pendientes»: tiene un
 *     aviso de estado con una sola salida («Reactivar»);
 *   - un solo botón primario por vista; el segundo pasa a outline;
 *   - la barra de Crédito y su cifra dicen lo mismo («Quedan 3 800 de 5 000»);
 *   - cada incidencia (canal caído, crédito agotado, publicación fallida) se
 *     dice con su causa y su salida, nunca con un color solo;
 *   - publicar pasa siempre por la hoja de diferencias (resumen + confirmación)
 *     y se puede deshacer durante unos minutos; el borrador se puede descartar;
 *   - las pestañas con cambios sin publicar llevan un punto;
 *   - siguiente/anterior cliente y atajos de teclado para quien lleva muchos;
 *   - cada término de negocio lleva una ayuda alcanzable (HelpHint) y un
 *     enlace a la guía;
 *   - en pantalla se dice «crédito», nunca «cupo» (owner, 2026-09-24).
 */
const meta = {
  title: "Prototipos/Ficha de cliente",
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <TooltipProvider>
        <Story />
      </TooltipProvider>
    ),
  ],
} satisfies Meta;
export default meta;
type Story = StoryObj;

type StepKey = "agent" | "channel" | "quota" | "activation";
type Setup = { agent: boolean; channel: boolean; quota: boolean; active: boolean; next: StepKey | null };
type Status = "active" | "paused" | "archived";
type Role = "owner" | "analyst";
type Incident = "channel_down" | "credit_exhausted" | null;

const STEP_LABEL: Record<StepKey, string> = { agent: "Agente", channel: "Canal", quota: "Crédito", activation: "En marcha" };
const NEXT_ACTION: Record<StepKey, string> = {
  agent: "Preparar el agente",
  channel: "Conectar un canal",
  quota: "Asignar crédito",
  activation: "Activar el cliente",
};
const NEXT_WHY: Record<StepKey, string> = {
  agent: "Sin una versión publicada, el agente no sabe qué decir.",
  channel: "Un canal es por donde llegan los mensajes: hoy WhatsApp.",
  quota: "Los créditos son lo que el agente gasta al responder.",
  activation: "Activar es el último clic: a partir de ahí atiende.",
};
const STEP_ORDER: StepKey[] = ["agent", "channel", "quota", "activation"];

// ── Cabecera ────────────────────────────────────────────────────────────

function Header({ status, phone, serving, role, incident }: { status: Status; phone?: string; serving: boolean; role: Role; incident: Incident }) {
  const canWrite = role === "owner";
  const tone = incident ? "warning" : status === "active" ? "positive" : status === "paused" ? "warning" : "muted";
  const label = status === "active" ? (incident ? "Con incidencia" : "Activo") : status === "paused" ? "En pausa" : "Archivado";
  return (
    <header className="flex flex-col gap-(--space-stack)">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <nav aria-label="Migas">
          <a href="#" className="hover:text-foreground">
            Clientes
          </a>{" "}
          <span aria-hidden="true">/</span> <span className="text-foreground">Panadería La Espiga</span>
        </nav>
        {/* Siguiente/anterior cliente y sus atajos: para quien abre veinte fichas al día. */}
        <nav aria-label="Otros clientes" className="flex items-center gap-1">
          <Button variant="ghost" size="xs" aria-label="Cliente anterior: Clínica Boreal">
            <ChevronLeft aria-hidden="true" /> Clínica Boreal <Kbd aria-hidden="true">[</Kbd>
          </Button>
          <span aria-hidden="true">·</span>
          <Button variant="ghost" size="xs" aria-label="Cliente siguiente: Taller Ruiz">
            Taller Ruiz <Kbd aria-hidden="true">]</Kbd> <ChevronRight aria-hidden="true" />
          </Button>
        </nav>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-(--space-stack)">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-balance">Panadería La Espiga</h1>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <StatusBadge tone={tone}>{label}</StatusBadge>
            {serving && !incident ? <span className="text-status-positive-text">Atendiendo desde el 23 sept 2026</span> : null}
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
            <DropdownMenuContent align="end" className="w-64">
              {status === "active" ? (
                <DropdownMenuItem>
                  <span className="flex flex-col">
                    Pausar
                    <span className="text-xs text-muted-foreground">Deja de atender; se reactiva cuando quieras.</span>
                  </span>
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem>Reactivar</DropdownMenuItem>
              )}
              {status !== "archived" ? (
                <DropdownMenuItem>
                  <span className="flex flex-col">
                    Archivar
                    <span className="text-xs text-muted-foreground">Sale de la lista; nada se borra.</span>
                  </span>
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuSeparator />
              <DropdownMenuItem>Copiar referencia</DropdownMenuItem>
              {status === "archived" ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive">
                    <span className="flex flex-col">
                      Eliminar…
                      <span className="text-xs">Pide escribir el nombre. No se puede deshacer.</span>
                    </span>
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </header>
  );
}

// ── Incidencias y ciclo de vida ─────────────────────────────────────────

function IncidentNotice({ incident, role }: { incident: Exclude<Incident, null>; role: Role }) {
  const canAct = role === "owner";
  if (incident === "channel_down") {
    return (
      <Callout tone="danger" title="WhatsApp desconectado desde ayer a las 18:40" action={canAct ? <Button size="sm">Reconectar WhatsApp</Button> : undefined}>
        Meta cerró la sesión del número. Los mensajes que lleguen mientras tanto no se responden. Reconectar tarda un minuto y no cambia nada más.
      </Callout>
    );
  }
  return (
    <Callout tone="danger" title="Crédito agotado: el agente no responde" action={canAct ? <Button size="sm">Asignar crédito</Button> : undefined}>
      Se gastaron los 5 000 créditos del mes el 22 de septiembre. Asigna más, o mueve crédito desde otro cliente; el agente vuelve a atender al instante.
    </Callout>
  );
}

function LifecycleNotice({ status, role }: { status: Exclude<Status, "active">; role: Role }) {
  const isArchived = status === "archived";
  return (
    <Callout tone={isArchived ? "neutral" : "warning"} title={isArchived ? "Archivado el 12 sept 2026" : "En pausa desde el 12 sept 2026"} action={role === "owner" ? <Button size="sm" variant="outline">Reactivar</Button> : undefined}>
      El agente no atiende {isArchived ? "y el canal sigue reservado para este cliente" : "mientras el cliente esté en pausa"}. Reactivar lo devuelve a como estaba.
    </Callout>
  );
}

// ── Bloques de la primera fila ──────────────────────────────────────────

function SetupCard({ setup, role }: { setup: Setup; role: Role }) {
  const current = setup.next ? STEP_ORDER.indexOf(setup.next) : STEP_ORDER.length;
  return (
    <Section
      title={
        <span className="inline-flex items-center gap-1">
          Puesta en marcha <HelpHint>Los cuatro pasos que separan a este cliente de atender. Se hacen una vez; después este bloque desaparece.</HelpHint>
        </span>
      }
      description="Lo que falta para que el agente atienda."
      className="min-w-0"
    >
      <Stepper variant="line" ariaLabel="Puesta en marcha" current={current} steps={STEP_ORDER.map((k) => ({ key: k, label: STEP_LABEL[k] }))} stepOfLabel={(n, t) => `Paso ${n} de ${t}`} />
      {setup.next ? (
        <div className="flex flex-col gap-2 pt-1">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="text-sm text-muted-foreground">Siguiente paso</span>
            {role === "owner" ? (
              <Button size="sm">{NEXT_ACTION[setup.next]}</Button>
            ) : (
              <span className="text-sm">
                {NEXT_ACTION[setup.next]} <span className="text-muted-foreground">(lo hace el propietario)</span>
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">{NEXT_WHY[setup.next]}</p>
        </div>
      ) : null}
    </Section>
  );
}

function CreditCard({ quota, status, incident, role }: { quota: { cap: number; remaining: number } | null; status: Status; incident: Incident; role: Role }) {
  const consumed = quota ? quota.cap - quota.remaining : 0;
  const exhausted = incident === "credit_exhausted";
  return (
    <Section
      title={
        <span className="inline-flex items-center gap-1">
          Crédito <HelpHint>Lo que este cliente puede gastar cada mes. Un mensaje respondido cuesta unos 3 créditos. Se renueva el día 1; lo que sobra no se acumula.</HelpHint>
        </span>
      }
      actions={role === "owner" && quota && !exhausted ? <Button size="xs" variant="ghost">Ajustar</Button> : undefined}
      className="min-w-0"
    >
      {quota ? (
        <Meter
          label="Crédito"
          labelHidden
          value={consumed}
          max={quota.cap}
          valueLabel={exhausted ? `0 de ${quota.cap.toLocaleString("es")} créditos` : `Quedan ${quota.remaining.toLocaleString("es")} de ${quota.cap.toLocaleString("es")} créditos`}
          hint={status === "active" ? `${consumed.toLocaleString("es")} consumidos este mes · se renueva el 1 de octubre.` : `${consumed.toLocaleString("es")} consumidos este mes.`}
        />
      ) : (
        <p className="text-sm text-muted-foreground">Sin crédito asignado. El agente no puede atender hasta que se le asigne.</p>
      )}
    </Section>
  );
}

function ActivityCard() {
  return (
    <Section
      title={
        <span className="inline-flex items-center gap-1">
          Actividad <HelpHint>Solo conversaciones de clientes finales por el canal; las pruebas del Playground no cuentan.</HelpHint>
        </span>
      }
      actions={
        <Button size="xs" variant="ghost">
          Ver conversaciones
        </Button>
      }
      className="min-w-0"
    >
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

// ── Navegación ──────────────────────────────────────────────────────────

const GROUPS = [
  { label: "Configurar", items: ["Agente", "Ajustes", "Capacidades", "Conocimiento"] },
  { label: "Conectar", items: ["Canales", "Integraciones", "Puesto de trabajo"] },
  { label: "Observar", items: ["Resumen", "Conversaciones", "Playground"] },
];
const TAB_KEY: Record<string, string> = { Resumen: "1", Conversaciones: "2", Agente: "3", Capacidades: "4", Canales: "5" };

function Nav({ current, compact, hide = [], marked = [], alert = [] }: { current: string; compact?: boolean; hide?: string[]; marked?: string[]; alert?: string[] }) {
  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => !hide.includes(i)) })).filter((g) => g.items.length);
  if (compact) {
    return (
      <NativeSelect aria-label="Sección de la ficha" defaultValue={current} wrapperClassName="w-full">
        {groups.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.items.map((i) => (
              <option key={i}>{marked.includes(i) ? `${i} · sin publicar` : alert.includes(i) ? `${i} · incidencia` : i}</option>
            ))}
          </optgroup>
        ))}
      </NativeSelect>
    );
  }
  return (
    <nav aria-label="Sección de la ficha" className="flex flex-wrap items-end justify-between gap-x-10 gap-y-2 border-b border-border">
      <div className="flex flex-wrap gap-x-10 gap-y-2">
        {groups.map((g) => (
          <div key={g.label} className="flex flex-col gap-1">
            <span className="px-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{g.label}</span>
            <ul className="flex gap-1">
              {g.items.map((i) => (
                <li key={i}>
                  <a
                    href="#"
                    aria-current={i === current ? "page" : undefined}
                    title={TAB_KEY[i] ? `Atajo: G y ${TAB_KEY[i]}` : undefined}
                    className={[
                      "-mb-px inline-flex items-center gap-2 border-b-2 px-2 py-2 text-sm",
                      i === current ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                    ].join(" ")}
                  >
                    {i}
                    {marked.includes(i) ? <StatusDot tone="info" label="cambios sin publicar" /> : null}
                    {alert.includes(i) ? <StatusDot tone="danger" label="incidencia" /> : null}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <a href="#" className="pb-2 text-xs text-muted-foreground underline-offset-4 hover:underline">
        Guía de la ficha
      </a>
    </nav>
  );
}

// ── Borrador ────────────────────────────────────────────────────────────

type DraftState = "pending" | "publishing" | "failed" | "published";

function DraftBar({ screens, canPublish, primary, initial = "pending" }: { screens: string[]; canPublish: boolean; primary: boolean; initial?: DraftState }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<DraftState>(initial);

  if (state === "published") {
    return (
      <Callout tone="positive" title="Versión 4 publicada hace un momento" dismissible dismissLabel="Cerrar" action={canPublish ? <Button size="sm" variant="outline" onClick={() => setState("pending")}>Deshacer (vuelve a la v3)</Button> : undefined}>
        El agente ya responde con los cambios de Ajustes y Capacidades. Puedes deshacerlo durante 10 minutos.
      </Callout>
    );
  }
  if (state === "failed") {
    return (
      <Callout tone="danger" title="No se pudo publicar la versión 4" action={canPublish ? <Button size="sm" onClick={() => setState("pending")}>Reintentar</Button> : undefined}>
        La versión activa sigue siendo la 3 y el borrador no se ha perdido. El servidor no respondió; suele resolverse al reintentar.
      </Callout>
    );
  }
  return (
    <div role="status" aria-busy={state === "publishing"} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-status-info-border bg-status-info-bg px-3 py-2 text-sm">
      <span className="inline-flex items-center gap-2">
        <StatusDot tone="info" pulse={state === "publishing"} label="borrador" />
        <span>
          {state === "publishing" ? (
            "Publicando la versión 4…"
          ) : (
            <>
              Cambios sin publicar en <strong>{screens.join(" y ")}</strong>
              {canPublish ? null : " · Puede publicar: propietario, administrador o builder"}
            </>
          )}
        </span>
      </span>
      <span className="flex gap-2">
        <Button size="sm" variant={canPublish ? "ghost" : "outline"} onClick={() => setOpen(true)} disabled={state === "publishing"}>
          Ver diferencias
        </Button>
        {canPublish ? (
          <Button size="sm" variant={primary ? "default" : "outline"} onClick={() => setOpen(true)} loading={state === "publishing"}>
            Publicar…
          </Button>
        ) : null}
      </span>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="flex flex-col gap-(--space-block) overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Publicar la versión 4</SheetTitle>
            <SheetDescription>Esto es lo que cambia respecto a la versión 3, la que atiende ahora. Al publicar, el agente lo aplica al instante; podrás deshacerlo durante 10 minutos.</SheetDescription>
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
          <SheetFooter className="flex-row flex-wrap items-center justify-between gap-2">
            {canPublish ? (
              <Button variant="ghost" size="sm" className="text-destructive">
                Descartar borrador…
              </Button>
            ) : (
              <span />
            )}
            <span className="flex gap-2">
              <Button variant="outline" onClick={() => setOpen(false)}>
                Cerrar
              </Button>
              {canPublish ? (
                <Button
                  onClick={() => {
                    setOpen(false);
                    setState("publishing");
                    window.setTimeout(() => setState("published"), 1200);
                  }}
                >
                  Publicar v4
                </Button>
              ) : null}
            </span>
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
  draftState,
  incident = null,
  compact,
}: {
  setup: Setup;
  quota: { cap: number; remaining: number } | null;
  status?: Status;
  phone?: string;
  role?: Role;
  draft?: string[];
  draftState?: DraftState;
  incident?: Incident;
  compact?: boolean;
}) {
  const canWrite = role === "owner";
  const serving = status === "active" && setup.next === null;
  const pending = status === "active" && setup.next !== null;
  const alertTabs = incident === "channel_down" ? ["Canales"] : [];
  return (
    <div className={compact ? "mx-auto flex w-96 flex-col gap-(--space-section) p-4" : "mx-auto flex max-w-(--width-content) flex-col gap-(--space-section) p-8"}>
      <Header status={status} phone={phone} serving={serving} role={role} incident={incident} />

      {incident ? <IncidentNotice incident={incident} role={role} /> : null}
      {status !== "active" ? <LifecycleNotice status={status} role={role} /> : null}

      <div className={compact ? "flex flex-col gap-(--space-block)" : "grid gap-(--space-block) lg:grid-cols-[2fr_1fr]"}>
        {pending ? <SetupCard setup={setup} role={role} /> : <ActivityCard />}
        <CreditCard quota={quota} status={status} incident={incident} role={role} />
      </div>

      <div className="flex flex-col gap-(--space-block)">
        <Nav current="Resumen" compact={compact} hide={role === "analyst" ? ["Playground"] : []} marked={draft} alert={alertTabs} />
        {draft.length ? <DraftBar screens={draft} canPublish={canWrite} primary={!pending && !incident} initial={draftState} /> : null}
        <Section title="Resumen">
          <p className="text-sm text-muted-foreground">(contenido de la pestaña)</p>
        </Section>
      </div>
    </div>
  );
}

function LoadingPage() {
  return (
    <div className="mx-auto flex max-w-(--width-content) flex-col gap-(--space-section) p-8" aria-busy="true" aria-label="Cargando la ficha">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-3 w-48" />
        <Skeleton className="h-8 w-80" />
        <Skeleton className="h-5 w-64" />
      </div>
      <div className="grid gap-(--space-block) lg:grid-cols-[2fr_1fr]">
        <CardSkeleton lines={3} label="Cargando" />
        <CardSkeleton lines={2} label="Cargando" />
      </div>
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

const QUOTA = { cap: 5000, remaining: 3800 };
const SERVING: Setup = { agent: true, channel: true, quota: true, active: true, next: null };

export const FaltaCanal: Story = {
  render: () => <Page setup={{ agent: true, channel: false, quota: true, active: true, next: "channel" }} quota={QUOTA} />,
};
export const Atendiendo: Story = {
  render: () => <Page setup={SERVING} quota={QUOTA} phone="+34 653 32 16 93" />,
};
export const SinCreditoAsignado: Story = {
  render: () => <Page setup={{ agent: true, channel: true, quota: false, active: true, next: "quota" }} quota={null} phone="+34 653 32 16 93" />,
};
export const ConBorrador: Story = {
  render: () => <Page setup={SERVING} quota={QUOTA} phone="+34 653 32 16 93" draft={["Ajustes", "Capacidades"]} />,
};
export const PublicacionFallida: Story = {
  render: () => <Page setup={SERVING} quota={QUOTA} phone="+34 653 32 16 93" draft={["Ajustes", "Capacidades"]} draftState="failed" />,
};
export const RecienPublicado: Story = {
  render: () => <Page setup={SERVING} quota={QUOTA} phone="+34 653 32 16 93" draft={["Ajustes", "Capacidades"]} draftState="published" />,
};
export const CanalCaido: Story = {
  render: () => <Page setup={SERVING} quota={QUOTA} phone="+34 653 32 16 93" incident="channel_down" />,
};
export const CreditoAgotado: Story = {
  render: () => <Page setup={SERVING} quota={{ cap: 5000, remaining: 0 }} phone="+34 653 32 16 93" incident="credit_exhausted" />,
};
export const Analyst: Story = {
  render: () => <Page role="analyst" setup={{ agent: true, channel: false, quota: true, active: true, next: "channel" }} quota={QUOTA} draft={["Ajustes"]} />,
};
export const Archivado: Story = {
  render: () => <Page status="archived" setup={{ agent: true, channel: true, quota: true, active: false, next: "activation" }} quota={QUOTA} phone="+34 653 32 16 93" />,
};
export const Cargando: Story = { render: () => <LoadingPage /> };
export const Movil: Story = {
  render: () => <Page compact setup={{ agent: true, channel: false, quota: true, active: true, next: "channel" }} quota={QUOTA} draft={["Ajustes"]} />,
};
