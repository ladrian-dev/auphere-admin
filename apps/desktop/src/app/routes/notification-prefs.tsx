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

import { Button } from "@nexus/ui";

import { losesWhenDenied, type PermissionState } from "../../permissions";
import { bridge } from "../bridge";
import { type AppKey, useAppT } from "../i18n";
import { PermissionSwitch } from "./new-teammate";

export function NotificationPrefs() {
  const t = useAppT();
  const [silenced, setSilenced] = useState<boolean | null>(null);
  const [permission, setPermission] = useState<PermissionState>("desconocido");

  useEffect(() => {
    let alive = true;
    void bridge.notificationsPrefs().then((prefs) => {
      if (!alive) return;
      setSilenced(prefs.silenceAviso);
      setPermission(prefs.permission);
    });
    return () => {
      alive = false;
    };
  }, []);

  if (silenced === null) return null;

  const denegado = losesWhenDenied("notifications");

  return (
    <section className="flex min-w-0 flex-col gap-2" aria-label={t("notifications.title")}>
      <h2 className="text-base font-semibold text-balance">{t("notifications.title")}</h2>

      {/*
        R7.8 — se pide **al usarlo**, con su porqué delante. Pedir permisos al
        arrancar, de golpe y sin contexto, es la razón por la que la gente los
        deniega: nadie concede acceso a algo que todavía no sabe para qué es.
      */}
      {permission === "desconocido" ? (
        <div className="flex max-w-prose flex-col items-start gap-2 rounded-md border border-border p-3">
          <p className="text-ui text-pretty text-muted-foreground">{t("permission.notifications.why")}</p>
          <Button
            size="sm"
            onClick={() => void bridge.notificationsPrefs({ ask: true }).then((p) => setPermission(p.permission))}
          >
            {t("permission.notifications.ask")}
          </Button>
        </div>
      ) : null}

      {/*
        R7.10 — denegado dice **qué deja de funcionar**, qué sigue funcionando
        —que es casi todo, y sin eso denegar parece haber roto la aplicación— y
        lleva al panel concreto de Ajustes, no a «busca en Ajustes».
      */}
      {permission === "denegado" ? (
        <div className="flex max-w-prose flex-col items-start gap-2 rounded-md border border-border p-3">
          <p className="text-ui text-pretty">{t(denegado.loses as AppKey)}</p>
          <p className="text-ui text-pretty text-muted-foreground">{t(denegado.keeps as AppKey)}</p>
          <Button size="sm" variant="outline" onClick={() => void bridge.openNotificationSettings()}>
            {t("permission.notifications.settings")}
          </Button>
        </div>
      ) : null}

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
