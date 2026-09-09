/**
 * El estado del puente, con sitio donde vivir — Requisitos 15.4 y 4.3.
 *
 * `OutboundBridge` ya calculaba `reconectando`, pero no había pantalla que lo
 * mostrara: por eso T050 quedó a medias. Esto le da su sitio y, sobre todo, lo ata
 * a la consecuencia que importa.
 *
 * **Ningún estado del puente es un error.** Perder la conexión en un portátil es
 * lo normal —se cierra la tapa, cambia el wifi—; pintarlo en rojo enseña a la
 * gente a ignorar los rojos, que es peor que no avisar.
 *
 * **Y hacen falta las dos cosas.** Puente y dispositivo: un catálogo que ofrece
 * herramientas locales sin puente invita al agente a afirmar resultados de
 * comandos que nunca corrieron, que es justo lo que §V prohíbe.
 */
import type { LinkState } from "./bridge.js";
import type { Presence } from "./presence.js";

export type StatusTone = "estado" | "error";

export type StatusLabel = {
  /** Clave de i18n. La cáscara no incrusta copy: lo traduce como la consola. */
  key: string;
  tone: StatusTone;
};

export function statusLabel(link: LinkState): StatusLabel {
  switch (link) {
    case "conectando":
      return { key: "workstation.link.connecting", tone: "estado" };
    case "reconectando":
      return { key: "workstation.link.reconnecting", tone: "estado" };
    case "conectado":
      return { key: "workstation.link.connected", tone: "estado" };
  }
}

/** Las herramientas locales necesitan puente **y** dispositivo. */
export function localToolsAvailable(link: LinkState, presence: Presence): boolean {
  return link === "conectado" && presence === "presente";
}
