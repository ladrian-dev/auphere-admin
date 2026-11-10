import Link from "next/link";

import { buttonVariants, cn } from "@nexus/ui";

import type { MessageKey } from "@/i18n/messages";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * The words of a 404 (spec 056, 14.2 to 14.4): it does not say whether what was
 * asked for exists, and it always leaves a way out — the first module of whoever
 * is signed in, or «Entrar» for whoever is not.
 */
export function NotFoundView({ t, home }: { t: T; home: string | null }) {
  return (
    <section aria-labelledby="not-found-title" className="mx-auto flex w-full max-w-md min-w-0 flex-col items-center gap-3 px-4 py-16 text-center">
      <span aria-hidden="true" className="font-mono text-sm font-semibold text-muted-foreground tabular-nums">
        404
      </span>
      <h1 id="not-found-title" className="text-lg font-semibold text-balance">
        {t("shell.notFound.title")}
      </h1>
      <p className="text-sm text-pretty text-muted-foreground">{t("shell.notFound.body")}</p>
      <Link href={home ?? "/login"} className={cn(buttonVariants({ variant: home ? "outline" : "default" }), "mt-2")}>
        {home ? t("shell.notFound.home") : t("shell.notFound.signIn")}
      </Link>
    </section>
  );
}
