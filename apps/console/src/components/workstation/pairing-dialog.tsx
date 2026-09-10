"use client";

import { Copy, Laptop } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@nexus/ui";

import { issuePairingCodeAction } from "@/app/(console)/workstation/actions";
import { useT } from "@/i18n/client";
import type { PairingCodeOut } from "@/lib/backend/workstation";

/**
 * «Emparejar esta máquina» — Requisito 3 (spec 002).
 *
 * El canal entre la consola y la cáscara es la persona: aquí se muestra el
 * código, en la barra de la aplicación se teclea. Cinco estados: cerrado,
 * generando, mostrado con cuenta atrás, caducado y error. **Al cerrar, el
 * código no se vuelve a mostrar** — la base solo guarda su hash.
 */
type Phase =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "shown"; code: PairingCodeOut }
  | { kind: "expired" }
  | { kind: "error" };

function mmss(secondsLeft: number): string {
  const s = Math.max(0, secondsLeft);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function PairingDialog({ variant = "default" }: { variant?: "default" | "outline" }) {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const [phase, setPhase] = React.useState<Phase>({ kind: "idle" });
  const [left, setLeft] = React.useState(0);

  const issue = React.useCallback(async () => {
    setPhase({ kind: "loading" });
    const res = await issuePairingCodeAction();
    if (!res.ok) {
      setPhase({ kind: "error" });
      return;
    }
    setPhase({ kind: "shown", code: res.data });
    setLeft(res.data.ttl_seconds);
  }, []);

  React.useEffect(() => {
    if (phase.kind !== "shown") return;
    const expiresAt = Date.parse(phase.code.expires_at);
    const tick = () => {
      const remaining = Math.round((expiresAt - Date.now()) / 1000);
      if (remaining <= 0) {
        setPhase({ kind: "expired" });
        return;
      }
      setLeft(remaining);
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [phase]);

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) void issue();
    else setPhase({ kind: "idle" }); // nunca se vuelve a mostrar
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      toast.success(t("ws.pair.copied"));
    } catch {
      /* sin portapapeles: el código sigue en pantalla */
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <Button type="button" variant={variant} onClick={() => onOpenChange(true)}>
        <Laptop aria-hidden="true" />
        {t("ws.pair.button")}
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("ws.pair.title")}</DialogTitle>
          <DialogDescription>{t("ws.pair.intro")}</DialogDescription>
        </DialogHeader>
        {phase.kind === "loading" ? (
          <p role="status" className="text-sm text-muted-foreground">
            {t("ws.pair.loading")}
          </p>
        ) : null}
        {phase.kind === "shown" ? (
          <div className="flex flex-col items-center gap-3 py-2">
            <output aria-label={t("ws.pair.title")} className="font-mono text-3xl tracking-widest tabular-nums">
              {phase.code.code}
            </output>
            <p className="text-sm text-muted-foreground tabular-nums" role="timer" aria-live="off">
              {t("ws.pair.expiresIn", { mmss: mmss(left) })}
            </p>
            <Button type="button" variant="outline" size="sm" onClick={() => void copy(phase.code.code)}>
              <Copy aria-hidden="true" />
              {t("ws.pair.copy")}
            </Button>
          </div>
        ) : null}
        {phase.kind === "expired" ? (
          <p role="status" className="text-sm">
            {t("ws.pair.expired")}
          </p>
        ) : null}
        {phase.kind === "error" ? (
          <p role="alert" className="text-sm text-destructive">
            {t("ws.pair.error")}
          </p>
        ) : null}
        <DialogFooter className="items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground text-pretty">{t("ws.pair.onceOnly")}</p>
          <div className="flex gap-2">
            {phase.kind === "expired" || phase.kind === "error" ? (
              <Button type="button" variant="outline" onClick={() => void issue()}>
                {t("ws.pair.another")}
              </Button>
            ) : null}
            <Button type="button" onClick={() => onOpenChange(false)}>
              {t("ws.pair.done")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
