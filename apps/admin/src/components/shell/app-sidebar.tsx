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

import { NAV, isActive } from "./nav";
import { UserMenu } from "./user-menu";

type Props = {
  user: { name: string; email: string; role: string };
  /** R2.5: a count next to an entry, by href (open tickets). Zero hides it. */
  badges?: Record<string, number>;
};

/**
 * Spec 031: the operator panel's sidebar, built like the console's — the
 * same primitive, the same fade when it folds to icons (⌘B), the same
 * group labels — with the panel's own navigation (`nav.ts`).
 */
export function AppSidebar({ user, badges = {} }: Props) {
  const pathname = usePathname();
  const { state, isMobile } = useSidebar();
  const collapsed = state === "collapsed" && !isMobile;

  return (
    <Sidebar variant="inset" collapsible="icon" aria-label="Principal">
      <SidebarHeader>
        <Link href="/" className="flex h-10 min-w-0 items-center gap-2 overflow-hidden rounded-sm px-1 outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring">
          <BrandMark className="size-7 shrink-0 text-primary" />
          <BrandWordmark
            className={cn(
              "h-5 w-auto shrink-0 text-foreground transition-opacity duration-300 ease-(--ease-in-out) motion-reduce:transition-none",
              collapsed && "opacity-0",
            )}
          />
          <span
            className={cn(
              "shrink-0 rounded-full bg-primary/15 px-2 text-xs leading-5 font-semibold text-accent-foreground transition-opacity duration-300 ease-(--ease-in-out) motion-reduce:transition-none",
              collapsed && "opacity-0",
            )}
          >
            admin
          </span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        {NAV.map((group) => (
          <SidebarGroup key={group.id}>
            {group.label ? (
              <SidebarGroupLabel className="text-xs font-medium tracking-eyebrow uppercase">{group.label}</SidebarGroupLabel>
            ) : null}
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(pathname, item);
                  const badge = badges[item.href] ?? 0;
                  return (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton
                        isActive={active}
                        tooltip={item.label}
                        render={
                          <Link href={item.href} aria-current={active ? "page" : undefined}>
                            <Icon className="size-4" aria-hidden="true" />
                            <span className="flex-1 truncate">{item.label}</span>
                            {badge > 0 ? (
                              <span className="grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1 text-xs leading-none font-semibold text-primary-foreground tabular-nums">
                                <span className="sr-only">{badge} abiertos</span>
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
        <UserMenu user={user} collapsed={collapsed} />
      </SidebarFooter>
    </Sidebar>
  );
}
