/** Spec 044 (avisos y Entrar): the app's own words, Spanish. Spread into `app.es.ts`. */
export const avisosEs = {
  // ── the kinds of Reservas (R14.2) ────────────────────────────────
  "avisos.kind.reservations.changed": "Reserva nueva o cambiada por el agente",
  "avisos.kind.reservations.changed.hint": "Una vez por reserva.",
  "avisos.kind.reservations.cancelled_today": "Cancelaciones de hoy",
  "avisos.kind.reservations.cancelled_today.hint": "Cuando alguien cancela una reserva de hoy.",
  "avisos.kind.reservations.waitlist_accepted": "Alguien de la lista de espera aceptó",
  "avisos.kind.reservations.waitlist_accepted.hint": "Cuando el agente cierra una reserva desde la lista de espera.",
  // ── groups (R14.1) ───────────────────────────────────────────────
  "avisos.group.inbox": "Bandeja",
  "avisos.group.reservas": "Reservas",
  "avisos.group.balance": "Saldo",
  // ── quiet hours (R14.3) ──────────────────────────────────────────
  "avisos.quiet": "Silenciar fuera del horario del negocio",
  "avisos.quiet.hint": "{hours}. Lo urgente sigue llegando.",
  "avisos.quiet.hint.noHours": "Lo urgente sigue llegando.",
  // ── the permission screen (R14.4) ────────────────────────────────
  "avisos.permission.title": "Te avisamos cuando alguien te necesita",
  "avisos.permission.body": "En este teléfono, solo de esto:",
  "avisos.permission.reservas": "Cambios en las reservas de hoy",
  "avisos.permission.reservas.hint": "Nuevas o cambiadas por el agente, y las cancelaciones.",
  "avisos.example.app": "Auphere Customers",
  "avisos.example.when": "ahora",
  "avisos.example.title": "Lucía Fernández espera a una persona",
  "avisos.example.body": "Pide que le devuelvan la seña…",
  "avisos.example.a11y": "Ejemplo de aviso: {title}. {body}",
  // ── Android channel and iOS category (R14.6) ─────────────────────
  "avisos.channel.reservations": "Reservas",
  "avisos.placeholder.reservations": "Cambio en una reserva",
  // ── Ajustes and Entrar ───────────────────────────────────────────
  "avisos.signOut.row": "Cerrar sesión en este teléfono",
  "avisos.signIn.googleNote": "Usa la cuenta de Google del mismo correo. Si no tienes acceso, pídelo a quien gestiona tu negocio en Auphere.",
} as const;
