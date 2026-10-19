import { Settings2 } from "lucide-react";
import Link from "next/link";

import { Button, EmptyState, ErrorState, PageHeader, StatusDot } from "@nexus/ui";

import { ChannelIcon } from "@/components/brand/channel-icon";
import { CHANNEL_NAME, CHANNEL_STATUS, ROLE_LABEL } from "@/components/channels/labels";
import { backend } from "@/lib/backend";

export const dynamic = "force-dynamic";

const TIKTOK_RESULT: Record<string, { tone: "ok" | "error"; text: string }> = {
  connected: { tone: "ok", text: "TikTok quedó conectado." },
  state_expired: { tone: "error", text: "La autorización de TikTok caducó. Vuelve a empezar desde «Añadir canal»." },
};

/**
 * Spec 035: the client's channels, like Chatwoot's inbox list — one row per
 * channel with its mark, name, type · identifier and state, and «Configurar».
 * «Añadir canal» opens the four-step wizard.
 */
export default async function TenantChannelsPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tiktok?: string }>;
}) {
  const { id } = await params;
  const tiktok = (await searchParams).tiktok;
  const channels = await backend.listChannels(id).catch(() => null);
  const visible = channels?.filter((c) => c.provider !== "qa_playground") ?? null;
  const result = tiktok ? (TIKTOK_RESULT[tiktok] ?? { tone: "error" as const, text: `TikTok respondió con un error (${tiktok}).` }) : null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        size="compact"
        title="Canales"
        description="Por dónde escriben los clientes de este negocio y su agente responde. Las integraciones con otras apps están en Conectores."
        actions={
          <Button nativeButton={false} render={<Link href={`/tenants/${id}/channels/new`} />}>
            Añadir canal
          </Button>
        }
      />
      {result ? (
        <p role="status" className={result.tone === "ok" ? "text-sm text-status-positive-text" : "text-sm text-destructive"}>
          {result.text}
        </p>
      ) : null}
      {visible === null ? (
        <ErrorState title="No se pudieron leer los canales" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : visible.length === 0 ? (
        <EmptyState
          title="Este cliente todavía no tiene canales"
          description="Conecta su número de WhatsApp para que su agente empiece a atender."
          action={
            <Button nativeButton={false} render={<Link href={`/tenants/${id}/channels/new`} />}>
              Añadir canal
            </Button>
          }
        />
      ) : (
        <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
          {visible.map((c) => {
            const status = CHANNEL_STATUS[c.status] ?? { label: c.status, tone: "muted" as const };
            const role = typeof c.config?.role === "string" ? ROLE_LABEL[c.config.role as string] : null;
            const name =
              (typeof c.config?.verified_name === "string" && c.config.verified_name) ||
              (typeof c.config?.display_name === "string" && c.config.display_name) ||
              CHANNEL_NAME[c.type] ||
              c.type;
            return (
              <li key={c.id} className="flex items-center gap-4 px-4 py-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-md bg-muted">
                  <ChannelIcon channel={c.type} className="size-5" />
                </span>
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium">{name}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {CHANNEL_NAME[c.type] ?? c.type} · {c.provider_identifier}
                    {role ? ` · ${role}` : ""}
                  </span>
                </div>
                <span className="hidden items-center gap-2 text-sm sm:inline-flex">
                  <StatusDot tone={status.tone} />
                  {status.label}
                </span>
                <Button
                  nativeButton={false}
                  variant="ghost"
                  size="sm"
                  render={<Link href={`/tenants/${id}/channels/${c.id}`} />}
                >
                  <Settings2 aria-hidden="true" />
                  Configurar
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
