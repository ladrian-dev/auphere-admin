"use client";

import { ExternalLink } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";

/**
 * Dentro de la aplicación de escritorio, conectar un canal de Meta se hace en
 * el navegador (spec 002, decisión D-2 de la evaluación). No hay botón apagado:
 * hay un enlace que copiar, y se dice como estado. Cuando el flujo sea estable
 * dentro de la cáscara, este componente desaparece.
 */
export function WhatsAppContinueInBrowser({ href }: { href: string }) {
  const t = useT();
  // La URL absoluta se compone al copiar: el origen es del navegador, no del render.
  const absolute = () => new URL(href, window.location.origin).toString();

  async function copy() {
    try {
      await navigator.clipboard.writeText(absolute());
      toast.success(t("ws.meta.copied"));
    } catch {
      /* sin portapapeles: el enlace sigue en pantalla */
    }
  }

  return (
    <div className="flex max-w-sm flex-col items-end gap-1" role="status">
      <Button type="button" variant="outline" onClick={() => void copy()}>
        <ExternalLink aria-hidden="true" />
        {t("ws.meta.copyLink")}
      </Button>
      <p className="text-xs text-muted-foreground text-pretty">{t("ws.meta.continueInBrowser")}</p>
      <output className="font-mono text-xs text-muted-foreground break-all">{href}</output>
    </div>
  );
}
