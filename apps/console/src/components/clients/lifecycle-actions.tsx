"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { deleteClientAction, setClientStatusAction } from "@/app/(console)/clients/actions";

import { statusActionNeedsConfirm } from "./lifecycle-status";

type Props = { refId: string; status: string; name: string; canDelete: boolean };
type StatusNext = "active" | "paused" | "archived";

export function ClientLifecycleActions({ refId, status, name, canDelete }: Props) {
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
        toast.error(res.message);
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
      {canDelete ? (
        <>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => {
              if (status !== "archived") {
                toast.error(t("clients.delete.mustArchive"));
                return;
              }
              setDeleteError(null);
              setConfirmDelete(true);
            }}
            disabled={pending}
          >
            {t("clients.action.delete")}
          </Button>
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
                setDeleteError(res.message);
                return;
              }
              setConfirmDelete(false);
              router.replace("/clients");
              router.refresh();
            }}
          />
        </>
      ) : null}
    </div>
  );
}
