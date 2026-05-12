"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronsUpDown,
  LayoutDashboard,
  LogOut,
  Plug,
  type LucideIcon,
} from "lucide-react";

import { Wordmark } from "@/components/brand/wordmark";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
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
import { cn } from "@/lib/utils";

type Item = { href: string; label: string; icon: LucideIcon };

const NAV: Item[] = [
  { href: "/tenants", label: "Tenants", icon: LayoutDashboard },
  { href: "/connectors", label: "Connectors", icon: Plug },
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
 * Footer user menu.
 *
 * Originally I tried wrapping ``SidebarMenuButton`` inside
 * ``DropdownMenuTrigger`` via the ``render`` prop. Both components use
 * Base UI's ``useRender`` and the nested composition crashes on click.
 * Inlining the sidebar-button styles on the trigger directly is the
 * documented Base UI escape hatch, and lets us flip to icon-only
 * layout via ``useSidebar`` without losing the dropdown affordance.
 */
function UserMenu({
  user,
}: {
  user: { name?: string | null; email: string };
}) {
  const router = useRouter();
  const { state, isMobile } = useSidebar();
  const collapsed = state === "collapsed" && !isMobile;
  const initials = (user.name ?? user.email).slice(0, 2).toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={user.email}
        className={cn(
          "group/menu-button flex w-full items-center gap-2 overflow-hidden rounded-sm text-left text-sm outline-none ring-sidebar-ring",
          "transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
          "focus-visible:ring-2 active:bg-sidebar-accent",
          "data-[popup-open]:bg-sidebar-accent data-[popup-open]:text-sidebar-accent-foreground",
          collapsed ? "size-8 justify-center p-0" : "h-10 px-2 py-1.5",
        )}
      >
        <span
          aria-hidden="true"
          className="grid size-6 shrink-0 place-items-center rounded-sm bg-[color:var(--color-pistachio)] text-[color:var(--color-bangladesh-green)] text-[11px] font-semibold"
        >
          {initials}
        </span>
        {!collapsed ? (
          <>
            <span className="grid flex-1 text-left leading-tight overflow-hidden">
              <span className="truncate text-sm font-medium">
                {user.name ?? "Operador"}
              </span>
              <span className="truncate text-[11px] text-muted-foreground">
                {user.email}
              </span>
            </span>
            <ChevronsUpDown
              className="ml-auto size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
          </>
        ) : null}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side="right"
        align="end"
        sideOffset={8}
        className="min-w-56"
      >
        {/*
          Base UI requires GroupLabel + every Item that shares its label
          to live inside a single Menu.Group. We wrap the whole menu in
          one ``DropdownMenuGroup`` to satisfy the contract — the group
          here is the entire user menu.
        */}
        <DropdownMenuGroup>
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
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
