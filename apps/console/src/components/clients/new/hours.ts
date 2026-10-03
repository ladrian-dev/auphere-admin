/**
 * El horario del negocio (spec 019, R7). Puro: sin React y sin fetch.
 *
 * **Se elige, no se escribe.** Hasta ahora `tenant.business_hours_label` era
 * texto libre que alguien tecleaba («Lun-Sáb 10-19»), con un campo «Sábados»
 * aparte porque los sábados no cabían en esa cadena. El campo era el síntoma
 * y el texto libre la causa: al elegir el horario, el sábado es un día más y
 * el campo sobra.
 *
 * **La frontera con la semilla no cambia.** La plantilla sigue recibiendo una
 * cadena; lo que cambia es quién la escribe. Por eso `hoursLabel` vive aquí y
 * se prueba sola: es la traducción entre lo que el partner elige y lo que el
 * agente dirá por teléfono.
 */

export const DAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
] as const;

export type Day = (typeof DAYS)[number];

/** Un tramo, o `null` si ese día está cerrado. **No** un tramo vacío: dos
 *  horas que no significan nada son una fila que se contradice. */
export type Slot = { from: string; to: string } | null;
export type Hours = Record<Day, Slot>;

const NOMBRES: Record<Day, string> = {
  monday: "Lunes",
  tuesday: "Martes",
  wednesday: "Miércoles",
  thursday: "Jueves",
  friday: "Viernes",
  saturday: "Sábado",
  sunday: "Domingo",
};

/** El plural que se usa al agrupar: «lunes a viernes, sábados 10-14». */
const PLURALES: Record<Day, string> = {
  monday: "lunes",
  tuesday: "martes",
  wednesday: "miércoles",
  thursday: "jueves",
  friday: "viernes",
  saturday: "sábados",
  sunday: "domingos",
};

/** Lo que casi todo negocio hace, para no empezar de cero. */
export function defaultHours(): Hours {
  const laborable: Slot = { from: "10:00", to: "19:00" };
  return {
    monday: laborable,
    tuesday: laborable,
    wednesday: laborable,
    thursday: laborable,
    friday: laborable,
    saturday: { from: "10:00", to: "14:00" },
    sunday: null,
  };
}

export function dayName(day: Day): string {
  return NOMBRES[day];
}

function same(a: Slot, b: Slot): boolean {
  if (a === null || b === null) return a === b;
  return a.from === b.from && a.to === b.to;
}

/**
 * La cadena que recibe la plantilla, y que el agente le dirá a quien pregunte
 * por teléfono. Por eso **agrupa los días seguidos que abren igual**: nadie
 * recita siete renglones.
 */
export function hoursLabel(hours: Hours): string {
  const abiertos = DAYS.filter((d) => hours[d] !== null);
  if (abiertos.length === 0) return "";

  const primero = hours[abiertos[0]!]!;
  if (abiertos.length === DAYS.length && DAYS.every((d) => same(hours[d], primero))) {
    return `Todos los días ${primero.from}–${primero.to}`;
  }

  const tramos: string[] = [];
  let i = 0;
  while (i < DAYS.length) {
    const day = DAYS[i]!;
    const slot = hours[day];
    if (slot === null) {
      i += 1;
      continue;
    }
    let j = i;
    while (j + 1 < DAYS.length && same(hours[DAYS[j + 1]!], slot)) j += 1;
    const horas = `${slot.from}–${slot.to}`;
    if (j === i) {
      // Un solo día abre así. En cabeza va con mayúscula, dentro no.
      tramos.push(`${tramos.length === 0 ? NOMBRES[day] : PLURALES[day]} ${horas}`);
    } else {
      const desde = tramos.length === 0 ? NOMBRES[day] : PLURALES[day];
      tramos.push(`${desde} a ${PLURALES[DAYS[j]!]} ${horas}`);
    }
    i = j + 1;
  }
  // Coma y no punto y coma: ninguna pantalla lleva punto y coma.
  return tramos.join(", ");
}

/**
 * Poner el mismo tramo en todos los días **que ya abrían**.
 *
 * No abre ninguno que estuviera cerrado: resumir es una comodidad de edición,
 * no una decisión sobre el negocio. Abrir el domingo porque alguien pulsó
 * «todos los días son iguales» sería la pantalla decidiendo por él.
 */
export function summarise(hours: Hours, slot: NonNullable<Slot>): Hours {
  const out = {} as Hours;
  for (const day of DAYS) out[day] = hours[day] === null ? null : { ...slot };
  return out;
}
