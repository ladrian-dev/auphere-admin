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
    // La excepción medida: doce. Queda anotada en paridad.
    campos: [
      ...CAMPOS_COMUNES,
      "Sábados",
      "Profesional titular",
      "Credencial del titular",
      "Clínica de referencia",
      "Teléfono de referencia",
      "Instagram",
      "Teléfono de recepción",
      "Precio de la consulta",
      "Tabla de precios",
      "Formas de pago",
    ],
  },
  { id: "cobranza", nombre: "Cobranza / Asistente del administrador", para: "Recordatorios y estado de pagos.", habilidades: 12, campos: [] },
  { id: "inventario", nombre: "Inventario / Asistente de almacén", para: "Stock y entradas y salidas.", habilidades: 5, campos: [] },
  { id: "woocommerce", nombre: "Ventas / Tienda WooCommerce", para: "Catálogo, pedidos y envíos.", habilidades: 9, campos: [] },
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

function PasoNegocio({ plantilla }: { plantilla: Plantilla }) {
  const [nombre, setNombre] = useState("");
  const [zona, setZona] = useState("Europe/Madrid");
  const [avanzadas, setAvanzadas] = useState(false);
  const total = 2 + plantilla.campos.length;

  return (
    <div className="flex flex-col gap-4">
      {/* La frase que hace corto un formulario corto. Sin ella, cuatro
          campos se leen como «cuatro, de momento». */}
      <p className="text-sm text-pretty text-muted-foreground">
        {plantilla.campos.length === 0
          ? `«${plantilla.nombre}» no necesita nada más del negocio. Solo esto y ya existe.`
          : `Esto es todo lo que «${plantilla.nombre}» necesita para empezar: ${total} datos. El resto se lo puedes ir contando desde su ficha.`}
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
        {plantilla.campos.map((campo) => (
          <div key={campo} className="grid min-w-0 content-start gap-2">
            <Label htmlFor={`pn-${campo}`}>{campo}</Label>
            <Input id={`pn-${campo}`} />
          </div>
        ))}
      </div>

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

/** El caso normal: diez de las trece plantillas piden exactamente esto. */
export const NegocioDosCampos: Story = {
  name: "2 · El negocio (cuatro campos)",
  render: () => (
    <Marco paso={1}>
      <PasoNegocio plantilla={PLANTILLAS[0]!} />
    </Marco>
  ),
};

/** Tres plantillas no piden nada del negocio. */
export const NegocioSinCampos: Story = {
  name: "2 · El negocio (dos campos)",
  render: () => (
    <Marco paso={1}>
      <PasoNegocio plantilla={PLANTILLAS.find((p) => p.id === "cobranza")!} />
    </Marco>
  ),
};

/**
 * La excepción medida: `aesthetic_clinic_v1` exige doce campos y no se puede
 * evitar sin tocar su semilla. Se enseña **tal cual es** en vez de esconderla:
 * si el prototipo solo mostrara el caso bonito, la aprobación valdría para una
 * pantalla que no existe.
 */
export const NegocioCasoPesado: Story = {
  name: "2 · El negocio (la excepción: catorce campos)",
  render: () => (
    <Marco paso={1}>
      <PasoNegocio plantilla={PLANTILLAS.find((p) => p.id === "aesthetic")!} />
    </Marco>
  ),
};

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
      <PasoNegocio plantilla={PLANTILLAS[0]!} />
    </Marco>
  ),
};
