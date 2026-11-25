import { PartyPopper } from "lucide-react";
import Link from "next/link";

import { Button } from "@nexus/ui";

import { CHANNEL_NAME } from "@/components/channels/labels";
import { backend } from "@/lib/backend";

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
  const tenant = await backend.getTenant(id).catch(() => null);
  if (tenant?.send_only) {
    // Spec 077 (2.2): no agent step — the number is connected and sends only what the API asks.
    return (
      <div className="flex flex-col items-center gap-4 py-10 text-center">
        <span className="grid size-12 place-items-center rounded-full bg-primary/15 text-primary">
          <PartyPopper className="size-6" aria-hidden="true" />
        </span>
        <h2 className="text-xl font-semibold text-balance">Su número de {CHANNEL_NAME[channel] ?? channel} está conectado</h2>
        <p className="max-w-md text-sm text-pretty text-muted-foreground">
          Queda activo y sin agente que responda: solo envía lo que pide su sistema por la API. Su Resumen dice qué
          falta para que empiece a enviar.
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          <Button nativeButton={false} variant="outline" render={<Link href={`/tenants/${id}/channels`} />}>
            Ver canales
          </Button>
          <Button nativeButton={false} render={<Link href={`/tenants/${id}`} />}>
            Volver al Resumen
          </Button>
        </div>
      </div>
    );
  }
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
