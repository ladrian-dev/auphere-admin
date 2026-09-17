import Link from "next/link";
import type { ReactNode } from "react";

import { BrandMark } from "@/components/ui/BrandMark";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

/** Cabecera: logo centrado, interruptor de tema a la derecha y un hueco a la izquierda para acciones (p. ej. reiniciar). */
export function Header({ tone = "light", left, themeToggle = true }: { tone?: "light" | "dark"; left?: ReactNode; themeToggle?: boolean }) {
  return (
    <header className="grid h-16 grid-cols-[44px_1fr_44px] items-center px-4 sm:px-6">
      <div className="flex items-center">{left}</div>
      <Link href="/" aria-label="Amacrux, inicio" className="flex justify-center rounded-md">
        <BrandMark variant={tone === "dark" ? "chrome" : "auto"} height={20} priority />
      </Link>
      <div className="flex justify-end">
        {themeToggle ? <ThemeToggle className={tone === "dark" ? "border-ink-on-strong/25 bg-ink-on-strong/10 text-ink-on-strong hover:bg-ink-on-strong/20" : ""} /> : null}
      </div>
    </header>
  );
}
