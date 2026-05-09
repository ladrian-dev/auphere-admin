"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, Library, LogOut, type LucideIcon } from "lucide-react";

import { Wordmark } from "@/components/brand/wordmark";
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
} from "@/components/ui/sidebar";
import { signOut } from "@/lib/auth-client";

type Item = { href: string; label: string; icon: LucideIcon };

const NAV: Item[] = [
  { href: "/tenants", label: "Tenants", icon: LayoutDashboard },
  { href: "/tool-catalog", label: "Catálogo de tools", icon: Library },
];

/**
 * Editorial sidebar — bone background, hairline border, no gradients.
 * Active state uses pistachio accent (per brand-system) instead of the
 * primary green so the cue is calm rather than highlighty. Lee will
 * see this for hours; it has to behave like a piece of furniture.
 */
export function AppSidebar({
  user,
}: {
  user: { name?: string | null; email: string };
}) {
  const pathname = usePathname();
  const router = useRouter();
  const initials = (user.name ?? user.email).slice(0, 2).toUpperCase();

  return (
    <Sidebar variant="inset" collapsible="icon">
      <SidebarHeader>
        <div className="flex h-12 items-center px-2">
          <Wordmark variant="compact" />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="font-mono uppercase text-[10px]"
            style={{ letterSpacing: "var(--tracking-eyebrow)" }}
          >
            Operación
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV.map((item) => {
                const active =
                  item.href === "/tenants"
                    ? pathname === "/tenants" || pathname.startsWith("/tenants/")
                    : pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      isActive={active}
                      tooltip={item.label}
                      render={
                        <Link href={item.href}>
                          <Icon className="size-4" aria-hidden="true" />
                          <span>{item.label}</span>
                        </Link>
                      }
                    />
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <div className="flex items-center gap-3 rounded-md px-2 py-2">
          <div
            aria-hidden="true"
            className="grid size-8 place-items-center rounded-md bg-[color:var(--color-pistachio)] text-[color:var(--color-bangladesh-green)] text-xs font-semibold"
          >
            {initials}
          </div>
          <div className="flex flex-1 flex-col leading-tight overflow-hidden">
            <span className="truncate text-sm font-medium">
              {user.name ?? "Operador"}
            </span>
            <span className="truncate text-xs text-muted-foreground">
              {user.email}
            </span>
          </div>
          <button
            type="button"
            aria-label="Cerrar sesión"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition"
            onClick={async () => {
              await signOut();
              router.replace("/login");
              router.refresh();
            }}
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
