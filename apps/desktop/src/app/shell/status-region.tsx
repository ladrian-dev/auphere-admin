/**
 * La región educada del armazón — spec 010, Requisito 5.7.
 *
 * Una sola por vista. Las bandas del armazón —sin conexión, versión nueva,
 * versión no admitida, avisos de la taxonomía, sección que no cargó— pueden
 * estar puestas a la vez, y cada una llegó con su `role="status"`. Cuatro
 * regiones vivas en la misma pantalla no hacen que se oiga cuatro veces mejor:
 * hacen que se apague el lector.
 *
 * Educada y no urgente a propósito: nada de esto impide seguir trabajando, y
 * `alert` interrumpe la frase que la persona está oyendo. El único urgente del
 * producto es la petición de confirmación, y vive en el hilo.
 *
 * Sin nada dentro no deja una región puesta. Una región viva vacía no molesta,
 * pero un `<div>` sobrante en el árbol tampoco ayuda a nadie.
 */
import { Children, type ReactNode } from "react";

export function StatusRegion({ children }: { children: ReactNode }) {
  // `toArray` ya descarta `null`, `undefined` y booleanos: lo que queda es lo
  // que de verdad se va a pintar.
  if (Children.toArray(children).length === 0) return null;
  return (
    <div role="status" className="flex flex-col">
      {children}
    </div>
  );
}
