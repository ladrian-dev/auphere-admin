"use client";

import { Languages, LogOut, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  cn,
} from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import { roleKey } from "@/i18n/messages";
import { signOutAction } from "@/lib/auth-actions";
import type { Role } from "@/lib/permissions";

type Props = {
  user: { name: string; email: string };
  role: Role;
  partnerName: string;
  /** Equipo, Facturación y API (las que su rol puede ver): viven aquí, no en el lateral. */
  account?: { href: string; label: string; icon: LucideIcon }[];
  /** `avatar`: solo las iniciales (barra superior en móvil). */
  variant: "full" | "avatar";
  /** En el lateral plegado: el nombre se desvanece y el avatar no se mueve. */
  collapsed?: boolean;
  /** Hacia dónde se abre: arriba al pie del lateral, abajo en la barra superior. */
  side?: "top" | "bottom";
  className?: string;
};

/**
 * Spec 047 (R47.1): el menú de perfil del marco nuevo. Lleva la cuenta
 * (Equipo, Facturación y API, que salieron del lateral), el idioma y «Cerrar
 * sesión», en rojo tras un separador. El tema es el interruptor de la barra
 * (Andrés, 2026-10-28). Está también en la barra superior de las pantallas
 * estrechas.
 */
export function ProfileMenu({ user, role, partnerName, account = [], variant, collapsed = false, side = "top", className }: Props) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
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
          variant === "full" ? "h-12 w-full px-1" : "size-10 shrink-0 justify-center",
          className,
        )}
      >
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
          {initials}
        </span>
        {variant === "full" ? (
          <span className={cn("flex min-w-0 flex-col transition-opacity duration-(--duration-state) motion-reduce:transition-none", collapsed && "opacity-0")}>
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
        {account.length ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuLabel>{t("nav.group.account")}</DropdownMenuLabel>
              {account.map(({ href, label, icon: Icon }) => (
                <DropdownMenuItem key={href} render={<Link href={href} />}>
                  <Icon aria-hidden="true" /> {label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </>
        ) : null}
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
