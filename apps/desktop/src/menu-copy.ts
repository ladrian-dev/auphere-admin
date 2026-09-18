/**
 * Los textos del menú de la aplicación — spec 010, Requisitos 1.7 y 12.2.
 *
 * El menú lo construye el **proceso principal**, que no tiene el catálogo de la
 * pantalla ni el del hilo. Hasta ahora eso se traducía en un menú a medias en
 * español («Ver», «Equipo», «Consola») dentro de una aplicación que podía estar
 * en inglés, junto a etiquetas que ponía Electron en el idioma del sistema.
 *
 * Módulo puro para que se pueda comprobar que las dos lenguas tienen las mismas
 * claves: lo que delata que nadie miró un menú es precisamente la entrada que
 * se quedó sin traducir.
 */

export type Lang = "es" | "en";

export type MenuCopy = {
  /** La orden de salir, y lo que se pregunta si hay trabajo vivo (R3.5). */
  quit: string;
  title: string;
  detail: string;
  cancel: string;
  about: string;
  settings: string;
  checkUpdates: string;
  /** Con `{version}` dentro: se sustituye por la que está lista (R6.2). */
  installUpdate: string;
  file: string;
  newTeammate: string;
  edit: string;
  view: string;
  today: string;
  pending: string;
  toggleSidebar: string;
  zoomReset: string;
  zoomIn: string;
  zoomOut: string;
  fullscreen: string;
  reload: string;
  window: string;
  help: string;
  releaseNotes: string;
  /** El aviso de prueba que dispara la autorización de macOS (R7.8). */
  notificationsProbe: string;
  /** El título del selector nativo de carpetas (R8.4). */
  pickDirectory: string;
};

const ES: MenuCopy = {
  quit: 'Salir de Auphere',
  title: 'Hay trabajo en marcha',
  detail: 'Si sales ahora, las decisiones que esperan se quedan sin tomar y las sesiones en vuelo se cortan. La ventana se puede cerrar sin salir.',
  cancel: 'No salir',
  about: "Acerca de Auphere",
  settings: "Ajustes…",
  checkUpdates: "Buscar actualizaciones",
  installUpdate: "Instalar la versión {version}…",
  file: "Archivo",
  newTeammate: "Nuevo teammate",
  edit: "Edición",
  view: "Ver",
  today: "Hoy",
  pending: "Pendientes",
  toggleSidebar: "Mostrar u ocultar la lista lateral",
  zoomReset: "Tamaño real",
  zoomIn: "Aumentar",
  zoomOut: "Reducir",
  fullscreen: "Pantalla completa",
  reload: "Recargar la sección",
  window: "Ventana",
  help: "Ayuda",
  releaseNotes: "Novedades de esta versión",
  notificationsProbe: "Los avisos están activados. Así te enterarás de lo que espera tu decisión.",
  pickDirectory: "Elige el directorio del cliente",
};

const EN: MenuCopy = {
  quit: 'Quit Auphere',
  title: 'There is work in progress',
  detail: 'If you quit now, the decisions waiting on you stay untaken and any running sessions are cut off. You can close the window without quitting.',
  cancel: "Don't quit",
  about: "About Auphere",
  settings: "Settings…",
  checkUpdates: "Check for updates",
  installUpdate: "Install version {version}…",
  file: "File",
  newTeammate: "New teammate",
  edit: "Edit",
  view: "View",
  today: "Today",
  pending: "Pending",
  toggleSidebar: "Show or hide the sidebar",
  zoomReset: "Actual size",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  fullscreen: "Full screen",
  reload: "Reload this section",
  window: "Window",
  help: "Help",
  releaseNotes: "What's new in this version",
  notificationsProbe: "Notifications are on. This is how you will hear about what waits on your decision.",
  pickDirectory: "Choose the client's directory",
};

export function menuCopy(lang: Lang): MenuCopy {
  return lang === "en" ? EN : ES;
}

/** Para el test: las dos lenguas, para poder compararlas. */
export const MENU_CATALOGUES: Record<Lang, MenuCopy> = { es: ES, en: EN };
