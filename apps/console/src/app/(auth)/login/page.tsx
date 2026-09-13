import Link from "next/link";
import { redirect } from "next/navigation";

import { getT } from "@/i18n/server";
import { env } from "@/lib/env";
import { resolvePrincipal } from "@/lib/principal";

import { LoginForm } from "./login-form";

export async function generateMetadata() {
  const { t } = await getT("es");
  return { title: t("login.title") };
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ from?: string }> }) {
  // A live session skips the form. "Live" here means the API still knows
  // the cookie — a stale one resolves to `anonymous` and stays on /login.
  const resolution = await resolvePrincipal();
  if (resolution.kind !== "anonymous") redirect("/");
  const { from } = await searchParams;
  const { t } = await getT("es");
  // Same-origin path only: one leading slash and no backslash (browsers
  // treat "/\evil.com" as protocol-relative).
  const redirectTo = from && /^\/(?![\/\\])[^\\]*$/.test(from) ? from : "/";
  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-3xl font-semibold">{t("login.title")}</h1>
      <LoginForm redirectTo={redirectTo} />
      {/* Con el alta apagada NO hay enlace, ni gris ni con explicación: la
          ausencia se diseña (constitución §V). Quien no puede registrarse no
          tiene por qué enterarse de que existe un registro. */}
      {env().NEXUS_SIGNUP_ENABLED ? (
        <p className="text-sm text-muted-foreground">
          <Link href="/signup" className="underline underline-offset-4">
            {t("login.noAccount")}
          </Link>
        </p>
      ) : null}
    </section>
  );
}
