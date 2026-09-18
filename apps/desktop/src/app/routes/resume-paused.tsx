/**
 * Lo que quedó en pausa por consumo — spec 010, Requisito 9.11.
 *
 * Dos frases y una acción, y la elección entre las dos la hace la causa: con el
 * pool de vuelta se reanuda, y con el pool todavía agotado lo que se ofrece es
 * lo que lo resuelve. Un botón «Reanudar» con el tope en pie devolvería el
 * mismo 409 — un fallo mudo con un botón delante.
 *
 * Se dice **«sigue donde se quedó»** porque es la duda real: nadie reanuda algo
 * si sospecha que va a empezar de cero y gastar otra vez.
 */
import { Button } from "@nexus/ui";

import { useAppT } from "../i18n";

export function ResumePaused({
  count,
  capped,
  onResume,
  onBuy,
}: {
  count: number;
  /** La causa sigue en pie. */
  capped: boolean;
  onResume: () => void;
  onBuy: () => void;
}) {
  const t = useAppT();
  if (count === 0) return null;

  return (
    <div role="status" className="flex max-w-prose flex-col items-start gap-2 rounded-md border border-border p-3">
      <p className="text-ui text-pretty">
        {capped ? t("resume.capped", { count }) : t("resume.ready", { count })}
      </p>
      {capped ? (
        <Button size="sm" onClick={onBuy}>
          {t("plan.action.pool_agotado")}
        </Button>
      ) : (
        <Button size="sm" onClick={onResume}>
          {t("resume.action")}
        </Button>
      )}
    </div>
  );
}
