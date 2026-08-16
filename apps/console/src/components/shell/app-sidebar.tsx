"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
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
  useSidebar,
} from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { Role } from "@/lib/principal";

import { isActive, navForRole } from "./nav";
import { UserMenu } from "./user-menu";

type Props = {
  partnerName: string;
  partnerSlug: string;
  role: Role;
  user: { name: string; email: string };
};

export function AppSidebar({ partnerName, partnerSlug, role, user }: Props) {
  const t = useT();
  const pathname = usePathname();
  const { state, isMobile } = useSidebar();
  const collapsed = state === "collapsed" && !isMobile;
  const groups = navForRole(role);

  return (
    <Sidebar variant="inset" collapsible="icon" aria-label="Primary">
      <SidebarHeader>
        <div className={collapsed ? "flex h-10 items-center justify-center" : "flex h-10 min-w-0 flex-col justify-center px-2"}>
          {collapsed ? (
            <span className="font-mono text-sm font-semibold text-primary-deep" aria-label="Auphere">
              a.
            </span>
          ) : (
            <>
              <span className="font-mono text-xs tracking-eyebrow text-muted-foreground uppercase">{t("shell.partner")}</span>
              <span className="min-w-0 truncate text-sm font-semibold" title={partnerName}>
                {partnerName}
              </span>
            </>
          )}
        </div>
      </SidebarHeader>
      <SidebarContent>
        {groups.map((group) => (
          <SidebarGroup key={group.labelKey}>
            <SidebarGroupLabel className="font-mono text-xs tracking-eyebrow uppercase">{t(group.labelKey)}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(pathname, item);
                  return (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton
                        isActive={active}
                        tooltip={t(item.labelKey)}
                        render={
                          <Link href={item.href} aria-current={active ? "page" : undefined}>
                            <Icon className="size-4" aria-hidden="true" />
                            <span>{t(item.labelKey)}</span>
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
        <UserMenu user={user} role={role} partnerSlug={partnerSlug} collapsed={collapsed} />
      </SidebarFooter>
    </Sidebar>
  );
}
