import { reasonText } from "@/components/clients/v2/client-v2-model";
import { moneyText } from "@/components/money/money-model";
import type { MessageKey } from "@/i18n/messages";
import type { PanelAttention, PanelAttentionCode } from "@/lib/backend/home-usage";

/**
 * «Lo que te necesita» (spec 071): cómo se dice y cómo se arregla cada fila de
 * la lista. La lista la manda la API (una sola regla); aquí solo se pinta, igual
 * en el Panel, en «Ahora» de la campana y en los avisos de Consumo.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const PARTNER: ReadonlySet<PanelAttentionCode> = new Set([
  "build_cap_exhausted",
  "build_cap_warning",
  "account_empty",
  "account_low",
  "billing_payment_failed",
]);

/** Lo que afecta al dinero: lo que Consumo enseña en sus avisos (5.1). */
export const MONEY_CODES: ReadonlySet<PanelAttentionCode> = new Set([
  "build_cap_exhausted",
  "build_cap_warning",
  "account_empty",
  "account_low",
  "no_balance",
  "low_balance",
]);

const CRITICAL: ReadonlySet<PanelAttentionCode> = new Set([
  "build_cap_exhausted",
  "account_empty",
  "billing_payment_failed",
  "no_balance",
  "channel_problem",
]);

export function isPartnerRow(row: PanelAttention): boolean {
  return row.scope ? row.scope === "partner" : PARTNER.has(row.code);
}

/** Rojo para lo que ya se paró, ámbar para lo que se va a parar (nunca solo color: va con su texto). */
export function attentionSeverity(row: PanelAttention): "critical" | "warning" {
  return row.severity ?? (CRITICAL.has(row.code) ? "critical" : "warning");
}

/** La primera línea de la fila: el cliente, o de qué parte de la cuenta se trata. */
export function attentionTitle(t: T, row: PanelAttention): string {
  if (!isPartnerRow(row)) return row.client_name ?? row.external_client_ref ?? "";
  if (row.code.startsWith("build_cap")) return t("att.title.build");
  if (row.code.startsWith("account")) return t("att.title.account");
  return t("att.title.billing");
}

/** La segunda línea: qué pasa, con la cifra cuando la API la manda. */
export function attentionText(t: T, row: PanelAttention): string {
  const d = row.data ?? {};
  switch (row.code) {
    case "build_cap_exhausted":
      return t("att.build_cap_exhausted");
    case "build_cap_warning":
      return d.spent && d.cap && d.pct != null
        ? t("att.build_cap_warning.figures", { spent: moneyText(d.spent), cap: moneyText(d.cap), pct: d.pct })
        : t("att.build_cap_warning");
    case "account_empty":
      return t("att.account_empty");
    case "account_low":
      return d.days_left != null
        ? t("att.account_low.days", { days: Math.max(1, Math.round(d.days_left)) })
        : d.available
          ? t("att.account_low.amount", { amount: moneyText(d.available) })
          : t("att.account_low");
    case "billing_payment_failed":
      return t("att.billing_payment_failed");
    default:
      return reasonText(
        t,
        row.code as Parameters<typeof reasonText>[1],
        row.count,
        d.days_left != null ? ({ days_left: d.days_left } as Parameters<typeof reasonText>[3]) : null,
      );
  }
}

/**
 * El arreglo de una fila: el saldo se asigna o se pide en el sitio, la
 * ampliación del tope se pide en el sitio; lo demás lleva a su pantalla.
 */
export type AttentionFix = { kind: "assign" | "request" | "build" } | { kind: "link"; href: string; label: MessageKey };

export function attentionFix(row: PanelAttention): AttentionFix {
  switch (row.action) {
    case "assign_balance":
      return { kind: "assign" };
    case "request_balance":
      return { kind: "request" };
    case "request_build_extension":
      return { kind: "build" };
    default:
      return { kind: "link", href: row.href, label: `panel.v2.fix.${row.action}` as MessageKey };
  }
}

/** Una clave estable por fila (lo del partner no tiene cliente). */
export function attentionKey(row: PanelAttention): string {
  return `${row.external_client_ref ?? "partner"}:${row.code}`;
}
