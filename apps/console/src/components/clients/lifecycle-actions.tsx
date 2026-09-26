"use client";

import { useRouter } from "next/navigation";
import { Fragment } from "react";
import * as React from "react";
import { toast } from "sonner";

import { MoreHorizontal } from "lucide-react";

import {
  Button,
  ConfirmDialog,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";

import { deleteClientAction, setClientStatusAction } from "@/app/(console)/clients/actions";
import { actionErrorText } from "@/lib/action-error";

import { deleteIsOffered, moreMenuItems, statusActionNeedsConfirm, type MoreMenuItem } from "./lifecycle-status";

type Props = {
  refId: string;
  status: string;
  name: string;
  canDelete: boolean;
  /** `menu` es la cabecera de la ficha (spec 017 R1.6): un solo «Más» en el
   *  mismo sitio para todos los roles, con dentro lo que cada uno puede.
   *  `buttons` es la fila suelta de siempre, que no desaparece. */
  layout?: "buttons" | "menu";
  canWrite?: boolean;
};
type StatusNext = "active" | "paused" | "archived";

export function ClientLifecycleActions({ refId, status, name, canDelete, layout = "buttons", canWrite = true }: Props) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);
  const [confirmStatus, setConfirmStatus] = React.useState<StatusNext | null>(null);

  function applyStatus(next: StatusNext) {
    startTransition(async () => {
      const res = await setClientStatusAction({ ref: refId, status: next });
      if (!res.ok) {
        toast.error(actionErrorText(res, t));
        return;
      }
      setConfirmStatus(null);
      router.refresh();
    });
  }

  function requestStatus(next: StatusNext) {
    if (statusActionNeedsConfirm(next)) {
      setConfirmStatus(next);
      return;
    }
    applyStatus(next);
  }

  // Las dos confirmaciones las comparten la fila de botones y el menú: una
  // sola fuente para «pausar», «archivar» y «eliminar».
  const dialogs = (
    <>
      {deleteIsOffered(status, canDelete) ? (
          <ConfirmDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title={t("clients.delete.title", { name })}
          description={t("clients.delete.body")}
          confirmLabel={t("clients.delete.confirm")}
          cancelLabel={t("common.cancel")}
          destructive
          typeToConfirm={name}
          error={deleteError}
          onConfirm={async () => {
            const res = await deleteClientAction({ ref: refId, confirm_name: name });
            if (!res.ok) {
              setDeleteError(actionErrorText(res, t));
              return;
            }
            setConfirmDelete(false);
            router.replace("/clients");
            router.refresh();
          }}
        />
      ) : null}
    </>
  );

  const ACTION_LABEL: Record<MoreMenuItem, MessageKey> = {
    pause: "clients.action.pause",
    resume: "clients.action.resume",
    activate: "clients.action.activate",
    archive: "clients.action.archive",
    unarchive: "clients.action.unarchive",
    copyRef: "clients.more.copyRef",
    delete: "clients.action.delete",
  };

  function runItem(item: MoreMenuItem) {
    if (item === "copyRef") {
      void navigator.clipboard?.writeText(refId).then(() => toast.success(t("clients.more.copyRef.done")));
      return;
    }
    if (item === "delete") {
      setDeleteError(null);
      setConfirmDelete(true);
      return;
    }
    requestStatus(item === "pause" ? "paused" : item === "archive" ? "archived" : "active");
  }

  if (layout === "menu") {
    const items = moreMenuItems(status, { canWrite, canDelete });
    return (
      <>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="outline" size="sm" aria-label={t("clients.more.aria")} disabled={pending}>
                <MoreHorizontal aria-hidden="true" /> {t("clients.more.label")}
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="w-64">
            {items.map((item, i) => (
              <Fragment key={item}>
                {item === "delete" ? <DropdownMenuSeparator /> : null}
                <DropdownMenuItem
                  variant={item === "delete" ? "destructive" : undefined}
                  onClick={() => runItem(item)}
                >
                  <span className="flex flex-col">
                    {t(ACTION_LABEL[item])}
                    <span className={item === "delete" ? "text-xs" : "text-xs text-muted-foreground"}>
                      {t(`clients.more.why.${item}` as MessageKey)}
                    </span>
                  </span>
                </DropdownMenuItem>
                {i === items.length - 1 ? null : null}
              </Fragment>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        {dialogs}
      </>
    );
  }

  return (
    <div className="flex flex-wrap gap-2" aria-busy={pending}>
      {status === "active" ? (
        <Button variant="outline" size="sm" onClick={() => requestStatus("paused")} disabled={pending}>
          {t("clients.action.pause")}
        </Button>
      ) : null}
      {status === "paused" ? (
        <Button variant="outline" size="sm" onClick={() => requestStatus("active")} disabled={pending}>
          {t("clients.action.resume")}
        </Button>
      ) : null}
      {status === "provisioning" ? (
        <Button variant="outline" size="sm" onClick={() => requestStatus("active")} disabled={pending}>
          {t("clients.action.activate")}
        </Button>
      ) : null}
      {status !== "archived" ? (
        <Button variant="ghost" size="sm" onClick={() => requestStatus("archived")} disabled={pending}>
          {t("clients.action.archive")}
        </Button>
      ) : (
        <Button variant="outline" size="sm" onClick={() => requestStatus("active")} disabled={pending}>
          {t("clients.action.unarchive")}
        </Button>
      )}
      <ConfirmDialog
        open={confirmStatus !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmStatus(null);
        }}
        title={
          confirmStatus === "paused"
            ? t("clients.pause.title", { name })
            : t("clients.archive.title", { name })
        }
        description={confirmStatus === "paused" ? t("clients.pause.body") : t("clients.archive.body")}
        confirmLabel={confirmStatus === "paused" ? t("clients.pause.confirm") : t("clients.archive.confirm")}
        cancelLabel={t("common.cancel")}
        onConfirm={async () => {
          if (confirmStatus) applyStatus(confirmStatus);
        }}
      />
      {deleteIsOffered(status, canDelete) ? (
        <Button
          variant="destructive"
          size="sm"
          onClick={() => {
            setDeleteError(null);
            setConfirmDelete(true);
          }}
          disabled={pending}
        >
          {t("clients.action.delete")}
        </Button>
      ) : null}
      {dialogs}
    </div>
  );
}
