import type { Meta, StoryObj } from "@storybook/react-vite";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "../../components/button";
import { Checklist, type ChecklistItem } from "../../components/checklist";
import { Combobox } from "../../components/combobox";
import { DescriptionList } from "../../components/description-list";
import { EmptyState } from "../../components/empty-state";
import { Input } from "../../components/input";
import { Label } from "../../components/label";
import { Stepper } from "../../components/stepper";
import { TooltipProvider } from "../../components/tooltip";
import { UiCopyProvider } from "../../components/ui-copy";

/**
 * Prototipo · iteración 1 (spec 019): el alta de un cliente deja de pesar.
 *
 * Solo forma: copy real en español, nada de router, de i18n ni de API.
 *
 * **La decisión que este prototipo somete a aprobación** es qué se pregunta,
 * en qué orden, y qué desaparece. Hoy el alta son cuatro pasos y veintitrés
 * campos; aquí son tres pasos y cuatro campos.
 *
 * Lo que fija, y por qué:
 *
 * 1. **A qué se dedica el negocio es la primera pregunta.** La plantilla
 *    decide el prompt, las herramientas y qué campos existen siquiera, así
 *    que decidirla primero estrecha todo lo demás. Hoy es la segunda, y viene
 *    marcada la que la API devuelve primera — por orden alfabético, no por
 *    encaje. Da la casualidad de que es **la más pesada de las trece**.
 * 2. **Nada viene preseleccionado.** Una elección arbitraria es peor que
 *    ninguna: continuar por inercia con una plantilla que nadie eligió es
 *    exactamente el defecto de hoy.
 * 3. **Solo se pide lo que la plantilla no puede rellenar sola.** Medido
 *    ejecutando el renderizador de semillas: diez plantillas exigen dos
 *    campos —dirección y horario—, tres no exigen ninguno, y
 *    `aesthetic_clinic_v1` exige doce. Lo demás tiene valor por defecto y hoy
 *    se pregunta igual.
 * 4. **La pantalla dice que eso es todo.** «Esto es lo único que hace falta»
 *    no es un adorno: es la diferencia entre un formulario corto y un
 *    formulario que parece que va a seguir.
 * 5. **El paso «Canal» desaparece.** Su respuesta no viajaba a ningún sitio:
 *    era un cuarto del asistente para una pregunta que se descartaba. Conectar
 *    el canal es el primer paso pendiente de la ficha, y ahí se queda.
 * 6. **La referencia se pliega.** Se deriva del nombre y vive bajo «opciones
 *    avanzadas» para quien la necesite. Hoy es el segundo campo del alta:
 *    vocabulario de la API como segundo contacto con el producto.
 * 7. **Publicar se decide junto al resumen**, que es lo que lo hace
 *    entendible, y con las dos salidas escritas. Hoy aparece la última.
 *
 * La caja del Companion —«cuéntame del negocio»— va arriba del paso 1 y se
 * prototipa aparte, en la iteración 3. Aquí se deja su hueco marcado.
 */
const meta = {
  title: "Prototipos/Alta de cliente",
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <UiCopyProvider copy={{ close: "Cerrar", cancel: "Cancelar", confirm: "Confirmar", loading: "Cargando" }}>
        <TooltipProvider>
          <div className="mx-auto flex max-w-3xl flex-col gap-(--space-section) p-4">
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

type Plantilla = {
  id: string;
  nombre: string;
  para: string;
  habilidades: number;
  /** Lo que el renderizador exige. Medido, no estimado. */
  campos: string[];
};

/** Lo que el alta pide, y es **lo mismo para las trece** (owner, 2026-09-28):
 *  dónde está el negocio y cuándo abre. Todo lo demás —precios, formas de
 *  pago, credenciales del titular— es dato avanzado y se rellena en los
 *  ajustes del agente. */
const CAMPOS_COMUNES = ["Dirección", "Horario"];

const PLANTILLAS: Plantilla[] = [
  { id: "barbershop", nombre: "Barbería / Peluquería", para: "Reserva de citas, precios y horarios.", habilidades: 18, campos: CAMPOS_COMUNES },
  { id: "beauty", nombre: "Salón de belleza", para: "Citas y tratamientos, con sus tiempos.", habilidades: 14, campos: CAMPOS_COMUNES },
  { id: "nail", nombre: "Estudio de uñas", para: "Citas, diseños y depósitos.", habilidades: 19, campos: CAMPOS_COMUNES },
  { id: "spa", nombre: "Spa (belleza y wellness)", para: "Reservas y paquetes.", habilidades: 14, campos: CAMPOS_COMUNES },
  { id: "dental", nombre: "Clínica dental", para: "Citas, urgencias y presupuestos.", habilidades: 14, campos: CAMPOS_COMUNES },
  { id: "clinica", nombre: "Clínica / Consultorio", para: "Citas y preguntas frecuentes.", habilidades: 13, campos: CAMPOS_COMUNES },
  { id: "medspa", nombre: "Medicina estética (sin cirugía)", para: "Citas y valoraciones.", habilidades: 14, campos: CAMPOS_COMUNES },
  { id: "restaurante", nombre: "Restaurante (reservas)", para: "Reservas, carta y horarios.", habilidades: 13, campos: CAMPOS_COMUNES },
  { id: "generic", nombre: "Genérica (asistente básico)", para: "Responde lo básico del negocio.", habilidades: 5, campos: CAMPOS_COMUNES },
  {
    id: "aesthetic",
    nombre: "Clínica estética (medspa + cirugía)",
    para: "Citas, valoraciones y referencias quirúrgicas.",
    habilidades: 15,
    // Era la excepción: pedía doce campos porque su prompt los exige. El
    // owner lo cortó el 2026-09-28 — precios, formas de pago, credenciales
    // del titular y teléfonos de referencia **no se rellenan en el alta**.
    // Van a los ajustes del agente, y la semilla lleva mientras tanto una
    // respuesta segura («consúltalo con recepción»), no un hueco vacío.
    campos: CAMPOS_COMUNES,
  },
  { id: "cobranza", nombre: "Cobranza / Asistente del administrador", para: "Recordatorios y estado de pagos.", habilidades: 12, campos: CAMPOS_COMUNES },
  { id: "inventario", nombre: "Inventario / Asistente de almacén", para: "Stock y entradas y salidas.", habilidades: 5, campos: CAMPOS_COMUNES },
  { id: "woocommerce", nombre: "Ventas / Tienda WooCommerce", para: "Catálogo, pedidos y envíos.", habilidades: 9, campos: CAMPOS_COMUNES },
];

const ZONAS = ["Europe/Madrid", "Europe/Lisbon", "America/Bogota", "America/Santiago", "America/Mexico_City"];

// ── Paso 1 · ¿A qué se dedica? ──────────────────────────────────────────

function PasoPlantilla({
  qInicial = "",
  elegidaInicial = null,
}: {
  qInicial?: string;
  elegidaInicial?: string | null;
}) {
  const [q, setQ] = useState(qInicial);
  const [elegida, setElegida] = useState<string | null>(elegidaInicial);
  const aguja = q.trim().toLowerCase();
  const visibles = useMemo(
    () => (aguja ? PLANTILLAS.filter((p) => `${p.nombre} ${p.para}`.toLowerCase().includes(aguja)) : PLANTILLAS),
    [aguja],
  );

  return (
    <div className="flex flex-col gap-4">
      {/* El hueco del Companion. Se prototipa en la iteración 3; aquí se
          marca para que el sitio esté decidido y no aparezca luego donde
          quepa. */}
      <div className="rounded-md border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
        Aquí irá «Cuéntame del negocio» — la caja del Companion (iteración 3).
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span className="relative inline-flex min-w-0 flex-1 basis-64 items-center">
          <Search aria-hidden="true" className="absolute left-3 size-4 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar entre 13 tipos de negocio…"
            aria-label="Buscar un tipo de negocio"
            className="w-full pl-9"
          />
        </span>
        <span className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
          {visibles.length} de {PLANTILLAS.length}
        </span>
      </div>

      {visibles.length === 0 ? (
        <EmptyState
          icon={Search}
          title={`Nada coincide con «${q.trim()}»`}
          description="Prueba con otra palabra, o empieza sin plantilla y escribe el agente tú."
          action={
            <Button variant="outline" onClick={() => setQ("")}>
              Quitar la búsqueda
            </Button>
          }
        />
      ) : (
        <div role="radiogroup" aria-label="A qué se dedica el negocio" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {visibles.map((p) => (
            <button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={elegida === p.id}
              onClick={() => setElegida(p.id)}
              className="flex min-w-0 flex-col items-start gap-1 rounded-md border border-border px-3 py-2 text-left transition-colors hover:bg-muted/60 aria-checked:border-foreground aria-checked:bg-muted"
            >
              <span className="min-w-0 truncate font-medium">{p.nombre}</span>
              {/* Para qué sirve y cuánto trae: es lo que convierte trece
                  nombres en una decisión. Hoy la tarjeta enseña su clave
                  interna y el número de herramientas. */}
              <span className="text-sm text-pretty text-muted-foreground">{p.para}</span>
              <span className="text-xs text-muted-foreground tabular-nums">
                Enciende {p.habilidades} habilidades
                {p.campos.length > 0 ? ` · te pedirá ${p.campos.length} ${p.campos.length === 1 ? "dato" : "datos"}` : " · no te pedirá nada más"}
              </span>
            </button>
          ))}
          <button
            type="button"
            role="radio"
            aria-checked={elegida === "ninguna"}
            onClick={() => setElegida("ninguna")}
            className="flex min-w-0 flex-col items-start gap-1 rounded-md border border-dashed border-border px-3 py-2 text-left transition-colors hover:bg-muted/60 aria-checked:border-foreground aria-checked:bg-muted"
          >
            <span className="font-medium">Ninguna de estas</span>
            <span className="text-sm text-pretty text-muted-foreground">
              El agente nace vacío y lo escribes tú. Puedes elegir una plantilla más adelante.
            </span>
          </button>
        </div>
      )}

      <Navegacion siguiente="Continuar" siguienteActivo={elegida !== null} />
      {elegida === null ? (
        <p className="text-sm text-muted-foreground">Elige un tipo de negocio para continuar.</p>
      ) : null}
    </div>
  );
}

// ── Paso 2 · El negocio ─────────────────────────────────────────────────

function PasoNegocio() {
  const [nombre, setNombre] = useState("");
  const [zona, setZona] = useState("Europe/Madrid");
  const [avanzadas, setAvanzadas] = useState(false);

  return (
    <div className="flex flex-col gap-4">
      {/* La frase que hace corto un formulario corto. Sin ella, cuatro
          campos se leen como «cuatro, de momento». */}
      {/* Una sola frase para las trece, porque las trece piden lo mismo. Lo
          avanzado —precios, formas de pago, credenciales— vive en los ajustes
          del agente (owner, 2026-09-28). */}
      <p className="text-sm text-pretty text-muted-foreground">
        Esto es todo lo que hace falta para empezar: dónde está el negocio y cuándo abre. Los precios, las
        formas de pago y lo demás se rellenan en los ajustes del agente, cuando quieras.
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="grid min-w-0 content-start gap-2">
          <Label htmlFor="pn-nombre">Nombre del negocio</Label>
          <Input id="pn-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} autoComplete="organization" />
        </div>
        <div className="grid min-w-0 content-start gap-2">
          <Label htmlFor="pn-zona">Zona horaria</Label>
          <Combobox id="pn-zona" items={ZONAS} value={zona} onValueChange={setZona} emptyLabel="Nada coincide." />
        </div>
        <div className="grid min-w-0 content-start gap-2 sm:col-span-2">
          <Label htmlFor="pn-dir">Dirección</Label>
          <Direccion />
        </div>
      </div>

      <Horario />

      {/* La referencia, fuera del camino. Se deriva del nombre y casi nadie
          quiere tocarla; hoy es el segundo campo del alta. */}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={() => setAvanzadas((v) => !v)}
          aria-expanded={avanzadas}
          className="self-start text-sm text-muted-foreground underline underline-offset-4"
        >
          Opciones avanzadas
        </button>
        {avanzadas ? (
          <div className="grid min-w-0 max-w-md content-start gap-2">
            <Label htmlFor="pn-ref">Referencia</Label>
            <Input id="pn-ref" className="font-mono" value={nombre ? slug(nombre) : ""} readOnly />
            <p className="text-sm text-muted-foreground text-pretty">
              Se usa en la API y no se puede cambiar después. Si no la tocas, sale del nombre.
            </p>
          </div>
        ) : null}
      </div>

      <Navegacion atras siguiente="Continuar" siguienteActivo={nombre.trim() !== ""} />
    </div>
  );
}

/**
 * La dirección. **Pendiente de decisión** (owner, 2026-09-28): se pidió elegir
 * la ubicación exacta en Google Maps, y eso no es un control más — es un
 * script de terceros en el navegador del partner, una clave de API y la
 * dirección de su cliente viajando a Google. Cambia la superficie de confianza
 * que la spec declara, así que se pregunta antes de construirlo.
 *
 * Mientras tanto, el campo es lo que el agente necesita de verdad: **la
 * dirección en texto**, que es lo que le dirá a quien pregunte cómo llegar.
 */
function Direccion() {
  return (
    <>
      <Input id="pn-dir" placeholder="Calle, número, ciudad" autoComplete="street-address" />
      <p className="text-sm text-muted-foreground">
        El agente la usa para decirle a la gente dónde estáis.
      </p>
    </>
  );
}

const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"] as const;

/**
 * El horario, con controles de hora en vez de texto libre.
 *
 * **Esto es lo que mata el campo «Sábados»** (owner, 2026-09-28). Ese campo
 * existe porque el horario es una cadena que alguien escribe a mano, y los
 * sábados no cabían en ella. Con un horario de verdad, el sábado es un día
 * más y el campo sobra.
 *
 * Empieza por lo que casi siempre vale —un tramo de lunes a viernes— y solo
 * se abre día a día si el negocio lo necesita. Es un campo hasta que deja de
 * serlo.
 */
function Horario() {
  const [detallado, setDetallado] = useState(false);
  const [abre, setAbre] = useState("10:00");
  const [cierra, setCierra] = useState("19:00");
  const [sabado, setSabado] = useState(true);

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="text-sm font-medium">Horario</legend>

      {detallado ? (
        <div className="flex flex-col gap-2">
          {DIAS.map((dia) => (
            <div key={dia} className="flex flex-wrap items-center gap-2">
              <span className="w-24 shrink-0 text-sm">{dia}</span>
              <Input type="time" defaultValue="10:00" aria-label={`${dia}: abre`} className="w-32" />
              <span className="text-sm text-muted-foreground">a</span>
              <Input type="time" defaultValue="19:00" aria-label={`${dia}: cierra`} className="w-32" />
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-32 shrink-0 text-sm">De lunes a viernes</span>
            <Input type="time" value={abre} onChange={(e) => setAbre(e.target.value)} aria-label="Abre" className="w-32" />
            <span className="text-sm text-muted-foreground">a</span>
            <Input type="time" value={cierra} onChange={(e) => setCierra(e.target.value)} aria-label="Cierra" className="w-32" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-32 shrink-0 text-sm">Sábados</span>
            <button
              type="button"
              role="switch"
              aria-checked={sabado}
              aria-label="Abre los sábados"
              onClick={() => setSabado((v) => !v)}
              className="rounded-md border border-border px-3 py-1 text-sm aria-checked:border-foreground aria-checked:bg-muted"
            >
              {sabado ? "Abre" : "Cerrado"}
            </button>
            {sabado ? (
              <>
                <Input type="time" defaultValue="10:00" aria-label="Sábados: abre" className="w-32" />
                <span className="text-sm text-muted-foreground">a</span>
                <Input type="time" defaultValue="14:00" aria-label="Sábados: cierra" className="w-32" />
              </>
            ) : null}
          </div>
          <p className="text-sm text-muted-foreground">Domingos, cerrado.</p>
        </div>
      )}

      <button
        type="button"
        onClick={() => setDetallado((v) => !v)}
        aria-expanded={detallado}
        className="self-start text-sm text-muted-foreground underline underline-offset-4"
      >
        {detallado ? "Volver al horario sencillo" : "Cada día es distinto"}
      </button>
    </fieldset>
  );
}

function slug(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

// ── Paso 3 · Confirmar ──────────────────────────────────────────────────

type EstadoEtapa = "todo" | "running" | "done" | "failed" | "skipped";

function PasoConfirmar({
  publicarInicial = true,
  etapas,
}: {
  publicarInicial?: boolean;
  etapas?: Array<{ key: string; label: string; status: EstadoEtapa; detail?: string }>;
}) {
  const [publicar, setPublicar] = useState(publicarInicial);
  const corriendo = etapas?.some((e) => e.status === "running") ?? false;
  const fallida = etapas?.find((e) => e.status === "failed");

  return (
    <div className="flex flex-col gap-4">
      <DescriptionList
        layout="inline"
        items={[
          { key: "tipo", term: "Tipo de negocio", detail: "Barbería / Peluquería" },
          { key: "nombre", term: "Nombre", detail: "Barbería El Corte" },
          { key: "ref", term: "Referencia", detail: "barberia-el-corte", mono: true },
          { key: "tz", term: "Zona horaria", detail: "Europe/Madrid", mono: true },
        ]}
      />

      {/* Las dos salidas escritas, no una casilla que hay que interpretar.
          Es la decisión que más pesa del alta. */}
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">¿Empieza a atender en cuanto exista?</legend>
        {/* Una al lado de la otra (owner, 2026-09-28): son dos caminos que se
            comparan, no una lista que se recorre. Apiladas, la segunda se lee
            después de haber decidido con la primera. */}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {(
          [
            [true, "Sí, publícalo", "El agente queda vivo. Le faltará conectar el canal para recibir mensajes."],
            [false, "No, déjalo en borrador", "Lo revisas y lo publicas tú cuando quieras."],
          ] as const
        ).map(([valor, titulo, cuerpo]) => (
          <button
            key={String(valor)}
            type="button"
            role="radio"
            aria-checked={publicar === valor}
            onClick={() => setPublicar(valor)}
            disabled={Boolean(etapas)}
            className="flex min-w-0 flex-col items-start gap-1 rounded-md border border-border px-3 py-2 text-left transition-colors hover:bg-muted/60 disabled:opacity-60 aria-checked:border-foreground aria-checked:bg-muted"
          >
            <span className="font-medium">{titulo}</span>
            <span className="text-sm text-pretty text-muted-foreground">{cuerpo}</span>
          </button>
        ))}
        </div>
      </fieldset>

      {etapas ? (
        <section aria-label="Creando el cliente" aria-live="polite" className="flex flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10">
          <Checklist
            ariaLabel="Creando el cliente"
            items={etapas.map<ChecklistItem>((e) => ({
              key: e.key,
              label: e.label,
              status: e.status,
              detail: e.detail,
              onRetry: e.status === "failed" ? () => {} : undefined,
              retryLabel: "Reintentar",
            }))}
          />
          {fallida ? (
            // §V: lo que quedó hecho no se pierde, y se dice.
            <p className="text-sm text-pretty text-muted-foreground">
              El cliente ya existe y su agente está escrito. Lo único que falta es publicarlo, y puedes
              reintentarlo aquí o hacerlo desde su ficha.
            </p>
          ) : null}
        </section>
      ) : null}

      {etapas ? null : <Navegacion atras siguiente="Crear el cliente" siguienteActivo />}
      {corriendo ? <p className="text-sm text-muted-foreground">Creando…</p> : null}
    </div>
  );
}

// ── Piezas comunes ──────────────────────────────────────────────────────

function Navegacion({
  atras = false,
  siguiente,
  siguienteActivo = true,
}: {
  atras?: boolean;
  siguiente: string;
  siguienteActivo?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline">{atras ? "Atrás" : "Cancelar"}</Button>
      <Button disabled={!siguienteActivo}>{siguiente}</Button>
    </div>
  );
}

function Marco({ paso, children }: { paso: number; children: React.ReactNode }) {
  const titulos = ["A qué se dedica", "El negocio", "Confirmar"];
  return (
    <>
      <div className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold">Nuevo cliente</h1>
        <p className="text-sm text-pretty text-muted-foreground">
          Tres pasos. Al terminar tendrás un agente listo para probar.
        </p>
      </div>
      <Stepper
        variant="pills"
        ariaLabel="Pasos del alta"
        current={paso}
        steps={titulos.map((t, i) => ({ key: String(i), label: t }))}
        stepOfLabel={(n, total) => `paso ${n} de ${total}`}
      />
      <section aria-label={titulos[paso]} className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">{titulos[paso]}</h2>
        {children}
      </section>
    </>
  );
}

// ── Los estados ─────────────────────────────────────────────────────────

export const ElegirPlantilla: Story = {
  name: "1 · Elegir, sin nada marcado",
  render: () => (
    <Marco paso={0}>
      <PasoPlantilla />
    </Marco>
  ),
};

export const Buscando: Story = {
  name: "1 · Buscando",
  render: () => (
    <Marco paso={0}>
      <PasoPlantilla qInicial="cl" />
    </Marco>
  ),
};

export const SinResultados: Story = {
  name: "1 · La búsqueda no encuentra nada",
  render: () => (
    <Marco paso={0}>
      <PasoPlantilla qInicial="ferretería" />
    </Marco>
  ),
};

/** El único caso: **las trece plantillas piden exactamente esto**. */
export const Negocio: Story = {
  name: "2 · El negocio",
  render: () => (
    <Marco paso={1}>
      <PasoNegocio />
    </Marco>
  ),
};

/**
 * **Ya no hay caso pesado.** Lo hubo: `aesthetic_clinic_v1` pedía doce campos
 * porque su prompt los exige, y este prototipo llegó a enseñarlos. El owner lo
 * cortó el 2026-09-28 con una regla que vale para las trece: **lo básico se
 * rellena aquí, lo avanzado en los ajustes del agente**.
 *
 * Precios, formas de pago, credenciales del titular y teléfonos de referencia
 * no son datos de alta: son configuración del agente. La semilla lleva
 * mientras tanto una respuesta segura —«consúltalo con recepción»—, que es lo
 * que un agente bien educado contesta cuando aún no se lo han dicho.
 *
 * Consecuencia: **las trece plantillas piden lo mismo**, y el estado de arriba
 * las cubre todas.
 */
export const Confirmar: Story = {
  name: "3 · Confirmar",
  render: () => (
    <Marco paso={2}>
      <PasoConfirmar />
    </Marco>
  ),
};

export const Creando: Story = {
  name: "3 · Creando",
  render: () => (
    <Marco paso={2}>
      <PasoConfirmar
        etapas={[
          { key: "crear", label: "Crear el cliente", status: "done" },
          { key: "sembrar", label: "Escribir el agente", status: "running" },
          { key: "publicar", label: "Publicarlo", status: "todo" },
          { key: "activar", label: "Activarlo", status: "todo" },
        ]}
      />
    </Marco>
  ),
};

export const UnaEtapaFalla: Story = {
  name: "3 · Una etapa falla",
  render: () => (
    <Marco paso={2}>
      <PasoConfirmar
        etapas={[
          { key: "crear", label: "Crear el cliente", status: "done" },
          { key: "sembrar", label: "Escribir el agente", status: "done" },
          { key: "publicar", label: "Publicarlo", status: "failed", detail: "El servidor no respondió." },
          { key: "activar", label: "Activarlo", status: "todo" },
        ]}
      />
    </Marco>
  ),
};

/** El cupo se dice **antes** de pedir el primer dato, no después del formulario. */
export const CupoLleno: Story = {
  name: "Cupo lleno",
  render: () => (
    <Marco paso={0}>
      <div className="flex flex-col gap-4">
        <EmptyState
          title="Has llegado a tus 5 clientes"
          description="Para dar de alta otro, archiva uno que ya no uses o amplía tu plan."
          action={<Button variant="outline">Ver mis clientes</Button>}
          readonly
        />
      </div>
    </Marco>
  ),
};

export const Movil: Story = {
  name: "Móvil",
  parameters: { viewport: { defaultViewport: "mobile2" } },
  render: () => (
    <Marco paso={1}>
      <PasoNegocio />
    </Marco>
  ),
};
