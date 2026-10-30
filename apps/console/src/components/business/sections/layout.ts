/**
 * La rejilla de Negocio (spec 047, T060; T218): la comparten la página
 * (`BusinessSectionsView`) y su esqueleto (`business/loading.tsx`) para que
 * nada salte cuando llegan los datos. Un módulo sin "use client": el esqueleto
 * es de servidor y no puede leer constantes de un módulo de cliente.
 */

/** Índice de 12,5 rem a la izquierda desde `lg`; una columna por debajo. */
export const BUSINESS_GRID = "grid min-w-0 gap-6 lg:grid-cols-[12.5rem_minmax(0,1fr)] lg:items-start";

/** El índice: una fila que se desplaza en el móvil, una lista desde `lg`. */
export const BUSINESS_INDEX_LIST = "relative flex min-w-0 gap-1 overflow-x-auto pb-1 lg:grid lg:overflow-visible lg:pb-0";

/** La columna de las secciones. */
export const BUSINESS_SECTIONS_COLUMN = "grid min-w-0 gap-4";
