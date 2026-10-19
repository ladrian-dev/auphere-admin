"use client";

import { Wrench } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { CatalogBrowser, EmptyState } from "@nexus/ui";

import { catalogLabels, useCatalog } from "@/components/catalog/use-catalog";
import type { CapabilitiesOut } from "@/lib/backend";

import { CapabilityCard } from "./capability-card";

const FUNCTION_LABEL: Record<string, string> = {
  appointments: "Citas",
  orders: "Pedidos",
  messages: "Mensajes",
  escalation: "Escalado",
  knowledge: "Conocimiento",
  other: "Otras",
};

/** Spec 037: the partner console's Habilidades, in the operator panel. */
export function CapabilitiesCatalog({
  tenantId,
  data,
  seeAllHref,
  seeOwnHref,
  agentId,
}: {
  tenantId: string;
  data: CapabilitiesOut;
  seeAllHref: string;
  seeOwnHref: string;
  agentId?: string;
}) {
  const router = useRouter();
  const catalog = useCatalog(`/tenants/${tenantId}/capabilities`);
  const labels = React.useMemo(
    () => catalogLabels({ title: "Habilidades", category: (k) => FUNCTION_LABEL[k] ?? k, activeLabel: "Activos" }),
    [],
  );
  const items = React.useMemo(
    () =>
      data.groups
        .flatMap((g) => g.items)
        .map((cap) => ({
          id: `${cap.kind}:${cap.key}`,
          name: cap.business_name,
          search: cap.description,
          category: cap.function,
          active: cap.enabled,
          cap,
        })),
    [data.groups],
  );
  const viewingAll = data.hidden_by_sector === 0 && data.sector !== null;

  return (
    <CatalogBrowser
      {...catalog}
      items={items}
      labels={labels}
      renderLink={(href, children, props) => (
        <Link href={href} {...props}>
          {children}
        </Link>
      )}
      renderItem={({ id, cap }) => (
        <CapabilityCard key={id} tenantId={tenantId} cap={cap} agentId={agentId} onChanged={() => router.refresh()} />
      )}
      empty={
        <EmptyState
          icon={Wrench}
          title="Auphere todavía no ha publicado habilidades para este entorno"
          description="En cuanto se publiquen aparecerán aquí. Los conectores sí se pueden conectar mientras tanto."
          readonly
        />
      }
      notice={
        data.sector === null ? (
          <p className="text-sm text-muted-foreground">Este cliente no tiene sector, así que se ven todas las habilidades.</p>
        ) : viewingAll ? (
          <p className="text-sm text-muted-foreground">
            Viendo todas las habilidades, también las de otros sectores.{" "}
            <Link href={seeOwnHref} className="underline underline-offset-4">
              Ver solo las de este sector
            </Link>
          </p>
        ) : data.hidden_by_sector > 0 ? (
          <p className="text-sm text-muted-foreground">
            {data.hidden_by_sector === 1
              ? "1 habilidad es de otro sector y no se muestra."
              : `${data.hidden_by_sector} habilidades son de otros sectores y no se muestran.`}{" "}
            <Link href={seeAllHref} className="underline underline-offset-4">
              Ver todas
            </Link>
          </p>
        ) : null
      }
    />
  );
}
