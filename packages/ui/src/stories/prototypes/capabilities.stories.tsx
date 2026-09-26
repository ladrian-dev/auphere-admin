import type { Meta, StoryObj } from "@storybook/react-vite";
import { Search, Wrench } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "../../components/button";
import { Callout } from "../../components/callout";
import { EmptyState } from "../../components/empty-state";
import { HelpHint } from "../../components/help-hint";
import { Input } from "../../components/input";
import { NativeSelect } from "../../components/native-select";
import { Section } from "../../components/section";
import { StatusBadge } from "../../components/status-badge";
import { Switch } from "../../components/switch";
import { TooltipProvider } from "../../components/tooltip";
import { UiCopyProvider } from "../../components/ui-copy";

/**
 * Prototipo · iteración 2 (spec 017, R4–R5): Capacidades e Integraciones.
 *
 * Funde Herramientas y Habilidades en una sola pantalla, agrupada por lo que
 * el negocio quiere conseguir en vez de por si por dentro es una herramienta
 * o una habilidad. Solo forma: copy real en español, nada de router ni i18n.
 *
 * Decisiones del owner (2026-09-26), que es lo que este prototipo fija:
 *   - una capacidad a la que le falta una integración **avisa y deja
 *     encenderla**: encenderla es decir «la quiero», y bloquearla castiga al
 *     partner por un orden que no eligió. (Hoy las herramientas avisan y las
 *     habilidades bloquean: dos políticas para el mismo problema.)
 *   - los modos son «Siempre» y «Nunca». «Requiere aprobación» se retira
 *     porque hoy se comporta como un bloqueo y engaña;
 *   - el bloque de Integraciones **desbloquea, no duplica**: solo aparece si
 *     estorba, dice cuánto desbloquea cada una, se conecta en diálogo sin
 *     salir de aquí, y pausar/desconectar/sincronizar viven solo en su
 *     pestaña — desconectar desde aquí rompería en silencio lo que estás
 *     mirando;
 *   - el interruptor guarda con el clic; quien no puede escribir **no lo ve**
 *     y el estado se lee igual;
 *   - el nombre técnico, el tipo y la versión son detalle plegado.
 */
const meta = {
  title: "Prototipos/Capacidades",
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

// ── Los datos de la demostración ────────────────────────────────────────

type Funcion = "citas" | "pedidos" | "mensajes" | "escalado" | "conocimiento" | "otras";
type Modo = "siempre" | "nunca";

type Capacidad = {
  key: string;
  nombre: string;
  descripcion: string;
  funcion: Funcion;
  /** Vacío = común a todos los sectores. */
  sectores: string[];
  recomendada: boolean;
  encendida: boolean;
  enLaActiva: boolean;
  soloLectura?: boolean;
  destructiva?: boolean;
  /** La integración que necesita, si no está conectada. */
  necesita?: string;
  /** Solo las herramientas tienen modo; las habilidades, no. */
  modo?: { pordefecto: Modo; forzado: Modo | null };
  tecnico: { nombre: string; tipo: "Herramienta" | "Habilidad"; version: string; etiquetas: string[] };
};

const FUNCIONES: { key: Funcion; label: string }[] = [
  { key: "citas", label: "Citas" },
  { key: "pedidos", label: "Pedidos" },
  { key: "mensajes", label: "Mensajes" },
  { key: "escalado", label: "Escalado" },
  { key: "conocimiento", label: "Conocimiento" },
  { key: "otras", label: "Otras" },
];

const CAPACIDADES: Capacidad[] = [
  {
    key: "reservar",
    nombre: "Reservar una cita",
    descripcion: "El agente propone huecos libres y deja la cita puesta en la agenda del negocio.",
    funcion: "citas",
    sectores: ["panaderia", "clinica"],
    recomendada: true,
    encendida: false,
    enLaActiva: false,
    necesita: "AgendaPro",
    modo: { pordefecto: "siempre", forzado: null },
    tecnico: { nombre: "booking.create", tipo: "Herramienta", version: "12 sept 2026", etiquetas: ["booking", "write"] },
  },
  {
    key: "consultar-hueco",
    nombre: "Consultar disponibilidad",
    descripcion: "Mira qué huecos quedan antes de proponer nada.",
    funcion: "citas",
    sectores: ["panaderia", "clinica"],
    recomendada: true,
    encendida: true,
    enLaActiva: true,
    necesita: "AgendaPro",
    modo: { pordefecto: "siempre", forzado: null },
    tecnico: { nombre: "booking.check_availability", tipo: "Herramienta", version: "12 sept 2026", etiquetas: ["booking", "read"] },
  },
  {
    key: "consultar-pedido",
    nombre: "Consultar un pedido",
    descripcion: "Responde por dónde va un pedido con el número o el correo del cliente.",
    funcion: "pedidos",
    sectores: [],
    recomendada: true,
    encendida: true,
    enLaActiva: true,
    soloLectura: true,
    modo: { pordefecto: "siempre", forzado: null },
    tecnico: { nombre: "orders.get", tipo: "Herramienta", version: "2 sept 2026", etiquetas: ["orders", "read"] },
  },
  {
    key: "cancelar-pedido",
    nombre: "Cancelar un pedido",
    descripcion: "Cancela un pedido que aún no ha salido. No se puede deshacer desde el chat.",
    funcion: "pedidos",
    sectores: [],
    recomendada: false,
    encendida: false,
    enLaActiva: false,
    destructiva: true,
    modo: { pordefecto: "nunca", forzado: null },
    tecnico: { nombre: "orders.cancel", tipo: "Herramienta", version: "2 sept 2026", etiquetas: ["orders", "write"] },
  },
  {
    key: "resumen",
    nombre: "Resumir la conversación",
    descripcion: "Deja un resumen de lo hablado cuando la conversación se cierra.",
    funcion: "mensajes",
    sectores: [],
    recomendada: true,
    encendida: true,
    enLaActiva: false,
    tecnico: { nombre: "summary", tipo: "Habilidad", version: "20 sept 2026", etiquetas: ["core"] },
  },
  {
    key: "pasar-persona",
    nombre: "Pasar a una persona",
    descripcion: "Cuando el cliente lo pide o se enfada, avisa al equipo y deja de responder.",
    funcion: "escalado",
    sectores: [],
    recomendada: true,
    encendida: true,
    enLaActiva: true,
    tecnico: { nombre: "handoff", tipo: "Habilidad", version: "20 sept 2026", etiquetas: ["core"] },
  },
  {
    key: "buscar-conocimiento",
    nombre: "Responder con los documentos del negocio",
    descripcion: "Busca la respuesta en lo que hayas subido a Conocimiento antes de improvisar.",
    funcion: "conocimiento",
    sectores: [],
    recomendada: true,
    encendida: true,
    enLaActiva: true,
    modo: { pordefecto: "siempre", forzado: "siempre" },
    tecnico: { nombre: "kb.search", tipo: "Herramienta", version: "2 sept 2026", etiquetas: ["knowledge", "read"] },
  },
  {
    key: "cobrar",
    nombre: "Cobrar por el chat",
    descripcion: "Manda un enlace de pago y avisa al negocio cuando se paga.",
    funcion: "otras",
    sectores: ["comercio"],
    recomendada: false,
    encendida: false,
    enLaActiva: false,
    necesita: "Amigable Cobro",
    modo: { pordefecto: "nunca", forzado: null },
    tecnico: { nombre: "payments.link", tipo: "Herramienta", version: "2 sept 2026", etiquetas: ["payments", "write"] },
  },
];

type Integracion = { nombre: string; desbloquea: number; estado: "No conectado" | "Con errores" };

// ── Piezas ──────────────────────────────────────────────────────────────

/**
 * El bloque que desbloquea. Solo lista lo que estorba **a lo que se está
 * viendo**, y dice cuánto desbloquea cada cosa: ese número es lo que
 * convierte una tarea aburrida en una decisión fácil.
 */
function Integraciones({ items, sinCatalogo = false }: { items: Integracion[]; sinCatalogo?: boolean }) {
  if (items.length === 0) return null;
  const titulo = sinCatalogo
    ? "Estas integraciones se pueden conectar ya"
    : items.length === 1
      ? "Falta una integración para poder usar todo esto"
      : `Faltan ${items.length} integraciones para poder usar todo esto`;
  return (
    <Callout tone={sinCatalogo ? "neutral" : "warning"} title={titulo}>
      <div className="flex flex-col gap-3">
        <ul className="flex flex-col gap-2">
          {items.map((i) => (
            <li key={i.nombre} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-medium">{i.nombre}</span>
              {i.desbloquea > 0 ? (
                <span className="text-xs text-muted-foreground">
                  desbloquea {i.desbloquea} {i.desbloquea === 1 ? "capacidad" : "capacidades"} de las que ves
                </span>
              ) : null}
              <StatusBadge tone={i.estado === "Con errores" ? "danger" : "muted"}>{i.estado}</StatusBadge>
              {/* Se conecta aquí mismo, en diálogo: mandarte a otra pestaña
                  te haría perder el filtro, el buscador y el sitio por donde
                  ibas. */}
              <Button size="xs" className="ml-auto" aria-haspopup="dialog">
                {i.estado === "Con errores" ? "Reconectar" : "Conectar"}
              </Button>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">
          Pausar, desconectar o sincronizar se hace en{" "}
          <a href="#" className="underline underline-offset-4">
            Integraciones
          </a>
          .
        </p>
      </div>
    </Callout>
  );
}

function Tarjeta({ cap, puedeEscribir }: { cap: Capacidad; puedeEscribir: boolean }) {
  const [encendida, setEncendida] = useState(cap.encendida);
  const idNombre = `cap-${cap.key}`;
  return (
    <li className="flex flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span id={idNombre} className="font-medium">
              {cap.nombre}
            </span>
            {cap.recomendada ? <StatusBadge tone="info">Recomendada para tu sector</StatusBadge> : null}
            {cap.enLaActiva ? <StatusBadge tone="positive">En la versión activa</StatusBadge> : encendida ? <StatusBadge tone="info">Aún no publicada</StatusBadge> : null}
            {cap.soloLectura ? <StatusBadge tone="muted">Solo lectura</StatusBadge> : null}
            {cap.destructiva ? <StatusBadge tone="danger">Destructiva</StatusBadge> : null}
          </div>
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">{cap.descripcion}</p>
        </div>
        {/* Quien no puede escribir no ve interruptor: el estado se lee en la
            insignia, y un control muerto es peor que ninguno. */}
        {puedeEscribir ? (
          <Switch aria-labelledby={idNombre} checked={encendida} onCheckedChange={(v) => setEncendida(Boolean(v))} />
        ) : (
          <StatusBadge tone={encendida ? "positive" : "muted"}>{encendida ? "Encendida" : "Apagada"}</StatusBadge>
        )}
      </div>

      {cap.necesita ? (
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-warning">
          Necesita {cap.necesita} para funcionar.{" "}
          <a href="#" className="underline underline-offset-4">
            Conectarlo
          </a>
          <HelpHint label={`Ayuda: ${cap.necesita}`}>
            Puedes encenderla igual: queda encendida y empieza a funcionar en cuanto conectes {cap.necesita}. Hasta entonces el agente no la usa.
          </HelpHint>
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
        {cap.modo && puedeEscribir ? (
          <span className="flex items-center gap-2">
            <label htmlFor={`${idNombre}-modo`} className="text-xs text-muted-foreground">
              Cuándo la usa
            </label>
            <NativeSelect id={`${idNombre}-modo`} size="sm" defaultValue={cap.modo.forzado ?? "__default"} wrapperClassName="w-52">
              <option value="__default">Por defecto ({cap.modo.pordefecto === "siempre" ? "Siempre" : "Nunca"})</option>
              <option value="siempre">Siempre</option>
              <option value="nunca">Nunca</option>
            </NativeSelect>
            {cap.modo.forzado ? <HelpHint label="Ayuda: modo forzado">Lo has fijado tú; si no, seguiría el valor por defecto.</HelpHint> : null}
          </span>
        ) : (
          <span />
        )}
        {/* El nombre interno y la versión existen, pero no compiten con el
            nombre del negocio (R5.6). */}
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Detalle técnico</summary>
          <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            <span>
              <dt className="inline">Nombre: </dt>
              <dd className="inline font-mono">{cap.tecnico.nombre}</dd>
            </span>
            <span>
              <dt className="inline">Tipo: </dt>
              <dd className="inline">{cap.tecnico.tipo}</dd>
            </span>
            <span>
              <dt className="inline">Versión: </dt>
              <dd className="inline">{cap.tecnico.version}</dd>
            </span>
            <span>
              <dt className="inline">Etiquetas: </dt>
              <dd className="inline font-mono">{cap.tecnico.etiquetas.join(" ")}</dd>
            </span>
          </dl>
        </details>
      </div>
    </li>
  );
}

// ── La pantalla ─────────────────────────────────────────────────────────

function Pantalla({
  sector = "panaderia",
  puedeEscribir = true,
  todoConectado = false,
  catalogoVacio = false,
  busquedaInicial = "",
  verTodasInicial = false,
  compact,
}: {
  sector?: string | null;
  puedeEscribir?: boolean;
  todoConectado?: boolean;
  catalogoVacio?: boolean;
  busquedaInicial?: string;
  verTodasInicial?: boolean;
  compact?: boolean;
}) {
  const [busqueda, setBusqueda] = useState(busquedaInicial);
  const [verTodas, setVerTodas] = useState(verTodasInicial);

  const todas = catalogoVacio ? [] : CAPACIDADES;
  const delSector = useMemo(
    () => (sector === null || verTodas ? todas : todas.filter((c) => c.sectores.length === 0 || c.sectores.includes(sector))),
    [todas, sector, verTodas],
  );
  const ocultas = todas.length - delSector.length;
  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return delSector;
    return delSector.filter((c) => `${c.nombre} ${c.descripcion}`.toLowerCase().includes(q));
  }, [delSector, busqueda]);

  const encendidas = visibles.filter((c) => c.encendida).length;
  // Con el catálogo vacío las integraciones NO salen de las capacidades
  // visibles —no hay ninguna—, salen del catálogo de conectores, que es otra
  // lectura. Hoy la pantalla las esconde en ese caso y no hay forma de
  // conectar nada; aquí no.
  const integraciones: Integracion[] = todoConectado
    ? []
    : catalogoVacio
      ? [
          { nombre: "AgendaPro", desbloquea: 0, estado: "No conectado" },
          { nombre: "Amigable Cobro", desbloquea: 0, estado: "Con errores" },
        ]
      : Object.entries(
        visibles.reduce<Record<string, number>>((acc, c) => (c.necesita ? { ...acc, [c.necesita]: (acc[c.necesita] ?? 0) + 1 } : acc), {}),
      ).map(([nombre, desbloquea]) => ({ nombre, desbloquea, estado: nombre === "Amigable Cobro" ? "Con errores" : "No conectado" }));

  return (
    <div className={compact ? "mx-auto flex w-full max-w-96 flex-col gap-(--space-section) p-4" : "mx-auto flex max-w-(--width-content) flex-col gap-(--space-section) p-8"}>
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">Capacidades</h1>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">
          Lo que el agente sabe hacer. Lo que dejes apagado, el agente no lo ve. Cada cambio se guarda en el borrador; publicar sigue siendo un paso aparte.
        </p>
      </header>

      <Integraciones items={integraciones} sinCatalogo={catalogoVacio} />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <label htmlFor="buscar" className="sr-only">
            Buscar una capacidad
          </label>
          <span className="relative inline-flex items-center">
            <Search aria-hidden="true" className="absolute left-3 size-4 text-muted-foreground" />
            <Input
              id="buscar"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar una capacidad…"
              className="w-72 pl-9"
            />
          </span>
          <span className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
            {encendidas} de {visibles.length} encendidas
          </span>
        </div>
        {puedeEscribir && visibles.length > 0 ? (
          <span className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm">
              Encender las visibles
            </Button>
            <Button variant="ghost" size="sm">
              Apagar las visibles
            </Button>
          </span>
        ) : null}
      </div>

      {sector === null ? (
        <p className="text-sm text-muted-foreground">
          Este cliente no tiene sector, así que se ven todas las capacidades.{" "}
          <a href="#" className="underline underline-offset-4">
            Elegir un sector
          </a>{" "}
          deja a la vista solo lo suyo.
        </p>
      ) : ocultas > 0 || verTodas ? (
        <p className="text-sm text-muted-foreground">
          {verTodas ? (
            <>
              Viendo todas las capacidades, también las de otros sectores.{" "}
              <button type="button" onClick={() => setVerTodas(false)} className="underline underline-offset-4">
                Ver solo las de panadería
              </button>
            </>
          ) : (
            <>
              {ocultas} {ocultas === 1 ? "capacidad es de otro sector" : "capacidades son de otros sectores"} y no se muestran.{" "}
              <button type="button" onClick={() => setVerTodas(true)} className="underline underline-offset-4">
                Ver todas
              </button>
            </>
          )}
        </p>
      ) : null}

      {!puedeEscribir ? <p className="text-sm text-muted-foreground">Tu rol permite ver las capacidades, no cambiarlas.</p> : null}

      {catalogoVacio ? (
        <EmptyState
          icon={Wrench}
          title="Auphere todavía no ha publicado capacidades para este entorno"
          description="En cuanto las publiquemos aparecerán aquí. Las integraciones de arriba sí se pueden conectar mientras tanto."
          readonly
        />
      ) : visibles.length === 0 ? (
        <EmptyState
          icon={Search}
          title={`Ninguna capacidad coincide con «${busqueda}»`}
          description="Prueba con otra palabra, o mira también las de otros sectores."
          action={
            <Button variant="outline" onClick={() => { setBusqueda(""); setVerTodas(true); }}>
              Ver todas
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-(--space-section)">
          {FUNCIONES.filter((f) => visibles.some((c) => c.funcion === f.key)).map((f) => (
            <Section key={f.key} title={f.label} headingLevel={2} flat>
              <ul className="flex flex-col gap-2">
                {visibles
                  .filter((c) => c.funcion === f.key)
                  .map((c) => (
                    <Tarjeta key={c.key} cap={c} puedeEscribir={puedeEscribir} />
                  ))}
              </ul>
            </Section>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Historias ───────────────────────────────────────────────────────────

export const ConSector: Story = { render: () => <Pantalla /> };
export const VerTodas: Story = { render: () => <Pantalla verTodasInicial /> };
export const SinSector: Story = { render: () => <Pantalla sector={null} /> };
export const TodoConectado: Story = { render: () => <Pantalla todoConectado /> };
export const Buscando: Story = { render: () => <Pantalla busquedaInicial="pedido" /> };
export const SinResultados: Story = { render: () => <Pantalla busquedaInicial="factura" /> };
export const SoloLectura: Story = { render: () => <Pantalla puedeEscribir={false} /> };
/** El fallo de hoy: con el catálogo vacío no había forma de conectar nada. */
export const CatalogoVacio: Story = { render: () => <Pantalla catalogoVacio /> };
export const Movil: Story = {
  render: () => <Pantalla compact />,
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
