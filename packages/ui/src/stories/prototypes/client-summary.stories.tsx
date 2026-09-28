import type { Meta, StoryObj } from "@storybook/react-vite";
import { AlertTriangle, RotateCw } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription } from "../../components/alert";
import { Button } from "../../components/button";
import { Combobox } from "../../components/combobox";
import { HelpHint } from "../../components/help-hint";
import { Input } from "../../components/input";
import { Label } from "../../components/label";
import { Meter } from "../../components/meter";
import { Metric } from "../../components/metric";
import { Section } from "../../components/section";
import { StatusBadge } from "../../components/status-badge";
import { StatusDot } from "../../components/status-dot";
import { StepTrack } from "../../components/step-track";
import { TooltipProvider } from "../../components/tooltip";
import { UiCopyProvider } from "../../components/ui-copy";

/**
 * Prototipo · iteración 1 (spec 018, R1/R2/R6): el Resumen del cliente.
 *
 * Solo forma: copy real en español, nada de router, de i18n ni de API.
 *
 * **Aprobado por el owner el 2026-09-27**, y **puesto al día el 2026-09-28**
 * con lo que el propio owner cambió al ver la pantalla en marcha. Un
 * prototipo que describe una pantalla que ya no existe es peor que no
 * tenerlo: el siguiente lo lee y trabaja sobre lo que no hay.
 *
 * **La decisión que este prototipo sometió a aprobación** es qué significa
 * «resumen completo». El owner pidió ver «todos los datos importantes»; un
 * resumen que lo enseña todo deja de resumir y vuelve a ser una pantalla que
 * hay que leer entera. Así que el Resumen contesta **cuatro preguntas**, con
 * la cifra que responde a cada una y el detalle a un clic:
 *
 *   1. **¿Quién es?** — nombre, zona horaria y, en una sola línea, si atiende.
 *   2. **¿Cuánto consume y cuánto le queda?** — créditos, gasto y a qué ritmo.
 *   3. **¿Cómo va la conversación?** — volumen, escaladas y fallos.
 *   4. **¿Qué tiene conectado?** — canales y conectores, con lo que necesita
 *      atención primero.
 *
 * ## Lo que cambió el 2026-09-28, y por qué
 *
 * - **Los datos van primero, no al final.** Son la identidad, y son el único
 *   bloque que se edita: enterrarlos bajo cuatro bloques de solo lectura
 *   obligaba a recorrer la pantalla entera para cambiar un nombre.
 * - **El bloque «¿atiende?» desapareció.** Eran cinco bloques y tres de
 *   ellos decían lo mismo: la insignia de la cabecera, la tarjeta de pasos
 *   —que ya nombra lo que falta— y un «Sin atender · falta canal» debajo.
 *   Ahora el estado es **una línea** dentro de los datos, y los hechos
 *   sueltos (versión del agente, canal) viven en la tarjeta de pasos, que es
 *   donde se resuelven.
 * - **La zona horaria se elige de una lista**, no se escribe. Un campo de
 *   texto con sugerencias acepta «Europe/Madriz»; esto no.
 * - **Guardar va en la fila de los campos**, no debajo: dos campos cortos
 *   uno encima de otro desperdiciaban el ancho entero.
 * - **«Puesta en marcha» pasó a llamarse «Pasos para activar tu agente»**,
 *   en verde oscuro y con una barra por paso que enseña **cuánto** lleva
 *   hecho cada uno. Y sin botón al pie: el paso pendiente lleva su enlace en
 *   la misma línea donde los pasos hechos llevan su dato.
 *
 * Lo demás que fija, y que no ha cambiado:
 *
 *   - **Sin actividad no es cero.** Un cliente recién creado dice «todavía no
 *     hay datos», no «0», que se lee como una caída.
 *   - **Una lectura caída no tumba la pantalla.** El Resumen junta cuatro
 *     fuentes; si una falla, lo dice en su bloque y ofrece reintentar, y las
 *     otras tres siguen. Por eso se piden por separado.
 *   - **El crédito sobrevive a la puesta en marcha.** Compartían tarjeta, y
 *     por eso se veía pesada; pero el crédito sigue importando cuando los
 *     pasos están hechos, así que es un bloque del Resumen y no un paso.
 *   - **Editar los datos no entra en el borrador del agente**: cambiar el
 *     nombre del negocio no es cambiar lo que el agente hace.
 *   - **Quien no puede escribir no ve controles muertos**, y lee las cifras
 *     igual.
 *
 * Fuera de este prototipo, en la cabecera de la ficha: la insignia de estado
 * vive junto a «Más», a la altura del nombre del cliente.
 */
const meta = {
  title: "Prototipos/Resumen del cliente",
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

type Estado = "ok" | "sin-datos" | "error";

const CLIENTE = { nombre: "Panadería La Espiga", zona: "Europe/Madrid" };
const ZONAS = ["Europe/Madrid", "Europe/Lisbon", "America/Bogota", "America/Santiago", "America/Mexico_City"];

// ── Piezas ──────────────────────────────────────────────────────────────

/** Lo que un bloque enseña cuando su lectura no llegó. §V: se dice y se
 *  ofrece salida; no se finge un cero ni se tumba la pantalla. */
function LecturaCaida({ que }: { que: string }) {
  return (
    <Alert role="status" className="border-status-warning/40">
      <AlertDescription className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span>No se pudo leer {que}.</span>
        <Button size="xs" variant="outline">
          <RotateCw className="size-3" aria-hidden="true" />
          Reintentar
        </Button>
      </AlertDescription>
    </Alert>
  );
}

/** Sin actividad todavía. Un cero aquí se leería como una caída. */
function SinDatos({ children }: { children: string }) {
  return <p className="max-w-prose text-sm text-pretty text-muted-foreground">{children}</p>;
}

// 1 ── ¿Quién es? — y, en una línea, si atiende

/**
 * Los datos del cliente, que dejaron de ser una pestaña, con **una sola**
 * línea de estado debajo. Antes esto eran dos bloques y el estado se repetía
 * en tres sitios de la ficha.
 */
function BloqueIdentidad({
  atiende = true,
  falta,
  puedeEscribir = true,
}: {
  atiende?: boolean;
  falta?: string;
  puedeEscribir?: boolean;
}) {
  const [nombre, setNombre] = useState(CLIENTE.nombre);
  const [zona, setZona] = useState(CLIENTE.zona);
  return (
    <Section
      title="Datos del cliente"
      description="Cambiarlos no toca lo que el agente hace, así que no crea un borrador."
      actions={
        <Button size="xs" variant="ghost">
          Ver el agente
        </Button>
      }
      className="min-w-0"
    >
      {puedeEscribir ? (
        // Tres columnas: los dos campos y el botón en la misma fila. El
        // botón arranca a la altura de los campos, no de las etiquetas, y
        // el espaciador replica la etiqueta en vez de un margen a ojo.
        <form className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-start">
          <div className="grid min-w-0 content-start gap-2">
            <Label htmlFor="proto-nombre">Nombre</Label>
            <Input id="proto-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </div>
          <div className="grid min-w-0 content-start gap-2">
            <Label htmlFor="proto-zona">Zona horaria</Label>
            {/* Elegible, no escrita a mano: lo que se guarda sale siempre de
                la lista. Aquí van cinco zonas; en la consola son las ~400
                que el propio navegador conoce. */}
            <Combobox
              id="proto-zona"
              items={ZONAS}
              value={zona}
              onValueChange={setZona}
              emptyLabel="Nada coincide con lo que has escrito."
            />
          </div>
          <div className="grid content-start gap-2">
            <span aria-hidden="true" className="hidden text-sm leading-none sm:block">
              &nbsp;
            </span>
            <Button type="button">Guardar</Button>
          </div>
        </form>
      ) : (
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <div>
            <dt className="inline text-muted-foreground">Nombre: </dt>
            <dd className="inline">{CLIENTE.nombre}</dd>
          </div>
          <div>
            <dt className="inline text-muted-foreground">Zona horaria: </dt>
            <dd className="inline">{CLIENTE.zona}</dd>
          </div>
        </dl>
      )}

      {/* La única línea de toda la ficha que dice si el agente atiende. */}
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-3 text-sm">
        <span className="inline-flex items-center gap-2">
          <StatusDot tone={atiende ? "positive" : "warning"} />
          {atiende ? "Atendiendo" : `Sin atender · falta ${falta}`}
        </span>
        <span className="text-muted-foreground">Sector: barbería</span>
      </p>
    </Section>
  );
}

// 2 ── ¿Cuánto consume?

function BloqueConsumo({ estado = "ok", agotado = false }: { estado?: Estado; agotado?: boolean }) {
  const restantes = agotado ? 0 : 31_400;
  return (
    <Section
      title={
        <span className="inline-flex items-center gap-1">
          Crédito y consumo
          <HelpHint label="Crédito y consumo">
            Un crédito es una unidad de consumo. El agente gasta créditos al leer y al responder.
          </HelpHint>
        </span>
      }
      actions={
        <Button size="xs" variant="ghost">
          Ver el detalle
        </Button>
      }
      className="min-w-0"
    >
      {estado === "error" ? (
        <LecturaCaida que="el consumo" />
      ) : estado === "sin-datos" ? (
        <SinDatos>Todavía no ha gastado nada: el agente aún no ha atendido ninguna conversación.</SinDatos>
      ) : (
        <div className="flex flex-col gap-3">
          <Meter
            label="Crédito restante"
            labelHidden
            value={restantes}
            max={50_000}
            tone={agotado ? "danger" : "positive"}
            valueLabel={`Quedan ${restantes.toLocaleString("es")} de 50.000 créditos`}
            hint={`${(50_000 - restantes).toLocaleString("es")} gastados este mes`}
          />
          {agotado ? (
            <Alert role="status" className="border-status-warning/40">
              <AlertDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span>Sin crédito: el agente no está respondiendo.</span>
                <a href="#" className="font-medium underline underline-offset-4">
                  Asignar más crédito
                </a>
              </AlertDescription>
            </Alert>
          ) : (
            <p className="text-sm text-muted-foreground">
              Al ritmo de estos 30 días, acabará el mes en <span className="tabular-nums">17.778</span> créditos.
            </p>
          )}
        </div>
      )}
    </Section>
  );
}

// 3 ── ¿Cómo va la conversación?

function BloqueConversacion({ estado = "ok" }: { estado?: Estado }) {
  return (
    <Section title="Conversaciones" description="Últimos 30 días" className="min-w-0">
      {estado === "error" ? (
        <LecturaCaida que="las conversaciones" />
      ) : estado === "sin-datos" ? (
        <SinDatos>Todavía no ha habido ninguna conversación.</SinDatos>
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          <Metric label="Conversaciones" value="128" href="#" />
          <Metric label="Escaladas" value="9" hint="7 % del total" href="#" />
          <Metric label="Mensajes fallidos" value="2" href="#" />
        </div>
      )}
    </Section>
  );
}

// 4 ── ¿Qué tiene conectado?

function BloqueConectado({ estado = "ok" }: { estado?: Estado }) {
  return (
    <Section
      title="Lo que tiene conectado"
      actions={
        <Button size="xs" variant="ghost">
          Conectores
        </Button>
      }
      className="min-w-0"
    >
      {estado === "error" ? (
        <LecturaCaida que="lo que tiene conectado" />
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {/* Lo que necesita atención, primero. */}
          <li className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <AlertTriangle className="size-4 text-status-warning" aria-hidden="true" />
            <span className="font-medium">WooCommerce</span>
            <StatusBadge tone="danger">Error</StatusBadge>
            <span className="text-xs text-muted-foreground">desbloquea 12 habilidades</span>
            <Button size="xs" variant="outline" className="ml-auto">
              Reconectar
            </Button>
          </li>
          <li className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-medium">WhatsApp</span>
            <StatusBadge tone="positive">Conectado</StatusBadge>
            <span className="text-xs text-muted-foreground">+34 600 123 456</span>
          </li>
          <li className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-medium">AgendaPro</span>
            <StatusBadge tone="positive">Conectado</StatusBadge>
          </li>
          <li className="text-xs text-muted-foreground">2 conectores más sin conectar.</li>
        </ul>
      )}
    </Section>
  );
}

/**
 * Los pasos para activar, solos. Ya no comparten fila con el crédito —es lo
 * que los hacía pesados— y desaparecen enteros cuando están todos hechos.
 *
 * En verde oscuro porque es lo único que hay que hacer ahora mismo y compite
 * con cuatro bloques blancos; un segundo panel en este tono y ninguno de los
 * dos destacaría. Tres pasos, tres barras del mismo ancho, y un contador que
 * cuenta barras: el ojo cuenta barras, así que el contador tiene que contar
 * lo mismo.
 */
function PasosParaActivar() {
  return (
    <Section
      tone="spotlight"
      title="Pasos para activar tu agente"
      description="Cuando estén hechos, tu agente empieza a atender. Puedes hacerlos en el orden que quieras."
      actions={<span className="text-sm text-pistachio tabular-nums">2 de 3 pasos hechos</span>}
      className="min-w-0"
    >
      <StepTrack
        ariaLabel="Pasos para activar tu agente"
        summary="2 de 3 pasos hechos"
        steps={[
          // «Agente» son dos cosas: escribirlo y publicarlo. La barra a
          // medias lo dice sin tener que explicarlo.
          { key: "agente", label: "Agente", done: 2, of: 2, detail: "v1" },
          {
            key: "canal",
            label: "Canal",
            done: 0,
            of: 1,
            current: true,
            href: "#",
            hrefLabel: "Conectar un canal",
          },
          { key: "credito", label: "Crédito", done: 2, of: 2, detail: "50.000" },
        ]}
      />
    </Section>
  );
}

// ── Las historias ───────────────────────────────────────────────────────

/** El caso normal: atiende, y las cuatro preguntas tienen respuesta. */
export const Atendiendo: Story = {
  render: () => (
    <>
      <BloqueIdentidad atiende />
      <div className="grid grid-cols-1 gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo />
        <BloqueConversacion />
      </div>
      <BloqueConectado />
    </>
  ),
};

/** A medio configurar: los pasos aparecen **solos** y arriba del todo, y el
 *  crédito sigue siendo un bloque del Resumen y no un paso suyo. */
export const AMedioConfigurar: Story = {
  render: () => (
    <>
      <PasosParaActivar />
      <BloqueIdentidad atiende={false} falta="conectar un canal" />
      <div className="grid grid-cols-1 gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo />
        <BloqueConversacion estado="sin-datos" />
      </div>
      <BloqueConectado />
    </>
  ),
};

/** Recién creado. Ningún bloque enseña un cero que parezca una caída. */
export const SinActividad: Story = {
  render: () => (
    <>
      <BloqueIdentidad atiende={false} falta="conectar un canal" />
      <div className="grid grid-cols-1 gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo estado="sin-datos" />
        <BloqueConversacion estado="sin-datos" />
      </div>
      <BloqueConectado />
    </>
  ),
};

/** Una de las cuatro lecturas no llegó. Lo dice en su bloque, ofrece
 *  reintentar, y los otros tres siguen funcionando. */
export const UnaLecturaCaida: Story = {
  render: () => (
    <>
      <BloqueIdentidad atiende />
      <div className="grid grid-cols-1 gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo estado="error" />
        <BloqueConversacion />
      </div>
      <BloqueConectado />
    </>
  ),
};

/** Sin crédito: el agente calla, y la pantalla lo dice donde está la cifra
 *  que lo explica, con la salida al lado. */
export const SinCredito: Story = {
  render: () => (
    <>
      <BloqueIdentidad atiende={false} falta="crédito" />
      <div className="grid grid-cols-1 gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo agotado />
        <BloqueConversacion />
      </div>
      <BloqueConectado />
    </>
  ),
};

/** Analista: lee las mismas cifras y no ve un solo control que le
 *  respondería que no tiene permiso. */
export const Analista: Story = {
  render: () => (
    <>
      <BloqueIdentidad atiende puedeEscribir={false} />
      <div className="grid grid-cols-1 gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo />
        <BloqueConversacion />
      </div>
      <BloqueConectado />
    </>
  ),
};

/** A 390 px: los bloques se apilan y nada se sale. */
export const Movil: Story = {
  parameters: { viewport: { defaultViewport: "mobile2" } },
  render: () => (
    <>
      <PasosParaActivar />
      <BloqueIdentidad atiende={false} falta="conectar un canal" />
      <BloqueConsumo />
      <BloqueConversacion />
      <BloqueConectado />
    </>
  ),
};
