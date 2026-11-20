/** ES/EN de la spec 067: crear cuenta con el mismo oficio que Entrar.
 *
 *  El panel del alta con los tres pasos del arranque, Google primero, el
 *  «enviado» con su correo y el segundo paso con la regla de la contraseña en
 *  vivo. El «enviado» dice lo mismo pueda registrarse la dirección o no (spec
 *  006, R1.2): repite el correo escrito, nada más. */
export const authAltaMessages = {
  // ── El panel (R1) ────────────────────────────────────────────────────────
  "signup.hero.title": { es: "Empieza con Auphere.", en: "Start with Auphere." },
  "signup.hero.body": {
    es: "Tres pasos y el agente de tu primer cliente ya responde.",
    en: "Three steps and your first client's agent is answering.",
  },
  "signup.hero.steps": { es: "Los tres pasos del arranque", en: "The three steps to get started" },
  "signup.step1.title": { es: "Crea tu cuenta", en: "Create your account" },
  "signup.step1.body": { es: "Tu correo y una contraseña", en: "Your e-mail and a password" },
  "signup.step2.title": { es: "Añade tu primer cliente", en: "Add your first client" },
  "signup.step2.body": { es: "Nombre, nicho y su web", en: "Name, niche and its website" },
  "signup.step3.title": { es: "Configura tu agente y publícalo", en: "Set up your agent and publish it" },
  "signup.step3.body": { es: "Su agente empieza a responder", en: "Its agent starts answering" },
  "signup.step.current": { es: "paso actual", en: "current step" },
  "signup.step.next": { es: "pendiente", en: "pending" },
  "signup.stepOf": { es: "Paso 1 de 3", en: "Step 1 of 3" },
  // ── Pedir el alta (R2) ───────────────────────────────────────────────────
  "signup.google": { es: "Registrarte con Google", en: "Sign up with Google" },
  "signup.orEmail": { es: "o con tu correo", en: "or with your e-mail" },
  "signup.workEmail": { es: "Correo de trabajo", en: "Work e-mail" },
  "signup.workEmail.example": { es: "nombre@agencia.com", en: "name@agency.com" },
  "signup.signIn": { es: "Iniciar sesión", en: "Sign in" },
  // En Entrar, el enlace al alta.
  "login.signUp": { es: "Regístrate", en: "Sign up" },
  // ── Enviado (R3) ─────────────────────────────────────────────────────────
  "signup.sent.bodyTo": {
    es: "Si {email} puede registrarse, ya tiene un enlace esperando. Ábrelo para terminar tu cuenta. Caduca en 24 horas.",
    en: "If {email} can be registered, a link is already waiting. Open it to finish your account. It expires in 24 hours.",
  },
  "signup.sent.other": { es: "Usar otro correo", en: "Use another e-mail" },
  "signup.resent": {
    es: "Te mandamos otro enlace. El anterior deja de valer.",
    en: "We sent you another link. The previous one stops working.",
  },
  // ── Terminar (R4) ────────────────────────────────────────────────────────
  "signup.verifiedEmail": { es: "Correo verificado", en: "Verified e-mail" },
  "signup.askAnother": { es: "Pedir otro enlace", en: "Request another link" },
} as const;
