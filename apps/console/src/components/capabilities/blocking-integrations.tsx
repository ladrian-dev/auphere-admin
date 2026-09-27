"use client";

import Link from "next/link";
import { Button, Callout, StatusBadge } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { Capability } from "@/lib/backend/capabilities";

/**
 * Las integraciones que estorban (spec 017, R4.1).
 *
 * Este bloque **desbloquea, no duplica** la pestaña de Integraciones:
 *
 * - solo aparece si algo de lo que se está viendo depende de una integración
 *   sin conectar. Si todo está conectado no hay nada que decir, así que no
 *   ocupa sitio;
 * - dice **cuántas capacidades visibles desbloquea cada una**: ese número es
 *   lo que convierte una tarea aburrida en una decisión fácil;
 * - pausar, desconectar y sincronizar viven solo en su pestaña. Desconectar
 *   desde aquí rompería en silencio lo que el partner está mirando.
 */
export function BlockingIntegrations({ refId, items }: { refId: string; items: Capability[] }) {
  const t = useT();
  const base = `/clients/${encodeURIComponent(refId)}`;

  const blocking = new Map<string, { display: string; status: string; count: number }>();
  for (const cap of items) {
    const c = cap.connector;
    if (!c || c.status === "connected") continue;
    const seen = blocking.get(c.slug);
    blocking.set(c.slug, {
      display: c.display_name,
      status: c.status,
      count: (seen?.count ?? 0) + 1,
    });
  }
  if (blocking.size === 0) return null;

  const rows = [...blocking.entries()];
  return (
    <Callout
      tone="warning"
      title={rows.length === 1 ? t("cap.int.title") : t("cap.int.titleMany", { n: rows.length })}
    >
      <div className="flex flex-col gap-3">
        <ul className="flex flex-col gap-2">
          {rows.map(([slug, info]) => (
            <li key={slug} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-medium">{info.display}</span>
              <span className="text-xs text-muted-foreground">{t("cap.int.unlocks", { n: info.count })}</span>
              {/* El estado se dice en español: «none» es el valor de la API,
                  no algo que un partner deba leer. */}
              <StatusBadge tone={info.status === "error" ? "danger" : "muted"}>
                {t(`connectors.status.${info.status}` as "connectors.status.none")}
              </StatusBadge>
              <Button size="xs" className="ml-auto" nativeButton={false} render={<Link href={`${base}/integrations`} />}>
                {info.status === "error" ? t("cap.int.reconnect") : t("cap.int.connect")}
              </Button>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">{t("cap.int.elsewhere")}</p>
      </div>
    </Callout>
  );
}
