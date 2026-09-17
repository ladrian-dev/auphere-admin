/**
 * Las comodidades de ventana — spec 010, Requisitos 1.10 y 2.3.
 *
 * Tema, ancho de la lista lateral, última sección y ruido de avisos. Nada de
 * esto dice quién eres ni qué haces: son preferencias de una ventana, y la
 * lista de claves que la cáscara puede guardar en disco sigue siendo cerrada
 * (`shell-state.ts`).
 *
 * El tema merece una nota. Hasta ahora había **dos**: la pantalla y la barra
 * seguían al sistema operativo, y la consola tenía su propio selector con su
 * propia preferencia. Dentro de la misma ventana se podía tener la consola en
 * claro y todo lo demás en oscuro. Ahora decide la cáscara y arrastra a las
 * tres superficies; por eso esta preferencia vive aquí y no en la consola.
 */

export type Theme = "system" | "light" | "dark";

export type ShellPrefs = {
  theme: Theme;
  sidebarWidth: number;
  /** La última sección visitada, para volver a ella al reabrir (R1.10). */
  section: string;
  silenceAviso: boolean;
};

export const MIN_SIDEBAR_WIDTH = 220;
export const MAX_SIDEBAR_WIDTH = 320;

export const DEFAULT_SHELL_PREFS: ShellPrefs = {
  // «Sistema» por defecto: la guía de Apple desaconseja que una aplicación
  // imponga su propio tema, y quien quiera otra cosa puede decirlo.
  theme: "system",
  sidebarWidth: MIN_SIDEBAR_WIDTH,
  section: "hoy",
  silenceAviso: false,
};

const isTheme = (value: unknown): value is Theme => value === "system" || value === "light" || value === "dark";

/**
 * Lee lo guardado sin fiarse: un fichero de preferencias puede venir de una
 * versión anterior, estar a medias o haberse editado a mano. Lo que no se
 * entiende vuelve a su valor por defecto en vez de tumbar el arranque.
 */
export function normaliseShellPrefs(saved: unknown): ShellPrefs {
  if (!saved || typeof saved !== "object") return { ...DEFAULT_SHELL_PREFS };
  const raw = saved as Partial<Record<keyof ShellPrefs, unknown>>;

  const width = typeof raw.sidebarWidth === "number" && Number.isFinite(raw.sidebarWidth) ? Math.round(raw.sidebarWidth) : DEFAULT_SHELL_PREFS.sidebarWidth;

  return {
    theme: isTheme(raw.theme) ? raw.theme : DEFAULT_SHELL_PREFS.theme,
    // Cero es válido: es la lista lateral colapsada. Por encima del máximo o
    // por debajo del mínimo se acota, que es lo mismo que hace el armazón.
    sidebarWidth: width === 0 ? 0 : Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, width)),
    section: typeof raw.section === "string" ? raw.section : DEFAULT_SHELL_PREFS.section,
    silenceAviso: raw.silenceAviso === true,
  };
}

/** Aplica un cambio parcial sobre lo que había, normalizando el resultado. */
export function mergeShellPrefs(previous: ShellPrefs, next: Partial<ShellPrefs>): ShellPrefs {
  return normaliseShellPrefs({ ...previous, ...next });
}
