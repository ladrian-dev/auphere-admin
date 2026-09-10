/**
 * Pendientes — lo que tus teammates esperan de ti (spec 003, Requisito 5).
 *
 * Cinco estados: cargando, vacío (que explica **cuándo** aparece algo y que
 * nada se ejecuta antes), error con reintento, parcial —una tarjeta que este
 * rol no puede decidir se muestra y lo dice— e ideal. Decidir aquí quita la
 * tarjeta del hilo, y al revés, sin recargar.
 */
import { Badge, Button, Skeleton } from "@nexus/ui";
import { useCallback, useEffect, useState } from "react";

import { type InboxItem, type Level, bridge } from "../bridge";
import { useAppT } from "../i18n";

/** El nivel se pinta con las variantes del sistema; ningún color suelto. */
const VARIANT: Record<Level, "destructive" | "secondary" | "outline"> = {
  critico: "destructive",
  aviso: "secondary",
  informativo: "outline",
};

type Props = { onOpenThread: (teammateId: string) => void; focus: string | null };

export function Inbox({ onOpenThread, focus }: Props) {
  const t = useAppT();
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [deciding, setDeciding] = useState<string | null>(null);

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

  const decide = async (item: InboxItem, decision: "confirm" | "cancel") => {
    if (!item.run_id) return;
    setDeciding(item.action_id);
    await bridge.inboxDecide({ action_id: item.action_id, run_id: item.run_id, decision });
    setDeciding(null);
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
      <h2 className="text-sm font-semibold text-balance">{t("inbox.title")}</h2>
      <ul className="flex flex-col gap-3">
        {items.map((item) => (
          <li
            key={item.action_id}
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
            <p className="min-w-0 text-xs text-pretty text-muted-foreground">
              {item.teammate.name}
              {item.client_ref ? ` · ${item.client_ref}` : ""}
            </p>
            {item.can_decide ? (
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
              <p className="text-xs text-pretty text-muted-foreground" role="note">
                {t("inbox.cannotDecide")}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
