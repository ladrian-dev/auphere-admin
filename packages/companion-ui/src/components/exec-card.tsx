"use client";

/**
 * La tarjeta de una ejecución en la máquina — spec 003, Requisitos 10.3 y 10.5.
 *
 * Lo que enseña, y por qué exactamente esto:
 *
 * * **El comando literal**: ejecutable, argumentos uno a uno y el subdirectorio.
 *   Sin esto la persona aprueba una frase, no una orden — y la frase la
 *   escribió un modelo.
 * * **Nunca la salida.** Aquí no hay nada que pintar del resultado: la salida
 *   es del turno siguiente, no de la decisión (§III).
 * * **Tres respuestas y no dos**: «una vez», «siempre» y «nunca». Las dos
 *   últimas guardan la preferencia de **esta persona**; ninguna la de nadie más.
 * * Cuando el techo del partner baja lo que la persona pidió, se dice —y se
 *   dice *dónde* se cambia—, en vez de guardar una preferencia que no se
 *   aplica y dejar que parezca rota (Requisito 10.4).
 *
 * `onPolicy` es **opcional**: donde no hay dónde guardar una preferencia (la
 * consola, hoy), los dos botones no se pintan. Un control que no hace nada es
 * una pantalla que miente.
 */
import { Terminal } from "lucide-react";
import * as React from "react";

import { Button } from "@nexus/ui";

import { useT } from "../i18n";
import type { ActionItem } from "../state";
import type { Decision } from "../types";

export type ExecMode = "ask" | "always" | "never";

export type ExecPreview = {
  executable: string;
  args: string[];
  cwdRelative: string | null;
  clientRef: string | null;
};

/** Lee el `preview` de una acción `local_exec`. Nunca lanza. */
export function readExecPreview(preview: Record<string, unknown> | null | undefined): ExecPreview | null {
  if (!preview || typeof preview !== "object") return null;
  const executable = preview.executable;
  if (typeof executable !== "string" || !executable) return null;
  const rawArgs = preview.args;
  return {
    executable,
    args: Array.isArray(rawArgs) ? rawArgs.filter((a): a is string => typeof a === "string") : [],
    cwdRelative: typeof preview.cwd_relative === "string" ? preview.cwd_relative : null,
    clientRef: typeof preview.client_ref === "string" ? preview.client_ref : null,
  };
}

type Props = {
  item: ActionItem;
  busy: boolean;
  /** El techo del partner bajó lo que esta persona prefiere. */
  capped?: boolean;
  onDecide: (decision: Decision) => void;
  /** Guardar la preferencia. Sin él, los dos botones no existen. */
  onPolicy?: (mode: Exclude<ExecMode, "ask">) => void;
};

export function ExecCard({ item, busy, capped = false, onDecide, onPolicy }: Props) {
  const t = useT();
  const exec = readExecPreview(item.preview);
  const pending = item.state === "pending";
  if (!exec) return null;

  const command = [exec.executable, ...exec.args].join(" ");

  return (
    <section
      aria-label={t("companion.exec.title")}
      className={`min-w-0 rounded-sm border-2 p-3 ${pending ? "border-primary bg-card" : "border-border bg-card"}`}
    >
      <header className="flex min-w-0 items-center gap-2">
        <Terminal aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <h3 className="min-w-0 text-sm font-semibold text-balance">{t("companion.exec.title")}</h3>
      </header>

      <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted-foreground">{t("companion.exec.command")}</dt>
        <dd className="min-w-0">
          {/* Entero y seleccionable: aprobar a ciegas no debería ser posible. */}
          <code className="font-mono text-xs break-all select-all">{command}</code>
        </dd>
        {exec.cwdRelative ? (
          <>
            <dt className="text-muted-foreground">{t("companion.exec.cwd")}</dt>
            <dd className="min-w-0 font-mono text-xs break-all">{exec.cwdRelative}</dd>
          </>
        ) : null}
        {exec.clientRef ? (
          <>
            <dt className="text-muted-foreground">{t("companion.exec.client")}</dt>
            <dd className="min-w-0 truncate">{exec.clientRef}</dd>
          </>
        ) : null}
      </dl>

      <p className="mt-2 text-xs text-pretty text-muted-foreground">{t("companion.exec.undo")}</p>

      {pending ? (
        <div className="mt-3 flex min-w-0 flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={() => onDecide("confirm")}>
            {t("companion.exec.once")}
          </Button>
          {onPolicy ? (
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => {
                onPolicy("always");
                onDecide("confirm");
              }}
            >
              {t("companion.exec.always")}
            </Button>
          ) : null}
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onDecide("cancel")}>
            {t("companion.exec.reject")}
          </Button>
          {onPolicy ? (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                onPolicy("never");
                onDecide("cancel");
              }}
            >
              {t("companion.exec.never")}
            </Button>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground" role="status">
          {item.decision === "confirm" ? t("companion.exec.ran") : t("companion.exec.notRan")}
        </p>
      )}

      {capped ? (
        <p className="mt-2 text-xs text-pretty text-muted-foreground" role="note">
          {t("companion.exec.capped")}
        </p>
      ) : null}
    </section>
  );
}
