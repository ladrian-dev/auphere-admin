import { redirect } from "next/navigation";

import { ErrorState, PageHeader } from "@nexus/ui";

import { isChannelOnly } from "@/components/connectors/labels";
import { backend } from "@/lib/backend";

import { ConnectorsGrid } from "./connectors-grid";

export const dynamic = "force-dynamic";

/**
 * Spec 035: Conectores — every app the client's agent can work with that is
 * not a messaging channel. The channel rows (WhatsApp, TikTok) live in
 * Canales; an old `?tiktok=` link is sent there.
 */
export default async function TenantConnectorsPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tiktok?: string }>;
}) {
  const { id } = await params;
  const { tiktok } = await searchParams;
  if (tiktok) redirect(`/tenants/${id}/channels?tiktok=${encodeURIComponent(tiktok)}`);

  const [catalog, installed] = await Promise.all([
    backend.listConnectors().catch(() => null),
    backend.listTenantConnectors(id).catch(() => null),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        size="compact"
        title="Conectores"
        description="Las apps con las que trabaja el agente de este cliente: citas, cobros, tienda, documentos. Los canales de mensajería están en Canales."
      />
      {catalog === null || installed === null ? (
        <ErrorState title="No se pudieron leer los conectores" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <ConnectorsGrid
          tenantId={id}
          rows={catalog
            .filter((c) => !isChannelOnly(c) && c.status !== "deprecated")
            .map((c) => ({
              connector: c,
              status: installed.find((tc) => tc.connector_slug === c.slug)?.status ?? null,
            }))}
        />
      )}
    </div>
  );
}
