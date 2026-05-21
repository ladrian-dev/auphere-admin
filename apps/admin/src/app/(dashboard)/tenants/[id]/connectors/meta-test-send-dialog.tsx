"use client";

/**
 * "Enviar prueba" dialog for the connected Meta WhatsApp channel.
 *
 * Hits ``POST /admin/tenants/{tid}/integrations/meta/test-send`` and
 * surfaces the returned wamid as a toast. Defaults to the pre-approved
 * ``hello_world`` template so the call works outside the 24h service
 * window (which is the common case when the operator just clicks
 * "Enviar prueba" right after Embedded Signup).
 *
 * Surfaces dual purpose:
 *  1. Smoke test the BISUAT after Embedded Signup completes.
 *  2. Exercise the ``whatsapp_business_messaging`` permission so Meta's
 *     App Review counter increments without leaving admin.auphere.com
 *     — useful for the screencast.
 */

import { Send } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { metaTestSendAction } from "./setup-actions";

type Kind = "template" | "text";

export function MetaTestSendDialog({ tenantId }: { tenantId: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [to, setTo] = useState("");
  const [kind, setKind] = useState<Kind>("template");
  const [templateName, setTemplateName] = useState("hello_world");
  const [language, setLanguage] = useState("en_US");
  const [textBody, setTextBody] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!to.trim()) {
      toast.error("Falta el número de destino", {
        description: "Ingresa un número en formato E.164 (ej. +56911112222).",
      });
      return;
    }
    setBusy(true);
    try {
      const payload =
        kind === "template"
          ? {
              to: to.trim(),
              kind,
              template_name: templateName.trim() || "hello_world",
              language: language.trim() || "en_US",
            }
          : {
              to: to.trim(),
              kind,
              text_body: textBody,
            };
      const result = await metaTestSendAction(tenantId, payload);
      if (!result.ok) {
        toast.error("Meta rechazó el envío", { description: result.error });
        return;
      }
      toast.success("Mensaje enviado", {
        description: `wamid ${result.data.wamid}`,
      });
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (busy) return;
        setOpen(next);
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant="outline">
            <Send className="h-3.5 w-3.5" strokeWidth={1.75} />
            Enviar prueba
          </Button>
        }
      />
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Enviar mensaje de prueba</DialogTitle>
          <DialogDescription>
            Usa el BISUAT del tenant para enviar un mensaje desde el número
            conectado. El template <code>hello_world</code> está pre-aprobado y
            funciona aunque no haya ventana de servicio abierta.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="meta-test-to">Número destino (E.164)</Label>
            <Input
              id="meta-test-to"
              placeholder="+56911112222"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              autoComplete="off"
              disabled={busy}
            />
          </div>

          <div className="flex gap-2 text-xs">
            <button
              type="button"
              onClick={() => setKind("template")}
              disabled={busy}
              className={[
                "flex-1 rounded-md border px-3 py-2 text-left transition",
                kind === "template"
                  ? "border-primary/50 bg-primary/[0.04]"
                  : "border-border hover:border-border/80",
              ].join(" ")}
            >
              <div className="font-medium">Template</div>
              <div className="text-muted-foreground text-[11px] leading-snug">
                Funciona fuera de la ventana de 24h
              </div>
            </button>
            <button
              type="button"
              onClick={() => setKind("text")}
              disabled={busy}
              className={[
                "flex-1 rounded-md border px-3 py-2 text-left transition",
                kind === "text"
                  ? "border-primary/50 bg-primary/[0.04]"
                  : "border-border hover:border-border/80",
              ].join(" ")}
            >
              <div className="font-medium">Texto libre</div>
              <div className="text-muted-foreground text-[11px] leading-snug">
                Requiere ventana abierta (24h)
              </div>
            </button>
          </div>

          {kind === "template" ? (
            <div className="grid grid-cols-2 gap-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="meta-test-tpl">Template</Label>
                <Input
                  id="meta-test-tpl"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="meta-test-lang">Idioma</Label>
                <Input
                  id="meta-test-lang"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  disabled={busy}
                />
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="meta-test-body">Cuerpo del mensaje</Label>
              <Input
                id="meta-test-body"
                placeholder="Ping desde Auphere"
                value={textBody}
                onChange={(e) => setTextBody(e.target.value)}
                disabled={busy}
              />
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={busy}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Enviando…" : "Enviar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
