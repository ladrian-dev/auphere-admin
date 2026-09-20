/**
 * Qué texto le corresponde a un fallo de emparejamiento.
 *
 * Vive **fuera** del diálogo a propósito: es una función pura y el diálogo
 * arrastra el puente con él, así que dejarla dentro la hacía imposible de
 * probar sin montar media aplicación. Una regla que no se puede probar sola
 * acaba sin probar.
 *
 * El código lo elige la plataforma; esta tabla tiene tres. Uno nuevo —o uno
 * viejo que cambie de nombre— construía una clave inexistente, y eso lanzaba
 * durante el render: la ventana en negro
 * (`.specify/bugs/la-ventana-no-se-puede-usar/`).
 */
import type { AppKey } from "../i18n";

/** Los códigos que esta pantalla sabe explicar. */
const CONOCIDOS = new Set(["pairing_code_invalid", "pairing_rate_limited", "pairing_unavailable"]);

/**
 * Lo desconocido cae en «no se pudo emparejar; tu máquina sigue como estaba»,
 * que es verdad en cualquier caso. Decir «el código ya no vale» sin saberlo
 * mandaría a la persona a pedir otro código que tampoco va a funcionar.
 */
export function pairErrorKey(code: string): AppKey {
  return CONOCIDOS.has(code) ? (`pair.error.${code}` as AppKey) : "pair.error.pairing_unavailable";
}
