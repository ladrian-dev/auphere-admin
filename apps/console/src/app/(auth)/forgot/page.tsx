import { redirect } from "next/navigation";

import { getT } from "@/i18n/server";
import { resolvePrincipal } from "@/lib/principal";

import { ForgotForm } from "./forgot-form";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("forgot.title") };
}

/**
 * Pedir el enlace para recuperar la cuenta — spec 011, Requisito 1.
 *
 * **Esta página existe siempre**, a diferencia del alta: no hay bandera que la
 * apague, porque la capacidad que retira es un procedimiento manual con acceso
 * a producción y no un botón de producto.
 *
 * Con sesión viva no se enseña: quien ya está dentro no ha olvidado nada, y
 * cambiar la contraseña estando dentro es otra pantalla y otro flujo — está
 * declarado fuera de alcance en la spec.
 */
export default async function ForgotPage() {
  const resolution = await resolvePrincipal();
  if (resolution.kind !== "anonymous") redirect("/");
  const { t } = await getT();
  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div className="flex min-w-0 flex-col gap-2">
        <h1 className="text-balance text-3xl font-semibold">{t("forgot.title")}</h1>
        <p className="text-pretty text-muted-foreground">{t("forgot.body")}</p>
      </div>
      <ForgotForm />
    </section>
  );
}
