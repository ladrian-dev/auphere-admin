import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  Brush,
  Flower2,
  HeartPulse,
  MessageCircle,
  Package,
  PenLine,
  Plus,
  Receipt,
  Scissors,
  Search,
  ShoppingCart,
  Smile,
  Sparkles,
  Stethoscope,
  Syringe,
  UtensilsCrossed,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "../../components/button";
import { Checklist, type ChecklistItem } from "../../components/checklist";
import { Combobox } from "../../components/combobox";
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
  /** El rubro, de un vistazo. Trece nombres en una rejilla se leen uno a uno;
   *  con icono se reconoce el tuyo sin leerlos todos (owner, 2026-09-28). */
  icono: LucideIcon;
};

const PLANTILLAS: Plantilla[] = [
  { id: "barbershop", nombre: "Barbería / Peluquería", para: "Reserva de citas, precios y horarios.", habilidades: 18, icono: Scissors },
  { id: "beauty", nombre: "Salón de belleza", para: "Citas y tratamientos, con sus tiempos.", habilidades: 14, icono: Sparkles },
  { id: "nail", nombre: "Estudio de uñas", para: "Citas, diseños y depósitos.", habilidades: 19, icono: Brush },
  // «wellness» era inglés dentro de una pantalla en español (owner,
  // 2026-09-28). El nombre vive en la semilla, así que se cambia allí.
  { id: "spa", nombre: "Spa (belleza y bienestar)", para: "Reservas y paquetes.", habilidades: 14, icono: Flower2 },
  { id: "dental", nombre: "Clínica dental", para: "Citas, urgencias y presupuestos.", habilidades: 14, icono: Smile },
  { id: "clinica", nombre: "Clínica / Consultorio", para: "Citas y preguntas frecuentes.", habilidades: 13, icono: Stethoscope },
  { id: "medspa", nombre: "Medicina estética (sin cirugía)", para: "Citas y valoraciones.", habilidades: 14, icono: Syringe },
  { id: "restaurante", nombre: "Restaurante (reservas)", para: "Reservas, carta y horarios.", habilidades: 13, icono: UtensilsCrossed },
  { id: "generic", nombre: "Genérica (asistente básico)", para: "Responde lo básico del negocio.", habilidades: 5, icono: MessageCircle },
  // «medspa» también era inglés.
  { id: "aesthetic", nombre: "Clínica estética (con cirugía)", para: "Citas, valoraciones y referencias quirúrgicas.", habilidades: 15, icono: HeartPulse },
  { id: "cobranza", nombre: "Cobranza / Asistente del administrador", para: "Recordatorios y estado de pagos.", habilidades: 12, icono: Receipt },
  { id: "inventario", nombre: "Inventario / Asistente de almacén", para: "Control de existencias, entradas y salidas.", habilidades: 5, icono: Package },
  { id: "woocommerce", nombre: "Ventas / Tienda WooCommerce", para: "Catálogo, pedidos y envíos.", habilidades: 9, icono: ShoppingCart },
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
              <span className="flex min-w-0 items-center gap-2">
                <p.icono aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 truncate font-medium">{p.nombre}</span>
              </span>
              {/* Para qué sirve y cuánto trae: es lo que convierte trece
                  nombres en una decisión. Hoy la tarjeta enseña su clave
                  interna y el número de herramientas. Ya no dice «te pedirá N
                  datos» porque las trece piden lo mismo. */}
              <span className="text-sm text-pretty text-muted-foreground">{p.para}</span>
              <span className="text-xs text-muted-foreground tabular-nums">Enciende {p.habilidades} habilidades</span>
            </button>
          ))}
          <button
            type="button"
            role="radio"
            aria-checked={elegida === "ninguna"}
            onClick={() => setElegida("ninguna")}
            className="flex min-w-0 flex-col items-start gap-1 rounded-md border border-dashed border-border px-3 py-2 text-left transition-colors hover:bg-muted/60 aria-checked:border-foreground aria-checked:bg-muted"
          >
            <span className="flex min-w-0 items-center gap-2">
              <PenLine aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
              <span className="font-medium">Ninguna de estas</span>
            </span>
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
type Dia = (typeof DIAS)[number];
type Tramo = { abre: string; cierra: string } | null;

const POR_DEFECTO: Record<Dia, Tramo> = {
  Lunes: { abre: "10:00", cierra: "19:00" },
  Martes: { abre: "10:00", cierra: "19:00" },
  Miércoles: { abre: "10:00", cierra: "19:00" },
  Jueves: { abre: "10:00", cierra: "19:00" },
  Viernes: { abre: "10:00", cierra: "19:00" },
  Sábado: { abre: "10:00", cierra: "14:00" },
  Domingo: null,
};

/**
 * El horario, con controles de hora en vez de texto libre.
 *
 * **Esto es lo que mató el campo «Sábados»** (owner, 2026-09-28). Ese campo
 * existía porque el horario era una cadena que alguien escribía a mano y los
 * sábados no cabían en ella. Aquí el sábado es un día más.
 *
 * **Día a día primero** (owner, 2026-09-28). El resumido parecía más amable,
 * pero mentía por omisión: casi ningún negocio abre los siete días igual, así
 * que empezar por «de lunes a viernes» obliga a descubrir dónde se corrige. Se
 * enseña la verdad y se ofrece resumirla.
 *
 * **Un día cerrado se quita, no se apaga.** La «X» lo saca de la lista y deja
 * un «+» para volver a ponerlo. Un interruptor «Abre / Cerrado» con dos horas
 * al lado que ya no significan nada era una fila que se contradecía.
 */
function Horario() {
  const [dias, setDias] = useState<Record<Dia, Tramo>>(POR_DEFECTO);
  const [resumido, setResumido] = useState(false);

  function cambiar(dia: Dia, tramo: Tramo) {
    setDias((d) => ({ ...d, [dia]: tramo }));
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="text-sm font-medium">Horario</legend>

      {resumido ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-32 shrink-0 text-sm">Todos los días</span>
          <Input type="time" defaultValue="10:00" aria-label="Abre" className="w-32" />
          <span className="text-sm text-muted-foreground">a</span>
          <Input type="time" defaultValue="19:00" aria-label="Cierra" className="w-32" />
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {DIAS.map((dia) => {
            const tramo = dias[dia];
            return (
              <div key={dia} className="flex flex-wrap items-center gap-2">
                <span className="w-24 shrink-0 text-sm">{dia}</span>
                {tramo ? (
                  <>
                    <Input
                      type="time"
                      value={tramo.abre}
                      onChange={(e) => cambiar(dia, { ...tramo, abre: e.target.value })}
                      aria-label={`${dia}: abre`}
                      className="w-32"
                    />
                    <span className="text-sm text-muted-foreground">a</span>
                    <Input
                      type="time"
                      value={tramo.cierra}
                      onChange={(e) => cambiar(dia, { ...tramo, cierra: e.target.value })}
                      aria-label={`${dia}: cierra`}
                      className="w-32"
                    />
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label={`${dia}: cerrado`}
                      onClick={() => cambiar(dia, null)}
                    >
                      <X aria-hidden="true" />
                    </Button>
                  </>
                ) : (
                  <>
                    <span className="text-sm text-muted-foreground">Cerrado</span>
                    <Button
                      size="icon-sm"
                      variant="outline"
                      aria-label={`${dia}: abrir`}
                      onClick={() => cambiar(dia, { abre: "10:00", cierra: "19:00" })}
                    >
                      <Plus aria-hidden="true" />
                    </Button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      <button
        type="button"
        onClick={() => setResumido((v) => !v)}
        aria-expanded={!resumido}
        className="self-start text-sm text-muted-foreground underline underline-offset-4"
      >
        {resumido ? "Poner un horario por día" : "Todos los días son iguales"}
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

/**
 * Confirmar.
 *
 * **Ya no se pregunta si publicar** (owner, 2026-09-28). Era una decisión sin
 * consecuencia: el cliente no atiende hasta estar configurado y con canal, así
 * que «publícalo ahora» no adelantaba nada — solo obligaba a elegir entre dos
 * palabras que no cambiaban el día siguiente. Publicar es un paso de la ficha,
 * donde la tarjeta ya lo pide.
 *
 * **Y el resumen dejó de ser una lista de términos.** Repetir «Nombre:
 * Barbería El Corte» debajo de donde acabas de escribirlo no informa. Lo que
 * falta saber es **qué va a pasar al pulsar**, así que eso es lo que se
 * enseña: qué se crea, con qué agente, y con qué **no** nace.
 */
function PasoConfirmar({
  etapas,
}: {
  etapas?: Array<{ key: string; label: string; status: EstadoEtapa; detail?: string }>;
}) {
  const plantilla = PLANTILLAS[0]!;
  const fallida = etapas?.find((e) => e.status === "failed");

  return (
    <div className="flex flex-col gap-4">
      {/* Quién es, con la cara de su rubro. */}
      <div className="flex min-w-0 items-start gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
          <plantilla.icono aria-hidden="true" className="size-5 text-muted-foreground" />
        </span>
        <div className="flex min-w-0 flex-col gap-1">
          <span className="font-medium">Barbería El Corte</span>
          <span className="text-sm text-muted-foreground">
            {plantilla.nombre} · Europe/Madrid · Calle Mayor 3, Madrid
          </span>
          <span className="text-sm text-muted-foreground">De lunes a viernes 10:00–19:00 · sábados 10:00–14:00</span>
        </div>
      </div>

      {/* Qué va a pasar, en **dos** cosas y no en cuatro frases sueltas: lo que
          se crea, y lo que quedará pendiente. Las cuatro pesaban igual y se
          leían como un muro (owner, 2026-09-28).

          Y los tres pendientes son, uno a uno, los tres pasos de «Pasos para
          activar tu agente». No es una lista de advertencias: es la tarjeta
          que va a ver al llegar, enseñada antes de llegar. */}
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-medium">Al crearlo</h3>
          <p className="text-sm text-pretty text-muted-foreground">
            Se crea el cliente y se escribe su agente, con {plantilla.habilidades} habilidades encendidas.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Y le quedarán tres pasos</h3>
          <Checklist
            dense
            ariaLabel="Lo que quedará pendiente"
            items={[
              {
                key: "publicar",
                label: "Publicar el agente",
                status: "todo",
                detail: "Nace en borrador. Lo revisas y lo publicas desde su ficha.",
              },
              {
                key: "credito",
                label: "Asignarle crédito",
                status: "todo",
                detail: "Empieza en cero: sin crédito no responde. Se lo das tú desde Consumo.",
              },
              {
                key: "canal",
                label: "Conectar un canal",
                status: "todo",
                detail: "Sin canal no le llegan mensajes.",
              },
            ]}
          />
          <p className="text-sm text-muted-foreground">Su ficha te los irá pidiendo, no hace falta que los recuerdes.</p>
        </div>
      </div>

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
              El cliente ya existe y su agente está escrito. Puedes reintentar aquí o seguir desde su ficha.
            </p>
          ) : null}
        </section>
      ) : (
        <Navegacion atras siguiente="Crear el cliente" siguienteActivo />
      )}
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
          { key: "cupo", label: "Preparar su cupo", status: "todo" },
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
          { key: "cupo", label: "Preparar su cupo", status: "failed", detail: "El servidor no respondió." },
        ]}
      />
    </Marco>
  ),
};

/**
 * El cupo se dice **antes** de pedir el primer dato, no después del
 * formulario.
 *
 * **No hay plan que comprar** (owner, 2026-09-28): a un partner no se le cobra
 * por añadir un cliente. Así que la pantalla no vende nada — dice la única
 * salida que existe hoy y quién puede dar la otra, con las mismas palabras
 * que usa la API al rechazar: «Archive a client you no longer need or ask
 * Auphere to raise the limit».
 *
 * **Y queda una pregunta abierta.** El owner cree que los partners no tienen
 * límite de clientes; `partners.max_clients` existe, vale 5 por defecto y
 * bloquea con un 409 antes de crear nada. Si el límite no debe existir, esta
 * pantalla sobra entera. Mientras exista, tiene que decir algo.
 */
export const CupoLleno: Story = {
  name: "Cupo lleno",
  render: () => (
    <Marco paso={0}>
      <EmptyState
        icon={Users}
        title="Has llegado a tus 5 clientes"
        description="Archiva uno que ya no uses para dejar un sitio libre, o escríbenos y te ampliamos el límite."
        action={<Button variant="outline">Archivar un cliente</Button>}
      />
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
