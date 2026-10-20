/** ES/EN del lane `membership` (spec 005). Se difunde en `i18n/messages.ts`. */
export const membershipMessages = {
  "membership.title": { es: "Tu plan", en: "Your plan" },
  "membership.description": {
    es: "Qué incluye tu plan, qué estás usando y cómo cambiarlo.",
    en: "What your plan includes, what you are using, and how to change it.",
  },

  // ── el nivel actual ────────────────────────────────────────────────
  "membership.current": { es: "Plan actual", en: "Current plan" },
  "membership.perMonth": { es: "al mes", en: "per month" },
  "membership.free": { es: "Gratis", en: "Free" },
  "membership.teammates": { es: "Agentes", en: "Agents" },
  "membership.members": { es: "Personas", en: "People" },
  "membership.consumption": { es: "Consumo", en: "Consumption" },
  // El múltiplo es lo que se publica en vez de la cifra del pool: las cifras
  // son provisionales y un número en una tabla de precios convierte cada
  // ajuste de capacidad en un recorte o un regalo visible (research D9).
  "membership.multiple": { es: "×{n} el de Pro", en: "×{n} that of Pro" },
  "membership.multiple.base": { es: "Consumo base", en: "Base consumption" },
  "membership.usage": { es: "Estás usando {teammates} de {maxTeammates} agentes y {members} de {maxMembers} personas.", en: "You are using {teammates} of {maxTeammates} agents and {members} of {maxMembers} people." },
  "membership.renews": { es: "Se renueva el {date}.", en: "Renews on {date}." },

  // ── el nivel gratuito ──────────────────────────────────────────────
  // Sin botón apagado: se dice qué desbloquea un plan y se ofrece el paso.
  "membership.free.title": { es: "Estás en el plan gratuito", en: "You are on the free plan" },
  "membership.free.body": {
    es: "Con un plan puedes crear agentes que trabajen contigo y darles acceso a tu máquina. Elige uno abajo cuando quieras empezar.",
    en: "With a plan you can create agents that work alongside you and give them access to your machine. Pick one below whenever you want to start.",
  },

  // ── el catálogo ────────────────────────────────────────────────────
  "membership.catalog": { es: "Planes", en: "Plans" },
  "membership.choose": { es: "Elegir {tier}", en: "Choose {tier}" },
  "membership.currentBadge": { es: "Tu plan", en: "Your plan" },
  "membership.pending": {
    es: "Has pedido cambiar a {tier}. El cambio se aplica el {date} y puedes anularlo hasta entonces.",
    en: "You asked to move to {tier}. The change applies on {date} and you can undo it until then.",
  },

  // ── la escalera de impago ──────────────────────────────────────────
  // Cada estado dice qué lo arregla. Ninguno culpa al partner: un impago es
  // un problema de facturación, no una falta.
  "membership.state.current": { es: "Al corriente", en: "Up to date" },
  "membership.state.payment_failed.title": { es: "No pudimos cobrar tu tarjeta", en: "We could not charge your card" },
  "membership.state.payment_failed.body": {
    es: "Lo volveremos a intentar durante los próximos días. No cambia nada mientras tanto: tus agentes, tus tareas y tus confirmaciones siguen donde estaban. Actualizar la tarjeta lo resuelve al momento.",
    en: "We will retry over the coming days. Nothing changes meanwhile: your agents, tasks and pending confirmations stay where they were. Updating the card resolves it right away.",
  },
  "membership.state.unpaid.title": { es: "El cobro no salió y el consumo incluido está en pausa", en: "The charge did not go through and included usage is paused" },
  "membership.state.unpaid.body": {
    es: "Se agotaron los intentos de cobro. El consumo incluido deja de reponerse, pero el saldo que compraste sigue disponible y no se ha perdido nada: ni un agente, ni una tarea, ni una confirmación pendiente. Actualiza la tarjeta y todo vuelve solo.",
    en: "Retries ran out. Included usage stops replenishing, but the balance you purchased is still available and nothing has been lost: not an agent, not a task, not a pending confirmation. Update your card and everything comes back on its own.",
  },
  "membership.state.canceled.title": { es: "Tu plan está cancelado", en: "Your plan is cancelled" },
  "membership.state.canceled.body": {
    es: "Tu cuenta sigue entera y puedes leerlo todo. Para volver a crear agentes, elige un plan abajo.",
    en: "Your account is intact and you can read everything. To create agents again, pick a plan below.",
  },
  "membership.state.fix": { es: "Actualizar la tarjeta", en: "Update card" },
  "membership.state.since": { es: "Desde el {date}.", en: "Since {date}." },

  // ── saldo comprado ─────────────────────────────────────────────────
  "membership.credit.keeps": {
    es: "Conservas tu saldo comprado hasta el {date}.",
    en: "You keep your purchased balance until {date}.",
  },

  // ── cancelar ───────────────────────────────────────────────────────
  // Lo que se dice al cancelar importa tanto como lo que pasa: quien cancela
  // quiere saber ahora mismo qué ocurre con el dinero que ya puso.
  "membership.cancel": { es: "Cancelar plan", en: "Cancel plan" },
  "membership.cancel.confirm.title": { es: "¿Cancelar el plan?", en: "Cancel the plan?" },
  "membership.cancel.confirm.body": {
    es: "No se pierde nada: tus agentes, tus tareas y tus confirmaciones pendientes siguen donde están, y puedes seguir leyéndolo todo. Lo que deja de reponerse es el consumo incluido. Tu saldo comprado se conserva doce meses.",
    en: "Nothing is lost: your agents, tasks and pending confirmations stay where they are, and you can still read everything. What stops replenishing is the included usage. Your purchased balance is kept for twelve months.",
  },
  "membership.cancel.confirm.cta": { es: "Sí, cancelar", en: "Yes, cancel" },
  "membership.cancel.done": { es: "Plan cancelado. Conservas tu saldo hasta el {date}.", en: "Plan cancelled. You keep your balance until {date}." },

  // ── compra de crédito ──────────────────────────────────────────────
  "membership.credit.title": { es: "Comprar saldo", en: "Buy balance" },
  // ── spec 041: the card on file and how it is charged ─────────────
  "card.title": { es: "Tarjeta y cobro automático", en: "Card and automatic charging" },
  "card.help": {
    es: "Guarda una tarjeta en la página segura de Stripe: su número nunca pasa por Auphere. Con ella puedes recargar solo o pagar a fin de mes.",
    en: "Save a card on Stripe's secure page: its number never goes through Auphere. With it you can top up automatically or pay at the end of the month.",
  },
  "card.none": { es: "No hay ninguna tarjeta guardada.", en: "No card saved." },
  "card.saved": { es: "{brand} terminada en {last4} · caduca {month}/{year}", en: "{brand} ending in {last4} · expires {month}/{year}" },
  "card.savedOther": { es: "Método de pago guardado: {method}", en: "Saved payment method: {method}" },
  "card.method.unknown": { es: "sin detalles de Stripe", en: "no details from Stripe" },
  "card.add": { es: "Añadir tarjeta", en: "Add a card" },
  "card.replace": { es: "Cambiar tarjeta", en: "Change card" },
  "card.remove": { es: "Quitar tarjeta", en: "Remove card" },
  "card.remove.title": { es: "Quitar la tarjeta", en: "Remove the card" },
  "card.remove.body": { es: "Sin tarjeta, el cobro vuelve a ser manual: tendrás que comprar saldo a mano.", en: "Without a card, charging goes back to manual: you will buy balance by hand." },
  "card.justSaved": { es: "Tarjeta guardada. Puede tardar unos segundos en aparecer aquí.", en: "Card saved. It may take a few seconds to show here." },
  "card.mode": { es: "Cómo se cobra", en: "How you are charged" },
  "card.mode.manual": { es: "Manual: compro saldo cuando lo necesito", en: "Manual: I buy balance when I need it" },
  "card.mode.auto_recharge": { es: "Recarga automática: cuando el saldo baja de un mínimo", en: "Automatic top-up: when the balance drops below a minimum" },
  "card.mode.postpaid": { es: "Pospago: pago lo consumido el día 1 de cada mes", en: "Postpaid: I pay what I used on the 1st of each month" },
  "card.mode.postpaid.locked": {
    es: "El pospago lo activa Auphere con una línea de crédito. Escríbenos si lo necesitas.",
    en: "Postpaid is enabled by Auphere with a credit line. Write to us if you need it.",
  },
  "card.mode.postpaid.line": {
    es: "Tu línea de crédito es de {limit}. Si se agota, los agentes se pausan hasta el cobro. Ahora debes {owed}.",
    en: "Your credit line is {limit}. If it runs out, the agents pause until the charge. You owe {owed} now.",
  },
  "card.threshold": { es: "Cuando el saldo baje de (US$)", en: "When the balance drops below (US$)" },
  "card.amount": { es: "Recargar (US$)", en: "Top up (US$)" },
  "card.amount.min": { es: "La recarga mínima es de US$5.", en: "The minimum top-up is US$5." },
  "card.save": { es: "Guardar", en: "Save" },
  "card.saving": { es: "Guardando…", en: "Saving…" },
  "card.saveDone": { es: "Cobro guardado.", en: "Charging saved." },
  "card.needsCard": { es: "Añade una tarjeta para elegir un cobro automático.", en: "Add a card to choose an automatic charge." },
  "card.paused": {
    es: "Los cobros automáticos están parados: la tarjeta se rechazó tres veces seguidas. Cambia la tarjeta para reanudarlos.",
    en: "Automatic charges are stopped: the card was declined three times in a row. Change the card to resume them.",
  },
  "card.charges": { es: "Cobros a la tarjeta", en: "Card charges" },
  "card.charge.auto_recharge": { es: "Recarga automática", en: "Automatic top-up" },
  "card.charge.postpaid": { es: "Consumo de {period}", en: "Usage of {period}" },
  "card.charge.paid": { es: "Pagado", en: "Paid" },
  "card.charge.pending": { es: "En curso", en: "In progress" },
  "card.charge.failed": { es: "Rechazado", en: "Declined" },
  "card.charge.action_required": { es: "Falta confirmar", en: "Needs confirming" },
  "card.charge.confirm": { es: "Confirmar el pago", en: "Confirm the payment" },
  "card.charge.invoice": { es: "Ver factura", en: "View invoice" },
  "card.charge.invoiceMissing": {
    es: "No se pudo abrir esa factura. Stripe no tiene factura para ese cobro o no respondió. Prueba de nuevo en un rato.",
    en: "That invoice could not be opened. Stripe has no invoice for that charge or did not answer. Try again in a while.",
  },
  "card.actionRequired": {
    es: "Tu banco pide confirmar un cobro. Confírmalo para que se complete: también te lo enviamos por correo.",
    en: "Your bank asks you to confirm a charge. Confirm it so it goes through: we also sent it to you by e-mail.",
  },
  "card.frozen": {
    es: "El cobro del consumo no se pudo completar y la línea de crédito está congelada: tus agentes no consumirán más a crédito hasta que se pague. Revisa tu tarjeta.",
    en: "The usage charge could not be completed and the credit line is frozen: your agents will not consume more on credit until it is paid. Check your card.",
  },
  "card.error.card_required": { es: "Primero añade una tarjeta.", en: "Add a card first." },
  "card.error.no_credit_line": { es: "El pospago necesita una línea de crédito de Auphere.", en: "Postpaid needs a credit line from Auphere." },
  "card.error.amount_too_small": { es: "La recarga mínima es de US$5.", en: "The minimum top-up is US$5." },
  "card.error.threshold_required": { es: "Indica el mínimo de saldo.", en: "Enter the minimum balance." },
  "card.error.provider": { es: "Stripe no aceptó la petición: {reason}", en: "Stripe did not accept the request: {reason}" },
  "card.error.unavailable": {
    es: "El cobro con tarjeta no está disponible ahora. Prueba de nuevo en un rato.",
    en: "Card charging is not available right now. Try again in a while.",
  },
  "membership.credit.amount": { es: "Importe en dólares", en: "Amount in dollars" },
  "membership.credit.buy": { es: "Comprar", en: "Buy" },
  // Se dice qué compra ese dinero ANTES de pagarlo: «50 $» no significa nada
  // por sí solo, y la relación con lo que consume un turno es justo lo que el
  // partner no tiene por qué saber de memoria.
  "membership.credit.buys": { es: "Recibirás {amount} de saldo.", en: "You will receive {amount} of balance." },
  "membership.credit.range": { es: "Entre {min} y {max} dólares, en números enteros.", en: "Between {min} and {max} dollars, whole numbers." },
  "membership.credit.invalid": { es: "El importe tiene que estar entre {min} y {max} dólares.", en: "The amount must be between {min} and {max} dollars." },
  "membership.credit.help": { es: "El saldo comprado no caduca mientras tu cuenta siga viva, y es lo que gastan los agentes de tus clientes.", en: "Purchased balance does not expire while your account is alive, and it is what your clients' agents spend." },

  // ── facturas del proveedor ─────────────────────────────────────────
  // No se nombra al proveedor: cuál es es un detalle nuestro, y el día que
  // cambie esta pantalla no tiene por qué cambiar con él.
  "membership.invoices": { es: "Ver mis facturas", en: "View my invoices" },
  "membership.invoices.help": {
    es: "Las facturas son el documento fiscal. Este recibo explica en qué se fue el consumo, cliente por cliente.",
    en: "Invoices are the fiscal document. This receipt explains where the usage went, client by client.",
  },

  // ── errores ────────────────────────────────────────────────────────
  // Ninguno enseña el mensaje crudo del proveedor: lo que llega de una API
  // externa es contenido externo y no se pone delante de una persona (§III).
  "membership.error.unavailable": {
    es: "Ahora mismo no podemos abrir el pago. Inténtalo en un momento.",
    en: "We cannot open the payment page right now. Try again in a moment.",
  },
  "membership.error.belowUsage": {
    es: "Ese plan admite menos de lo que usas. Te sobran {over}. Quítalos y podrás bajar.",
    en: "That plan allows less than you use. You have {over} too many. Remove them and you can downgrade.",
  },
  "membership.error.pending": {
    es: "Ya hay un cambio de plan programado. Anúlalo antes de pedir otro.",
    en: "A plan change is already scheduled. Cancel it before asking for another.",
  },
} as const;
