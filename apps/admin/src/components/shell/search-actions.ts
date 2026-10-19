"use server";

import { backend } from "@/lib/backend";
import { requireOperator } from "@/lib/session";

export type SearchIndex = {
  partners: { id: string; name: string; slug: string }[];
  tenants: { id: string; name: string; slug: string }[];
  tickets: { id: string; ref: string; topic: string; partner: string }[];
};

/**
 * Spec 031 (R2.4): what ⌘K can find. Three reads the panel already makes,
 * trimmed to what a search row shows; filtered in the browser. A list that
 * fails comes back empty and the palette says so — the others still work.
 */
export async function loadSearchIndexAction(): Promise<{ index: SearchIndex; partial: boolean }> {
  await requireOperator();
  const [partners, tenants, tickets] = await Promise.allSettled([
    backend.listPartners(),
    backend.listTenants(),
    backend.listTickets({ status: "open" }),
  ]);
  return {
    partial: [partners, tenants, tickets].some((r) => r.status === "rejected"),
    index: {
      partners:
        partners.status === "fulfilled" ? partners.value.map((p) => ({ id: p.id, name: p.name, slug: p.slug })) : [],
      tenants:
        tenants.status === "fulfilled" ? tenants.value.map((t) => ({ id: t.id, name: t.name, slug: t.slug })) : [],
      tickets:
        tickets.status === "fulfilled"
          ? tickets.value.map((t) => ({ id: t.id, ref: t.ticket_ref, topic: t.topic, partner: t.partner_name }))
          : [],
    },
  };
}
