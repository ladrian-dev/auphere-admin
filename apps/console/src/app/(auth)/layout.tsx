import { Eyebrow } from "@nexus/ui";

import { getT } from "@/i18n/server";

export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const { t } = await getT();
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-md flex-col justify-center gap-8 px-6 py-12">
      <div className="flex flex-col gap-2">
        <span className="font-mono text-sm font-semibold tracking-tight text-primary-deep">auphere</span>
        <Eyebrow>{t("login.eyebrow")}</Eyebrow>
      </div>
      {children}
      <p className="font-mono text-xs text-muted-foreground">Nexus · Auphere</p>
    </main>
  );
}
