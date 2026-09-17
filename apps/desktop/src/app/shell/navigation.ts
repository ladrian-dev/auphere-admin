/**
 * La navegación del armazón — spec 010, Requisitos 1.6 y 1.10.
 *
 * No entra un enrutador: son doce pantallas y lo que hace falta no es un
 * enrutador, es una **ruta canónica**. Con ella, cuatro cosas hablan el mismo
 * idioma —la lista lateral, el historial de atrás y adelante, la búsqueda de
 * acciones y lo que se restaura al reabrir— en vez de cada una con su propio
 * concepto de «dónde estoy».
 *
 * Módulo puro y con test: el historial es de las cosas que parecen triviales y
 * se comportan mal en los bordes (volver atrás hasta el principio, ir a donde
 * ya estás, avanzar después de ramificar).
 */
import { isSection, type Section } from "../../sections";

export type History = {
  /** Las secciones visitadas, la actual incluida. */
  entries: readonly Section[];
  /** Dónde está el cursor dentro de `entries`. */
  index: number;
};

export const initialHistory = (section: Section = "hoy"): History => ({ entries: [section], index: 0 });

export const current = (history: History): Section => history.entries[history.index] ?? "hoy";

export const canGoBack = (history: History): boolean => history.index > 0;
export const canGoForward = (history: History): boolean => history.index < history.entries.length - 1;

/**
 * Ir a una sección.
 *
 * Ir a donde ya estás **no** añade una entrada: si lo hiciera, «atrás» se
 * convertiría en «quedarse», que es de las cosas que hacen dudar de si el botón
 * funciona. Y navegar después de haber ido hacia atrás **corta** lo que había
 * delante, como en cualquier navegador.
 */
export function go(history: History, section: Section): History {
  if (current(history) === section) return history;
  const entries = [...history.entries.slice(0, history.index + 1), section];
  return { entries, index: entries.length - 1 };
}

export function back(history: History): History {
  return canGoBack(history) ? { ...history, index: history.index - 1 } : history;
}

export function forward(history: History): History {
  return canGoForward(history) ? { ...history, index: history.index + 1 } : history;
}

/**
 * La sección con la que se abre la aplicación.
 *
 * Se restaura la última visitada (R1.10). Dos salvaguardas: lo que no está en
 * la lista canónica se ignora —una preferencia vieja no puede llevar a una
 * sección que ya no existe— y la primera vez se empieza en «Hoy».
 */
export function restoredSection(saved: unknown): Section {
  return isSection(saved) ? saved : "hoy";
}
