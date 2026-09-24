import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChevronLeft, ChevronRight, MoreHorizontal, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

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
import { Meter, type MeterTone } from "../../components/meter";
import { NativeSelect } from "../../components/native-select";
import { Section } from "../../components/section";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "../../components/sheet";
import { CardSkeleton, Skeleton } from "../../components/skeleton";
import { StatusBadge } from "../../components/status-badge";
import { StatusDot } from "../../components/status-dot";
import { Stepper, type StepState } from "../../components/stepper";
import { TooltipProvider } from "../../components/tooltip";

/**
 * Prototipo · iteración 1 (spec 017, R1–R3): la cabecera de la ficha, la
 * navegación en tres grupos y la barra de borrador. Solo forma: los textos
 * son los de la consola en español, pero nada aquí importa i18n ni router.
 *
 * Reglas que fija (crítica del 2026-09-24, dos vueltas):
 *   - el badge de la cabecera responde a «¿atiende ahora?», no al ciclo de
 *     vida: Atendiendo · Sin atender (y por qué) · Con incidencia · En pausa ·
 *     Archivado; el ciclo de vida vive en el aviso y en «Más»;
 *   - los cuatro pasos son independientes: cada uno con su estado real;
 *   - la ficha tiene dos vidas: mientras falta algo, «Puesta en marcha» con UN
 *     botón; cuando ya atiende, Actividad y Crédito;
 *   - la barra de Crédito mide lo que queda, igual que su cifra;
 *   - cada incidencia se dice con hora, causa, consecuencia y una salida;
 *   - publicar pasa siempre por la hoja («Revisar y publicar»); se puede
 *     deshacer 10 minutos y el aviso no se cierra mientras dure; los puntos
 *     «sin publicar» desaparecen al publicar;
 *   - solo los atajos que hacen falta (owner, 2026-09-24): anterior y
 *     siguiente cliente, e «Ir a cliente…»; las pestañas no llevan atajo;
 *   - cada término de negocio lleva una ayuda alcanzable y hay guía;
 *   - un solo botón primario por vista; en pantalla se dice «crédito».
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

const STEP_LABEL: Record<StepKey, string> = { agent: "Agente", channel: "Canal", quota: "Crédito", activation: "Activación" };
const NEXT_ACTION: Record<StepKey, string> = {
  agent: "Preparar el agente",
  channel: "Conectar un canal",
  quota: "Asignar crédito",
  activation: "Empezar a atender",
};
const NEXT_WHY: Record<StepKey, string> = {
  agent: "Sin una versión publicada, el agente no sabe qué decir.",
  channel: "Un canal es por donde llegan los mensajes: hoy WhatsApp.",
  quota: "Los créditos son lo que el agente gasta al responder.",
  activation: "El último clic: a partir de ahí el agente atiende.",
};
const MISSING: Record<StepKey, string> = { agent: "falta el agente", channel: "falta el canal", quota: "falta crédito", activation: "falta activarlo" };
const STEP_ORDER: StepKey[] = ["agent", "channel", "quota", "activation"];

/** «5 000», también con cuatro cifras (es-ES no agrupa 4 dígitos por defecto). */
const n = (v: number) => new Intl.NumberFormat("es-ES", { minimumFractionDigits: 0 }).format(v).replace(/^(\d)(\d{3})$/, "$1 $2");

// ── Cabecera ────────────────────────────────────────────────────────────

function ServingBadge({ status, setup, incident }: { status: Status; setup: Setup; incident: Incident }) {
  if (status === "paused") return <StatusBadge tone="muted">En pausa</StatusBadge>;
  if (status === "archived") return <StatusBadge tone="muted">Archivado</StatusBadge>;
  if (incident) return <StatusBadge tone="danger">Con incidencia</StatusBadge>;
  if (setup.next) return <StatusBadge tone="warning">Sin atender · {MISSING[setup.next]}</StatusBadge>;
  return <StatusBadge tone="positive">Atendiendo</StatusBadge>;
}

function Header({ status, setup, phone, role, incident }: { status: Status; setup: Setup; phone?: string; role: Role; incident: Incident }) {
  const canWrite = role === "owner";
  const serving = status === "active" && setup.next === null && !incident;
  return (
    <header className="flex flex-col gap-(--space-stack)">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <nav aria-label="Migas">
          <a href="#" className="hover:text-foreground">
            Clientes
          </a>{" "}
          <span aria-hidden="true">/</span> <span className="text-foreground">Panadería La Espiga</span>
        </nav>
        {/* Para quien abre veinte fichas al día: anterior, siguiente, salto directo y la lista de atajos. */}
        <nav aria-label="Otros clientes" className="flex flex-wrap items-center gap-1">
          <Button variant="ghost" size="xs" aria-label="Cliente anterior: Clínica Boreal">
            <ChevronLeft aria-hidden="true" /> Clínica Boreal <Kbd aria-hidden="true">[</Kbd>
          </Button>
          <Button variant="ghost" size="xs" aria-label="Cliente siguiente: Taller Ruiz">
            Taller Ruiz <Kbd aria-hidden="true">]</Kbd> <ChevronRight aria-hidden="true" />
          </Button>
          <Button variant="outline" size="xs" aria-label="Ir a otro cliente">
            <Search aria-hidden="true" /> Ir a cliente… <Kbd aria-hidden="true">⌘K</Kbd>
          </Button>
          <Button variant="ghost" size="xs" nativeButton={false} render={<a href="#" />}>
            Guía de la ficha
          </Button>
        </nav>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-(--space-stack)">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-balance">Panadería La Espiga</h1>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <ServingBadge status={status} setup={setup} incident={incident} />
            {serving ? <span className="text-muted-foreground">desde el 23 sept 2026</span> : null}
            {phone ? <span className="text-muted-foreground">WhatsApp {phone}</span> : null}
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
      <Callout tone="danger" title="WhatsApp desconectado desde ayer a las 18:40" action={canAct ? <Button size="sm">Reconectar WhatsApp</Button> : <Button size="sm" variant="outline">Avisar al propietario</Button>}>
        Meta cerró la sesión del número. Los mensajes que lleguen mientras tanto no se responden. Reconectar tarda un minuto y no cambia nada más; si no funciona, Canales explica qué mirar en Meta.
      </Callout>
    );
  }
  return (
    <Callout tone="danger" title="Crédito agotado: el agente no responde" action={canAct ? <Button size="sm">Asignar crédito</Button> : <Button size="sm" variant="outline">Avisar al propietario</Button>}>
      Se gastaron los {n(5000)} créditos del mes el 22 de septiembre. Asigna más, o mueve crédito desde otro cliente; el agente vuelve a atender al instante.
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
  const done: Record<StepKey, boolean> = { agent: setup.agent, channel: setup.channel, quota: setup.quota, activation: setup.active };
  const steps = STEP_ORDER.map((k) => ({ key: k, label: STEP_LABEL[k], state: (done[k] ? "done" : k === setup.next ? "current" : "todo") as StepState }));
  return (
    <Section
      title={
        <span className="inline-flex items-center gap-1">
          Puesta en marcha <HelpHint label="Ayuda: puesta en marcha">Cuatro pasos, en cualquier orden, que separan a este cliente de atender. Se hacen una vez; después este bloque desaparece.</HelpHint>
        </span>
      }
      description="Lo que falta para que el agente atienda."
      className="min-w-0"
    >
      <Stepper variant="line" ariaLabel="Puesta en marcha" current={-1} steps={steps} stepOfLabel={() => `${STEP_ORDER.filter((k) => done[k]).length} de 4 pasos hechos`} />
      {setup.next ? (
        <div className="flex flex-col gap-2 pt-1">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="text-sm text-muted-foreground">Siguiente paso</span>
            {role === "owner" ? (
              <Button>{NEXT_ACTION[setup.next]}</Button>
            ) : (
              <>
                <span className="text-sm">
                  {NEXT_ACTION[setup.next]} <span className="text-muted-foreground">(lo hace el propietario)</span>
                </span>
                <Button size="sm" variant="outline">
                  Avisar al propietario
                </Button>
              </>
            )}
          </div>
          <p className="text-xs text-muted-foreground">{NEXT_WHY[setup.next]}</p>
        </div>
      ) : null}
    </Section>
  );
}

function creditTone(remaining: number, cap: number): MeterTone {
  if (remaining <= 0) return "danger";
  if (remaining / cap <= 0.2) return "warning";
  return "positive";
}

function CreditCard({ quota, status, role }: { quota: { cap: number; remaining: number } | null; status: Status; role: Role }) {
  const consumed = quota ? quota.cap - quota.remaining : 0;
  const live = status === "active";
  return (
    <Section
      title={
        <span className="inline-flex items-center gap-1">
          Crédito <HelpHint label="Ayuda: crédito">Lo que este cliente puede gastar cada mes. Un mensaje respondido cuesta unos 3 créditos. Se renueva el día 1; lo que sobra no se acumula.</HelpHint>
        </span>
      }
      actions={role === "owner" && quota && live ? <Button size="xs" variant="ghost">Ajustar</Button> : undefined}
      className="min-w-0"
    >
      {quota ? (
        <Meter
          label="Crédito restante"
          labelHidden
          value={quota.remaining}
          max={quota.cap}
          tone={creditTone(quota.remaining, quota.cap)}
          valueLabel={`Quedan ${n(quota.remaining)} de ${n(quota.cap)} créditos`}
          hint={live ? `${n(consumed)} gastados este mes · se renueva el 1 de octubre.` : `${n(consumed)} gastados este mes.`}
        />
      ) : (
        <p className="text-sm text-muted-foreground">Sin crédito asignado. El agente no puede atender hasta que se le asigne.</p>
      )}
    </Section>
  );
}

function ActivityCard({ status }: { status: Status }) {
  const live = status === "active";
  return (
    <Section
      title={
        <span className="inline-flex items-center gap-1">
          Actividad <HelpHint label="Ayuda: actividad">Solo conversaciones de clientes finales por el canal; las pruebas del Playground no cuentan.</HelpHint>
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
        items={
          live
            ? [
                { key: "conv", term: "Conversaciones (7 días)", detail: "12" },
                { key: "last", term: "Último mensaje", detail: "hace 2 h" },
                { key: "esc", term: "Escaladas a una persona", detail: "1" },
              ]
            : [
                { key: "conv", term: "Conversaciones (7 días)", detail: "0" },
                { key: "last", term: "Último mensaje", detail: "12 sept 2026" },
              ]
        }
      />
    </Section>
  );
}

// ── Navegación ──────────────────────────────────────────────────────────

const GROUPS = [
  { label: "Observar", items: ["Resumen", "Conversaciones", "Playground"] },
  { label: "Configurar", items: ["Agente", "Ajustes", "Capacidades", "Conocimiento"] },
  { label: "Conectar", items: ["Canales", "Integraciones", "Puesto de trabajo"] },
];
const TAB_HELP: Record<string, string> = {
  Playground: "Prueba el agente sin gastar el crédito del cliente ni escribir a nadie.",
  "Puesto de trabajo": "La máquina del partner que el agente puede usar para este cliente.",
  Integraciones: "Sistemas externos conectados: tienda, agenda, cobros.",
};

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
    <nav aria-label="Sección de la ficha" className="flex flex-wrap gap-x-10 gap-y-2 border-b border-border">
      <div className="flex flex-wrap gap-x-10 gap-y-2">
        {groups.map((g) => (
          <div key={g.label} className="flex flex-col gap-1">
            <span className="px-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{g.label}</span>
            <ul className="flex gap-1">
              {g.items.map((i) => (
                <li key={i} className="inline-flex items-center">
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
                    {alert.includes(i) ? <StatusDot tone="danger" label="incidencia" /> : null}
                  </a>
                  {TAB_HELP[i] ? <HelpHint label={`Ayuda: ${i}`}>{TAB_HELP[i]}</HelpHint> : null}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}

// ── Borrador ────────────────────────────────────────────────────────────

type DraftState = "pending" | "publishing" | "failed" | "published";

function DraftBar({ screens, canPublish, primary, initial = "pending", onPublished }: { screens: string[]; canPublish: boolean; primary: boolean; initial?: DraftState; onPublished?: () => void }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<DraftState>(initial);
  const successRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  // Focus moves to the success notice so a keyboard user does not land on body.
  useEffect(() => {
    if (state === "published") successRef.current?.focus();
  }, [state]);

  if (state === "published") {
    return (
      <div ref={successRef} tabIndex={-1} className="outline-none">
        <Callout tone="positive" title="Versión 4 publicada hace un momento" action={canPublish ? <Button size="sm" variant="outline" onClick={() => setState("pending")}>Deshacer · vuelve a la versión 3</Button> : undefined}>
          El agente ya responde con los cambios de Ajustes y Capacidades. Puedes deshacerlo durante 10 minutos; este aviso se cierra solo cuando pase el plazo.
        </Callout>
      </div>
    );
  }
  if (state === "failed") {
    return (
      <Callout tone="danger" title="No se pudo publicar la versión 4" action={canPublish ? <Button size="sm" onClick={() => setState("pending")}>Reintentar</Button> : undefined}>
        La versión activa sigue siendo la 3 y el borrador no se ha perdido. El servidor no respondió; suele resolverse al reintentar. Si vuelve a fallar, escríbenos desde Ayuda con la hora y el nombre del cliente.
      </Callout>
    );
  }
  return (
    <div role="status" aria-live="polite" aria-busy={state === "publishing"} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-status-info-border bg-status-info-bg px-3 py-2 text-sm">
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
      {canPublish ? (
        <Button size="sm" variant={primary ? "default" : "outline"} onClick={() => setOpen(true)} loading={state === "publishing"} aria-haspopup="dialog">
          Revisar y publicar
        </Button>
      ) : (
        <Button size="sm" variant="ghost" onClick={() => setOpen(true)} aria-haspopup="dialog">
          Ver los cambios
        </Button>
      )}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent initialFocus={titleRef} className="flex flex-col gap-(--space-block) overflow-y-auto">
          <SheetHeader>
            <SheetTitle ref={titleRef} tabIndex={-1} className="outline-none">
              Publicar la versión 4
            </SheetTitle>
            <SheetDescription>Esto es lo que cambia respecto a la versión 3, la que atiende ahora. Al publicar, el agente lo aplica al instante; podrás deshacerlo durante 10 minutos.</SheetDescription>
          </SheetHeader>
          <Section title="Ajustes" headingLevel={3} flat>
            <DescriptionList layout="inline" items={[{ term: "Horario", detail: "Atiende siempre → L–V 9–18" }, { term: "Idiomas", detail: "español → español, inglés" }]} />
          </Section>
          <Section title="Capacidades" headingLevel={3} flat>
            <DescriptionList layout="inline" items={[{ term: "Reservas", detail: "apagada → activada" }, { term: "Consultar pedido", detail: "modo siempre → nunca" }]} />
          </Section>
          <p className="text-sm text-muted-foreground">
            El prompt completo se lee en <a href="#" className="underline underline-offset-4">Agente · versión 4</a>.
          </p>
          <SheetFooter className="flex-row flex-wrap items-center justify-between gap-2">
            {canPublish ? (
              <Button variant="ghost" size="sm" className="text-destructive">
                Descartar el borrador…
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
                    window.setTimeout(() => {
                      setState("published");
                      onPublished?.();
                    }, 1200);
                  }}
                >
                  Publicar la versión 4
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
  draftState = "pending",
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
  const pending = status === "active" && setup.next !== null;
  const [marked, setMarked] = useState<string[]>(draftState === "published" ? [] : draft);
  const alertTabs = incident === "channel_down" ? ["Canales"] : [];
  return (
    <div className={compact ? "mx-auto flex w-full max-w-96 flex-col gap-(--space-section) p-4" : "mx-auto flex max-w-(--width-content) flex-col gap-(--space-section) p-8"}>
      <Header status={status} setup={setup} phone={phone} role={role} incident={incident} />

      {incident ? <IncidentNotice incident={incident} role={role} /> : null}
      {status !== "active" ? <LifecycleNotice status={status} role={role} /> : null}

      <div className={compact ? "flex flex-col gap-(--space-block)" : "grid gap-(--space-block) lg:grid-cols-[2fr_1fr]"}>
        {pending ? <SetupCard setup={setup} role={role} /> : <ActivityCard status={status} />}
        <CreditCard quota={quota} status={status} role={role} />
      </div>

      <div className="flex flex-col gap-(--space-block)">
        <Nav current="Resumen" compact={compact} hide={role === "analyst" ? ["Playground"] : []} marked={marked} alert={alertTabs} />
        {draft.length ? <DraftBar screens={draft} canPublish={canWrite} primary={!pending && !incident} initial={draftState} onPublished={() => setMarked([])} /> : null}
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
      <Nav current="Resumen" />
      <CardSkeleton lines={2} label="Cargando" />
    </div>
  );
}

const QUOTA = { cap: 5000, remaining: 3800 };
const SERVING: Setup = { agent: true, channel: true, quota: true, active: true, next: null };

export const FaltaCanal: Story = {
  render: () => <Page setup={{ agent: true, channel: false, quota: true, active: false, next: "channel" }} quota={QUOTA} />,
};
export const Atendiendo: Story = {
  render: () => <Page setup={SERVING} quota={QUOTA} phone="+34 653 32 16 93" />,
};
export const SinCreditoAsignado: Story = {
  render: () => <Page setup={{ agent: true, channel: true, quota: false, active: false, next: "quota" }} quota={null} phone="+34 653 32 16 93" />,
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
  render: () => <Page role="analyst" setup={{ agent: true, channel: false, quota: true, active: false, next: "channel" }} quota={QUOTA} draft={["Ajustes"]} />,
};
export const Archivado: Story = {
  render: () => <Page status="archived" setup={{ agent: true, channel: true, quota: true, active: false, next: "activation" }} quota={QUOTA} phone="+34 653 32 16 93" />,
};
export const Cargando: Story = { render: () => <LoadingPage /> };
export const Movil: Story = {
  render: () => <Page compact setup={{ agent: true, channel: false, quota: true, active: false, next: "channel" }} quota={QUOTA} draft={["Ajustes"]} />,
};
