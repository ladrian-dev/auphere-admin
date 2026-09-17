import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

import { Footer } from "./Footer";
import { Header } from "./Header";
import { SkipLink } from "./SkipLink";

export interface AppShellProps {
  tone?: "light" | "dark";
  headerLeft?: ReactNode;
  /** El interruptor claro/oscuro no se muestra en la bienvenida. */
  themeToggle?: boolean;
  /** El sticker de partner no se muestra en la bienvenida. */
  sticker?: boolean;
  children: ReactNode;
  width?: "narrow" | "wide";
}

export function AppShell({ tone = "light", headerLeft, themeToggle = true, sticker = true, children, width = "narrow" }: AppShellProps) {
  return (
    <div className={cx("flex min-h-dvh flex-col", tone === "dark" ? "brand-gradient text-ink-on-strong" : "bg-canvas text-ink")}>
      <SkipLink />
      <Header tone={tone} left={headerLeft} themeToggle={themeToggle} />
      <main id="contenido" className={cx("mx-auto flex w-full flex-1 flex-col px-4 pb-6 sm:px-6", width === "narrow" ? "max-w-xl" : "max-w-3xl")}>
        {children}
      </main>
      <Footer tone={tone} sticker={sticker} />
    </div>
  );
}
