import { PartyPopper } from "lucide-react";
import Link from "next/link";

import { Button } from "@nexus/ui";

import { CHANNEL_NAME } from "@/components/channels/labels";

/** Step 4 — «¡Listo!», with where to go next (Chatwoot's FinishSetup). */
export default async function ChannelDonePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; channel: string }>;
  searchParams: Promise<{ channel?: string }>;
}) {
  const { id, channel } = await params;
  const channelId = (await searchParams).channel;
  return (
    <div className="flex flex-col items-center gap-4 py-10 text-center">
      <span className="grid size-12 place-items-center rounded-full bg-primary/15 text-primary">
        <PartyPopper className="size-6" aria-hidden="true" />
      </span>
      <h2 className="text-xl font-semibold">¡Tu canal de {CHANNEL_NAME[channel] ?? channel} está listo!</h2>
      <p className="max-w-md text-sm text-pretty text-muted-foreground">
        El agente ya atiende los mensajes que lleguen por aquí. Prueba un envío o ajusta el papel del número.
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {channelId ? (
          <Button nativeButton={false} variant="outline" render={<Link href={`/tenants/${id}/channels/${channelId}`} />}>
            Más ajustes
          </Button>
        ) : null}
        {channelId ? (
          <Button nativeButton={false} render={<Link href={`/tenants/${id}/channels/${channelId}?tab=health`} />}>
            Probar envío
          </Button>
        ) : (
          <Button nativeButton={false} render={<Link href={`/tenants/${id}/channels`} />}>
            Ver canales
          </Button>
        )}
      </div>
    </div>
  );
}
