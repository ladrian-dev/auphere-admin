"use client";

import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@nexus/ui";

import { clearCatalogAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { CatalogPicker, catalogFailureKey } from "@/components/channels/catalog-picker";
import { CatalogRow } from "@/components/channels/channel-card";
import { useT } from "@/i18n/client";
import type { ChannelPage } from "@/lib/backend/channel-config-types";

/**
 * Spec 022 en la página del número (spec 050 research D11): la misma fila
 * «Catálogo» que la tarjeta del número, con su selector y su «Desconectar».
 * Antes solo estaba en la lista de canales del cliente, a la que no lleva
 * ninguna pestaña de la consola v2 (QA 2026-10-30), y el revisor de Meta no
 * la habría encontrado.
 *
 * Tras cada cambio se recarga la página del canal (`onChanged`), que guarda
 * el canal en su propio estado.
 */
export function ChannelCatalogSection({
  refId,
  page,
  canWrite,
  onChanged,
}: {
  refId: string;
  page: ChannelPage;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const t = useT();
  const [choosing, setChoosing] = React.useState(false);
  const [clearing, setClearing] = React.useState(false);
  const [pending, startTransition] = React.useTransition();
  const channel = { catalog: page.catalog ?? null, catalog_state: page.catalog_state ?? "none", catalog_error: page.catalog_error ?? null };

  function clear() {
    startTransition(async () => {
      const res = await clearCatalogAction({ ref: refId, channelId: page.id });
      if (!res.ok) return void toast.error(res.message);
      setClearing(false);
      if (res.data.catalog_error) {
        const key = catalogFailureKey(res.data.catalog_error.code);
        toast.error(key ? t(key, { message: res.data.catalog_error.message ?? "" }) : t("common.error.backend"));
      } else toast.success(t("ch.catalog.cleared"));
      onChanged();
    });
  }

  return (
    <div className="grid min-w-0 gap-2" data-slot="channel-catalog">
      <CatalogRow channel={channel} manage={canWrite} pending={pending} onConnect={() => setChoosing(true)} onClear={() => setClearing(true)} />
      {canWrite ? (
        <>
          <CatalogPicker
            refId={refId}
            channelId={page.id}
            current={channel.catalog}
            open={choosing}
            onOpenChange={setChoosing}
            coexistence={channel.catalog_state === "coexistence"}
            onApplied={onChanged}
          />
          <ConfirmDialog
            open={clearing}
            onOpenChange={setClearing}
            title={t("ch.catalog.clear.title", { name: channel.catalog?.name ?? channel.catalog?.id ?? "" })}
            description={t("ch.catalog.clear.body")}
            confirmLabel={t("ch.catalog.clear")}
            cancelLabel={t("common.cancel")}
            destructive
            onConfirm={async () => clear()}
          />
        </>
      ) : null}
    </div>
  );
}
