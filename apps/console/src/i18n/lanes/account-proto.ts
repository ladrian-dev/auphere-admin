/**
 * ES/EN del carril `account-proto` (spec 047): lo que añaden Operar y Cuenta
 * para quedar como el prototipo aprobado «Consola de partners v2» —Consumo,
 * Auditoría, Guía del partner, Teammate, Equipo, Facturación, API y
 * Notificaciones—. Se difunde en `i18n/messages.ts`.
 */
export const accountProtoMessages = {
  // ── Consumo ──
  "proto.usage.unassigned": { es: "{amount} sin asignar", en: "{amount} unassigned" },
  "proto.usage.openClient": { es: "Abrir ficha del cliente", en: "Open the client" },
  "proto.alerts.month": { es: "Este mes", en: "This month" },
  "proto.alerts.messages": { es: "{used} mensajes", en: "{used} messages" },

  // ── Guía del partner ──
  "proto.guide.drop": { es: "PDF, TXT, MD o HTML · máx. 10 MB", en: "PDF, TXT, MD or HTML · max 10 MB" },
  "proto.guide.choose": { es: "Elegir archivo", en: "Choose file" },
  "proto.guide.uploading": { es: "Subiendo «{name}»…", en: "Uploading “{name}”…" },
  "proto.guide.title": { es: "Título", en: "Title" },
  "proto.guide.optional": { es: "opcional", en: "optional" },
  "proto.guide.url": { es: "URL pública", en: "Public URL" },
  "proto.guide.docs": { es: "Documentos", en: "Documents" },
  "proto.guide.usage": { es: "{used} de {cap} caracteres · {pct}", en: "{used} of {cap} characters · {pct}" },
  "proto.guide.delete.body": {
    es: "El Companion dejará de consultar este documento de inmediato. No se puede deshacer.",
    en: "The Companion stops consulting this document straight away. It cannot be undone.",
  },

  // ── Teammate ──
  "proto.ws.machine.actions": { es: "Más opciones de {name}", en: "More options for {name}" },
  "proto.ws.ceiling": { es: "Techo de ejecución", en: "Execution ceiling" },

  // ── Equipo ──
  "proto.team.email.placeholder": { es: "nombre@empresa.com", en: "name@company.com" },

  // ── Facturación ──
  "proto.billing.wallet": { es: "Saldo de tu cuenta", en: "Your account balance" },
  "proto.billing.available": { es: "Disponible", en: "Available" },
  "proto.billing.spentBy": { es: "Es lo que gastan los agentes de tus clientes.", en: "It is what your clients’ agents spend." },
  "proto.billing.keeps": {
    es: "El saldo comprado no caduca mientras tu cuenta siga viva.",
    en: "Purchased balance does not expire while your account is alive.",
  },
  "proto.billing.quick": { es: "Importes rápidos", en: "Quick amounts" },
  "proto.billing.other": { es: "Otro importe", en: "Other amount" },
  "proto.billing.chargedIn": {
    es: "Se cobra en {currency} en la página segura del proveedor. Tu saldo se ve en la moneda de tu cuenta.",
    en: "It is charged in {currency} on the provider’s secure page. Your balance is shown in your account’s currency.",
  },
  "proto.billing.secure": { es: "Se paga en la página segura del proveedor.", en: "You pay on the provider’s secure page." },
  "proto.billing.receipt.paid": { es: "Pagado", en: "Paid" },
  "proto.billing.receipt.issued": { es: "Emitido", en: "Issued" },
  "proto.billing.receipt.draft": { es: "Borrador", en: "Draft" },
  "proto.billing.receipt.void": { es: "Anulado", en: "Void" },
  "proto.billing.card.change": { es: "Cambiar", en: "Change" },
  "proto.billing.card.remove": { es: "Quitar", en: "Remove" },
  "proto.billing.card.expires": { es: "Caduca {month}/{year}", en: "Expires {month}/{year}" },
  "proto.billing.card.endsIn": { es: "{brand} terminada en {last4}", en: "{brand} ending in {last4}" },
  "proto.billing.mode.manual": { es: "Manual", en: "Manual" },
  "proto.billing.mode.manual.hint": { es: "Compro saldo cuando lo necesito.", en: "I buy balance when I need it." },
  "proto.billing.mode.auto_recharge": { es: "Recarga automática", en: "Automatic top-up" },
  "proto.billing.mode.auto_recharge.hint": { es: "Cuando el saldo baja de un mínimo.", en: "When the balance drops below a minimum." },
  "proto.billing.mode.postpaid": { es: "Pospago", en: "Postpaid" },
  "proto.billing.mode.postpaid.hint": {
    es: "Pago lo consumido el día 1 de cada mes. Lo activa Auphere con una línea de crédito: escríbenos si lo necesitas.",
    en: "I pay what I used on the 1st of each month. Auphere turns it on with a credit line: write to us if you need it.",
  },
  "proto.billing.threshold": { es: "Cuando el saldo baje de", en: "When the balance drops below" },
  "proto.billing.amount": { es: "Recargar", en: "Top up" },
  "proto.billing.amount.min": { es: "La recarga mínima es de {amount}.", en: "The minimum top-up is {amount}." },
  "proto.billing.credit.range": { es: "Entre {min} y {max}, en números enteros.", en: "Between {min} and {max}, in whole numbers." },
  "proto.billing.credit.invalid": {
    es: "El importe tiene que estar entre {min} y {max}, en números enteros.",
    en: "The amount must be between {min} and {max}, in whole numbers.",
  },

  // ── API ──
  "proto.keys.list": { es: "Claves", en: "Keys" },
  "proto.keys.active": { es: "{n} activas", en: "{n} active" },
  "proto.keys.active.one": { es: "1 activa", en: "1 active" },
  "proto.keys.lastUsed": { es: "Último uso: {when}", en: "Last used: {when}" },
  "proto.keys.actions": { es: "Más opciones de {prefix}", en: "More options for {prefix}" },
  "proto.keys.note.lead": { es: "Las claves de un solo cliente", en: "Single-client keys" },
  "proto.keys.note.rest": {
    es: "(envío de mensajes) se crean desde la ficha del cliente.",
    en: "(sending messages) are created from the client’s page.",
  },
  "proto.keys.scopes.error": { es: "Marca al menos un permiso.", en: "Tick at least one permission." },
  "proto.keys.scope.provision.hint": { es: "Crear y configurar clientes desde tu sistema.", en: "Create and set up clients from your system." },
  "proto.keys.scope.broadcasts.hint": {
    es: "Enviar mensajes masivos con plantillas aprobadas.",
    en: "Send bulk messages with approved templates.",
  },
  "proto.keys.create.submit": { es: "Crear clave", en: "Create key" },

  // ── Notificaciones ──
  "proto.notif.unread": { es: "Sin leer", en: "Unread" },
  "proto.notif.filter": { es: "Qué notificaciones se ven", en: "Which notifications you see" },
} as const;
