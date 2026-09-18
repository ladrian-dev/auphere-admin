/**
 * Esperando a que termines en el navegador — spec 010, Requisito 9.4.
 *
 * «Elegir plan» y «Comprar saldo» salían al navegador **sin decir nada**: la
 * ventana se quedaba exactamente igual mientras el pago ocurría detrás, y quien
 * volvía no tenía forma de saber si había pulsado bien.
 *
 * Las mismas tres salidas que la entrada, y por la misma razón: es el mismo
 * hecho —algo pasa fuera de la ventana y hay que volver— y darle dos formas
 * distintas es cómo se acaban pintando dos esperas que no se parecen.
 */
import { Button } from "@nexus/ui";

import type { HandoffView } from "../bridge";
import { type AppKey, useAppT } from "../i18n";

export function HandoffBanner({
  handoff,
  onDismiss,
}: {
  handoff: HandoffView | null;
  onDismiss: () => void;
}) {
  const t = useAppT();
  // Sólo mientras se espera. Al volver lo dice el propio plan, ya releído.
  if (!handoff || handoff.state !== "esperando" || handoff.kind === null) return null;

  return (
    <div data-handoff={handoff.kind} className="flex items-center gap-3 border-b border-border bg-muted px-4 py-2">
      <p className="min-w-0 flex-1 text-ui text-pretty text-muted-foreground">
        {t(`handoff.${handoff.kind}` as AppKey)}
      </p>
      {handoff.url ? (
        <Button size="sm" variant="outline" onClick={() => window.open(handoff.url, "_blank")}>
          {t("handoff.reopen")}
        </Button>
      ) : null}
      <Button size="sm" variant="ghost" onClick={onDismiss}>
        {t("handoff.cancel")}
      </Button>
    </div>
  );
}
