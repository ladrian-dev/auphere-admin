"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { useCrumbNames } from "./crumb-names";
import { crumbsFor, type CrumbLabel } from "./crumbs-v2";

/**
 * Volver, además de las migas (Andrés, 2026-10-28): un botón redondo de
 * vidrio, junto al título de la página, que lleva a la miga anterior. Es un enlace, no `history.back()`: lleva
 * siempre al mismo sitio, también si se llegó por un enlace de fuera. En una
 * pantalla de primer nivel no hay a dónde volver y no sale.
 */
export function ShellBackButton({ className }: { className?: string }) {
  const t = useT();
  const pathname = usePathname();
  const names = useCrumbNames();
  const crumbs = crumbsFor(pathname, names);
  const parent = [...crumbs].reverse().find((c, i) => i > 0 && c.href) ?? null;
  if (crumbs.length < 2 || !parent?.href) return null;
  const text = (label: CrumbLabel) => ("text" in label ? label.text : t(label.key, label.vars));
  return (
    <Link
      href={parent.href}
      aria-label={t("shell.back", { name: text(parent.label) })}
      className={cn(
        "glass grid size-9 shrink-0 place-items-center rounded-full text-foreground ring-1 ring-foreground/10 transition-transform duration-(--duration-hover) outline-none hover:-translate-x-px focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
        className,
      )}
    >
      <ArrowLeft aria-hidden="true" className="size-4" />
    </Link>
  );
}
