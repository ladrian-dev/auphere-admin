import { notFound, redirect } from "next/navigation";

import { getT } from "@/i18n/server";
import { consoleService } from "@/lib/backend";
import { env } from "@/lib/env";
import { resolvePrincipal } from "@/lib/principal";

import { GoogleButton } from "../google-button";

import { SignupForm } from "./signup-form";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("signup.title") };
}

/**
 * El primer acto del alta (spec 006, Requisito 1).
 *
 * **Con la bandera apagada esta página no existe: devuelve 404.** No hay un
 * formulario deshabilitado ni una pantalla que explique que el registro está
 * cerrado — la ausencia se diseña (constitución §V). Quien llegue por un
 * enlace viejo ve lo mismo que quien se inventa una URL.
 */
export default async function SignupPage() {
  if (!env().NEXUS_SIGNUP_ENABLED) notFound();
  // Con sesión viva no se enseña un alta: ya estás dentro.
  const resolution = await resolvePrincipal();
  if (resolution.kind !== "anonymous") redirect("/");
  const { t } = await getT();
  // Se resuelve **aquí, en el servidor**. Preguntarlo desde el navegador
  // costaba una llamada por visita y, cuando se preguntaba con `/start`, un
  // PKCE huérfano de diez minutos en Redis por cada carga de una página
  // pública.
  const googleAvailable = await consoleService.googleAvailable();
  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div className="flex min-w-0 flex-col gap-2">
        <h1 className="text-balance text-3xl font-semibold">{t("signup.title")}</h1>
        <p className="text-pretty text-muted-foreground">{t("signup.body")}</p>
      </div>
      <SignupForm />
      <GoogleButton intent="signup" available={googleAvailable} />
    </section>
  );
}
