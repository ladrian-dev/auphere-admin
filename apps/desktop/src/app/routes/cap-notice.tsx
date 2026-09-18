/**
 * El tope, dicho antes de rellenar nada — spec 010, Requisitos 9.1, 9.2 y 9.3.
 *
 * Lo que el anexo 04 anotó: «el tope del plan se descubre al enviar». Nombre,
 * oficio, cerebro, seis permisos y un interruptor — y entonces «tu plan admite
 * 0 teammates». Todo ese trabajo tirado, y la frase llega en el peor momento
 * posible: cuando ya habías decidido.
 *
 * Aquí el formulario **no se llega a ofrecer**. Se dice qué pasa, se lleva a
 * donde se resuelve —o se dice a quién pedírselo, si esta persona no puede
 * contratar— y se puede volver sin haber hecho nada.
 */
import { Button } from "@nexus/ui";

import { type Cap, type Destination, gateFor } from "../../gating";
import { type AppKey, useAppT } from "../i18n";

export function CapNotice({
  cap,
  permissions,
  onGo,
  onCancel,
}: {
  cap: Cap;
  permissions: readonly string[];
  onGo: (destination: Destination) => void;
  onCancel: () => void;
}) {
  const t = useAppT();
  const gate = gateFor(cap, permissions);

  return (
    <div className="m-auto flex max-w-prose flex-col items-center gap-4 p-8 text-center" role="status">
      <p className="text-ui text-pretty">{t(gate.clave as AppKey)}</p>
      <div className="flex flex-wrap justify-center gap-2">
        {gate.kind === "action" ? (
          <Button size="sm" onClick={() => onGo(gate.destination)}>
            {t(`plan.action.${cap}` as AppKey)}
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" onClick={onCancel}>
          {t("create.cancel")}
        </Button>
      </div>
    </div>
  );
}
