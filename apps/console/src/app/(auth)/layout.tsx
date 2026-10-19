import { Eyebrow } from "@nexus/ui";

import { getT } from "@/i18n/server";

export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const { t } = await getT("es");
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-md flex-col justify-center gap-8 px-6 py-12">
      <div className="flex flex-col gap-2">
        <span className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold tracking-tight text-primary-deep">auphere</span>
          {/* Owner, 2026-10-19: the partner console is in beta. */}
          <span className="rounded-full bg-status-warning-bg px-2 text-xs leading-5 font-semibold text-status-warning-text ring-1 ring-status-warning-border">
            {t("shell.beta")}
          </span>
        </span>
        <Eyebrow>{t("login.eyebrow")}</Eyebrow>
      </div>
      {children}
      <p className="font-mono text-xs text-muted-foreground">{t("login.footer")}</p>
    </main>
  );
}
