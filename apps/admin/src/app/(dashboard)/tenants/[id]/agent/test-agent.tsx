"use client";

/**
 * Block O — "Probar agente" dialog.
 *
 * Chat-like sandbox UI:
 *
 *  1. Operator clicks the play button next to the prompt textarea.
 *  2. Dialog opens. A version badge shows what's being tested (staged
 *     draft if there is one, else active).
 *  3. Operator types a message + Send. We POST history + new message;
 *     response shows assistant_message + any planned tool calls (with
 *     "DRY RUN — sandbox no ejecuta tools" banner).
 *  4. History persists in dialog state across multiple turns.
 *  5. "Reiniciar conversación" clears history; "Cerrar" closes.
 *
 * Hard rules from ADR-014:
 *  - The dialog NEVER stores history in localStorage / the DB. Closing
 *    discards.
 *  - Tool cards always show ``Sandbox · sin ejecutar`` so the operator
 *    doesn't confuse the sandbox with production.
 */

import { Play, RotateCcw, SendHorizonal } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type {
  PlannedToolCall,
  TestAgentHistoryMessage,
  TestTurnOut,
} from "@/lib/backend";

import { testAgentTurnAction } from "./actions";

type TurnEntry = {
  user: string;
  assistant: string;
  planned: PlannedToolCall[];
  iterations: number;
  latency_ms: number;
  tokens?: {
    input: number | null;
    output: number | null;
    cached: number | null;
  };
};

export function TestAgentButton({ tenantId }: { tenantId: string }) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<TurnEntry[]>([]);
  const [versionLabel, setVersionLabel] = useState<string | null>(null);

  function reset() {
    setTurns([]);
    setDraft("");
    setVersionLabel(null);
  }

  function onOpenChange(next: boolean) {
    if (pending) return;
    setOpen(next);
    if (!next) reset();
  }

  function send() {
    const message = draft.trim();
    if (!message) return;
    const history: TestAgentHistoryMessage[] = turns.flatMap((t) => [
      { role: "user", content: t.user },
      { role: "assistant", content: t.assistant },
    ]);
    setDraft("");
    start(async () => {
      const res = await testAgentTurnAction(tenantId, {
        user_message: message,
        history,
      });
      if (!res.ok) {
        toast.error(`No se pudo correr la prueba: ${res.error}`);
        // Restore the draft so the operator doesn't lose what they typed.
        setDraft(message);
        return;
      }
      const out: TestTurnOut = res.data;
      setVersionLabel(`v${out.version_tested} · ${out.version_status}`);
      setTurns((prev) => [
        ...prev,
        {
          user: message,
          assistant: out.assistant_message,
          planned: out.planned_tool_calls,
          iterations: out.iterations,
          latency_ms: out.latency_ms,
          tokens: {
            input: out.input_tokens,
            output: out.output_tokens,
            cached: out.cached_input_tokens,
          },
        },
      ]);
    });
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5"
      >
        <Play className="size-3.5" />
        Probar agente
      </Button>

      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <div className="flex items-center justify-between gap-3">
              <div className="flex flex-col gap-1">
                <DialogTitle className="inline-flex items-center gap-2">
                  <Play className="size-4" /> Probar agente
                </DialogTitle>
                <DialogDescription>
                  Sandbox. Mismo modelo + prompt + whitelist que producción,
                  pero las tools <strong>no se ejecutan</strong> y la
                  conversación no se guarda. Cerrá el dialog para descartar
                  el historial.
                </DialogDescription>
              </div>
              {versionLabel ? (
                <Badge variant="outline" className="text-[10px] uppercase">
                  {versionLabel}
                </Badge>
              ) : null}
            </div>
          </DialogHeader>

          <div className="grid gap-3 max-h-[60vh] overflow-y-auto pr-1">
            {turns.length === 0 ? (
              <div className="rounded-md border border-dashed border-border bg-muted/30 px-4 py-10 text-center text-sm text-muted-foreground">
                Escribí un mensaje como si fueras el cliente y mandalo
                con Enter. El sandbox usa la versión staged más reciente
                o la activa si no hay borrador.
              </div>
            ) : (
              turns.map((turn, i) => (
                <TurnRow key={i} turn={turn} />
              ))
            )}
          </div>

          <div className="flex items-center gap-2">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Mensaje del cliente simulado"
              disabled={pending}
              className="flex-1"
            />
            <Button
              type="button"
              size="sm"
              disabled={pending || !draft.trim()}
              onClick={send}
              className="inline-flex items-center gap-1.5"
            >
              <SendHorizonal className="size-3.5" />
              {pending ? "Enviando…" : "Enviar"}
            </Button>
          </div>

          <DialogFooter className="flex-wrap gap-2">
            {turns.length > 0 ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={reset}
                disabled={pending}
                className="inline-flex items-center gap-1.5"
              >
                <RotateCcw className="size-3.5" />
                Reiniciar conversación
              </Button>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function TurnRow({ turn }: { turn: TurnEntry }) {
  return (
    <div className="grid gap-2">
      <div className="self-end max-w-[80%] rounded-md bg-blue-50 dark:bg-blue-950/30 border border-blue-200/60 px-3 py-2 text-sm whitespace-pre-wrap break-words">
        {turn.user}
      </div>
      <div className="grid gap-2 max-w-[80%]">
        <div className="rounded-md bg-muted/50 border border-border px-3 py-2 text-sm whitespace-pre-wrap break-words">
          {turn.assistant || (
            <span className="italic text-muted-foreground">
              (sin texto final — el modelo se quedó pidiendo tools)
            </span>
          )}
        </div>
        {turn.planned.map((p) => (
          <ToolCallCard key={p.tool_call_id} call={p} />
        ))}
        <div className="text-[10px] font-mono uppercase text-muted-foreground tabular-nums flex flex-wrap gap-3">
          <span>{turn.latency_ms} ms</span>
          <span>{turn.iterations} llm call{turn.iterations === 1 ? "" : "s"}</span>
          {turn.tokens?.input ? <span>in: {turn.tokens.input}</span> : null}
          {turn.tokens?.output ? <span>out: {turn.tokens.output}</span> : null}
          {turn.tokens?.cached ? <span>cached: {turn.tokens.cached}</span> : null}
        </div>
      </div>
    </div>
  );
}

function ToolCallCard({ call }: { call: PlannedToolCall }) {
  return (
    <div className="rounded-md border border-amber-300/60 bg-amber-50/40 dark:bg-amber-950/20 px-3 py-2 text-xs">
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="font-mono font-medium">{call.name}</span>
        <Badge
          variant="outline"
          className="text-[9px] uppercase border-amber-500/60 text-amber-700 dark:text-amber-300"
        >
          Sandbox · sin ejecutar
        </Badge>
      </div>
      <pre className="overflow-x-auto rounded bg-muted/60 p-2 font-mono text-[11px] leading-relaxed">
        {JSON.stringify(call.arguments, null, 2)}
      </pre>
    </div>
  );
}
