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
  about: string;
  settings: string;
  checkUpdates: string;
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
};

const ES: MenuCopy = {
  about: "Acerca de Auphere",
  settings: "Ajustes…",
  checkUpdates: "Buscar actualizaciones",
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
};

const EN: MenuCopy = {
  about: "About Auphere",
  settings: "Settings…",
  checkUpdates: "Check for updates",
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
};

export function menuCopy(lang: Lang): MenuCopy {
  return lang === "en" ? EN : ES;
}

/** Para el test: las dos lenguas, para poder compararlas. */
export const MENU_CATALOGUES: Record<Lang, MenuCopy> = { es: ES, en: EN };
