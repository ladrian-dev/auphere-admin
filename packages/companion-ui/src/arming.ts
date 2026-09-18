/**
 * La protección anti-pulsación — spec 010, Requisito 10.3.
 *
 * «WHEN una tarjeta de decisión aparece THEN el sistema NO DEBE aceptar como
 * respuesta una pulsación hecha en el instante de aparecer.»
 *
 * El caso real: la tarjeta de confirmación llega **en medio de un hilo que se
 * está escribiendo solo**, y empuja hacia abajo lo que había. Alguien que
 * estuviera pulsando algo justo ahí acaba autorizando —o rechazando— sin haber
 * leído nada. No es hipotético: es el mismo patrón por el que los navegadores
 * llevan años retrasando los diálogos de permisos.
 *
 * Doscientos cincuenta milisegundos es el umbral que usan Chrome y Firefox para
 * esto mismo. Por debajo, ninguna persona ha leído la tarjeta; por encima,
 * empieza a notarse como un botón que no responde.
 *
 * **No desactiva el botón**: un control apagado que se enciende solo es peor —
 * parece roto y no dice por qué. Lo que hace es **ignorar** la respuesta, que
 * desde fuera se ve exactamente igual que no haber pulsado.
 */

export const ARM_MS = 250;

/** ¿Ha pasado ya el umbral desde que la tarjeta apareció? */
export function isArmed(appearedAt: number, now: number): boolean {
  return now - appearedAt >= ARM_MS;
}
