"use client";

import { Laptop, TerminalSquare } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
  Input,
  Label,
  StatusBadge,
  formatDateTime,
  formatRelative,
} from "@nexus/ui";

import {
  addExecutableAction,
  archiveExecutableAction,
} from "@/app/(console)/clients/[ref]/workstation/actions";
import { useLocale, useT } from "@/i18n/client";
import type { DeviceOut, ExecutableOut } from "@/lib/backend/workstation";

/** El mismo patrón que valida el backend y la base. Se repite aquí para que el
 *  error llegue antes de un viaje de ida y vuelta, no para sustituirlo. */
const EXECUTABLE = /^[A-Za-z0-9._+-]{1,128}$/;

export function WorkstationPanel({
  clientRef,
  executables,
  devices,
  devicesFailed,
  manage,
}: {
  clientRef: string;
  executables: ExecutableOut[];
  devices: DeviceOut[];
  devicesFailed: boolean;
  manage: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [addOpen, setAddOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [archiving, setArchiving] = React.useState<ExecutableOut | null>(null);

  const invalid = name.length > 0 && !EXECUTABLE.test(name);

  function add() {
    startTransition(async () => {
      const res = await addExecutableAction({ ref: clientRef, executable: name });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("workstation.allowlist.added", { name }));
      setAddOpen(false);
      setName("");
      router.refresh();
    });
  }

  function archive(row: ExecutableOut) {
    startTransition(async () => {
      const res = await archiveExecutableAction({ ref: clientRef, id: row.id });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("workstation.allowlist.archived", { name: row.executable }));
      setArchiving(null);
      router.refresh();
    });
  }

  return (
    <div className="flex min-w-0 flex-col gap-6" aria-busy={pending}>
      <section aria-labelledby="workstation-allowlist">
        <Card>
          <CardHeader className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle id="workstation-allowlist">{t("workstation.allowlist.title")}</CardTitle>
              <p className="mt-1 max-w-prose text-sm text-pretty text-muted-foreground">
                {t("workstation.allowlist.help")}
              </p>
            </div>
            {/* La ausencia se diseña (§V): sin permiso no hay botón apagado, no hay botón. */}
            {manage ? (
              <Button onClick={() => setAddOpen(true)}>{t("workstation.allowlist.add")}</Button>
            ) : null}
          </CardHeader>
          <CardContent>
            {executables.length === 0 ? (
              <EmptyState
                icon={TerminalSquare}
                title={t("workstation.allowlist.empty.title")}
                description={t("workstation.allowlist.empty.body")}
                readonly={!manage}
                action={
                  manage ? (
                    <Button onClick={() => setAddOpen(true)}>{t("workstation.allowlist.add")}</Button>
                  ) : undefined
                }
              />
            ) : (
              <ul className="flex min-w-0 flex-col divide-y divide-border">
                {executables.map((row) => (
                  <li key={row.id} className="flex min-w-0 flex-wrap items-center gap-3 py-3">
                    <code className="min-w-0 truncate font-mono text-sm">{row.executable}</code>
                    <span className="min-w-0 truncate text-xs text-muted-foreground">
                      {t("workstation.allowlist.addedBy", { who: row.added_by })} ·{" "}
                      <time dateTime={row.added_at}>{formatDateTime(row.added_at, locale)}</time>
                    </span>
                    {manage ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="ms-auto"
                        onClick={() => setArchiving(row)}
                      >
                        {t("workstation.allowlist.archive")}
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="workstation-devices">
        <Card>
          <CardHeader>
            <CardTitle id="workstation-devices" className="flex flex-wrap items-center justify-between gap-2">
              <span>{t("workstation.devices.title")}</span>
              <Link href="/workstation" className="text-sm font-normal text-primary underline-offset-4 hover:underline">
                {t("workstation.devices.manageLink")}
              </Link>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {devicesFailed ? (
              // `parcial` (§V): se acota el alcance de lo que se afirma. Lo de
              // arriba sigue siendo cierto; esto es lo que no se pudo leer.
              <p role="status" className="text-sm text-pretty text-status-warning">
                {t("workstation.devices.unavailable")}
              </p>
            ) : devices.length === 0 ? (
              <EmptyState
                icon={Laptop}
                title={t("workstation.devices.empty.title")}
                description={t("workstation.devices.empty.body")}
                readonly
              />
            ) : (
              <ul className="flex min-w-0 flex-col divide-y divide-border">
                {devices.map((device) => (
                  <li key={device.id} className="flex min-w-0 flex-wrap items-center gap-3 py-3">
                    <span className="min-w-0 truncate text-sm font-medium">{device.display_name}</span>
                    <StatusBadge tone={device.presence === "presente" ? "positive" : "muted"}>
                      {device.presence === "presente"
                        ? t("workstation.devices.present")
                        : device.last_heartbeat_at
                          ? t("workstation.devices.absentSince", {
                              when: formatRelative(device.last_heartbeat_at, locale),
                            })
                          : t("workstation.devices.never")}
                    </StatusBadge>
                    <span className="min-w-0 truncate font-mono text-xs text-muted-foreground">
                      {t("workstation.devices.workdir")}: {device.workdir ?? t("workstation.devices.noDirectory")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("workstation.allowlist.addTitle")}</DialogTitle>
            <DialogDescription>{t("workstation.allowlist.addBody")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="workstation-executable">{t("workstation.allowlist.field")}</Label>
            <Input
              id="workstation-executable"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={invalid || undefined}
              aria-describedby={invalid ? "workstation-executable-error" : undefined}
              autoComplete="off"
              spellCheck={false}
            />
            {invalid ? (
              <p id="workstation-executable-error" role="alert" className="text-sm text-status-danger">
                {t("workstation.allowlist.invalid")}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button onClick={add} disabled={pending || name.length === 0 || invalid}>
              {t("workstation.allowlist.add")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={archiving !== null}
        onOpenChange={(open) => !open && setArchiving(null)}
        title={t("workstation.allowlist.archiveTitle", { name: archiving?.executable ?? "" })}
        description={t("workstation.allowlist.archiveBody")}
        confirmLabel={t("workstation.allowlist.archive")}
        onConfirm={() => {
          if (archiving) archive(archiving);
        }}
      />
    </div>
  );
}
