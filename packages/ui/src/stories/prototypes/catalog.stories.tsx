import type { Meta, StoryObj } from "@storybook/react-vite";
import { MessageCircle, Plug, Search, Wrench } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "../../components/button";
import { EmptyState } from "../../components/empty-state";
import { Input } from "../../components/input";
import { Section } from "../../components/section";
import { StatusBadge } from "../../components/status-badge";
import { Switch } from "../../components/switch";
import { TooltipProvider } from "../../components/tooltip";
import { UiCopyProvider } from "../../components/ui-copy";

/**
 * Prototipo · iteración 2 (spec 018, R4): **un catálogo, tres pantallas**.
 *
 * Solo forma: copy real en español, nada de router, de i18n ni de API.
 *
 * **La decisión que este prototipo somete a aprobación** es cuáles son los
 * gestos del patrón y dónde viven. Hoy Habilidades tiene buscador y grupos,
 * Conectores tiene una rejilla ordenada por urgencia y Canales no tiene
 * ninguna de las dos cosas: tres pantallas que hacen lo mismo de tres
 * maneras. El patrón propone **tres gestos, siempre en el mismo sitio**:
 *
 *   1. **Buscar** — se escribe y la lista se reduce; el contador dice cuánto
 *      queda y cuánto está activo.
 *   2. **Activos / Todo** — ver solo lo que este cliente ya tiene, o
 *      descubrir lo que hay.
 *   3. **Filtrar por categoría** — pastillas con su cuenta, que además son
 *      el mapa de lo que hay dentro.
 *
 * Lo demás que fija:
 *
 *   - **El patrón navega; no actúa.** Encender una habilidad, pegar unas
 *     credenciales y conectar un canal son tres acciones distintas con tres
 *     diálogos distintos. Cada pantalla se queda con su tarjeta; el patrón
 *     solo decide cómo se llega hasta ella.
 *   - **Vacío por filtro ≠ catálogo vacío.** No dicen lo mismo y no pueden
 *     enseñar el mismo cartel: uno se arregla quitando el filtro y el otro
 *     no se arregla desde aquí. El cartel del filtro **nombra el filtro** y
 *     ofrece quitarlo.
 *   - **Lo que no tiene categoría va a un grupo con nombre propio.** «Otras»
 *     es un grupo; inventarle una categoría sería mentir sobre lo que es.
 *   - **Lo que no se puede conectar no está en la lista** (constitución §V).
 *     Canales enseña WhatsApp; Messenger, Instagram y Telegram no aparecen
 *     apagados ni prometidos, porque hoy no se pueden conectar.
 *   - **Quien no puede escribir no ve controles muertos**, y busca y filtra
 *     igual: mirar no es escribir.
 *
 * **Y una decisión de comportamiento que conviene mirar aquí**, porque se
 * nota al usarlo: las pestañas y las pastillas son **enlaces**, y el
 * buscador escribe en la dirección sin apilar historia. Así compartir el
 * enlace lleva a lo mismo y «atrás» deshace el filtro —no cada letra
 * tecleada, que no es lo que nadie espera—.
 */
const meta = {
  title: "Prototipos/Catálogo",
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <UiCopyProvider copy={{ close: "Cerrar", cancel: "Cancelar", confirm: "Confirmar", loading: "Cargando" }}>
        <TooltipProvider>
          <div className="mx-auto flex max-w-5xl flex-col gap-(--space-section) p-4">
            <Story />
          </div>
        </TooltipProvider>
      </UiCopyProvider>
    ),
  ],
} satisfies Meta;
export default meta;
type Story = StoryObj;

// ── Los datos de la demostración ────────────────────────────────────────

type Elemento = {
  id: string;
  nombre: string;
  descripcion: string;
  /** `null` = sin categoría. Va a un grupo con nombre propio, no inventado. */
  categoria: string | null;
  activo: boolean;
  /** El matiz del activo, que cada catálogo nombra a su manera. */
  matiz?: { texto: string; tono: "positive" | "warning" | "danger" | "info" | "muted" };
};

const HABILIDADES: Elemento[] = [
  { id: "book", nombre: "Reservar una cita", descripcion: "Propone huecos y confirma la reserva.", categoria: "Citas", activo: true, matiz: { texto: "En la versión activa", tono: "positive" } },
  { id: "cancel", nombre: "Cancelar una cita", descripcion: "Anula la reserva y libera el hueco.", categoria: "Citas", activo: true, matiz: { texto: "Sin publicar", tono: "info" } },
  { id: "remind", nombre: "Recordar la cita", descripcion: "Avisa el día antes.", categoria: "Citas", activo: false },
  { id: "order", nombre: "Tomar un pedido", descripcion: "Recoge productos, cantidades y entrega.", categoria: "Pedidos", activo: true, matiz: { texto: "Le falta WooCommerce", tono: "warning" } },
  { id: "track", nombre: "Seguir un pedido", descripcion: "Dice en qué estado está.", categoria: "Pedidos", activo: false },
  { id: "invoice", nombre: "Enviar la factura", descripcion: "Manda el documento al cliente.", categoria: "Pedidos", activo: false, matiz: { texto: "Aún no disponible", tono: "muted" } },
  { id: "hours", nombre: "Decir el horario", descripcion: "Responde cuándo está abierto.", categoria: "Información", activo: true, matiz: { texto: "En la versión activa", tono: "positive" } },
  { id: "where", nombre: "Decir dónde está", descripcion: "Da la dirección y cómo llegar.", categoria: "Información", activo: true, matiz: { texto: "En la versión activa", tono: "positive" } },
  { id: "price", nombre: "Consultar precios", descripcion: "Responde cuánto cuesta cada cosa.", categoria: "Información", activo: false },
  { id: "human", nombre: "Pasar a una persona", descripcion: "Escala la conversación al equipo.", categoria: null, activo: true, matiz: { texto: "En la versión activa", tono: "positive" } },
  { id: "survey", nombre: "Pedir una valoración", descripcion: "Pregunta qué tal fue.", categoria: null, activo: false },
];

const CONECTORES: Elemento[] = [
  { id: "woo", nombre: "WooCommerce", descripcion: "Catálogo y pedidos de la tienda.", categoria: "Tienda", activo: true, matiz: { texto: "Error al sincronizar", tono: "danger" } },
  { id: "agendapro", nombre: "AgendaPro", descripcion: "La agenda de citas del negocio.", categoria: "Citas", activo: false },
  { id: "cobro", nombre: "Amigable Cobro", descripcion: "Cobros y enlaces de pago.", categoria: "Pagos", activo: true, matiz: { texto: "Conectado", tono: "positive" } },
  { id: "venta", nombre: "Amigable Venta", descripcion: "Presupuestos y ventas.", categoria: "Pagos", activo: false },
];

const CANALES: Elemento[] = [
  { id: "wa", nombre: "WhatsApp", descripcion: "+34 600 123 456", categoria: null, activo: true, matiz: { texto: "Conectado", tono: "positive" } },
];

// ── El patrón ───────────────────────────────────────────────────────────

type Pestana = "activos" | "todo";

/**
 * La barra de gestos y la lista agrupada. En el componente de verdad las
 * pestañas y las pastillas serán enlaces; aquí son botones porque un
 * prototipo no tiene dirección que escribir.
 */
function Catalogo({
  elementos,
  singular,
  plural,
  sinCategoria = "Otras",
  puedeEscribir = true,
  icono: Icono = Wrench,
  vacio,
  qInicial = "",
  pestanaInicial = "todo",
  categoriaInicial = null,
}: {
  elementos: Elemento[];
  singular: string;
  plural: string;
  sinCategoria?: string;
  puedeEscribir?: boolean;
  icono?: typeof Wrench;
  vacio: { titulo: string; cuerpo: string };
  qInicial?: string;
  pestanaInicial?: Pestana;
  categoriaInicial?: string | null;
}) {
  const [q, setQ] = useState(qInicial);
  const [pestana, setPestana] = useState<Pestana>(pestanaInicial);
  const [categoria, setCategoria] = useState<string | null>(categoriaInicial);

  const aguja = q.trim().toLowerCase();
  const visibles = useMemo(
    () =>
      elementos.filter((e) => {
        if (pestana === "activos" && !e.activo) return false;
        if (categoria !== null && (e.categoria ?? sinCategoria) !== categoria) return false;
        if (aguja && !`${e.nombre} ${e.descripcion}`.toLowerCase().includes(aguja)) return false;
        return true;
      }),
    [elementos, pestana, categoria, aguja, sinCategoria],
  );

  // Las categorías salen de los elementos, en el orden en que aparecen: una
  // lista fija se queda vieja en cuanto la API añade una.
  const categorias = useMemo(() => {
    const cuenta = new Map<string, number>();
    for (const e of elementos) {
      const k = e.categoria ?? sinCategoria;
      cuenta.set(k, (cuenta.get(k) ?? 0) + 1);
    }
    return [...cuenta.entries()];
  }, [elementos, sinCategoria]);

  const grupos = useMemo(() => {
    const porCat = new Map<string, Elemento[]>();
    for (const e of visibles) {
      const k = e.categoria ?? sinCategoria;
      porCat.set(k, [...(porCat.get(k) ?? []), e]);
    }
    return [...porCat.entries()];
  }, [visibles, sinCategoria]);

  const activos = visibles.filter((e) => e.activo).length;
  const hayFiltro = aguja !== "" || categoria !== null || pestana === "activos";

  return (
    <div className="flex flex-col gap-(--space-section)">
      {/* Los tres gestos, en una sola barra y siempre en este orden. */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="relative inline-flex min-w-0 flex-1 basis-64 items-center">
            <Search aria-hidden="true" className="absolute left-3 size-4 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={`Buscar entre ${elementos.length} ${plural.toLowerCase()}…`}
              aria-label={`Buscar ${plural.toLowerCase()}`}
              className="w-full pl-9"
            />
          </span>
          {/* Activos / Todo. «Activos» primero porque es lo que se mira al
              volver; «Todo» es para descubrir, que se hace menos veces. */}
          <div role="group" aria-label="Qué se ve" className="inline-flex rounded-md bg-muted p-1">
            {(["activos", "todo"] as const).map((p) => (
              <button
                key={p}
                type="button"
                aria-pressed={pestana === p}
                onClick={() => setPestana(p)}
                className="rounded-md px-3 py-1 text-sm aria-pressed:bg-card aria-pressed:shadow-sm"
              >
                {p === "activos" ? "Activos" : "Todo"}
              </button>
            ))}
          </div>
          <span className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
            {visibles.length} {visibles.length === 1 ? singular.toLowerCase() : plural.toLowerCase()} · {activos} activ
            {activos === 1 ? "a" : "as"}
          </span>
        </div>

        {/* Las pastillas llevan su cuenta: además de filtrar, son el mapa de
            lo que hay dentro sin tener que bajar a mirarlo. Con una sola
            categoría no filtran nada, así que no se pintan. */}
        {categorias.length > 1 ? (
          <div className="flex flex-wrap items-center gap-2">
            {categorias.map(([cat, n]) => (
              <button
                key={cat}
                type="button"
                aria-pressed={categoria === cat}
                onClick={() => setCategoria(categoria === cat ? null : cat)}
                className="rounded-full border border-border px-3 py-1 text-xs tabular-nums aria-pressed:border-transparent aria-pressed:bg-mountain-meadow aria-pressed:text-dark-green"
              >
                {cat} · {n}
              </button>
            ))}
          </div>
        ) : null}

        {!puedeEscribir ? (
          <p className="text-sm text-muted-foreground">Tu rol permite mirar, no cambiar nada aquí.</p>
        ) : null}
      </div>

      {elementos.length === 0 ? (
        // Catálogo vacío: no hay nada que enseñar y quitar un filtro no lo
        // arregla. Otro cartel, otro texto.
        <EmptyState icon={Icono} title={vacio.titulo} description={vacio.cuerpo} readonly />
      ) : visibles.length === 0 ? (
        // Vacío por filtro: se nombra el filtro y se ofrece quitarlo.
        <EmptyState
          icon={Search}
          title={
            aguja
              ? `Nada coincide con «${q.trim()}»`
              : pestana === "activos"
                ? `Este cliente no tiene ${plural.toLowerCase()} activas`
                : `No hay nada en «${categoria}»`
          }
          description={
            hayFiltro
              ? `Estás viendo ${pestana === "activos" ? "solo lo activo" : "todo"}${categoria ? `, en «${categoria}»` : ""}${aguja ? `, buscando «${q.trim()}»` : ""}.`
              : undefined
          }
          action={
            <Button
              variant="outline"
              onClick={() => {
                setQ("");
                setPestana("todo");
                setCategoria(null);
              }}
            >
              Quitar los filtros
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-(--space-section)">
          {grupos.map(([cat, items]) => (
            <Section key={cat} title={cat} headingLevel={2} flat>
              <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
                {items.map((e) => (
                  <Tarjeta key={e.id} elemento={e} puedeEscribir={puedeEscribir} />
                ))}
              </ul>
            </Section>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * La tarjeta es de cada pantalla, no del patrón: aquí se dibuja una genérica
 * solo para que la rejilla tenga algo dentro. Lo que el prototipo somete a
 * aprobación es la barra y los grupos, no esto.
 */
function Tarjeta({ elemento, puedeEscribir }: { elemento: Elemento; puedeEscribir: boolean }) {
  return (
    <li className="flex min-w-0 flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="font-medium">{elemento.nombre}</span>
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">{elemento.descripcion}</p>
        </div>
        {puedeEscribir ? (
          <Switch checked={elemento.activo} aria-label={elemento.nombre} />
        ) : (
          <StatusBadge tone={elemento.activo ? "positive" : "muted"}>
            {elemento.activo ? "Activa" : "Apagada"}
          </StatusBadge>
        )}
      </div>
      {elemento.matiz ? <StatusBadge tone={elemento.matiz.tono}>{elemento.matiz.texto}</StatusBadge> : null}
    </li>
  );
}

const VACIO_HAB = { titulo: "Todavía no hay habilidades", cuerpo: "Auphere publica las habilidades; aquí aparecerán en cuanto existan." };

// ── Estados ─────────────────────────────────────────────────────────────

export const Lleno: Story = {
  name: "Lleno",
  render: () => (
    <Catalogo elementos={HABILIDADES} singular="habilidad" plural="Habilidades" vacio={VACIO_HAB} />
  ),
};

export const Buscando: Story = {
  name: "Buscando",
  render: () => (
    <Catalogo elementos={HABILIDADES} singular="habilidad" plural="Habilidades" vacio={VACIO_HAB} qInicial="cita" />
  ),
};

export const Filtrado: Story = {
  name: "Filtrado por categoría",
  render: () => (
    <Catalogo
      elementos={HABILIDADES}
      singular="habilidad"
      plural="Habilidades"
      vacio={VACIO_HAB}
      categoriaInicial="Pedidos"
    />
  ),
};

export const SoloActivo: Story = {
  name: "Solo lo activo",
  render: () => (
    <Catalogo
      elementos={HABILIDADES}
      singular="habilidad"
      plural="Habilidades"
      vacio={VACIO_HAB}
      pestanaInicial="activos"
    />
  ),
};

export const FiltroSinResultados: Story = {
  name: "Filtro sin resultados",
  render: () => (
    <Catalogo
      elementos={HABILIDADES}
      singular="habilidad"
      plural="Habilidades"
      vacio={VACIO_HAB}
      qInicial="devolución"
      categoriaInicial="Citas"
    />
  ),
};

export const CatalogoVacio: Story = {
  name: "Catálogo vacío",
  render: () => (
    <Catalogo elementos={[]} singular="habilidad" plural="Habilidades" vacio={VACIO_HAB} />
  ),
};

export const SoloLectura: Story = {
  name: "Solo lectura",
  render: () => (
    <Catalogo
      elementos={HABILIDADES}
      singular="habilidad"
      plural="Habilidades"
      vacio={VACIO_HAB}
      puedeEscribir={false}
    />
  ),
};

/**
 * Los tres catálogos uno debajo de otro: es la comprobación de R4.6 —los
 * tres llaman igual a lo mismo y lo colocan en el mismo sitio— y la de §V
 * en Canales: WhatsApp está; Messenger, Instagram y Telegram **no**, ni
 * apagados ni prometidos.
 */
export const LosTres: Story = {
  name: "Los tres, comparados",
  render: () => (
    <div className="flex flex-col gap-(--space-section)">
      <Section title="Habilidades" description="Lo que el agente sabe hacer.">
        <Catalogo elementos={HABILIDADES} singular="habilidad" plural="Habilidades" vacio={VACIO_HAB} />
      </Section>
      <Section title="Conectores" description="Lo que conecta al agente con lo que el negocio ya usa.">
        <Catalogo
          elementos={CONECTORES}
          singular="conector"
          plural="Conectores"
          icono={Plug}
          vacio={{ titulo: "Todavía no hay conectores", cuerpo: "Aquí aparecerán cuando existan." }}
        />
      </Section>
      <Section title="Canales" description="Por dónde llegan los mensajes.">
        <Catalogo
          elementos={CANALES}
          singular="canal"
          plural="Canales"
          icono={MessageCircle}
          vacio={{ titulo: "Todavía no hay canales", cuerpo: "Conecta WhatsApp para que el agente empiece a atender." }}
        />
      </Section>
    </div>
  ),
};

export const Movil: Story = {
  name: "Móvil",
  parameters: { viewport: { defaultViewport: "mobile1" } },
  render: () => (
    <Catalogo elementos={HABILIDADES} singular="habilidad" plural="Habilidades" vacio={VACIO_HAB} />
  ),
};
