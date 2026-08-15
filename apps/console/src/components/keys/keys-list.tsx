"use client";

import { Copy, KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
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

import { createKeyAction, revokeKeyAction, rotateKeyAction } from "@/app/(console)/keys/actions";
import { useLocale, useT } from "@/i18n/client";
import type { ApiKey, ApiKeyCreated } from "@/lib/backend";

const SCOPES = ["provision", "broadcasts", "widget_sessions"] as const;

export function KeysList({ keys, manage }: { keys: ApiKey[]; manage: boolean }) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [type, setType] = React.useState<"live" | "test">("live");
  const [scopes, setScopes] = React.useState<string[]>(["provision", "broadcasts"]);
  const [created, setCreated] = React.useState<ApiKeyCreated | null>(null);
  const [rotating, setRotating] = React.useState<ApiKey | null>(null);
  const [revoking, setRevoking] = React.useState<ApiKey | null>(null);

  function create() {
    startTransition(async () => {
      const res = await createKeyAction({ type, scopes });
      if (!res.ok) return void toast.error(res.message);
      setCreated(res.data);
      setCreateOpen(false);
      router.refresh();
    });
  }

  const live = keys.filter((k) => !k.revoked_at || (k.grace_expires_at && new Date(k.grace_expires_at) > new Date()));
  const dead = keys.filter((k) => !live.includes(k));

  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
      {manage ? (
        <div>
          <Button onClick={() => setCreateOpen(true)}>{t("keys.new")}</Button>
        </div>
      ) : null}
      {keys.length === 0 ? (
        <EmptyState icon={KeyRound} title={t("keys.empty")} description={t("keys.empty.body")} action={manage ? <Button onClick={() => setCreateOpen(true)}>{t("keys.new")}</Button> : undefined} readonly={!manage} />
      ) : (
        <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
          {[...live, ...dead].map((k) => {
            const inGrace = !!k.revoked_at && !!k.grace_expires_at && new Date(k.grace_expires_at) > new Date();
            const revoked = !!k.revoked_at && !inGrace;
            return (
              <li key={k.id} className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-3">
                <span className="min-w-0 truncate font-mono text-sm">{k.prefix_snippet}…</span>
                <StatusBadge tone={k.type === "live" ? "positive" : "info"} dot={false}>
                  {t(`keys.type.${k.type}` as "keys.type.live")}
                </StatusBadge>
                {revoked ? <StatusBadge tone="muted">{t("keys.revoked")}</StatusBadge> : null}
                {inGrace ? <StatusBadge tone="warning">{t("keys.grace", { date: formatDateTime(k.grace_expires_at, locale) })}</StatusBadge> : null}
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground" title={k.scopes.join(", ")}>
                  {k.scopes.map((s) => t(`keys.scope.${s}` as "keys.scope.provision")).join(" · ")}
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {t("keys.lastUsed")}: {k.last_used_at ? formatRelative(k.last_used_at, locale) : t("keys.never")}
                </span>
                {manage && !k.revoked_at ? (
                  <span className="flex gap-1">
                    <Button variant="outline" size="sm" onClick={() => setRotating(k)}>
                      {t("keys.rotate")}
                    </Button>
                    <Button variant="destructive" size="sm" onClick={() => setRevoking(k)}>
                      {t("keys.revoke")}
                    </Button>
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      <Dialog open={createOpen} onOpenChange={(o) => setCreateOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("keys.create.title")}</DialogTitle>
            <DialogDescription>{t("keys.create.body")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-medium">{t("keys.type")}</legend>
              {(["live", "test"] as const).map((v) => (
                <label key={v} className="flex items-center gap-2 text-sm">
                  <input type="radio" name="type" value={v} checked={type === v} onChange={() => setType(v)} />
                  {t(`keys.type.${v}` as "keys.type.live")}
                </label>
              ))}
            </fieldset>
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-medium">{t("keys.scopes")}</legend>
              {SCOPES.map((s) => (
                <label key={s} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={scopes.includes(s)}
                    onChange={(e) => setScopes((prev) => (e.target.checked ? [...prev, s] : prev.filter((x) => x !== s)))}
                  />
                  {t(`keys.scope.${s}` as "keys.scope.provision")}
                </label>
              ))}
            </fieldset>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={create} disabled={pending || scopes.length === 0}>
              {t("keys.new")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={created !== null} onOpenChange={(o) => !o && setCreated(null)}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>{t("keys.created.title")}</DialogTitle>
            <DialogDescription>{t("keys.created.body")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="plaintext">{t("keys.title")}</Label>
            <div className="flex gap-2">
              <Input id="plaintext" readOnly value={created?.plaintext ?? ""} className="font-mono text-xs" />
              <Button
                variant="outline"
                size="icon"
                aria-label={t("common.copy")}
                onClick={async () => {
                  await navigator.clipboard.writeText(created?.plaintext ?? "");
                  toast.success(t("common.copied"));
                }}
              >
                <Copy />
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setCreated(null)}>{t("common.close")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={rotating !== null}
        onOpenChange={(o) => !o && setRotating(null)}
        title={t("keys.rotate.title", { prefix: rotating?.prefix_snippet ?? "" })}
        description={t("keys.rotate.body")}
        confirmLabel={t("keys.rotate")}
        cancelLabel={t("common.cancel")}
        onConfirm={async () => {
          if (!rotating) return;
          const res = await rotateKeyAction({ id: rotating.id });
          if (!res.ok) return void toast.error(res.message);
          setRotating(null);
          setCreated(res.data);
          router.refresh();
        }}
      />
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(o) => !o && setRevoking(null)}
        title={t("keys.revoke.title", { prefix: revoking?.prefix_snippet ?? "" })}
        description={t("keys.revoke.body")}
        confirmLabel={t("keys.revoke")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={async () => {
          if (!revoking) return;
          const res = await revokeKeyAction({ id: revoking.id });
          if (!res.ok) return void toast.error(res.message);
          setRevoking(null);
          router.refresh();
        }}
      />
    </div>
  );
}
