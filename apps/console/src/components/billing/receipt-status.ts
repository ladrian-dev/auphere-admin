import type { MessageKey } from "@/i18n/messages";

type Tone = "positive" | "info" | "muted";

/**
 * El estado de un recibo en palabras (spec 047, prototipo): la API manda el
 * código de `invoices.status` (`draft`, `issued`, `paid`, `void`) y la pantalla
 * lo escribía tal cual. Uno que no conozca sale con el código, en gris.
 */
const RECEIPT: Record<string, { key: MessageKey; tone: Tone }> = {
  paid: { key: "proto.billing.receipt.paid", tone: "positive" },
  issued: { key: "proto.billing.receipt.issued", tone: "info" },
  draft: { key: "proto.billing.receipt.draft", tone: "muted" },
  void: { key: "proto.billing.receipt.void", tone: "muted" },
};

export function receiptStatus(status: string, t: (key: MessageKey) => string): { label: string; tone: Tone } {
  const known = RECEIPT[status];
  return known ? { label: t(known.key), tone: known.tone } : { label: status, tone: "muted" };
}
