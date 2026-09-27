import type { Meta, StoryObj } from "@storybook/react-vite";
import { AlertTriangle, Check, RotateCw } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription } from "../../components/alert";
import { Button } from "../../components/button";
import { HelpHint } from "../../components/help-hint";
import { Input } from "../../components/input";
import { Label } from "../../components/label";
import { Meter } from "../../components/meter";
import { Metric } from "../../components/metric";
import { NativeSelect } from "../../components/native-select";
import { Section } from "../../components/section";
import { StatusBadge } from "../../components/status-badge";
import { StatusDot } from "../../components/status-dot";
import { Stepper } from "../../components/stepper";
import { TooltipProvider } from "../../components/tooltip";
import { UiCopyProvider } from "../../components/ui-copy";

/**
 * Prototipo · iteración 1 (spec 018, R1/R2/R6): el Resumen del cliente.
 *
 * Solo forma: copy real en español, nada de router, de i18n ni de API.
 *
 * **La decisión que este prototipo somete a aprobación** es qué significa
 * «resumen completo». El owner pidió ver «todos los datos importantes»; un
 * resumen que lo enseña todo deja de resumir y vuelve a ser una pantalla que
 * hay que leer entera. Así que el Resumen contesta **cuatro preguntas**, con
 * la cifra que responde a cada una y el detalle a un clic:
 *
 *   1. **¿Atiende?** — y si no, qué falta y quién puede resolverlo.
 *   2. **¿Cuánto consume y cuánto le queda?** — créditos, gasto y a qué ritmo.
 *   3. **¿Cómo va la conversación?** — volumen, escaladas y fallos.
 *   4. **¿Qué tiene conectado?** — canales y conectores, con lo que necesita
 *      atención primero.
 *
 * Lo demás que fija:
 *
 *   - **Sin actividad no es cero.** Un cliente recién creado dice «todavía no
 *     hay datos», no «0», que se lee como una caída.
 *   - **Una lectura caída no tumba la pantalla.** El Resumen junta cuatro
 *     fuentes; si una falla, lo dice en su bloque y ofrece reintentar, y las
 *     otras tres siguen. Por eso se piden por separado.
 *   - **El crédito sobrevive a la puesta en marcha.** Hoy comparten tarjeta, y
 *     por eso se ve pesada; pero el crédito sigue importando cuando los cuatro
 *     pasos están hechos, así que es un bloque del Resumen y no un paso.
 *   - **Nombre y zona horaria se editan aquí**, que es donde se leen, y su
 *     edición **no** entra en el borrador del agente: cambiar el nombre del
 *     negocio no es cambiar lo que el agente hace.
 *   - **Quien no puede escribir no ve controles muertos**, y lee las cifras
 *     igual.
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

// 1 ── ¿Atiende?

function BloqueAtiende({
  atiende,
  falta,
  puedeEscribir = true,
}: {
  atiende: boolean;
  falta?: string;
  puedeEscribir?: boolean;
}) {
  return (
    <Section
      title={
        <span className="inline-flex items-center gap-2">
          <StatusDot tone={atiende ? "positive" : "warning"} />
          {atiende ? "Atendiendo" : `Sin atender · falta ${falta}`}
        </span>
      }
      // No puede decir «falta conectar un canal» y debajo «WhatsApp
      // conectado»: sería la pantalla contradiciéndose en dos líneas.
      description={
        atiende
          ? "Agente · versión 3 · WhatsApp conectado · +34 600 123 456"
          : "Agente · versión 1 · sin canal conectado"
      }
      actions={
        puedeEscribir ? (
          <Button size="xs" variant="ghost">
            Ver el agente
          </Button>
        ) : undefined
      }
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        {atiende ? (
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <Check className="size-4 text-status-positive" aria-hidden="true" /> Activo desde el 12 de agosto
          </span>
        ) : null}
        <span className="text-muted-foreground">Sector: barbería</span>
      </div>
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
                <Button size="xs" variant="outline">
                  Asignar más crédito
                </Button>
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

// Datos del cliente, que dejan de ser una pestaña

function BloqueDatos({ puedeEscribir = true }: { puedeEscribir?: boolean }) {
  const [nombre, setNombre] = useState(CLIENTE.nombre);
  return (
    <Section
      title="Datos del cliente"
      description="Cambiarlos no toca lo que el agente hace, así que no crea un borrador."
      className="min-w-0"
    >
      {puedeEscribir ? (
        <form className="grid gap-3 sm:grid-cols-3 sm:items-end">
          <div className="grid gap-1 min-w-0">
            <Label htmlFor="proto-nombre">Nombre</Label>
            <Input id="proto-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </div>
          <div className="grid gap-1 min-w-0">
            <Label htmlFor="proto-zona">Zona horaria</Label>
            <NativeSelect id="proto-zona" defaultValue={CLIENTE.zona}>
              <option value="Europe/Madrid">Europe/Madrid</option>
              <option value="America/Santiago">America/Santiago</option>
            </NativeSelect>
          </div>
          {/* Sin estirar: un botón del ancho de la columna se lee como una
              franja de acción principal, y esto es guardar dos campos.
              (Si aquí se ve estirado, el Storybook que estás mirando lleva
              horas abierto y su Tailwind no ha vuelto a escanear: reinícialo
              antes de buscar el fallo en el código. Me pasó.) */}
          <Button type="button" className="sm:justify-self-start">
            Guardar
          </Button>
        </form>
      ) : (
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
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
    </Section>
  );
}

/** La puesta en marcha, sola. Ya no comparte fila con el crédito — es lo que
 *  la hacía pesada— y desaparece entera cuando los cuatro pasos están. */
function PuestaEnMarcha() {
  return (
    <Section
      title="Puesta en marcha"
      description="Lo que falta para que el agente atienda. Los cuatro pasos se pueden hacer en cualquier orden."
    >
      <Stepper
        variant="line"
        ordered={false}
        ariaLabel="Puesta en marcha"
        current={-1}
        steps={[
          { key: "agente", label: <span>Agente <span className="text-xs text-muted-foreground">· versión 1</span></span>, state: "done" },
          { key: "canal", label: "Canal", state: "current" },
          { key: "credito", label: "Crédito", state: "done" },
          { key: "activacion", label: "Activación", state: "done" },
        ]}
        stepOfLabel={() => "3 de 4 pasos hechos"}
      />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-1">
        <span className="text-sm text-muted-foreground">Siguiente paso</span>
        <Button>Conectar un canal</Button>
        <p className="text-xs text-muted-foreground">Un canal es por donde llegan los mensajes: hoy WhatsApp.</p>
      </div>
    </Section>
  );
}

// ── Las historias ───────────────────────────────────────────────────────

/** El caso normal: atiende, y las cuatro preguntas tienen respuesta. */
export const Atendiendo: Story = {
  render: () => (
    <>
      <BloqueAtiende atiende />
      <div className="grid gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo />
        <BloqueConversacion />
      </div>
      <BloqueConectado />
      <BloqueDatos />
    </>
  ),
};

/** A medio configurar: la puesta en marcha aparece **sola**, y el crédito
 *  sigue siendo un bloque del Resumen y no un paso suyo. */
export const AMedioConfigurar: Story = {
  render: () => (
    <>
      <PuestaEnMarcha />
      <BloqueAtiende atiende={false} falta="conectar un canal" />
      <div className="grid gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo />
        <BloqueConversacion estado="sin-datos" />
      </div>
      <BloqueConectado />
      <BloqueDatos />
    </>
  ),
};

/** Recién creado. Ningún bloque enseña un cero que parezca una caída. */
export const SinActividad: Story = {
  render: () => (
    <>
      <BloqueAtiende atiende={false} falta="conectar un canal" />
      <div className="grid gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo estado="sin-datos" />
        <BloqueConversacion estado="sin-datos" />
      </div>
      <BloqueConectado />
      <BloqueDatos />
    </>
  ),
};

/** Una de las cuatro lecturas no llegó. Lo dice en su bloque, ofrece
 *  reintentar, y los otros tres siguen funcionando. */
export const UnaLecturaCaida: Story = {
  render: () => (
    <>
      <BloqueAtiende atiende />
      <div className="grid gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo estado="error" />
        <BloqueConversacion />
      </div>
      <BloqueConectado />
      <BloqueDatos />
    </>
  ),
};

/** Sin crédito: el agente calla, y la pantalla lo dice donde está la cifra
 *  que lo explica, con la salida al lado. */
export const SinCredito: Story = {
  render: () => (
    <>
      <BloqueAtiende atiende={false} falta="crédito" />
      <div className="grid gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo agotado />
        <BloqueConversacion />
      </div>
      <BloqueConectado />
      <BloqueDatos />
    </>
  ),
};

/** Analista: lee las mismas cifras y no ve un solo control que le
 *  respondería que no tiene permiso. */
export const Analista: Story = {
  render: () => (
    <>
      <BloqueAtiende atiende puedeEscribir={false} />
      <div className="grid gap-(--space-block) lg:grid-cols-2">
        <BloqueConsumo />
        <BloqueConversacion />
      </div>
      <BloqueConectado />
      <BloqueDatos puedeEscribir={false} />
    </>
  ),
};

/** A 390 px: los cuatro bloques se apilan y nada se sale. */
export const Movil: Story = {
  parameters: { viewport: { defaultViewport: "mobile2" } },
  render: () => (
    <>
      <BloqueAtiende atiende />
      <BloqueConsumo />
      <BloqueConversacion />
      <BloqueConectado />
      <BloqueDatos />
    </>
  ),
};
