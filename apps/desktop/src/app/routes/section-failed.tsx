/**
 * Una sección de administrar que no cargó — spec 010, Requisito 4.1.
 *
 * Las secciones de administrar las pinta la consola **dentro del panel**. Con
 * la red caída, o con la consola devolviendo un error, lo que aparecía en ese
 * hueco era la página de error de Chromium: en inglés, con el aspecto de un
 * navegador roto dentro de una aplicación de escritorio, y sin nada que pulsar.
 *
 * Aquí se dice en la lengua de la aplicación, se nombra **qué** sección falló
 * —«no se pudo cargar» a secas no deja saber si falló lo que pediste o todo— y
 * se ofrece la única salida que hay. Sin rojo: que una sección no cargue no es
 * una avería de quien la abrió.
 */
import { Button } from "@nexus/ui";

import type { Section } from "../../sections";
import { type AppKey, useAppT } from "../i18n";

export function SectionFailed({ section, onRetry }: { section: Section; onRetry: () => void }) {
  const t = useAppT();
  return (
    <div className="m-auto flex max-w-prose flex-col items-center gap-3 p-8 text-center" role="status">
      <p className="text-ui text-pretty">
        {t("section.failed", { name: t(`shell.section.${section}` as AppKey) })}
      </p>
      <p className="text-ui text-pretty text-muted-foreground">{t("section.failed.keeps")}</p>
      <Button size="sm" onClick={onRetry}>
        {t("roster.retry")}
      </Button>
    </div>
  );
}
