/** ES/EN de la spec 066: Entrar con el líquido vivo.
 *
 *  El panel del líquido, mostrar/ocultar la contraseña, la pantalla de
 *  «enviado» con su correo, «Cambiar» y «Reenviar», y las reglas en vivo de la
 *  contraseña nueva. Lo de «enviado» dice lo mismo tenga cuenta o no (spec 011,
 *  R1.3): repite el correo que se escribió, no uno que haya confirmado nadie. */
export const authEntrarMessages = {
  // ── El panel (R1, R3) ────────────────────────────────────────────────────
  "auth.hero.title": { es: "Tus clientes, siempre al alcance.", en: "Your clients, always within reach." },
  // Debajo del «Inicia sesión.» de la página, no en el panel.
  "auth.hero.body": {
    es: "Cada cliente, sus agentes y su saldo, en un solo sitio.",
    en: "Every client, its agents and its balance, in one place.",
  },
  // ── Entrar (R4.1, R4.2) ──────────────────────────────────────────────────
  "auth.password.show": { es: "Mostrar contraseña", en: "Show password" },
  "auth.password.hide": { es: "Ocultar contraseña", en: "Hide password" },
  "auth.or": { es: "o", en: "or" },
  // ── Enviado (R4.4, R4.5) ─────────────────────────────────────────────────
  "forgot.sent.bodyTo": {
    es: "Si {email} tiene cuenta, ya tiene un enlace esperando. Caduca en una hora y sirve una sola vez.",
    en: "If {email} has an account, a link is already waiting. It expires in one hour and works once.",
  },
  "forgot.sent.change": { es: "Cambiar", en: "Change" },
  "forgot.sent.changeLabel": { es: "Cambiar el correo", en: "Change the e-mail" },
  "forgot.sent.spam": {
    es: "¿No llega? Mira también el correo no deseado. Si pides otro, el anterior deja de valer.",
    en: "Nothing yet? Check your spam folder too. If you ask for another, the previous one stops working.",
  },
  "forgot.resend": { es: "Reenviar el enlace", en: "Resend the link" },
  "forgot.resendIn": { es: "Reenviar en {s} s", en: "Resend in {s} s" },
  "forgot.resent": {
    es: "Te mandamos otro enlace. El anterior deja de valer.",
    en: "We sent you another link. The previous one stops working.",
  },
  // ── Contraseña nueva (R5) ────────────────────────────────────────────────
  "reset.confirm": { es: "Repítela", en: "Type it again" },
  "reset.mismatch": { es: "Las dos no coinciden.", en: "The two don't match." },
  "reset.rule.length": { es: "12 caracteres o más", en: "12 characters or more" },
  "reset.rule.match": { es: "Las dos coinciden", en: "The two match" },
  "reset.rule.met": { es: "cumplida", en: "met" },
  "reset.rule.unmet": { es: "pendiente", en: "pending" },
  "auth.passwords.show": { es: "Mostrar las contraseñas", en: "Show the passwords" },
  "auth.passwords.hide": { es: "Ocultar las contraseñas", en: "Hide the passwords" },
} as const;
