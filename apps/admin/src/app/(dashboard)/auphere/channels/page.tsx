import { Eyebrow } from "@/components/brand/eyebrow";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend } from "@/lib/backend";

import {
  createChannelAction,
  deactivateChannelAction,
  updateChannelAction,
} from "./actions";
import { ChannelsTable } from "./channels-table";
import { CreateChannelForm } from "./create-form";

type SearchParams = { include_inactive?: string };

/**
 * Global Auphere channel registry — Bloque D Fase 2 / D6.
 *
 * Lists every outbound number Auphere owns at a BSP (one per
 * country usually). Operators manage:
 *
 * - Adding a new number (default-flag toggle, country code, optional
 *   per-channel webhook secret).
 * - Rotating a webhook secret without redeploy.
 * - Promoting a number to default for its provider.
 * - Deactivating a number (soft-delete, reversible via PATCH
 *   ``active=true``).
 *
 * Numbers deactivated here do NOT cascade-delete owner registrations
 * — the FK is SET NULL, so existing OwnerPhoneIndex rows fall back to
 * the provider default on the next outbound.
 */
export default async function AuphereChannelsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const { include_inactive } = await searchParams;
  const showInactive = include_inactive === "true";
  const channels = await backend.listAuphereChannels(showInactive);

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Plataforma</Eyebrow>
          <CardTitle>Canales Auphere (backchannel)</CardTitle>
          <CardDescription>
            Registry global de los números desde los que Auphere escribe a
            los dueños de los tenants. Cada canal vive en la WABA de
            Auphere (Meta Cloud API) y necesita su phone_number_id + access
            token para poder enviar. Mantén un ★ default — el resolver cae
            ahí cuando un <code>owner_phone_index</code> no tiene channel
            pin.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChannelsTable
            channels={channels}
            showingInactive={showInactive}
            updateAction={updateChannelAction}
            deactivateAction={deactivateChannelAction}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Agregar</Eyebrow>
          <CardTitle>Registrar nuevo canal</CardTitle>
          <CardDescription>
            E.164 obligatorio. Si marcás <strong>Default</strong>, ningún
            otro canal puede ser default — desactivá el anterior primero.
            El access token y el webhook secret se guardan cifrados
            (Fernet) y no vuelven a mostrarse.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CreateChannelForm createAction={createChannelAction} />
        </CardContent>
      </Card>
    </div>
  );
}
