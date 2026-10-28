"use client";

import { CircleCheck, MoreHorizontal, Pause, Send } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  ConfirmDialog,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  StatusBadge,
  formatDate,
  formatRelative,
} from "@nexus/ui";

import { changeRoleAction, changeStatusAction, removeMemberAction, revokeInvitationAction } from "@/app/(console)/team/actions";
import { useLocale, useT } from "@/i18n/client";
import { roleKey } from "@/i18n/messages";
import type { Member, Team } from "@/lib/backend";

const ROLES = ["owner", "admin", "builder", "analyst", "billing"] as const;
const rank = (role: string) => {
  const i = (ROLES as readonly string[]).indexOf(role);
  return i === -1 ? ROLES.length : i;
};

/** La cabecera de una tarjeta del prototipo: el título y, a la derecha, el recuento. */
function CardHead({ id, title, count }: { id: string; title: string; count: number }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 px-4 pt-4 pb-2">
      <h2 id={id} className="text-base font-semibold">
        {title}
      </h2>
      <span className="text-xs text-muted-foreground tabular-nums">{count}</span>
    </div>
  );
}

export function TeamLists({ team, manage }: { team: Team; manage: boolean }) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [removing, setRemoving] = React.useState<Member | null>(null);

  function act(fn: () => Promise<{ ok: boolean; message?: string }>) {
    startTransition(async () => {
      const res = await fn();
      if (!res.ok) return void toast.error(res.message ?? t("common.error.backend"));
      toast.success(t("team.updated"));
      router.refresh();
    });
  }

  // Prototipo: el propietario primero, luego por rol; dentro del rol, como llegan.
  const members = [...team.members].sort((a, b) => rank(a.role) - rank(b.role));

  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
      <section aria-labelledby="members-h" className="overflow-hidden rounded-lg bg-card ring-1 ring-foreground/10" data-slot="team-members">
        <CardHead id="members-h" title={t("team.members")} count={team.members.length} />
        <ul className="divide-y divide-border">
          {members.map((m) => (
            <li
              key={m.id}
              className="grid min-w-0 grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 md:grid-cols-[36px_minmax(0,1fr)_120px_120px_140px_32px]"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-md bg-status-positive-bg text-xs font-semibold text-status-positive-text" aria-hidden="true">
                {(m.display_name || m.email).slice(0, 2).toUpperCase()}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-medium">
                  {m.display_name || m.email}
                  {m.is_you ? <span className="ml-1 text-xs font-normal text-muted-foreground">({t("team.you")})</span> : null}
                </span>
                <span className="truncate font-mono text-xs text-muted-foreground">{m.email}</span>
              </span>
              <span className="hidden text-sm md:block">{t(roleKey(m.role))}</span>
              <span className="hidden md:block">
                <StatusBadge tone={m.status === "active" ? "positive" : "warning"} dot={false}>
                  {m.status === "active" ? <CircleCheck aria-hidden="true" className="size-3" /> : <Pause aria-hidden="true" className="size-3" />}
                  {t(`status.${m.status}` as "status.active")}
                </StatusBadge>
              </span>
              <span className="hidden text-right text-xs text-muted-foreground tabular-nums md:block" title={m.accepted_at ?? undefined}>
                {t("team.joined")} {formatRelative(m.accepted_at ?? m.created_at, locale)}
              </span>
              {manage && !m.is_you ? (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    aria-label={`${t("common.actions")} ${m.email}`}
                    className="inline-flex size-8 items-center justify-center rounded-md hover:bg-muted"
                  >
                    <MoreHorizontal aria-hidden="true" className="size-4" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuGroup>
                      <DropdownMenuLabel>{t("team.changeRole")}</DropdownMenuLabel>
                      {ROLES.filter((r) => r !== m.role).map((r) => (
                        <DropdownMenuItem key={r} onClick={() => act(() => changeRoleAction({ id: m.id, role: r }))}>
                          {t(roleKey(r))}
                        </DropdownMenuItem>
                      ))}
                      <DropdownMenuSeparator />
                      {m.status === "active" ? (
                        <DropdownMenuItem onClick={() => act(() => changeStatusAction({ id: m.id, status: "suspended" }))}>{t("team.suspend")}</DropdownMenuItem>
                      ) : (
                        <DropdownMenuItem onClick={() => act(() => changeStatusAction({ id: m.id, status: "active" }))}>{t("team.reactivate")}</DropdownMenuItem>
                      )}
                      <DropdownMenuItem variant="destructive" onClick={() => setRemoving(m)}>
                        {t("team.remove")}
                      </DropdownMenuItem>
                    </DropdownMenuGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                // En tu fila, el hueco del «⋯»: las columnas no se mueven.
                <span aria-hidden="true" className="size-8" />
              )}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="inv-h" className="overflow-hidden rounded-lg bg-card ring-1 ring-foreground/10" data-slot="team-invitations">
        <CardHead id="inv-h" title={t("team.invitations")} count={team.invitations.length} />
        {team.invitations.length === 0 ? (
          <p className="px-4 pb-4 text-sm text-muted-foreground">{t("team.invitations.empty")}</p>
        ) : (
          <ul className="divide-y divide-border">
            {team.invitations.map((i) => (
              <li key={i.id} className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-3">
                <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground">
                  <Send className="size-4" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate font-mono text-sm font-medium">{i.email}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {t(roleKey(i.role))} · {t("team.expires")} {formatDate(i.expires_at, locale)}
                  </span>
                </span>
                {manage ? (
                  <Button variant="outline" size="sm" onClick={() => act(() => revokeInvitationAction({ id: i.id }))}>
                    {t("team.revoke")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={t("team.remove.title", { email: removing?.email ?? "" })}
        description={t("team.remove.body")}
        confirmLabel={t("team.remove")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={async () => {
          if (!removing) return;
          const res = await removeMemberAction({ id: removing.id });
          if (!res.ok) return void toast.error(res.message);
          setRemoving(null);
          router.refresh();
        }}
      />
    </div>
  );
}
