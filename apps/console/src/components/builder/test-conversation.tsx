"use client";

import { Flag, Zap } from "lucide-react";

import { useT } from "@/i18n/client";
import type { TestStop, TestTurn } from "@/lib/backend/agent-quality-types";

/**
 * La conversación de una prueba en «Por qué falló» (spec 047, enmienda del
 * 2026-10-29; requisito 61.6), turno a turno y con el estilo del chat de
 * prueba: el cliente simulado a la derecha (`--bubble-out`), el agente a la
 * izquierda, y lo que habría hecho como una nota discontinua «Lo que habría
 * hecho: …». Debajo, por qué terminó. Quién habla va para los lectores de
 * pantalla. Sin altura fija: está dentro de un desplegable y se lee entera.
 */
export function TestConversation({ transcript, stop }: { transcript: TestTurn[]; stop: TestStop | null }) {
  const t = useT();
  return (
    <div className="grid min-w-0 gap-2" data-slot="test-conversation">
      <ol aria-label={t("builder.suite.conversation")} className="flex min-w-0 flex-col gap-2 rounded-md bg-(--chat-bg) p-3">
        {transcript.map((turn, i) => {
          const mine = turn.role === "customer";
          return (
            <li key={i} className={`flex min-w-0 flex-col gap-1 ${mine ? "items-end" : "items-start"}`} data-slot="test-turn" data-role={turn.role}>
              <span className="sr-only">{mine ? t("builder.suite.conversation.customer") : t("builder.suite.conversation.agent")}</span>
              <p
                className={`max-w-4/5 min-w-0 rounded-lg px-3 py-2 text-sm/snug text-pretty break-words whitespace-pre-line text-foreground shadow-xs ${
                  mine ? "bg-(--bubble-out)" : "bg-card"
                }`}
              >
                {turn.text}
              </p>
              {!mine && turn.actions.length ? (
                <ul className="grid max-w-full min-w-0 gap-1" data-slot="test-turn-actions">
                  {turn.actions.map((action, j) => (
                    <li key={j} className="flex min-w-0 items-start gap-2 rounded-lg border border-dashed border-input bg-card px-3 py-2 text-xs text-pretty text-muted-foreground">
                      <Zap aria-hidden="true" className="mt-px size-3 shrink-0" />
                      <span className="min-w-0 break-words">{t("builder.pg.would", { phrase: action })}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ol>
      {stop ? (
        <p className="flex min-w-0 items-start gap-2 text-xs text-pretty text-muted-foreground" data-slot="test-stop" data-stop={stop}>
          <Flag aria-hidden="true" className="mt-px size-3 shrink-0" />
          <span className="min-w-0">{t(`builder.suite.stop.${stop}`)}</span>
        </p>
      ) : null}
    </div>
  );
}
