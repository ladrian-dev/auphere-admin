"use client";

import { Languages, LogOut, Moon, Sun } from "lucide-react";
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

import { useLocale, useT } from "@/i18n/client";
import { roleKey } from "@/i18n/messages";
import { signOutAction } from "@/lib/auth-actions";
import type { Role } from "@/lib/principal";

type Props = { user: { name: string; email: string }; role: Role; partnerSlug: string; collapsed: boolean };

export function UserMenu({ user, role, collapsed }: Props) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const initials = (user.name || user.email).slice(0, 2).toUpperCase();

  async function switchLocale(next: "es" | "en") {
    document.cookie = `nexus-console.locale=${next}; path=/; max-age=31536000; samesite=lax`;
    router.refresh();
  }

  return (
    <DropdownMenu>
      {/* Base UI: nesting SidebarMenuButton inside the trigger crashes (both use useRender);
          the sidebar-button styles are inlined on the trigger. */}
      <DropdownMenuTrigger
        aria-label={user.email}
        className={[
          "group/menu-button flex w-full items-center gap-2 overflow-hidden rounded-sm text-left text-sm outline-none ring-sidebar-ring",
          "transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2",
          "data-[popup-open]:bg-sidebar-accent data-[popup-open]:text-sidebar-accent-foreground",
          collapsed ? "size-8 justify-center p-0" : "h-10 px-2 py-1",
        ].join(" ")}
      >
        <span className="grid size-6 shrink-0 place-items-center rounded-sm bg-accent text-xs font-semibold text-accent-foreground" aria-hidden="true">
          {initials}
        </span>
        {!collapsed ? (
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-medium">{user.name || user.email}</span>
            <span className="truncate font-mono text-xs text-muted-foreground">{t(roleKey(role))}</span>
          </span>
        ) : null}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-56">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="truncate font-normal">
            <span className="block truncate text-sm font-medium">{user.name}</span>
            <span className="block truncate font-mono text-xs text-muted-foreground">{user.email}</span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuLabel>{t("shell.theme")}</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => setTheme("light")} data-checked={theme === "light" || undefined}>
            <Sun /> {t("shell.theme.light")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTheme("dark")} data-checked={theme === "dark" || undefined}>
            <Moon /> {t("shell.theme.dark")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTheme("system")}>{t("shell.theme.system")}</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuLabel>{t("shell.language")}</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => switchLocale(locale === "es" ? "en" : "es")}>
            <Languages /> {locale === "es" ? "English" : "Español"}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onClick={async () => {
              await signOutAction();
              router.replace("/login");
              router.refresh();
            }}
          >
            <LogOut /> {t("shell.signOut")}
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
