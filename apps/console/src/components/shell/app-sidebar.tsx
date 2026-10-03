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
        <UserMenu user={user} role={role} partnerName={partnerName} partnerSlug={partnerSlug} collapsed={collapsed} />
      </SidebarFooter>
    </Sidebar>
  );
}
