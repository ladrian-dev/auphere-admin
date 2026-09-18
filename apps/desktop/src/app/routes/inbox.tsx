/**
 * Pendientes — lo que tus teammates esperan de ti (spec 003, Requisito 5).
 *
 * Cinco estados: cargando, vacío (que explica **cuándo** aparece algo y que
 * nada se ejecuta antes), error con reintento, parcial —una tarjeta que este
 * rol no puede decidir se muestra y lo dice— e ideal. Decidir aquí quita la
 * tarjeta del hilo, y al revés, sin recargar.
 *
 * Spec 010 (R4.1): el **segundo** parcial, el que faltaba. Cuando la lista ya
 * estaba y el refresco falla, la pantalla se quedaba con la vieja sin decir
 * nada — y decidir sobre una tarjeta que quizá ya no existe es peor que ver un
 * error. Ahora lo dice y deja volver a intentarlo, sin borrar lo que hay: el
 * aviso acota el alcance de lo que se ve, no lo sustituye.
 */
import { Badge, Button, Skeleton } from "@nexus/ui";
import { useCallback, useEffect, useRef, useState } from "react";

import { type InboxItem, type Level, bridge } from "../bridge";
import { InlineNotice, useFeedback } from "../feedback/provider";
import { useAppT } from "../i18n";

/** El nivel se pinta con las variantes del sistema; ningún color suelto. */
const VARIANT: Record<Level, "destructive" | "secondary" | "outline"> = {
  critico: "destructive",
  aviso: "secondary",
  informativo: "outline",
};

type Props = { onOpenThread: (teammateId: string) => void; focus: string | null };

/** Un aviso por tarjeta: el fallo va **donde estaba el botón** (R5.2). */
const slotOf = (actionId: string) => `inbox.decide:${actionId}`;

/** Cuánto lleva esperando, dicho como lo diría una persona (R10.1). */
function ago(iso: string, locale: string): string | null {
  const ms = Date.now() - Date.parse(iso);
  if (Number.isNaN(ms) || ms < 60_000) return null;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return rtf.format(-minutes, "minute");
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? rtf.format(-hours, "hour") : rtf.format(-Math.floor(hours / 24), "day");
}

export function Inbox({ onOpenThread, focus }: Props) {
  const t = useAppT();
  const { notify, clear } = useFeedback();
  /*
   * R10.4 — al llegar desde un aviso, la tarjeta **recibe el foco**, no sólo se
   * colorea el borde: quien navega con teclado o lector de pantalla se
   * encontraba al principio de la lista sin saber cuál era la suya.
   */
  const focused = useRef<HTMLLIElement | null>(null);
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [deciding, setDeciding] = useState<string | null>(null);

  /*
   * R10.4 — al llegar desde un aviso, la tarjeta **recibe el foco**, no sólo se
   * colorea el borde: quien navega con teclado o lector de pantalla se
   * encontraba al principio de la lista sin saber cuál era la suya. Depende de
   * `items` porque la lista llega después que el foco pedido.
   */
  useEffect(() => {
    if (focus) focused.current?.focus();
  }, [focus, items]);

  const load = useCallback(async () => {
    const res = await bridge.inboxList();
    if (!res.ok) {
      setFailed(true);
      return;
    }
    setFailed(false);
    setItems(res.data);
  }, []);

  useEffect(() => {
    void load();
    // El principal empuja la lista entera cada vez que reconcilia: la pantalla
    // no sondea y no se queda con una tarjeta que ya se decidió en otro sitio.
    return bridge.on("app:inbox", (list) => {
      setFailed(false);
      setItems(list);
    });
  }, [load]);

  /*
   * Spec 010 R5.3 — decidir dejó de fallar en silencio.
   *
   * Esto era `await bridge.inboxDecide(...)` y nada más: con un 409 —alguien
   * decidió antes en otra superficie— o con la red caída, el botón se
   * reactivaba y la tarjeta seguía ahí. Indistinguible de no haber pulsado.
   */
  const decide = async (item: InboxItem, decision: "confirm" | "cancel") => {
    if (!item.run_id) return;
    setDeciding(item.action_id);
    clear(slotOf(item.action_id));
    const res = await bridge.inboxDecide({ action_id: item.action_id, run_id: item.run_id, decision });
    setDeciding(null);
    // El éxito no se anuncia: la tarjeta se va, y eso ya es la señal.
    if (res.ok) return;
    notify({
      severidad: "error",
      alcance: "elemento",
      urgencia: "diferible",
      slot: slotOf(item.action_id),
      clave: res.code === "conflict" ? "feedback.decide.conflict" : "feedback.decide.failed",
    });
  };

  if (failed && items === null) {
    return (
      <section className="flex flex-col gap-2 p-4" aria-label={t("inbox.title")} role="status">
        <p className="text-sm text-pretty text-muted-foreground">{t("inbox.error")}</p>
        <Button variant="outline" size="sm" onClick={() => void load()}>
          {t("roster.retry")}
        </Button>
      </section>
    );
  }

  if (items === null) {
    return (
      <section className="flex flex-col gap-3 p-4" aria-busy="true" aria-label={t("inbox.title")}>
        {[0, 1].map((i) => (
          <Skeleton key={i} className="h-24 w-full rounded-md" />
        ))}
      </section>
    );
  }

  if (items.length === 0) {
    return (
      <section className="mx-auto max-w-prose p-8 text-center" aria-label={t("inbox.title")}>
        <p className="text-sm font-medium text-balance">{t("inbox.empty.title")}</p>
        <p className="mt-2 text-sm text-pretty text-muted-foreground">{t("inbox.empty.body")}</p>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-3 p-4" aria-label={t("inbox.title")}>
      <div className="flex min-w-0 items-center gap-2">
        <h2 className="min-w-0 flex-1 text-sm font-semibold text-balance">{t("inbox.title")}</h2>
        <Button variant="ghost" size="sm" onClick={() => void load()}>
          {t("inbox.refresh")}
        </Button>
      </div>
      {failed ? (
        <p role="status" className="rounded-md bg-muted p-3 text-xs text-pretty text-muted-foreground">
          {t("inbox.stale")}
        </p>
      ) : null}
      <ul className="flex flex-col gap-3">
        {items.map((item) => (
          <li
            key={item.action_id}
            ref={focus === item.action_id ? focused : undefined}
            tabIndex={focus === item.action_id ? -1 : undefined}
            data-level={item.level}
            aria-current={focus === item.action_id ? "true" : undefined}
            className="flex min-w-0 flex-col gap-2 rounded-md border border-border p-3 aria-[current=true]:border-primary"
          >
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <Badge variant={VARIANT[item.level]}>{t(`level.${item.level}`)}</Badge>
              <span className="min-w-0 truncate text-sm font-medium" title={item.title}>
                {item.title}
              </span>
            </div>
            {/*
              R10.1 — qué se hará, sobre qué cliente y máquina, desde cuándo
              espera, y si tiene vuelta atrás. Antes sólo estaban el nivel, el
              título y el teammate: decidir así es decidir por el título.
              Lo que no consta **no se pinta**; no se inventa nada.
            */}
            <p className="min-w-0 text-xs text-pretty text-muted-foreground">
              {[
                item.teammate.name,
                item.client_ref,
                item.machine,
                ago(item.proposed_at, t("locale.tag")),
                item.reversible === null || item.reversible === undefined
                  ? null
                  : t(item.reversible ? "inbox.reversible" : "inbox.irreversible"),
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>

            {/* R10.7 — quién decidió y qué, para poder verlo después. */}
            {item.decided ? (
              <p className="min-w-0 text-xs text-pretty text-muted-foreground">
                {t(`inbox.decided.${item.decided.decision}`, { by: item.decided.by ?? t("inbox.decided.someone") })}
              </p>
            ) : null}
            {item.decided ? null : item.can_decide ? (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" disabled={deciding === item.action_id} onClick={() => void decide(item, "confirm")}>
                  {t("inbox.approve")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={deciding === item.action_id}
                  onClick={() => void decide(item, "cancel")}
                >
                  {t("inbox.reject")}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onOpenThread(item.teammate.id)}>
                  {t("inbox.openThread")}
                </Button>
              </div>
            ) : (
              /*
               * R10.6 — el callejón del anexo 04: sin permiso salía sólo «tu rol
               * no puede decidir esto» y **desaparecía también «Ver el hilo»**.
               * Ni decides ni puedes leer de qué va.
               */
              <div className="flex flex-wrap items-center gap-2">
                <p className="min-w-0 flex-1 text-xs text-pretty text-muted-foreground" role="note">
                  {t("inbox.cannotDecide")}
                </p>
                <Button size="sm" variant="ghost" onClick={() => onOpenThread(item.teammate.id)}>
                  {t("inbox.openThread")}
                </Button>
              </div>
            )}
            <InlineNotice slot={slotOf(item.action_id)} />
          </li>
        ))}
      </ul>
    </section>
  );
}
