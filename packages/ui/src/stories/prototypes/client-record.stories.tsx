import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChevronLeft, ChevronRight, CircleHelp, MoreHorizontal, Search } from "lucide-react";
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
import { Kbd, ShortcutKbd } from "../../components/kbd";
import { Meter, type MeterTone } from "../../components/meter";
import { NativeSelect } from "../../components/native-select";
import { Section } from "../../components/section";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "../../components/sheet";
import { CardSkeleton, Skeleton } from "../../components/skeleton";
import { StatusBadge } from "../../components/status-badge";
import { StatusDot } from "../../components/status-dot";
import { Stepper, type StepState } from "../../components/stepper";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../../components/tooltip";
import { UiCopyProvider } from "../../components/ui-copy";

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
      <UiCopyProvider copy={{ close: "Cerrar", cancel: "Cancelar", confirm: "Confirmar", loading: "Cargando" }}>
        <TooltipProvider>
          <Story />
        </TooltipProvider>
      </UiCopyProvider>
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
  const lifecycleItems = canWrite && status !== "archived";
  return (
    <header className="flex flex-col gap-(--space-stack)">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted-foreground">
        <nav aria-label="Migas" className="mr-auto">
          <a href="#" className="hover:text-foreground">
            Clientes
          </a>{" "}
          <span aria-hidden="true">/</span> <span className="text-foreground">Panadería La Espiga</span>
        </nav>
        {/* Para quien abre veinte fichas al día: anterior, siguiente, salto directo y la lista de atajos. */}
        <nav aria-label="Otros clientes" className="flex flex-wrap items-center gap-1">
          <Tooltip>
            <TooltipTrigger render={<Button variant="ghost" size="icon-xs" aria-label="Cliente anterior: Clínica Boreal" />}>
              <ChevronLeft aria-hidden="true" />
            </TooltipTrigger>
            <TooltipContent side="bottom">
              Anterior: Clínica Boreal <Kbd>[</Kbd>
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger render={<Button variant="ghost" size="icon-xs" aria-label="Cliente siguiente: Taller Ruiz" />}>
              <ChevronRight aria-hidden="true" />
            </TooltipTrigger>
            <TooltipContent side="bottom">
              Siguiente: Taller Ruiz <Kbd>]</Kbd>
            </TooltipContent>
          </Tooltip>
          <Button variant="outline" size="xs" aria-label="Ir a otro cliente">
            <Search aria-hidden="true" /> Ir a cliente… <ShortcutKbd keyName="K" aria-hidden="true" className="hidden sm:inline-flex" />
          </Button>
        </nav>
        <nav aria-label="Ayuda" className="flex items-center">
          <Button variant="ghost" size="xs" nativeButton={false} render={<a href="#" />}>
            <CircleHelp aria-hidden="true" /> Guía de la ficha
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
        {!lifecycleItems && status !== "archived" ? (
          <Button variant="ghost" size="sm">
            Copiar referencia
          </Button>
        ) : (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="outline" size="sm" aria-label="Más acciones">
                <MoreHorizontal aria-hidden="true" /> Más
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="w-64">
            {canWrite && serving ? (
              <DropdownMenuItem>
                <span className="flex flex-col">
                  Pausar
                  <span className="text-xs text-muted-foreground">Deja de atender; se reactiva cuando quieras.</span>
                </span>
              </DropdownMenuItem>
            ) : null}
            {canWrite && status !== "archived" ? (
              <>
                <DropdownMenuItem>
                  <span className="flex flex-col">
                    Archivar
                    <span className="text-xs text-muted-foreground">Sale de la lista; nada se borra.</span>
                  </span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            ) : null}
            <DropdownMenuItem>
              <span className="flex flex-col">
                Copiar referencia
                <span className="text-xs text-muted-foreground">El identificador de este cliente en la API.</span>
              </span>
            </DropdownMenuItem>
            {canWrite && status === "archived" ? (
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
        )}
      </div>
    </header>
  );
}

// ── Incidencias y ciclo de vida ─────────────────────────────────────────

function IncidentNotice({ incident, role }: { incident: Exclude<Incident, null>; role: Role }) {
  const canAct = role === "owner";
  if (incident === "channel_down") {
    return (
      <Callout tone="danger" title="WhatsApp desconectado desde ayer a las 18:40" action={canAct ? <Button size="sm">Reconectar WhatsApp</Button> : <Button size="sm" variant="outline">Avisar por correo al propietario</Button>}>
        Meta cerró la sesión del número. Los mensajes que lleguen mientras tanto no se responden. Reconectar tarda un minuto y no cambia nada más; si no funciona, Canales explica qué mirar en Meta.{canAct ? "" : " Lo hace el propietario, un administrador o un builder."}
      </Callout>
    );
  }
  return (
    <Callout tone="danger" title="Crédito agotado: el agente no responde" action={canAct ? <Button size="sm">Añadir crédito</Button> : <Button size="sm" variant="outline">Avisar por correo al propietario</Button>}>
      Se gastaron los {n(5000)} créditos del mes el 22 de septiembre. Añade crédito, o muévelo desde otro cliente que lo tenga de sobra; el agente vuelve a atender al instante.{canAct ? "" : " Lo hace el propietario, un administrador o un builder."}
    </Callout>
  );
}

function LifecycleNotice({ status, role }: { status: Exclude<Status, "active">; role: Role }) {
  const isArchived = status === "archived";
  return (
    <Callout tone={isArchived ? "neutral" : "warning"} title={isArchived ? "Archivado el 12 sept 2026" : "En pausa desde el 12 sept 2026"} action={role === "owner" ? <Button size="sm" variant="outline">Reactivar</Button> : undefined}>
      El agente no atiende {isArchived ? "y el canal sigue reservado para este cliente" : "mientras el cliente esté en pausa"}. Reactivar lo devuelve a como estaba, con la versión 3 del agente.
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
          Puesta en marcha <HelpHint label="Ayuda: puesta en marcha" side="top">Cuatro pasos, en cualquier orden, que separan a este cliente de atender. Se hacen una vez; después este bloque desaparece.</HelpHint>
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
                  {NEXT_ACTION[setup.next]} <span className="text-muted-foreground">(lo hace el propietario, un administrador o un builder)</span>
                </span>
                <Button size="sm" variant="outline">
                  Avisar por correo al propietario
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

function CreditCard({ quota, status, role, incident, pending }: { quota: { cap: number; remaining: number } | null; status: Status; role: Role; incident: Incident; pending: boolean }) {
  const consumed = quota ? quota.cap - quota.remaining : 0;
  const live = status === "active" && !pending;
  const exhausted = quota !== null && quota.remaining <= 0;
  return (
    <Section
      title={
        <span className="inline-flex items-center gap-1">
          Crédito <HelpHint label="Ayuda: crédito">Lo que este cliente puede gastar cada mes. Un mensaje respondido cuesta unos 3 créditos. Se renueva el día 1; lo que sobra no se acumula.</HelpHint>
        </span>
      }
      actions={role === "owner" && quota && live && !incident ? <Button size="xs" variant="ghost">Cambiar crédito</Button> : undefined}
      className="min-w-0"
    >
      {quota ? (
        <Meter
          label="Crédito restante"
          labelHidden
          value={quota.remaining}
          max={quota.cap}
          tone={live ? creditTone(quota.remaining, quota.cap) : exhausted ? "danger" : "neutral"}
          valueLabel={`Quedan ${n(quota.remaining)} de ${n(quota.cap)} créditos`}
          hint={live ? `${n(consumed)} gastados este mes · se renueva el 1 de octubre.` : consumed ? `${n(consumed)} gastados este mes.` : "Todavía sin gasto: el agente aún no atiende."}
          className={exhausted ? "[&_progress]:bg-status-danger-bg [&_progress::-webkit-progress-bar]:bg-status-danger-bg" : undefined}
        />
      ) : (
        <p className="text-sm text-muted-foreground">Sin crédito asignado. El agente no puede atender hasta que se le asigne.</p>
      )}
    </Section>
  );
}

function ActivityCard({ status, incident }: { status: Status; incident: Incident }) {
  const live = status === "active";
  const last = incident === "channel_down" ? "ayer, 18:35" : incident === "credit_exhausted" ? "22 sept 2026" : "hace 2 h";
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
                { key: "conv", term: "Conversaciones (7 días)", detail: incident ? "4" : "12" },
                { key: "last", term: "Último mensaje", detail: last },
                { key: "esc", term: "Escaladas a una persona (7 días)", detail: "1" },
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

type DiffRow = { term: string; before: string; after: string; narrows?: string };

/** Antes / ahora en dos columnas; lo que recorta lleva su aviso. */
function DiffTable({ title, rows }: { title: string; rows: DiffRow[] }) {
  return (
    <Section title={title} headingLevel={3} flat>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th scope="col" className="pb-1 font-medium">
              Qué
            </th>
            <th scope="col" className="pb-1 font-medium">
              Antes
            </th>
            <th scope="col" className="pb-1 font-medium">
              Ahora
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.term} className="border-t border-border align-top">
              <th scope="row" className="py-2 pr-3 text-left font-normal text-muted-foreground">
                {r.term}
              </th>
              <td className="py-2 pr-3 text-muted-foreground">{r.before}</td>
              <td className="py-2 font-medium">
                {r.after}
                {r.narrows ? (
                  <span className="mt-1 flex items-start gap-1 text-xs font-normal text-warning">
                    <StatusDot tone="warning" label="recorta" className="mt-1" /> {r.narrows}
                  </span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

type DraftState = "pending" | "publishing" | "failed" | "published";

function DraftBar({ screens, canPublish, primary, initial = "pending", onPublished }: { screens: string[]; canPublish: boolean; primary: boolean; initial?: DraftState; onPublished?: () => void }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<DraftState>(initial);
  const successRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  // A keyboard user never lands on body: the bar takes focus while it
  // publishes, the success notice when it is done.
  useEffect(() => {
    if (state === "published") successRef.current?.focus();
    if (state === "publishing") barRef.current?.focus();
  }, [state]);

  function publish() {
    setOpen(false);
    setState("publishing");
    window.setTimeout(() => {
      setState("published");
      onPublished?.();
    }, 1200);
  }

  const failed = state === "failed";
  if (state === "published") {
    return (
      <div ref={successRef} tabIndex={-1} className="outline-none">
        <Callout tone="positive" title="Versión 4 publicada hace un momento" action={canPublish ? <Button size="sm" variant="outline" onClick={() => setState("pending")}>Deshacer</Button> : undefined}>
          El agente ya responde con los cambios de Ajustes y Capacidades. Deshacer vuelve a la versión 3; quedan 9 minutos y este aviso se cierra solo al terminar.
        </Callout>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
    <div
      ref={barRef}
      tabIndex={-1}
      role={failed ? "alert" : "status"}
      aria-live="polite"
      aria-busy={state === "publishing"}
      className={[
        "flex flex-col gap-2 rounded-md border px-3 py-2 text-sm outline-none",
        failed ? "border-status-danger-border bg-status-danger-bg" : "border-status-info-border bg-status-info-bg",
      ].join(" ")}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-2">
          <StatusDot tone={failed ? "danger" : "info"} pulse={state === "publishing"} label={failed ? "fallo" : "borrador"} />
          <span>
            {state === "publishing" ? (
              "Publicando la versión 4…"
            ) : failed ? (
              <strong>No se pudo publicar la versión 4</strong>
            ) : (
              <>
                Cambios sin publicar en <strong>{screens.join(" y ")}</strong> · Marta, hace 40 min
                {canPublish ? null : " · Puede publicar: propietario, administrador o builder"}
              </>
            )}
          </span>
        </span>
        <span className="flex gap-2">
          {failed && canPublish ? (
            <Button size="sm" variant="outline" onClick={() => setOpen(true)} aria-haspopup="dialog">
              Ver los cambios
            </Button>
          ) : null}
          {canPublish ? (
            <Button size="sm" variant={primary ? "default" : "outline"} onClick={failed ? publish : () => setOpen(true)} loading={state === "publishing"} aria-haspopup={failed ? undefined : "dialog"}>
              {failed ? "Reintentar" : "Revisar y publicar"}
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setOpen(true)} aria-haspopup="dialog">
              Ver los cambios
            </Button>
          )}
        </span>
      </div>
      {failed ? (
        <p className="text-xs text-pretty">
          La versión activa sigue siendo la 3 y el borrador no se ha perdido. El servidor no respondió; suele resolverse al reintentar. Si vuelve a fallar,{" "}
          <a href="#" className="underline underline-offset-4">
            avisa a soporte
          </a>{" "}
          (el aviso ya lleva el cliente, la versión y la hora).
        </p>
      ) : null}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent initialFocus={titleRef} className="flex flex-col gap-(--space-block) overflow-y-auto">
          <SheetHeader>
            <SheetTitle ref={titleRef} tabIndex={-1} className="outline-none">
              Publicar la versión 4
            </SheetTitle>
            <SheetDescription>Cuatro cambios de Marta (hace 40 min) respecto a la versión 3, la que atiende ahora; dos recortan el servicio. Al publicar, el agente los aplica al instante; podrás deshacerlo durante 10 minutos.</SheetDescription>
          </SheetHeader>
          <DiffTable
            title="Ajustes"
            rows={[
              { term: "Horario", before: "Atiende siempre", after: "Lunes a viernes, 9–18", narrows: "Fuera de ese horario el agente no responderá." },
              { term: "Idiomas", before: "español", after: "español, inglés" },
            ]}
          />
          <DiffTable
            title="Capacidades"
            rows={[
              { term: "Reservas", before: "apagada", after: "activada" },
              { term: "Consultar pedido", before: "permitida siempre", after: "nunca", narrows: "Los clientes finales dejarán de poder consultar sus pedidos." },
            ]}
          />
          <p className="text-sm text-muted-foreground">
            El prompt completo se lee en <a href="#" className="underline underline-offset-4">Agente · versión 4</a>.
            {canPublish ? (
              <>
                {" "}
                Si no quieres estos cambios,{" "}
                <button type="button" className="text-destructive underline underline-offset-4">
                  descarta el borrador…
                </button>{" "}
                (te pedirá confirmar; se pierden los cuatro cambios).
              </>
            ) : null}
          </p>
          <SheetFooter className="mt-0 flex-row justify-end gap-2 px-0">
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cerrar
            </Button>
            {canPublish ? <Button onClick={publish}>Publicar la versión 4</Button> : null}
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
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
        {pending ? <SetupCard setup={setup} role={role} /> : <ActivityCard status={status} incident={incident} />}
        <CreditCard quota={quota} status={status} role={role} incident={incident} pending={pending} />
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
      <Skeleton className="h-10 w-full" />
      <CardSkeleton lines={2} label="Cargando" />
    </div>
  );
}

const QUOTA = { cap: 5000, remaining: 3800 };
const SERVING: Setup = { agent: true, channel: true, quota: true, active: true, next: null };

export const FaltaCanal: Story = {
  render: () => <Page setup={{ agent: true, channel: false, quota: true, active: false, next: "channel" }} quota={{ cap: 5000, remaining: 5000 }} />,
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
  render: () => <Page role="analyst" setup={{ agent: true, channel: false, quota: true, active: false, next: "channel" }} quota={{ cap: 5000, remaining: 5000 }} draft={["Ajustes"]} />,
};
export const Archivado: Story = {
  render: () => <Page status="archived" setup={{ agent: true, channel: true, quota: true, active: false, next: null }} quota={QUOTA} phone="+34 653 32 16 93" />,
};
export const Cargando: Story = { render: () => <LoadingPage /> };
export const Movil: Story = {
  render: () => <Page compact setup={{ agent: true, channel: false, quota: true, active: false, next: "channel" }} quota={{ cap: 5000, remaining: 5000 }} draft={["Ajustes"]} />,
};
