/**
 * La taxonomía de avisos — spec 010, Requisito 5.
 *
 * **El mecanismo no se elige en la llamada.** Quien avisa describe *qué* pasa
 * —gravedad, a qué alcanza, si hay que atenderlo ya— y esta función decide
 * *cómo* se comunica. Así la elección deja de tomarse componente a componente,
 * que es de donde salían las siete formas distintas de decir lo mismo.
 *
 * La tabla completa está en `contracts/feedback-taxonomia.md`. Las reglas duras,
 * que son las que este módulo existe para hacer imposibles de saltar:
 *
 * 1. **ningún error viaja en un aviso efímero**: se dice junto a lo que se
 *    intentaba, o en un banner si alcanza a toda la vista;
 * 2. **con la ventana enfocada no se avisa por fuera**: lo que ya es visible no
 *    vuelve a decirse por el sistema operativo;
 * 3. **un hecho, un mecanismo**: la misma situación elige siempre lo mismo, sin
 *    depender de quién llama.
 */

export type Severidad = "info" | "exito" | "aviso" | "error";
export type Alcance = "elemento" | "vista" | "aplicacion";
export type Urgencia = "diferible" | "inmediata";

export type Notice = {
  severidad: Severidad;
  /** A qué alcanza: un control, la vista entera, o toda la aplicación. */
  alcance: Alcance;
  /** `inmediata` = no se puede seguir sin atenderlo. */
  urgencia: Urgencia;
  /** Una sola acción, con destino exacto (R9.1). */
  accion?: { etiqueta: string; destino: string };
  /** La clave del catálogo de textos: aquí no se incrusta copy. */
  clave: string;
};

export type Mechanism = "en_linea" | "banner" | "efimero" | "dialogo" | "sistema";

export type Context = {
  /** Si la ventana tiene el foco, lo visible ya se ve: no hace falta gritar. */
  windowFocused: boolean;
};

export function mechanismFor(notice: Notice, context: Context): Mechanism {
  const { severidad, alcance, urgencia } = notice;

  // Lo inmediato es lo único que interrumpe. Sin foco sale por el sistema
  // operativo —es la única forma de alcanzar a la persona— y con foco se
  // resuelve dentro, en un diálogo.
  if (urgencia === "inmediata") return context.windowFocused ? "dialogo" : "sistema";

  // Regla 1. Un error nunca se va solo: se queda donde la persona pueda leerlo
  // y actuar, ligado al control que falló o a la vista que afecta.
  if (severidad === "error") return alcance === "elemento" ? "en_linea" : "banner";

  // Lo que afecta a la vista entera se queda mientras dure.
  if (alcance !== "elemento") return "banner";

  // Y lo que queda —una confirmación de algo que la persona acaba de hacer—
  // es lo único efímero.
  return severidad === "exito" ? "efimero" : "en_linea";
}
