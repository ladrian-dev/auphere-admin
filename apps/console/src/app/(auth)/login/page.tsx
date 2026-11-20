import Link from "next/link";
import { redirect } from "next/navigation";

import { getT } from "@/i18n/server";
import { consoleService } from "@/lib/backend";
import { env } from "@/lib/env";
import { resolvePrincipal } from "@/lib/principal";

import { GoogleButton } from "../google-button";

import { LoginForm } from "./login-form";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("login.title") };
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ from?: string }> }) {
  // A live session skips the form. "Live" here means the API still knows
  // the cookie — a stale one resolves to `anonymous` and stays on /login.
  const resolution = await resolvePrincipal();
  if (resolution.kind !== "anonymous") redirect("/");
  const { from } = await searchParams;
  const { t } = await getT();
  // Same-origin path only: one leading slash and no backslash (browsers
  // treat "/\evil.com" as protocol-relative).
  const redirectTo = from && /^\/(?![\/\\])[^\\]*$/.test(from) ? from : "/";
  // Se resuelve **aquí, en el servidor**. Preguntarlo desde el navegador
  // costaba una llamada por visita y, cuando se preguntaba con `/start`, un
  // PKCE huérfano de diez minutos en Redis por cada carga de una página
  // pública.
  const googleAvailable = await consoleService.googleAvailable();
  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold">{t("login.title")}</h1>
        <p className="text-pretty text-muted-foreground">{t("auth.hero.body")}</p>
      </div>
      <LoginForm redirectTo={redirectTo} />
      {/* Spec 066 (R4.2): con Google, un «o» que separa los dos caminos. Sin
          Google no hay botón (spec 006, 5.6) y tampoco separador. */}
      {googleAvailable ? (
        <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-hidden="true">
          <span className="h-px flex-1 bg-border" />
          {t("auth.or")}
          <span className="h-px flex-1 bg-border" />
        </div>
      ) : null}
      <GoogleButton intent="login" available={googleAvailable} returnTo={redirectTo} />
      {/* Con el alta apagada NO hay enlace, ni gris ni con explicación: la
          ausencia se diseña (constitución §V). Quien no puede registrarse no
          tiene por qué enterarse de que existe un registro. */}
      {env().NEXUS_SIGNUP_ENABLED ? (
        // Spec 067 (owner, 2026-11-20): la pregunta en texto y solo
        // «Regístrate» como enlace, igual que «Iniciar sesión» en el alta.
        <p className="text-sm text-muted-foreground">
          {t("login.noAccount")}{" "}
          <Link href="/signup" className="font-medium text-foreground underline underline-offset-4">
            {t("login.signUp")}
          </Link>
        </p>
      ) : null}
    </section>
  );
}
