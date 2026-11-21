/** Spec 069 — Entrar, recuperar la contraseña y el preaviso de los avisos: the app's own words, Spanish. Spread into `app.es.ts`. */
export const v13EntrarEs = {
  // ── Entrar (R5) ──────────────────────────────────────────────────
  "v13.entrar.brand": "Auphere",
  "v13.entrar.headline": "Tus clientes, siempre accesibles",
  "v13.entrar.error.email": "Escribe el correo con el que entras a Auphere.",
  "v13.entrar.error.password": "Escribe tu contraseña.",
  "v13.entrar.offline.title": "Sin conexión",
  "v13.entrar.back": "Atrás",
  // ── Contraseña nueva (R6) ────────────────────────────────────────
  "v13.entrar.forgot.body": "Te enviaremos un enlace para crearla. Tus conversaciones siguen atendidas mientras tanto.",
  "v13.entrar.sent.title": "Revisa tu correo",
  // R6.3 (spec 011, R1.3): the same sentence whether or not the account exists.
  "v13.entrar.sent.body": "Si ese correo tiene acceso, te hemos enviado un enlace para crear la contraseña nueva.",
  "v13.entrar.sent.address": "Correo: {email}",
  "v13.entrar.sent.change": "Cambiar",
  "v13.entrar.sent.changeA11y": "Usar otro correo",
  "v13.entrar.step.a11y": "Paso {n}: {title}",
  "v13.entrar.step.a11y.hint": "Paso {n}: {title}. {hint}",
  "v13.entrar.step1": "Abre el correo de Auphere",
  "v13.entrar.step2": "Abre el enlace y crea la contraseña",
  // services/password_reset.py, RESET_TTL: one hour.
  "v13.entrar.step2.hint": "El enlace dura una hora.",
  "v13.entrar.step3": "Vuelve aquí y entra",
  "v13.entrar.step3.hint": "Tus conversaciones siguen atendidas mientras tanto.",
  "v13.entrar.sent.help": "¿No aparece? Revisa spam o promociones. Si sigue sin llegar, pídeselo a quien gestiona tu negocio en Auphere.",
  "v13.entrar.resend.wait": "Reenviar en {time}",
  "v13.entrar.resend.cta": "Reenviar el enlace",
  "v13.entrar.resend.done": "Listo. Si ese correo tiene acceso, te llegará otro enlace.",
  // ── Avisos (R7) ──────────────────────────────────────────────────
  "v13.entrar.notices.later": "Puedes cambiar cada uno después en Ajustes.",
  "v13.entrar.notices.denied": "Sin avisos en este teléfono. Puedes activarlos en Ajustes cuando quieras.",
  "v13.entrar.notices.continue": "Seguir",
} as const;
