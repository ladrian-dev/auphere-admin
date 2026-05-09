"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronsUpDown,
  LayoutDashboard,
  Library,
  LogOut,
  type LucideIcon,
} from "lucide-react";

import { Wordmark } from "@/components/brand/wordmark";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
} from "@/components/ui/sidebar";
import { signOut } from "@/lib/auth-client";

type Item = { href: string; label: string; icon: LucideIcon };

const NAV: Item[] = [
  { href: "/tenants", label: "Tenants", icon: LayoutDashboard },
  { href: "/tool-catalog", label: "Catálogo de tools", icon: Library },
];

/**
 * Editorial sidebar — bone background, hairline border, no gradients.
 *
 * Active state uses pistachio accent (per brand-system) instead of the
 * primary green so the cue is calm rather than highlighty. Lee will see
 * this for hours; it has to behave like a piece of furniture.
 *
 * Collapse behaviour follows the Vercel / Linear pattern: in icon mode
 * we keep only the brand mark and the menu icons; the user menu turns
 * into a single avatar-shaped row with a popover so signOut stays one
 * click away regardless of state.
 */
export function AppSidebar({
  user,
}: {
  user: { name?: string | null; email: string };
}) {
  const pathname = usePathname();

  return (
    <Sidebar variant="inset" collapsible="icon">
      <SidebarHeader>
        <BrandHeader />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel
            className="font-mono uppercase text-[10px]"
            style={{ letterSpacing: "var(--tracking-eyebrow)" }}
          >
            Operación
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV.map((item) => {
                const active =
                  item.href === "/tenants"
                    ? pathname === "/tenants" ||
                      pathname.startsWith("/tenants/")
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
        <SidebarMenu>
          <SidebarMenuItem>
            <UserMenu user={user} />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

/**
 * Brand mark inside the sidebar header. In ``collapsed`` (icon-only)
 * mode we render the dot mark alone; in expanded mode the full
 * lowercase wordmark plus ``nexus`` suffix.
 */
function BrandHeader() {
  const { state, isMobile } = useSidebar();
  const collapsed = state === "collapsed" && !isMobile;
  return (
    <div className="flex h-10 items-center px-2">
      {collapsed ? (
        <span
          aria-hidden="true"
          aria-label="auphere"
          className="block size-2 rounded-[2px] bg-[color:var(--color-primary-deep)]"
        />
      ) : (
        <Wordmark variant="compact" />
      )}
    </div>
  );
}

/**
 * Footer user menu. Uses ``SidebarMenuButton`` so the row collapses to
 * the avatar in icon mode automatically; the dropdown keeps signOut
 * one click away in either state.
 */
function UserMenu({
  user,
}: {
  user: { name?: string | null; email: string };
}) {
  const router = useRouter();
  const initials = (user.name ?? user.email).slice(0, 2).toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <SidebarMenuButton
            size="lg"
            tooltip={user.email}
            className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
          >
            <span
              aria-hidden="true"
              className="grid size-7 shrink-0 place-items-center rounded-md bg-[color:var(--color-pistachio)] text-[color:var(--color-bangladesh-green)] text-xs font-semibold"
            >
              {initials}
            </span>
            <span className="grid flex-1 text-left leading-tight">
              <span className="truncate text-sm font-medium">
                {user.name ?? "Operador"}
              </span>
              <span className="truncate text-[11px] text-muted-foreground">
                {user.email}
              </span>
            </span>
            <ChevronsUpDown className="ml-auto size-4 text-muted-foreground" />
          </SidebarMenuButton>
        }
      />
      <DropdownMenuContent
        side="right"
        align="end"
        sideOffset={8}
        className="min-w-56"
      >
        <DropdownMenuLabel
          className="text-xs font-mono uppercase text-muted-foreground"
          style={{ letterSpacing: "var(--tracking-eyebrow)" }}
        >
          Operador
        </DropdownMenuLabel>
        <DropdownMenuItem disabled>
          <span className="grid leading-tight">
            <span className="text-sm font-medium">
              {user.name ?? "Operador"}
            </span>
            <span className="text-xs text-muted-foreground">
              {user.email}
            </span>
          </span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={async () => {
            await signOut();
            router.replace("/login");
            router.refresh();
          }}
        >
          <LogOut className="size-4" />
          Cerrar sesión
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
