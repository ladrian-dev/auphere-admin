import { EmptyState } from "@nexus/ui";

import { getT } from "@/i18n/server";

import { ResetForm } from "./reset-form";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("reset.title") };
}

/**
 * Elegir la contraseña nueva — spec 011, Requisitos 2 y 3.
 *
 * **No se le pregunta a la API si el enlace vale antes de pintar el
 * formulario**, y es deliberado: una ruta que conteste «este enlace existe» es
 * una ruta a la que se le puede preguntar por enlaces. El enlace se comprueba
 * al canjearlo, que es cuando hace falta, y los tres casos muertos
 * —inexistente, caducado y ya usado— dan la misma pantalla.
 *
 * Lo único que se mira aquí es la **forma** del token, que no consulta nada.
 */
export default async function ResetPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const { t } = await getT();
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(token)) {
    return <EmptyState title={t("reset.deadLink")} description={t("reset.deadLink.body")} readonly />;
  }
  return (
    <section className="flex min-w-0 flex-col gap-6">
      <h1 className="text-balance text-3xl font-semibold">{t("reset.title")}</h1>
      <ResetForm token={token} />
    </section>
  );
}
