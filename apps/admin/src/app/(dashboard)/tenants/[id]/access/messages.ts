import type { CapacityKind, ClientModule, ReservasMode } from "@/lib/backend";

/**
 * Spec 030: what each closed-vocabulary refusal of the client-access API
 * means for the operator. The API sends `detail.code`; the sentence lives
 * here, never in the backend.
 */
export const ACCESS_ERRORS: Record<string, string> = {
  no_partner:
    "Este cliente no está en ningún partner. Vincúlalo desde la ficha del partner antes de darle acceso.",
  archived: "El cliente está archivado: no se le puede dar acceso.",
  no_modules: "Elige al menos un módulo para encender el acceso.",
  inbox_requires_whatsapp: "La Bandeja de entrada necesita un WhatsApp conectado.",
  unknown_module: "Ese módulo no existe.",
  account_is_partner_member:
    "Ese correo ya es de un partner. Una cuenta no puede ser a la vez de un partner y de un cliente.",
  account_is_other_client: "Ese correo ya tiene acceso a la consola de otro cliente.",
  already_member: "Esa persona ya tiene acceso.",
  access_disabled: "Enciende el acceso antes de invitar a nadie.",
  not_an_invitation: "Solo se pueden reenviar invitaciones.",
  unknown_member: "Esa persona ya no está en la lista. Recarga la página.",
  // Spec 043 (contracts/admin-api.md)
  reservas_mode_required: "Elige cómo reserva el negocio: Servicios o Aforo.",
  reservas_kind_required: "Con Aforo, elige el tipo de negocio.",
  live_reservations: "Hay reservas futuras. Cambiar de modo las cancela y avisa a cada cliente por WhatsApp.",
};

export const MODULE_LABELS: Record<ClientModule, { label: string; description: string }> = {
  panel: { label: "Panel", description: "Cómo va su agente, lo que gasta y lo que le necesita." },
  inbox: {
    label: "Bandeja de entrada",
    description: "Sus conversaciones de WhatsApp: leer, tomar el control y contestar.",
  },
  reservas: {
    label: "Reservas",
    description: "Su agenda: lo que reserva el agente por WhatsApp y lo que apunta su equipo.",
  },
  usage: { label: "Consumo", description: "Su saldo, su gasto por día y el detalle técnico. Solo lectura." },
};

/** Spec 043: the two ways a business books. Only the operator chooses it. */
export const RESERVAS_MODES: { mode: ReservasMode; label: string; help: string }[] = [
  { mode: "services", label: "Servicios", help: "citas con una persona del equipo (peluquería, clínica, asesoría)" },
  {
    mode: "capacity",
    label: "Aforo",
    help: "personas por hora, sin mesas (restaurante, bar, clases, tours, salas, spa)",
  },
];

type KindStart = {
  label: string;
  /** How the screens call the stay: «mesa 1 h 30», «sesión 1 h». */
  stay: string;
  seats: number;
  stayMinutes: number;
  maxParty: number;
  walkinHold: number;
};

/**
 * Spec 043, data-model.md «Valores de partida por tipo». The API writes them on
 * the first activation; the panel only shows them before the operator saves.
 */
export const CAPACITY_KINDS: Record<CapacityKind, KindStart> = {
  restaurant: { label: "Restaurante", stay: "mesa", seats: 64, stayMinutes: 90, maxParty: 10, walkinHold: 6 },
  bar: { label: "Bar y terraza", stay: "mesa", seats: 80, stayMinutes: 120, maxParty: 12, walkinHold: 16 },
  classes: { label: "Clases y gimnasio", stay: "sesión", seats: 20, stayMinutes: 60, maxParty: 2, walkinHold: 2 },
  tours: { label: "Tours y experiencias", stay: "tour", seats: 16, stayMinutes: 120, maxParty: 8, walkinHold: 0 },
  rooms: { label: "Salas y eventos", stay: "sala", seats: 120, stayMinutes: 120, maxParty: 40, walkinHold: 0 },
  spa: { label: "Spa y circuitos", stay: "circuito", seats: 14, stayMinutes: 90, maxParty: 4, walkinHold: 2 },
};

export const CAPACITY_KIND_ORDER: CapacityKind[] = ["restaurant", "bar", "classes", "tours", "rooms", "spa"];

function hoursAndMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m}`;
}

/** One line with the starting values of a kind: «Aforo 64 · mesa 1 h 30 · hasta 10 por reserva · 6 guardadas». */
export function kindPreview(kind: CapacityKind): string {
  const k = CAPACITY_KINDS[kind];
  const hold = k.walkinHold === 0 ? "sin guardadas" : `${k.walkinHold} ${k.walkinHold === 1 ? "guardada" : "guardadas"}`;
  return [`Aforo ${k.seats}`, `${k.stay} ${hoursAndMinutes(k.stayMinutes)}`, `hasta ${k.maxParty} por reserva`, hold].join(
    " · ",
  );
}

/** Spec 043 (R1.4): what a mode change does to the live reservations. */
export function liveReservationsText(count: number | null): string {
  const head =
    count === null || count <= 0
      ? "Hay reservas futuras."
      : count === 1
        ? "Hay 1 reserva futura."
        : `Hay ${count} reservas futuras.`;
  const tail =
    count === 1
      ? "Cambiar de modo la cancela y avisa al cliente por WhatsApp."
      : "Cambiar de modo las cancela y avisa a cada cliente por WhatsApp.";
  return `${head} ${tail}`;
}

export const AGENT_PENDING_PROMOTION =
  "Hay una versión del agente preparada con las herramientas de Reservas. Revísala y promuévela en la pestaña Agente.";

export const INELIGIBLE: Record<"no_partner" | "archived", string> = {
  no_partner: ACCESS_ERRORS.no_partner!,
  archived: ACCESS_ERRORS.archived!,
};

/** Spec 031 (R7.4): why a phone stopped being signed in, for the operator. */
export const PHONE_REASONS: Record<string, string> = {
  signed_out: "Cerró sesión en el teléfono",
  closed_by_person: "Lo cerró la persona desde otro sitio",
  closed_by_auphere: "Lo cerró Auphere",
  access_disabled: "Se apagó el acceso del cliente",
  member_removed: "Se le retiró el acceso a la persona",
  password_reset: "La persona restableció su contraseña",
  abandoned: "Sin usarse 90 días",
  refresh_reused: "Se cerró por seguridad: su sesión se usó dos veces",
};

export const PHONE_GONE = "Ese teléfono ya no está en la lista. Vuelve a abrirla.";
