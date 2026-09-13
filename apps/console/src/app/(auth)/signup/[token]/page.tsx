import { notFound } from "next/navigation";
import { EmptyState } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { env } from "@/lib/env";
import { consoleService } from "@/lib/backend";

import { FinishForm } from "./finish-form";

export const metadata = { title: "Crea tu cuenta" };

/**
 * El segundo acto (Requisitos 2.1 y 3).
 *
 * **Los cuatro enlaces muertos —inexistente, caducado, usado, sustituido—
 * pintan lo mismo**, porque la API devuelve lo mismo para los cuatro. Si esta
 * pantalla los distinguiera, volvería a abrir el oráculo por el otro lado.
 *
 * Y aquí es donde se retoma quien verificó su correo y no llegó a nombrar la
 * empresa (3.6): mientras la solicitud siga viva, este enlace vuelve a traerlo
 * exactamente a este punto, sin empezar de cero.
 */
export default async function SignupTokenPage({ params }: { params: Promise<{ token: string }> }) {
  if (!env().NEXUS_SIGNUP_ENABLED) notFound();
  const { token } = await params;
  const { t } = await getT("es");
  const valid = /^[A-Za-z0-9_-]{16,128}$/.test(token);
  const signup = valid ? await consoleService.lookupSignup(token) : null;
  if (!signup) {
    return (
      <EmptyState title={t("signup.invalidLink")} description={t("signup.invalidLink.body")} readonly />
    );
  }
  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div className="flex min-w-0 flex-col gap-2">
        <h1 className="text-balance text-3xl font-semibold">{t("signup.finish.title")}</h1>
        <p className="text-pretty text-muted-foreground">{t("signup.finish.body")}</p>
      </div>
      <FinishForm token={token} email={signup.email} />
    </section>
  );
}
