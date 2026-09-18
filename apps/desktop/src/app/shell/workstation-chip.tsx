/**
 * El estado de la máquina, en la franja — spec 010, Requisitos 3.6 y 3.7.
 *
 * Esto es lo que sustituye a la barra de 44 px: el estado se ve **sin abrir
 * nada**, y con lo que hacía falta para no quedarse mirándolo.
 *
 * La sesión del 2026-09-17 dejó el caso que lo justifica: la barra pasó horas
 * diciendo `reconectando` sin decir de qué se reconectaba ni desde cuándo,
 * mientras la consola daba la máquina por emparejada. Las dos cosas eran
 * ciertas —emparejada no es conectada— y ninguna de las dos se entendía.
 */
import type { WorkstationView } from "../bridge";
import { useAppT } from "../i18n";

/** Cuánto hace, dicho como lo diría una persona. */
function ago(since: string | undefined, locale: string): string | null {
  if (!since) return null;
  const ms = Date.now() - new Date(since).getTime();
  if (Number.isNaN(ms) || ms < 0) return null;
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return null;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (minutes < 60) return rtf.format(-minutes, "minute");
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? rtf.format(-hours, "hour") : rtf.format(-Math.floor(hours / 24), "day");
}

export function WorkstationChip({
  state,
  announce = false,
}: {
  state: WorkstationView | null;
  /**
   * Si esto es lo que anuncia el estado de la máquina — spec 010, R5.7.
   *
   * El mismo estado se pinta al pie de la lista lateral **y** en Hoy. Con los
   * dos declarados como región viva, quien usa lector de pantalla oía
   * «MacBook de Luis · reconectando» dos veces seguidas. Anuncia el pie, que
   * es el que siempre está; Hoy lo pinta y calla.
   */
  announce?: boolean;
}) {
  const t = useAppT();
  if (!state) return null;

  const desde = ago(state.since, t("locale.tag"));
  // La causa sólo se dice cuando se sabe: inventarla sería peor que callar (§V).
  const causa = state.cause ? t(`workstation.cause.${state.cause}`) : null;

  return (
    <span
      className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground"
      {...(announce ? { role: "status" as const } : {})}
      data-workstation={state.status}
    >
      <span
        aria-hidden="true"
        className={`size-2 shrink-0 rounded-full ${state.status === "conectada" ? "bg-primary" : "bg-muted-foreground"}`}
      />
      <span className="truncate">
        {state.machine_name ? `${state.machine_name} · ` : ""}
        {t(`workstation.bar.${state.status}`)}
        {causa ? ` · ${causa}` : ""}
        {desde ? ` · ${desde}` : ""}
      </span>
    </span>
  );
}
