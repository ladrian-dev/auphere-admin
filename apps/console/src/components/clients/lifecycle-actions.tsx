"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { deleteClientAction, setClientStatusAction } from "@/app/(console)/clients/actions";

type Props = { refId: string; status: string; name: string; canDelete: boolean };

export function ClientLifecycleActions({ refId, status, name, canDelete }: Props) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);

  function setStatus(next: "active" | "paused" | "archived") {
    startTransition(async () => {
      const res = await setClientStatusAction({ ref: refId, status: next });
      if (!res.ok) {
        toast.error(res.message);
        return;
      }
      router.refresh();
    });
  }

  return (
    <div className="flex flex-wrap gap-2" aria-busy={pending}>
      {status === "active" ? (
        <Button variant="outline" size="sm" onClick={() => setStatus("paused")} disabled={pending}>
          {t("clients.action.pause")}
        </Button>
      ) : null}
      {status === "paused" ? (
        <Button variant="outline" size="sm" onClick={() => setStatus("active")} disabled={pending}>
          {t("clients.action.resume")}
        </Button>
      ) : null}
      {status === "provisioning" ? (
        <Button variant="outline" size="sm" onClick={() => setStatus("active")} disabled={pending}>
          {t("clients.action.activate")}
        </Button>
      ) : null}
      {status !== "archived" ? (
        <Button variant="ghost" size="sm" onClick={() => setStatus("archived")} disabled={pending}>
          {t("clients.action.archive")}
        </Button>
      ) : (
        <Button variant="outline" size="sm" onClick={() => setStatus("active")} disabled={pending}>
          {t("clients.action.unarchive")}
        </Button>
      )}
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
