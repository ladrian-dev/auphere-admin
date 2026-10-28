"use client";

import { MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@nexus/ui";

import {
  archiveClientAction,
  deleteClientV2Action,
  getClientV2Action,
  restoreClientAction,
  updateClientV2Action,
} from "@/app/(console)/clients/[ref]/client-v2-actions";
import { ClientModal } from "@/components/clients/client-modal";
import { BalanceDialogs, type BalanceMode } from "@/components/money/balance-button";
import { ReturnBagDialog } from "@/components/money/return-bag";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ClientAction, ClientDetailV2, ClientEditBody, ClientLifecycleResult, Money } from "@/lib/backend/client-records";
import type { NewClientBody } from "@/lib/backend/clients-v2";

import { actionHref, errorText, menuActions } from "./client-v2-model";

type Failed = { ok: false; status: number; message: string; code?: string | null };
type Result<T> = { ok: true; data: T } | Failed;

export type ClientMenuActions = {
  detail: (body: { ref: string }) => Promise<Result<ClientDetailV2>>;
  update: (body: { ref: string; revision: number; body: ClientEditBody }) => Promise<Result<ClientDetailV2>>;
  archive: (body: { ref: string }) => Promise<Result<ClientLifecycleResult>>;
  restore: (body: { ref: string }) => Promise<Result<ClientLifecycleResult>>;
  remove: (body: { ref: string; confirm_name: string }) => Promise<Result<null>>;
};

const DEFAULT_ACTIONS: ClientMenuActions = {
  detail: (b) => getClientV2Action(b),
  update: (b) => updateClientV2Action(b),
  archive: (b) => archiveClientAction(b),
  restore: (b) => restoreClientAction(b),
  remove: (b) => deleteClientV2Action(b),
};

/** Lo que el modal manda al guardar, sin los chips (las redes se editan en Negocio). */
export function editBody(body: NewClientBody): ClientEditBody {
  const out: ClientEditBody = { name: body.name, niche: body.niche, info: body.info ?? null };
  if (body.country !== undefined) out.country = body.country ?? null;
  if (body.timezone) out.timezone = body.timezone;
  if (body.price_currency !== undefined) out.price_currency = body.price_currency ?? null;
  if (body.wallet_currency) out.wallet_currency = body.wallet_currency;
  if (body.eu_only !== undefined && body.eu_only !== null) out.eu_only = body.eu_only;
  return out;
}

/**
 * El menú ⋯ de un cliente (spec 047, requisitos 6 y 7.6), el mismo en su fila
 * de la lista y en su cabecera: solo lo que esta persona puede hacer, salvo
 * «Asignar saldo», que para quien no puede pasa a «Pedir saldo». Los dos se
 * abren en el sitio, sin cambiar de pantalla (45.1). «Editar» abre el modal del
 * alta; «Archivar» lo confirma, el aviso trae «Deshacer» y, si quedaba saldo en
 * su bolsa, ofrece devolverlo a la cuenta (43.13); «Eliminar» pide escribir su
 * nombre.
 */
export function ClientMenu({
  refId,
  name,
  allowed,
  detail,
  actions,
  afterDelete = "/clients",
}: {
  refId: string;
  name: string;
  allowed: readonly ClientAction[];
  /** Si la página ya lo leyó (la cabecera); si no, se pide al editar. */
  detail?: ClientDetailV2 | null;
  actions?: Partial<ClientMenuActions>;
  afterDelete?: string | null;
}) {
  const t = useT();
  const router = useRouter();
  const act = React.useMemo(() => ({ ...DEFAULT_ACTIONS, ...actions }), [actions]);
  const [editing, setEditing] = React.useState<ClientDetailV2 | null>(null);
  const [archiving, setArchiving] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);
  const [balance, setBalance] = React.useState<BalanceMode | null>(null);
  const [leftover, setLeftover] = React.useState<Money | null>(null);
  const items = menuActions(allowed);
  if (!items.length) return null;

  async function openEdit() {
    const current = detail ?? null;
    if (current) return setEditing(current);
    const res = await act.detail({ ref: refId });
    if (!res.ok) return toast.error(errorText(t, res.code));
    setEditing(res.data);
  }

  async function restore() {
    const res = await act.restore({ ref: refId });
    if (!res.ok) return toast.error(errorText(t, res.code));
    toast.success(t("clients.v2.restored", { name }));
    router.refresh();
  }

  async function archive() {
    const res = await act.archive({ ref: refId });
    if (!res.ok) {
      toast.error(errorText(t, res.code));
      return;
    }
    setArchiving(false);
    setEditing(null);
    toast.success(t("clients.v2.archived", { name }), {
      action: { label: t("clients.v2.undo"), onClick: () => void restore() },
    });
    // Solo quien puede asignar puede devolver: bajar la bolsa es `usage:write`.
    const left = res.data.bag_left;
    if (left && left.amount_micros > 0 && allowed.includes("assign_balance")) setLeftover(left);
    router.refresh();
  }

  async function remove(typed: string) {
    setDeleteError(null);
    const res = await act.remove({ ref: refId, confirm_name: typed });
    if (!res.ok) {
      setDeleteError(errorText(t, res.code));
      return;
    }
    setDeleting(false);
    toast.success(t("clients.v2.deleted", { name }));
    if (afterDelete) router.push(afterDelete);
    router.refresh();
  }

  const label = (a: ClientAction) => t(`clients.v2.action.${a}` as MessageKey);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={t("clients.v2.menu", { name })}
          className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
          data-slot="client-menu"
        >
          <MoreHorizontal aria-hidden="true" className="size-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          {items.map((a) => {
            const href = actionHref(a, refId);
            if (a === "delete") {
              return (
                <React.Fragment key={a}>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onClick={() => setDeleting(true)}>
                    {label(a)}
                  </DropdownMenuItem>
                </React.Fragment>
              );
            }
            if (a === "assign_balance" || a === "request_balance") {
              return (
                <DropdownMenuItem key={a} onClick={() => setBalance(a === "assign_balance" ? "assign" : "request")}>
                  {label(a)}
                </DropdownMenuItem>
              );
            }
            if (href) {
              return (
                <DropdownMenuItem key={a} render={<Link href={href} />}>
                  {label(a)}
                </DropdownMenuItem>
              );
            }
            const onClick = a === "edit" ? () => void openEdit() : a === "archive" ? () => setArchiving(true) : () => void restore();
            return (
              <DropdownMenuItem key={a} onClick={onClick}>
                {label(a)}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      {editing ? (
        <ClientModal
          mode="edit"
          open
          onOpenChange={(open) => !open && setEditing(null)}
          initial={{
            name: editing.name,
            niche: editing.niche ?? "",
            info: editing.info ?? "",
            settings: {
              country: editing.country,
              timezone: editing.timezone,
              price_currency: editing.price_currency,
              wallet_currency: editing.wallet_currency ?? "USD",
              eu_only: editing.eu_only ?? false,
            },
          }}
          onSave={async (body) => {
            const res = await act.update({ ref: refId, revision: editing.revision ?? 0, body: editBody(body) });
            if (!res.ok) {
              toast.error(errorText(t, res.code));
              return res;
            }
            toast.success(t("clients.v2.saved"));
            router.refresh();
            return res;
          }}
        />
      ) : null}

      <BalanceDialogs refId={refId} name={name} open={balance} onClose={() => setBalance(null)} />
      {leftover ? <ReturnBagDialog refId={refId} name={name} amount={leftover} onOpenChange={(o) => !o && setLeftover(null)} /> : null}

      <ConfirmDialog
        open={archiving}
        onOpenChange={setArchiving}
        title={t("clients.v2.archive.title", { name })}
        description={t("clients.v2.archive.body")}
        confirmLabel={t("clients.v2.archive.confirm")}
        cancelLabel={t("business.submit.cancel")}
        onConfirm={archive}
      />
      <ConfirmDialog
        open={deleting}
        onOpenChange={(open) => {
          setDeleting(open);
          if (!open) setDeleteError(null);
        }}
        title={t("clients.v2.delete.title", { name })}
        description={t("clients.v2.delete.body")}
        confirmLabel={t("clients.v2.delete.confirm")}
        cancelLabel={t("business.submit.cancel")}
        destructive
        typeToConfirm={name}
        typeToConfirmLabel={t("clients.v2.delete.typeLabel", { name })}
        onConfirm={() => remove(name)}
        error={deleteError}
      />
    </>
  );
}
