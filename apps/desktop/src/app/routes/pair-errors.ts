/**
 * Qué texto le corresponde a un fallo al dar de alta la máquina.
 *
 * Vive **fuera** de la pantalla a propósito: es una función pura y la pantalla
 * arrastra el puente con ella, así que dejarla dentro la hacía imposible de
 * probar sin montar media aplicación. Una regla que no se puede probar sola
 * acaba sin probar.
 *
 * El código lo elige la plataforma; esta tabla tiene tres. Uno nuevo —o uno
 * viejo que cambie de nombre— construía una clave inexistente, y eso lanzaba
 * durante el render: la ventana en negro
 * (`.specify/bugs/la-ventana-no-se-puede-usar/`).
 */
import type { AppKey } from "../i18n";

/**
 * Los códigos que esta pantalla sabe explicar.
 *
 * Eran seis: tres del canje del código y tres del registro por sesión. La spec
 * 012 retiró el canje, y los tres suyos se fueron con él — un código que la
 * plataforma ya no puede emitir es una rama que ningún test recorre.
 */
const CONOCIDOS = new Set(["register_sign_in_again", "register_at_cap", "register_unavailable"]);

/**
 * Lo desconocido cae en «no se pudo dar de alta; tu máquina sigue como
 * estaba», que es verdad en cualquier caso. Nombrar una causa sin saberla
 * manda a la persona a arreglar algo que no está roto.
 */
export function pairErrorKey(code: string): AppKey {
  return CONOCIDOS.has(code) ? (`pair.error.${code}` as AppKey) : "pair.error.register_unavailable";
}
