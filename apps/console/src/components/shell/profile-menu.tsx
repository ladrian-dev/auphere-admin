"use client";

import { Languages, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  cn,
  useTheme,
} from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import { roleKey } from "@/i18n/messages";
import { signOutAction } from "@/lib/auth-actions";
import type { Role } from "@/lib/permissions";

type Props = {
  user: { name: string; email: string };
  role: Role;
  partnerName: string;
  /** `avatar`: solo las iniciales (menú plegado y barra superior en móvil). */
  variant: "full" | "avatar";
  /** Hacia dónde se abre: arriba al pie del lateral, abajo en la barra superior. */
  side?: "top" | "bottom";
  className?: string;
};

const THEMES = [
  { value: "light", key: "shell.theme.light" },
  { value: "dark", key: "shell.theme.dark" },
  { value: "system", key: "shell.theme.system" },
] as const;

/**
 * Spec 047 (R47.1): el menú de perfil del marco nuevo. Lleva el tema (Claro,
 * Oscuro o Sistema, como opciones de radio con la marcada a la vista), el
 * idioma y «Cerrar sesión», en rojo tras un separador. Está también en la
 * barra superior de las pantallas estrechas: el prototipo lo escondía en móvil
 * y con él el tema (`01` §10), y eso no se toma.
 */
export function ProfileMenu({ user, role, partnerName, variant, side = "top", className }: Props) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const shown = user.name || user.email;
  const initials = shown.slice(0, 2).toUpperCase();

  function switchLocale(next: "es" | "en") {
    document.cookie = `nexus-console.locale=${next}; path=/; max-age=31536000; samesite=lax`;
    router.refresh();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        // Con el nombre a la vista, el nombre accesible es ese texto (WCAG
        // 2.5.3). Solo con las iniciales hace falta decir de quién es.
        aria-label={variant === "avatar" ? t("shell.profile.open", { name: shown }) : undefined}
        className={cn(
          "flex min-w-0 items-center gap-2 overflow-hidden rounded-md text-left text-sm outline-none transition-colors duration-(--duration-hover)",
          "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-ring data-[popup-open]:bg-sidebar-accent",
          variant === "full" ? "h-12 w-full px-2" : "size-10 shrink-0 justify-center",
          className,
        )}
      >
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
          {initials}
        </span>
        {variant === "full" ? (
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-medium">{shown}</span>
            <span className="truncate text-xs text-muted-foreground">{t(roleKey(role))}</span>
          </span>
        ) : null}
      </DropdownMenuTrigger>
      <DropdownMenuContent align={side === "top" ? "start" : "end"} side={side} className="w-64">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="font-normal">
            <span className="block truncate text-sm font-medium text-foreground">{user.name}</span>
            <span className="block truncate text-xs text-muted-foreground tabular-nums">{user.email}</span>
            <span className="mt-1 block truncate text-xs text-muted-foreground" title={partnerName}>
              {t("shell.partner")}: {partnerName}
            </span>
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel>{t("shell.theme")}</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={theme ?? "system"} onValueChange={(value) => setTheme(String(value))}>
            {THEMES.map((option) => (
              // Elegir el tema lo aplica y cierra el menú, como en el prototipo.
              <DropdownMenuRadioItem key={option.value} value={option.value} closeOnClick>
                {t(option.key)}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel>{t("shell.language")}</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => switchLocale(locale === "es" ? "en" : "es")}>
            <Languages aria-hidden="true" /> {locale === "es" ? "English" : "Español"}
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onClick={async () => {
            await signOutAction();
            router.replace("/login");
            router.refresh();
          }}
        >
          <LogOut aria-hidden="true" /> {t("shell.signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
