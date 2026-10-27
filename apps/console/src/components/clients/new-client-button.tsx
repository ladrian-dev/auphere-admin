"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@nexus/ui";

import { clientHref } from "@/components/shell/routes-v2";
import { useT } from "@/i18n/client";
import type { NewClientCreated } from "@/lib/backend/clients-v2";

import { ClientModal, type ClientModalActions } from "./client-modal";

/**
 * «Nuevo cliente» de la consola nueva (spec 047, T050): abre el modal de tres
 * datos y, al crear, lleva al Panel del cliente con el aviso «{nombre}
 * creado.» (historia 3, escenario 6). La tarjeta de lectura del Panel
 * (`ClientReadCard`) cuenta lo que se está leyendo.
 *
 * `autoOpen` abre el modal al llegar (`/clients?new=1`, adonde lleva
 * `/clients/new` a los partners con la consola nueva); al cerrarlo, la URL
 * vuelve a la lista.
 */
export function NewClientButton({
  autoOpen = false,
  variant = "default",
  actions,
}: {
  autoOpen?: boolean;
  variant?: "default" | "outline";
  actions?: Partial<ClientModalActions>;
}) {
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = React.useState(autoOpen);
  // Cada apertura es un modal en blanco.
  const [generation, setGeneration] = React.useState(0);

  function change(next: boolean) {
    setOpen(next);
    if (!next) {
      setGeneration((g) => g + 1);
      if (autoOpen) router.replace("/clients");
    }
  }

  function created(client: NewClientCreated) {
    toast.success(t("business.created", { name: client.name }));
    if (client.duplicate_name) toast(t("business.created.duplicate", { name: client.name, ref: client.ref }));
    setOpen(false);
    router.push(clientHref(client.ref));
  }

  return (
    <>
      <Button type="button" variant={variant} onClick={() => setOpen(true)} aria-haspopup="dialog">
        <Plus aria-hidden="true" data-icon="inline-start" />
        {t("business.client.new.open")}
      </Button>
      <ClientModal key={generation} mode="create" open={open} onOpenChange={change} onCreated={created} actions={actions} />
    </>
  );
}
