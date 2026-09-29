import type { MeterTone } from "@nexus/ui";

/**
 * El color del crédito, en un solo sitio.
 *
 * La barra del medidor tiñe **al revés** que las demás: un medidor normal se
 * pone rojo cuando se llena, y aquí lo que alarma es que se **vacíe**. Vivía
 * dentro del Resumen de la ficha; la lista de clientes enseña el mismo dato,
 * y dos reglas de color para la misma cifra es como se empiezan a contradecir
 * dos pantallas.
 */
export function creditTone({ cap, remaining }: { cap: number; remaining: number }): MeterTone {
  if (remaining <= 0) return "danger";
  if (cap > 0 && remaining / cap <= 0.2) return "warning";
  return "positive";
}
