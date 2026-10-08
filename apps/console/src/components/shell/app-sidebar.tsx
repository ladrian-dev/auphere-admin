"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  BrandMark,
  BrandWordmark,
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  cn,
  useSidebar,
} from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { ClientModule, Role } from "@/lib/principal";

import { isActive, navForPrincipal } from "./nav";
import { useInboxUnread } from "./use-inbox-unread";
import { UserMenu } from "./user-menu";

/** Spec 030: who the sidebar is for. A client user sees its client's modules. */
export type SidebarWho =
  | { kind: "partner"; role: Role }
  | { kind: "client"; modules: ClientModule[]; clientName: string };

type Props = {
  who: SidebarWho;
  partnerName: string;
  partnerSlug: string;
  user: { name: string; email: string };
  /** Spec 030 (R3.5): a count next to a nav item, by href (unread in the inbox). */
  badges?: Record<string, number>;
};

export function AppSidebar({ who, partnerName, partnerSlug, user, badges }: Props) {
  const t = useT();
  const pathname = usePathname();
  const { state, isMobile } = useSidebar();
  const collapsed = state === "collapsed" && !isMobile;
  const groups = navForPrincipal(who);
  const lite = who.kind === "client";
  const unread = useInboxUnread(who.kind === "client" && who.modules.includes("inbox"));
  const counts: Record<string, number> = { ...badges, ...(unread > 0 ? { "/inbox": unread } : {}) };

  return (
    <Sidebar variant="inset" collapsible="icon" aria-label="Primary">
      <SidebarHeader>
        {/* The full logo (owner, 2026-09-24). Collapsing keeps the same layout:
            the mark stays put and the wordmark fades while the panel clips it
            (owner, 2026-10-03: the motion must be soft, not a jump). */}
        <div className="flex h-10 min-w-0 items-center gap-2 overflow-hidden px-1">
          <BrandMark className="size-7 shrink-0 text-primary" />
          <BrandWordmark
            className={cn(
              "h-5 w-auto shrink-0 text-foreground transition-opacity duration-300 ease-(--ease-in-out) motion-reduce:transition-none",
              collapsed && "opacity-0",
            )}
          />
          {lite ? (
            // Spec 030: the client console says it is the lite one.
            <span
              className={cn(
                "shrink-0 rounded-full bg-primary/15 px-2 text-xs leading-5 font-semibold text-accent-foreground transition-opacity duration-300 ease-(--ease-in-out) motion-reduce:transition-none",
                collapsed && "opacity-0",
              )}
            >
              lite
            </span>
          ) : null}
        </div>
      </SidebarHeader>
      <SidebarContent>
        {groups.map((group) => (
          <SidebarGroup key={group.labelKey}>
            <SidebarGroupLabel className="text-xs font-medium tracking-eyebrow uppercase">{t(group.labelKey)}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(pathname, item);
                  const badge = counts[item.href] ?? 0;
                  return (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton
                        isActive={active}
                        tooltip={t(item.labelKey)}
                        render={
                          <Link href={item.href} aria-current={active ? "page" : undefined}>
                            <Icon className="size-4" aria-hidden="true" />
                            <span className="flex-1 truncate">{t(item.labelKey)}</span>
                            {badge > 0 ? (
                              <span className="grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1 text-xs leading-none font-semibold text-primary-foreground tabular-nums">
                                <span className="sr-only">{t("nav.unread", { count: badge })}</span>
                                <span aria-hidden="true">{badge > 99 ? "99+" : badge}</span>
                              </span>
                            ) : null}
                          </Link>
                        }
                      />
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter>
        <UserMenu user={user} who={who} partnerName={partnerName} partnerSlug={partnerSlug} collapsed={collapsed} />
      </SidebarFooter>
    </Sidebar>
  );
}
