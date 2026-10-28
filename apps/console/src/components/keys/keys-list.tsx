"use client";

import { Ban, Copy, Info, KeyRound, MoreHorizontal, Plus, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Card,
  CardContent,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  EmptyState,
  Input,
  Label,
  SegmentedControl,
  StatusBadge,
  cn,
  formatDateTime,
  formatRelative,
} from "@nexus/ui";

import { createKeyAction, revokeKeyAction, rotateKeyAction } from "@/app/(console)/keys/actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
import { defaultNewKeyForm, type KeyType } from "@/components/keys/key-defaults";
import { useLocale, useT } from "@/i18n/client";
import type { ApiKey, ApiKeyCreated } from "@/lib/backend";

const SCOPES = ["provision", "broadcasts"] as const;

/** Viva = sin revocar, o revocada y todavía en su periodo de gracia. */
function isLive(k: ApiKey): boolean {
  return !k.revoked_at || (!!k.grace_expires_at && new Date(k.grace_expires_at) > new Date());
}

/**
 * «Nueva clave» (spec 047, prototipo «Consola de partners v2»): va en la
 * cabecera de la página y abre el modal de 540 px — el tipo en el conmutador de
 * vidrio y los permisos en tarjetas con su descripción. Después, «Guarda esta
 * clave ahora».
 */
export function NewKeyButton() {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [open, setOpen] = React.useState(false);
  const [type, setType] = React.useState<KeyType>(defaultNewKeyForm().type);
  const [scopes, setScopes] = React.useState<string[]>(() => defaultNewKeyForm().scopes);
  const [missing, setMissing] = React.useState(false);
  const [created, setCreated] = React.useState<ApiKeyCreated | null>(null);

  function create() {
    if (scopes.length === 0) return void setMissing(true);
    startTransition(async () => {
      const res = await createKeyAction({ type, scopes });
      if (!res.ok) return void toast.error(res.message);
      setCreated(res.data);
      setOpen(false);
      router.refresh();
    });
  }

  return (
    <>
      <Button
        onClick={() => {
          const d = defaultNewKeyForm();
          setType(d.type);
          setScopes(d.scopes);
          setMissing(false);
          setOpen(true);
        }}
      >
        <Plus aria-hidden="true" />
        {t("keys.new")}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("keys.create.title")}</DialogTitle>
            <DialogDescription>{t("keys.create.body")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4" aria-busy={pending}>
            <div className="grid gap-2">
              <p id="key-type-label" className="text-sm font-medium">
                {t("keys.type")}
              </p>
              <SegmentedControl
                aria-labelledby="key-type-label"
                value={type}
                onValueChange={setType}
                options={[
                  { value: "test", label: t("keys.type.test") },
                  { value: "live", label: t("keys.type.live") },
                ]}
              />
            </div>
            <fieldset className="grid gap-2" aria-describedby={missing ? "key-scopes-error" : undefined}>
              <legend className="mb-2 text-sm font-medium">{t("keys.scopes")}</legend>
              {SCOPES.map((s) => (
                <label key={s} className={cn("flex cursor-pointer items-start gap-3 rounded-lg border border-border p-4 text-sm", scopes.includes(s) && "border-primary")}>
                  <input
                    type="checkbox"
                    className="mt-1 size-4 shrink-0 accent-primary"
                    checked={scopes.includes(s)}
                    onChange={(e) => {
                      setMissing(false);
                      setScopes((prev) => (e.target.checked ? [...prev, s] : prev.filter((x) => x !== s)));
                    }}
                  />
                  <span className="flex min-w-0 flex-col">
                    <span className="font-medium">{t(`keys.scope.${s}`)}</span>
                    <span className="text-pretty text-muted-foreground">{t(`proto.keys.scope.${s}.hint`)}</span>
                  </span>
                </label>
              ))}
              {missing ? (
                <p id="key-scopes-error" className="text-sm text-destructive" role="alert">
                  {t("proto.keys.scopes.error")}
                </p>
              ) : null}
            </fieldset>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={create} disabled={pending}>
              {t("proto.keys.create.submit")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CreatedKeyDialog created={created} onClose={() => setCreated(null)} />
    </>
  );
}

/** «Guarda esta clave ahora»: la clave en claro, una sola vez, con «Copiar». */
function CreatedKeyDialog({ created, onClose }: { created: ApiKeyCreated | null; onClose: () => void }) {
  const t = useT();
  return (
    <Dialog open={created !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent showCloseButton={false} className="sm:max-w-lg">
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
          <Button onClick={onClose}>{t("common.close")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Las claves (spec 047, prototipo): la tarjeta «Claves» con cuántas están
 * activas; cada fila con su baldosa, el prefijo y debajo los permisos y el
 * último uso, y a la derecha el tipo y, si toca, «Revocada» o «En gracia». Las
 * acciones —Rotar, Revocar— se ven en la fila mientras la lista no pase de dos
 * botones (`row-actions-rule`), y si pasa, van en «⋯». Las revocadas al final,
 * atenuadas y sin acciones. Debajo, la nota de las claves de un solo cliente.
 */
export function KeysList({ keys, manage }: { keys: ApiKey[]; manage: boolean }) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [rotating, setRotating] = React.useState<ApiKey | null>(null);
  const [revoking, setRevoking] = React.useState<ApiKey | null>(null);
  const [created, setCreated] = React.useState<ApiKeyCreated | null>(null);

  const live = keys.filter(isLive);
  const dead = keys.filter((k) => !isLive(k));
  const actionable = manage ? keys.filter((k) => !k.revoked_at) : [];
  const menu = foldsIntoMenu(actionable.length * 2);
  const active = keys.filter((k) => !k.revoked_at).length;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {keys.length === 0 ? (
        <EmptyState icon={KeyRound} title={t("keys.empty")} description={t("keys.empty.body")} readonly />
      ) : (
        <Card aria-labelledby="keys-h" role="region" data-slot="keys-card">
          <CardContent className="grid min-w-0 gap-2">
            <div className="flex min-w-0 items-center justify-between gap-3">
              <h2 id="keys-h" className="text-base font-semibold">
                {t("proto.keys.list")}
              </h2>
              <span className="text-xs text-muted-foreground tabular-nums">
                {active === 1 ? t("proto.keys.active.one") : t("proto.keys.active", { n: active })}
              </span>
            </div>
            <ul className="-mx-4 divide-y divide-border">
              {[...live, ...dead].map((k) => {
                const inGrace = !!k.revoked_at && !!k.grace_expires_at && new Date(k.grace_expires_at) > new Date();
                const revoked = !!k.revoked_at && !inGrace;
                const used = k.last_used_at ? formatRelative(k.last_used_at, locale) : t("keys.never");
                const meta = [...k.scopes.map((s) => t(`keys.scope.${s}` as "keys.scope.provision")), t("proto.keys.lastUsed", { when: used })].join(" · ");
                return (
                  <li key={k.id} className={cn("flex min-w-0 flex-wrap items-center gap-3 px-4 py-3", revoked && "opacity-60")}>
                    <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground">
                      <KeyRound className="size-4" />
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate font-mono text-sm font-medium">{k.prefix_snippet}…</span>
                      <span className="truncate text-xs text-muted-foreground" title={meta}>
                        {meta}
                      </span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone={k.type === "live" ? "positive" : "info"}>{t(`keys.type.${k.type}`)}</StatusBadge>
                      {revoked ? <StatusBadge tone="muted">{t("keys.revoked")}</StatusBadge> : null}
                      {inGrace ? <StatusBadge tone="warning">{t("keys.grace", { date: formatDateTime(k.grace_expires_at, locale) })}</StatusBadge> : null}
                    </span>
                    {manage && !k.revoked_at ? (
                      menu ? (
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            aria-label={t("proto.keys.actions", { prefix: `${k.prefix_snippet}…` })}
                            className="inline-flex size-8 shrink-0 items-center justify-center rounded-md hover:bg-muted"
                            data-slot="row-actions"
                          >
                            <MoreHorizontal aria-hidden="true" className="size-4" />
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-56">
                            <DropdownMenuItem onClick={() => setRotating(k)}>
                              <RefreshCw aria-hidden="true" />
                              {t("keys.rotate")}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem variant="destructive" onClick={() => setRevoking(k)}>
                              <Ban aria-hidden="true" />
                              {t("keys.revoke")}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      ) : (
                        <span className="flex gap-1">
                          <Button variant="outline" size="sm" onClick={() => setRotating(k)}>
                            {t("keys.rotate")}
                          </Button>
                          <Button variant="destructive" size="sm" onClick={() => setRevoking(k)}>
                            {t("keys.revoke")}
                          </Button>
                        </span>
                      )
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* La nota del prototipo (`.callout`): las claves de un cliente viven en su ficha. */}
      <p className="flex items-start gap-3 rounded-lg bg-muted px-4 py-3 text-sm text-muted-foreground" data-slot="keys-note">
        <span aria-hidden="true" className="flex h-5 shrink-0 items-center">
          <Info className="size-4 text-foreground" />
        </span>
        <span>
          <b className="font-medium text-foreground">{t("proto.keys.note.lead")}</b> {t("proto.keys.note.rest")}
        </span>
      </p>

      <CreatedKeyDialog created={created} onClose={() => setCreated(null)} />

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
