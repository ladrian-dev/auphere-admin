import { ErrorState } from "@nexus/ui";

import { ChannelTile } from "@/components/channels/channel-tile";
import { backend } from "@/lib/backend";

export const dynamic = "force-dynamic";

/** Step 1 — the catalog, as Chatwoot's «Elegir canal». */
export default async function ChooseChannelPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const catalog = await backend.getChannelCatalog().catch(() => null);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold">Elige un canal</h2>
        <p className="text-sm text-muted-foreground">Los marcados «Próximamente» todavía no se pueden conectar.</p>
      </div>
      {catalog === null ? (
        <ErrorState title="No se pudo leer el catálogo de canales" description="La API no respondió." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {catalog.map((entry) => (
            <ChannelTile key={entry.key} entry={entry} href={`/tenants/${id}/channels/new/${entry.key}`} />
          ))}
        </div>
      )}
    </div>
  );
}
