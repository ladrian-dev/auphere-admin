import type { ComponentProps } from "react";

import { cn } from "../lib/utils";

/**
 * Uppercase, tracked label above a title. Editorial marker.
 *
 * En Helvena, no en la mono. La marca tiene UNA familia (brand-system §2) y
 * estas etiquetas —«Operar», «Cuenta», el nombre de una métrica— son texto
 * de interfaz, no código: ponerlas en monoespaciada era lo que hacía que la
 * consola no se leyera como Helvena. La mono se reserva para lo que de
 * verdad se copia y se compara carácter a carácter: referencias, claves,
 * identificadores y teclas.
 */
function Eyebrow({ className, ...props }: ComponentProps<"p">) {
  return (
    <p
      data-slot="eyebrow"
      className={cn("text-xs font-medium tracking-eyebrow text-muted-foreground uppercase", className)}
      {...props}
    />
  );
}

export { Eyebrow };
