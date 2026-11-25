import Link from "next/link";

import { EmptyState, ErrorState, PageHeader } from "@nexus/ui";

import { backend } from "@/lib/backend";
import { requirePageOperator } from "@/lib/session";

export const metadata = { title: "Playground QA" };
export const dynamic = "force-dynamic";

/**
 * Spec 031: the Playground had no entry of its own — it lived only at
 * /qa/{tenant}/chat. This is its door: pick the client whose agent you
 * want to talk to.
 */
export default async function QaIndexPage() {
  // Spec 079: only roles with `qa` reach this page; the rest get «no encontrada».
  await requirePageOperator("qa");
  const tenants = await backend.listTenants().catch(() => null);
  return (
    <>
      <PageHeader title="Playground QA" description="Conversa con el agente de un cliente sin tocar sus canales reales." />
      {tenants === null ? (
        <ErrorState title="No se pudieron leer los clientes" description="La API no respondió." />
      ) : tenants.length === 0 ? (
        <EmptyState title="Todavía no hay clientes" description="Crea uno para poder probar su agente." readonly />
      ) : (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {tenants
            .filter((t) => t.status !== "archived")
            .map((t) => (
              <li key={t.id}>
                <Link
                  href={`/qa/${t.id}/chat`}
                  className="flex flex-col gap-1 rounded-md bg-card px-4 py-3 ring-1 ring-foreground/10 outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="text-sm font-medium">{t.name}</span>
                  <span className="font-mono text-xs text-muted-foreground">{t.slug}</span>
                </Link>
              </li>
            ))}
        </ul>
      )}
    </>
  );
}
