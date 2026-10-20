"use client";

import { LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useRouter } from "next/navigation";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  useTheme,
} from "@nexus/ui";

import { logoutAction } from "@/app/(auth)/login/actions";

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrador",
  qa_operator: "Operador QA",
  viewer: "Solo lectura",
};

/** Spec 031 (R1.3): who is signed in, the theme, and the way out. */
export function UserMenu({ user, collapsed }: { user: { name: string; email: string; role: string }; collapsed: boolean }) {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const initials = (user.name || user.email).slice(0, 2).toUpperCase();

  return (
    <DropdownMenu>
      {/* Base UI: a SidebarMenuButton inside the trigger crashes (both use
          useRender); the sidebar-button styles are inlined, like the console. */}
      <DropdownMenuTrigger
        aria-label={user.email}
        className={[
          "group/menu-button flex w-full items-center gap-2 overflow-hidden rounded-sm text-left text-sm outline-none ring-sidebar-ring",
          "transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2",
          "data-[popup-open]:bg-sidebar-accent data-[popup-open]:text-sidebar-accent-foreground",
          "h-10 px-1 py-1",
        ].join(" ")}
      >
        <span className="grid size-6 shrink-0 place-items-center rounded-sm bg-accent text-xs font-semibold text-accent-foreground" aria-hidden="true">
          {initials}
        </span>
        <span
          aria-hidden={collapsed || undefined}
          className={`flex min-w-0 flex-col transition-opacity duration-300 ease-(--ease-in-out) motion-reduce:transition-none ${collapsed ? "opacity-0" : ""}`}
        >
          <span className="truncate text-sm font-medium">{user.name || user.email}</span>
          <span className="truncate text-xs text-muted-foreground">{ROLE_LABEL[user.role] ?? user.role}</span>
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-56">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="truncate font-normal">
            <span className="block truncate text-sm font-medium">{user.name}</span>
            <span className="block truncate text-xs text-muted-foreground">{user.email}</span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Tema</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => setTheme("light")} data-checked={theme === "light" || undefined}>
            <Sun /> Claro
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTheme("dark")} data-checked={theme === "dark" || undefined}>
            <Moon /> Oscuro
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTheme("system")} data-checked={theme === "system" || undefined}>
            <Monitor /> Sistema
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onClick={async () => {
              await logoutAction();
              router.replace("/login");
              router.refresh();
            }}
          >
            <LogOut /> Cerrar sesión
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
