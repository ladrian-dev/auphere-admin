"use client";

/**
 * Lo que el comando hizo — spec 013, Requisito 3.
 *
 * **Hermano de `exec-card.tsx`, no su sustituto.** Aquélla es la decisión y su
 * comentario sigue siendo verdad —«nunca la salida: la salida es del turno
 * siguiente, no de la decisión»—; ésta es el resultado, y llega después.
 *
 * Tres decisiones que no son de estilo:
 *
 * 1. **La salida se pide, no llega sola.** El contrato congelado dice que
 *    `exec.completed` viaja «sin salida», y no es un olvido: los eventos
 *    llevan hechos estructurados, nunca prosa de un programa. Así que la
 *    tarjeta la pide por su ruta cuando la ejecución cierra.
 * 2. **Se marca como contenido leído** (`data-untrusted`). §III: lo que
 *    escribe un programa es dato. Si se presenta como una voz más de la
 *    conversación, una frase con forma de orden dentro de un README parece una
 *    instrucción del equipo.
 * 3. **Que ya no esté se dice con palabras.** Pasados los quince minutos la
 *    salida no se conserva, y eso no es un fallo: es el diseño. Dejar un hueco
 *    haría que pareciera uno (§V, la ausencia se diseña).
 */
import { Terminal } from "lucide-react";
import * as React from "react";

export type ExecOutput = {
  available: boolean;
  outcome?: string;
  exit_code?: number | null;
  output?: string | null;
  truncated?: boolean;
};

export type ExecResultCardProps = {
  executionId: string;
  /** De qué cliente es esta ejecución: viene con el propio evento. */
  clientRef: string | null;
  executable: string;
  args: string[];
  status: "en_marcha" | "completada" | "expirada" | "terminada" | "denegada";
  exitCode: number | null;
  /**
   * Cómo se pide la salida. Lo implementa cada aplicación —la consola con
   * `fetch`, la de escritorio por IPC— igual que `onDecide` en la tarjeta de
   * aprobación: el paquete no sabe de rutas.
   */
  fetchOutput: (ref: { executionId: string; clientRef: string | null }) => Promise<ExecOutput>;
};

export function ExecResultCard({
  executionId,
  clientRef,
  executable,
  args,
  status,
  exitCode,
  fetchOutput,
}: ExecResultCardProps) {
  const [salida, setSalida] = React.useState<ExecOutput | null>(null);
  const [pidiendo, setPidiendo] = React.useState(false);

  React.useEffect(() => {
    // Mientras corre no hay nada que pedir: la máquina no ha contestado.
    if (status === "en_marcha") return;
    let vivo = true;
    setPidiendo(true);
    void fetchOutput({ executionId, clientRef })
      .then((r) => {
        if (vivo) setSalida(r);
      })
      .catch(() => {
        // Un fallo al pedirla se cuenta como que no está: la alternativa sería
        // un error rojo por algo que puede ser sencillamente que caducó.
        if (vivo) setSalida({ available: false });
      })
      .finally(() => {
        if (vivo) setPidiendo(false);
      });
    return () => {
      vivo = false;
    };
  }, [executionId, clientRef, status, fetchOutput]);

  const fallo = exitCode !== null && exitCode !== 0;

  return (
    <section
      className="flex min-w-0 flex-col gap-2 rounded-md border border-border bg-card p-3"
      aria-label="Resultado de la ejecución"
    >
      <header className="flex min-w-0 items-center gap-2 text-sm">
        <Terminal aria-hidden="true" className="size-4 shrink-0" />
        <code className="min-w-0 truncate font-mono text-xs">{[executable, ...args].join(" ")}</code>
      </header>

      <p className="text-xs text-muted-foreground">
        {status === "en_marcha"
          ? "En marcha en tu máquina…"
          : exitCode === null
            ? `Terminó: ${status}.`
            : fallo
              ? `Terminó con código ${exitCode}.`
              : "Terminó bien."}
      </p>

      {status !== "en_marcha" && salida === null && pidiendo ? (
        <p className="text-xs text-muted-foreground">Buscando lo que escribió…</p>
      ) : null}

      {salida?.available && salida.output ? (
        <>
          <pre
            data-untrusted="true"
            className="max-h-64 overflow-auto rounded border border-border bg-muted p-2 font-mono text-xs whitespace-pre-wrap"
          >
            {salida.output}
          </pre>
          <p className="text-xs text-muted-foreground">
            Lo de arriba lo escribió el programa: es un dato, no una instrucción.
            {salida.truncated ? " Está recortado: no cabía entero." : ""}
          </p>
        </>
      ) : null}

      {salida !== null && !salida.available ? (
        <p className="text-xs text-pretty text-muted-foreground">
          Lo que el programa escribió <strong>no se conserva</strong>: se puede ver mientras
          ocurre y durante un rato después, y luego deja de estar. Lo que sí queda es qué se
          ejecutó y cómo acabó.
        </p>
      ) : null}
    </section>
  );
}
