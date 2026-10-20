import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@nexus/ui";

import { canStart } from "@/components/channels/labels";
import { backend } from "@/lib/backend";

import { TikTokConnectDialog } from "../../../_integrations/tiktok-connect-dialog";
import { ConnectWhatsApp } from "./connect-whatsapp";

export const dynamic = "force-dynamic";

/** Step 2 — connect the chosen channel with the flow it already has. */
export default async function ConnectChannelPage({ params }: { params: Promise<{ id: string; channel: string }> }) {
  const { id, channel } = await params;
  const [catalog, tenant, links] = await Promise.all([
    backend.getChannelCatalog().catch(() => []),
    backend.getTenant(id).catch(() => null),
    // One live link per client (owner, 2026-10-20): the dialog says when a
    // new one replaces it.
    channel === "whatsapp" ? backend.listSignupLinks(id).catch(() => []) : Promise.resolve([]),
  ]);
  const entry = catalog.find((c) => c.key === channel);
  // A channel that cannot start has no step 2: back to the catalog.
  if (!entry || !canStart(entry.availability)) redirect(`/tenants/${id}/channels/new`);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold">Conectar {entry.name}</h2>
        <p className="text-sm text-pretty text-muted-foreground">{entry.description}</p>
      </div>
      {channel === "whatsapp" ? <ConnectWhatsApp
          tenantId={id}
          businessName={tenant?.name ?? "tu negocio"}
          hasLiveLink={links.some((l) => l.state === "valid")}
        /> : null}
      {channel === "tiktok" ? (
        <div className="flex flex-col gap-3 rounded-md p-6 ring-1 ring-foreground/10">
          <p className="text-sm text-pretty text-muted-foreground">
            TikTok autoriza en su propia página y vuelve a la lista de canales del cliente. Después asigna su agente desde
            «Configurar».
          </p>
          <div>
            <TikTokConnectDialog tenantId={id} />
          </div>
        </div>
      ) : null}
      <div>
        <Button nativeButton={false} variant="ghost" render={<Link href={`/tenants/${id}/channels/new`} />}>
          Elegir otro canal
        </Button>
      </div>
    </div>
  );
}
