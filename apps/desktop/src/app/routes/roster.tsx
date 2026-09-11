/** El roster (R1): oficio, modelo, estado derivado y `unread`. Cinco estados de Hurff. */
import { Button, Skeleton, StatusDot } from "@nexus/ui";

import type { Teammate } from "../bridge";
import { useAppT } from "../i18n";

type Props = {
  items: Teammate[];
  status: "loading" | "ready" | "error" | "forbidden";
  selected: string | null;
  onSelect: (id: string) => void;
  onRetry: () => void;
  onCreate: () => void;
};

const TONE: Record<Teammate["my_state"], "positive" | "warning" | "muted" | "info"> = {
  en_marcha: "info",
  esperandote: "warning",
  en_pausa_por_tope: "muted",
  en_espera: "muted",
};

export function Roster({ items, status, selected, onSelect, onRetry, onCreate }: Props) {
  const t = useAppT();
  return (
    <nav className="flex min-w-0 flex-col gap-2 p-3" aria-label={t("app.title")}>
      <div className="flex min-w-0 items-center gap-2 px-2">
        <h1 className="min-w-0 flex-1 text-sm font-semibold text-balance">{t("app.title")}</h1>
        {/* Crear no puede vivir solo en el estado vacío: con el equipo lleno
            seguiría haciendo falta, y no habría dónde pulsarlo (R2.1). */}
        {status === "ready" ? (
          <button
            type="button"
            onClick={onCreate}
            title={t("roster.create")}
            aria-label={t("roster.create")}
            className="inline-flex size-7 items-center justify-center rounded-md text-lg leading-none text-muted-foreground transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            +
          </button>
        ) : null}
      </div>
      {status === "loading" ? (
        <ul className="flex flex-col gap-2" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <li key={i} className="flex items-center gap-3 px-2 py-2">
              <Skeleton className="size-8 rounded-full" />
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-3 w-32" />
              </div>
            </li>
          ))}
        </ul>
      ) : status === "error" ? (
        <div className="flex flex-col gap-2 px-2 py-4" role="status">
          <p className="text-sm text-pretty text-muted-foreground">{t("roster.error")}</p>
          <Button variant="outline" size="sm" onClick={onRetry}>
            {t("roster.retry")}
          </Button>
        </div>
      ) : status === "forbidden" ? (
        <p className="px-2 py-4 text-sm text-pretty text-muted-foreground" role="status">
          {t("roster.forbidden")}
        </p>
      ) : items.length === 0 ? (
        <div className="flex flex-col gap-3 px-2 py-4">
          <p className="text-sm font-medium text-balance">{t("roster.empty.title")}</p>
          <p className="text-sm text-pretty text-muted-foreground">{t("roster.empty.body")}</p>
          <Button size="sm" onClick={onCreate}>
            {t("roster.create")}
          </Button>
        </div>
      ) : (
        <ul className="flex flex-col gap-1">
          {items.map((tm) => (
            <li key={tm.id}>
              <button
                type="button"
                aria-current={selected === tm.id ? "true" : undefined}
                onClick={() => onSelect(tm.id)}
                className="flex w-full min-w-0 items-center gap-3 rounded-md px-2 py-2 text-left hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none aria-[current=true]:bg-muted"
              >
                <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary">
                  {tm.name.slice(0, 1)}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-medium" title={tm.name}>
                      {tm.name}
                    </span>
                    {tm.my_unread ? (
                      <span role="img" className="size-2 shrink-0 rounded-full bg-primary" aria-label={t("state.unread")} />
                    ) : null}
                  </span>
                  <span className="truncate text-xs text-muted-foreground" title={tm.job}>
                    {tm.job}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                  <StatusDot tone={TONE[tm.my_state]} />
                  <span className="sr-only">{t(`state.${tm.my_state}`)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}
