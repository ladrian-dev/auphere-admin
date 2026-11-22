"use client";

import Link from "next/link";
import * as React from "react";

import { cn } from "@nexus/ui";

import { BalanceDialogs } from "@/components/money/balance-button";
import { RowActions } from "@/components/row-actions";
import { clientHref } from "@/components/shell/routes-v2";
import { useT } from "@/i18n/client";
import type { PanelAttention } from "@/lib/backend/home-usage";

import { useBuildExtension } from "./build-extension-button";
import { attentionFix, attentionSeverity, attentionText, attentionTitle, isPartnerRow } from "./attention-model";

/**
 * Una fila de «Lo que te necesita» (spec 071). La misma en el Panel, en «Ahora»
 * de la campana y en los avisos de Consumo.
 *
 * Sin botones sueltos (Andrés, 2026-10-28, y para todas las filas, también las
 * de la cuenta, 2026-11-22): el arreglo es la primera opción del «⋯». El saldo se asigna o se pide, y la ampliación del tope se pide, aquí
 * mismo. Lo del partner no lleva a un cliente: su título dice qué parte de la
 * cuenta es.
 *
 * `compact`: la variante de la campana, con el arreglo como botón pequeño (no
 * cabe un menú dentro de otro menú).
 */
export function AttentionRow({ row, compact = false }: { row: PanelAttention; compact?: boolean }) {
  const t = useT();
  const [dialog, setDialog] = React.useState<"assign" | "request" | null>(null);
  const { ask: askBuild, asking } = useBuildExtension();
  const partner = isPartnerRow(row);
  const title = attentionTitle(t, row);
  const fix = attentionFix(row);
  const critical = attentionSeverity(row) === "critical";

  const first =
    fix.kind === "link"
      ? { label: t(fix.label), href: fix.href, primary: true }
      : fix.kind === "build"
        ? { label: t("panel.v2.fix.request_build_extension"), onSelect: askBuild, primary: true, disabled: asking }
        : fix.kind === "assign"
          ? { label: t("money.assign.cta"), onSelect: () => setDialog("assign"), primary: true }
          : { label: t("money.request.cta"), onSelect: () => setDialog("request"), primary: true };
  const open = !partner && row.external_client_ref ? [{ label: t("panel.v2.attention.open"), href: clientHref(row.external_client_ref) }] : [];

  return (
    <li className="flex min-w-0 items-center gap-x-4 gap-y-2 py-3" data-code={row.code} data-scope={partner ? "partner" : "client"}>
      <span aria-hidden="true" className={cn("size-2 shrink-0 rounded-full", critical ? "bg-status-danger" : "bg-status-warning")} />
      <div className="flex min-w-0 flex-1 flex-col">
        {partner || !row.external_client_ref ? (
          <span className="truncate text-sm font-medium">{title}</span>
        ) : (
          <Link href={clientHref(row.external_client_ref)} className="truncate text-sm font-medium hover:underline">
            {title}
          </Link>
        )}
        <span className="text-sm text-pretty text-muted-foreground">{attentionText(t, row)}</span>
      </div>
      <RowActions menu={!compact} ariaLabel={t("panel.v2.attention.more", { name: title })} actions={[first, ...open]} />
      {fix.kind === "assign" || fix.kind === "request" ? (
        row.external_client_ref ? <BalanceDialogs refId={row.external_client_ref} name={title} open={dialog} onClose={() => setDialog(null)} /> : null
      ) : null}
    </li>
  );
}
