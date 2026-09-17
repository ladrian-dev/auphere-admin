/**
 * El hilo que no se pudo abrir — spec 010, Requisito 4.2.
 *
 * Uno de los cinco P0, y el más dañino de los silenciosos: hasta ahora un fallo
 * al abrir el hilo se pintaba como «tu hilo con Sofía está vacío». Una frase
 * tranquilizadora encima de algo roto enseña a no creerse la pantalla, y §V
 * existe justo para eso.
 *
 * Tres decisiones:
 *
 * * **se nombra el fallo**, sin adornos;
 * * **se dice que el trabajo sigue**: lo que falló es leer la conversación, no
 *   lo que el teammate estuviera haciendo, que corre en el servidor;
 * * **el código crudo no se pinta**, pero existe: se puede copiar para soporte.
 */
import { useState } from "react";

import { Button } from "@nexus/ui";

import { useAppT } from "../i18n";

export function ThreadOpenError({
  name,
  onRetry,
  detail,
}: {
  name: string;
  onRetry: () => void;
  /** Lo que diría un log. Nunca se pinta; se copia. */
  detail?: string;
}) {
  const t = useAppT();
  const [copiado, setCopiado] = useState(false);

  return (
    <div className="m-auto flex max-w-prose flex-col items-center gap-3 p-8 text-center" role="status">
      <p className="text-ui text-pretty">{t("thread.open.error", { name })}</p>
      <p className="text-ui text-pretty text-muted-foreground">{t("thread.open.error.keeps")}</p>
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={onRetry}>
          {t("roster.retry")}
        </Button>
        {detail ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              void navigator.clipboard?.writeText(detail);
              setCopiado(true);
            }}
          >
            {copiado ? t("thread.open.error.copied") : t("thread.open.error.detail")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
