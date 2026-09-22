/**
 * Qué conversación se abre, y cómo se llama — spec 013, Requisito 4.
 *
 * **Puro, como el resto de lo que decide.** Recibe lo que la plataforma
 * devolvió y dice a cuál ir; el proceso principal solo ejecuta lo que esto
 * contesta, igual que con `update-policy` y `notifications-policy`.
 *
 * El defecto que corrige: `app:thread.open` se quedaba con el **primero no
 * archivado** de la lista y, si no había, creaba uno llamado literalmente
 * «Hilo». Resultado: un hilo eterno por teammate, donde todo lo hablado se
 * acumulaba para siempre.
 *
 * La base de datos admite varias conversaciones desde la spec 003, y la API ya
 * las lista y las crea. Lo único que las impedía era esa elección.
 */

export type ThreadRow = {
  id: string;
  title: string;
  archived_at: string | null;
  last_run_at: string | null;
};

/** Un título no es un párrafo: cabe en una línea de la lista lateral. */
export const TITLE_MAX = 60;

/**
 * A cuál se vuelve.
 *
 * `preferred` es la última en la que se estuvo. Se respeta **si sigue viva**:
 * puede haberse archivado, o haberse abierto en otra máquina. Cuando no, se
 * cae a la más reciente, que es lo que menos sorprende.
 *
 * `null` significa que no hay ninguna: crear es decisión de quien llama, no de
 * esta función. Devolver un id inventado sería peor que no devolver nada.
 */
export function chooseThread(rows: ThreadRow[], preferred: string | null): string | null {
  const vivas = rows.filter((r) => r.archived_at === null);
  if (vivas.length === 0) return null;

  if (preferred && vivas.some((r) => r.id === preferred)) return preferred;

  // Sin turnos todavía no es «vieja»: es recién creada, y mandar a la persona
  // a otra parte justo después de crearla sería el peor momento para hacerlo.
  const orden = [...vivas].sort((a, b) => key(b).localeCompare(key(a)));
  return orden[0]?.id ?? null;
}

/** Las que no han corrido nunca van primero: son las más nuevas. */
function key(row: ThreadRow): string {
  return row.last_run_at ?? "9999";
}

/**
 * Cómo se llama una conversación.
 *
 * Sale de **lo primero que se escribió**, no del modelo: pedirle un título
 * sería un turno de más y un gasto por una etiqueta.
 */
export function titleFrom(firstMessage: string): string {
  const limpio = firstMessage.trim().replace(/\s+/g, " ");
  if (!limpio) return "Sin título todavía";
  if (limpio.length <= TITLE_MAX) return limpio;

  // Se corta por palabra: «necesito que revises el inf…» se lee, y
  // «necesito que revises el i…» parece un fallo.
  const corte = limpio.slice(0, TITLE_MAX - 1);
  const espacio = corte.lastIndexOf(" ");
  return `${(espacio > TITLE_MAX / 2 ? corte.slice(0, espacio) : corte).trimEnd()}…`;
}
