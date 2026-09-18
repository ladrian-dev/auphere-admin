/**
 * Bajar el ruido de los avisos — spec 010, Requisito 5.8.
 *
 * El canal existía desde la spec 003 y **no lo llamaba nadie**: la preferencia
 * estaba implementada en el puente y no existía para la persona, que es la
 * única forma en la que cuenta.
 *
 * Dos decisiones:
 *
 * * **un solo interruptor, y baja.** Si hubiera un «avísame de todo», el nivel
 *   `informativo` dejaría de significar nada y el crítico se perdería entre las
 *   notas — que es exactamente lo que la política de niveles evita;
 * * **dice qué sigue sonando.** Un interruptor llamado «silenciar» que deja
 *   pasar lo crítico sin decirlo es una promesa incumplida, aunque sea en la
 *   dirección buena: la primera vez que suene, nadie se lo vuelve a creer.
 */
import { useEffect, useState } from "react";

import { bridge } from "../bridge";
import { useAppT } from "../i18n";
import { PermissionSwitch } from "./new-teammate";

export function NotificationPrefs() {
  const t = useAppT();
  const [silenced, setSilenced] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    void bridge.notificationsPrefs().then((prefs) => {
      if (alive) setSilenced(prefs.silenceAviso);
    });
    return () => {
      alive = false;
    };
  }, []);

  if (silenced === null) return null;

  return (
    <section className="flex min-w-0 flex-col gap-2" aria-label={t("notifications.title")}>
      <h2 className="text-base font-semibold text-balance">{t("notifications.title")}</h2>
      <PermissionSwitch
        label={t("notifications.silence")}
        hint={t("notifications.silence.hint")}
        checked={silenced}
        /* Se pinta lo que respondió el guardado, no lo que se pulsó: pintar la
           intención sería afirmar algo que quizá no se guardó. */
        onToggle={() => {
          void bridge.notificationsPrefs({ silence_aviso: !silenced }).then((prefs) => setSilenced(prefs.silenceAviso));
        }}
      />
      <p className="max-w-prose text-xs text-pretty text-muted-foreground">{t("notifications.keeps")}</p>
    </section>
  );
}
