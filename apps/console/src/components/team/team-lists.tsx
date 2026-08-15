"use client";

import { MoreHorizontal } from "lucide-react";
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
  EmptyState,
  StatusBadge,
  formatDate,
  formatRelative,
} from "@nexus/ui";

import { changeRoleAction, changeStatusAction, removeMemberAction, revokeInvitationAction } from "@/app/(console)/team/actions";
import { useLocale, useT } from "@/i18n/client";
import { roleKey } from "@/i18n/messages";
import type { Member, Team } from "@/lib/backend";

const ROLES = ["owner", "admin", "builder", "analyst", "billing"] as const;

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

  return (
    <div className="flex min-w-0 flex-col gap-8" aria-busy={pending}>
      <section aria-labelledby="members-h" className="flex flex-col gap-3">
        <h2 id="members-h" className="text-lg font-semibold">
          {t("team.members")}
        </h2>
        <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
          {team.members.map((m) => (
            <li key={m.id} className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-3">
              <span className="grid size-8 shrink-0 place-items-center rounded-sm bg-accent text-xs font-semibold text-accent-foreground" aria-hidden="true">
                {(m.display_name || m.email).slice(0, 2).toUpperCase()}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm font-medium">
                  {m.display_name || m.email}
                  {m.is_you ? <span className="ml-2 font-mono text-xs text-muted-foreground">({t("team.you")})</span> : null}
                </span>
                <span className="truncate font-mono text-xs text-muted-foreground">{m.email}</span>
              </span>
              <StatusBadge tone={m.status === "active" ? "positive" : "warning"}>{t(`status.${m.status}` as "status.active")}</StatusBadge>
              <span className="text-sm">{t(roleKey(m.role))}</span>
              <span className="hidden text-sm text-muted-foreground tabular-nums md:inline" title={m.accepted_at ?? undefined}>
                {t("team.joined")} {formatRelative(m.accepted_at ?? m.created_at, locale)}
              </span>
              {manage && !m.is_you ? (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    aria-label={`${t("common.actions")} ${m.email}`}
                    className="inline-flex size-8 items-center justify-center rounded-sm hover:bg-muted"
                  >
                    <MoreHorizontal className="size-4" />
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
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="inv-h" className="flex flex-col gap-3">
        <h2 id="inv-h" className="text-lg font-semibold">
          {t("team.invitations")}
        </h2>
        {team.invitations.length === 0 ? (
          <EmptyState title={t("team.invitations.empty")} readonly className="py-8" />
        ) : (
          <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
            {team.invitations.map((i) => (
              <li key={i.id} className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-3">
                <span className="min-w-0 flex-1 truncate font-mono text-sm">{i.email}</span>
                <span className="text-sm">{t(roleKey(i.role))}</span>
                <span className="text-sm text-muted-foreground tabular-nums">
                  {t("team.expires")} {formatDate(i.expires_at, locale)}
                </span>
                {manage ? (
                  <Button variant="ghost" size="sm" onClick={() => act(() => revokeInvitationAction({ id: i.id }))}>
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
