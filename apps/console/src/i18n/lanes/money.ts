/** ES/EN del carril `money` — el dinero de la consola nueva (spec 047, T159 y
 *  T160; requisitos 43 a 46 y 55.3): «Asignar saldo», «Pedir saldo», mover,
 *  bajar, el relleno, la moneda, el tope del agente, Consumo por partidas y
 *  «Repartir tu saldo en bolsas».
 *
 *  Reglas de las palabras: «tope» es solo el del agente y el de la partida de
 *  construcción (45.6, 46.5), la bolsa de un cliente tiene «saldo». Nunca
 *  «créditos» ni «tokens» (spec 027, spec 033). Sin punto y coma
 *  (`words.test.ts`). Los importes los escribe `money-model.ts` en `es-ES`. */
export const moneyMessages = {
  // ── comunes ──
  "money.cancel": { es: "Cancelar", en: "Cancel" },
  "money.close": { es: "Cerrar", en: "Close" },
  "money.retry": { es: "Reintentar", en: "Retry" },
  "money.loading": { es: "Cargando el saldo", en: "Loading the balance" },
  "money.optional": { es: "Opcional", en: "Optional" },
  "money.approx": { es: "aprox.", en: "approx." },
  "money.approxPrefix": { es: "aprox.", en: "approx." },
  "money.fx.line": { es: "1 € = {rate} USD · BCE {date}", en: "1 € = {rate} USD · ECB {date}" },
  "money.fx.lineNoDate": { es: "1 € = {rate} USD · BCE", en: "1 € = {rate} USD · ECB" },
  "money.currency.eur": { es: "Euros (€)", en: "Euros (€)" },
  "money.currency.usd": { es: "Dólares (USD)", en: "Dollars (USD)" },
  "money.days.unknown": { es: "Sin ritmo para estimarlo", en: "Not enough activity to estimate" },
  "money.days.one": { es: "Un día", en: "One day" },
  "money.days.many": { es: "Unos {n} días", en: "About {n} days" },

  // ── el importe ──
  "money.amount.legend": { es: "Cuánto", en: "How much" },
  "money.amount.other": { es: "Otra cantidad", en: "Other amount" },
  "money.amount.otherLabel": { es: "Otra cantidad, en {currency}", en: "Other amount, in {currency}" },
  "money.amount.hint": { es: "Con coma para los decimales: 12,50", en: "Use a comma or a point for decimals: 12.50" },
  "money.amount.invalid": { es: "Escribe un importe como 25 o 25,50.", en: "Type an amount like 25 or 25.50." },
  "money.amount.positive": { es: "Escribe un importe mayor que cero.", en: "Type an amount above zero." },

  // ── «Asignar saldo a {cliente}» (45.2) ──
  "money.assign.cta": { es: "Asignar saldo", en: "Assign balance" },
  "money.assign.title": { es: "Asignar saldo a {name}", en: "Assign balance to {name}" },
  "money.assign.body": {
    es: "Sale de tu cuenta y queda en su bolsa. Lo que no gaste no caduca.",
    en: "It leaves your account and stays in their bag. What they do not spend does not expire.",
  },
  "money.assign.submit": { es: "Asignar saldo", en: "Assign balance" },
  "money.assign.done": { es: "Asignados {amount} a {name}. En tu cuenta quedan {left}.", en: "{amount} assigned to {name}. {left} left in your account." },
  "money.receipt.title": { es: "Recibo", en: "Receipt" },
  "money.receipt.before": { es: "Saldo actual de {name}", en: "{name}’s balance now" },
  "money.receipt.assigned": { es: "Asignas", en: "You assign" },
  "money.receipt.debit": { es: "Sale de tu cuenta", en: "Leaves your account" },
  "money.receipt.after": { es: "Nuevo saldo", en: "New balance" },
  "money.receipt.left": { es: "Queda en tu cuenta", en: "Left in your account" },
  "money.receipt.missing": { es: "Faltan {amount}", en: "{amount} short" },
  "money.receipt.recharge": { es: "Recargar mi cuenta", en: "Top up my account" },
  "money.receipt.askBilling": {
    es: "Pide a quien lleva la facturación que recargue la cuenta.",
    en: "Ask whoever handles billing to top up the account.",
  },
  "money.receipt.lowAccount": {
    es: "Tu cuenta se queda con menos del 20 % de lo que tenía.",
    en: "Your account is left with less than 20 % of what it had.",
  },
  "money.refill.check": { es: "Rellenar cada mes hasta…", en: "Top up every month to…" },
  "money.refill.amount": { es: "Hasta, en {currency}", en: "Up to, in {currency}" },
  "money.refill.hint": {
    es: "El día 1 de cada mes su bolsa sube hasta este importe con dinero de tu cuenta.",
    en: "On the 1st of each month their bag goes up to this amount with money from your account.",
  },
  "money.alertLow": { es: "Avisarme cuando le quede menos del 20 %", en: "Tell me when it has less than 20 % left" },

  // ── «Cambiar saldo»: subir o bajar (45.6, 43.6) ──
  "money.change.title": { es: "Cambiar el saldo de {name}", en: "Change {name}’s balance" },
  "money.change.body": {
    es: "Súbelo con dinero de tu cuenta o devuelve a tu cuenta lo que no ha gastado.",
    en: "Raise it with money from your account or return what they have not spent.",
  },
  "money.change.direction": { es: "Subir o bajar", en: "Raise or lower" },
  "money.change.up": { es: "Subir", en: "Raise" },
  "money.change.down": { es: "Devolver a tu cuenta", en: "Return to your account" },
  "money.lower.amount": { es: "Cuánto devuelves, en {currency}", en: "How much you return, in {currency}" },
  "money.lower.hint": { es: "Puedes devolver hasta {amount}, lo que le queda.", en: "You can return up to {amount}, what it has left." },
  "money.lower.after": { es: "Quedará en su bolsa", en: "Left in their bag" },
  "money.lower.back": { es: "Vuelve a tu cuenta", en: "Back to your account" },
  "money.lower.submit": { es: "Devolver a tu cuenta", en: "Return to your account" },
  "money.lower.done": { es: "Devueltos {amount} a tu cuenta. A {name} le quedan {left}.", en: "{amount} returned to your account. {name} has {left} left." },
  "money.lower.empty": { es: "La bolsa de {name} está vacía: no hay nada que devolver.", en: "{name}’s bag is empty: there is nothing to return." },

  // ── mover, relleno y moneda (43.7, 43.8, 43.3) ──
  "money.move.title": { es: "Mover saldo de {name} a otro cliente", en: "Move balance from {name} to another client" },
  "money.move.body": { es: "Le quedan {amount}. O cambian las dos bolsas o no cambia ninguna.", en: "It has {amount} left. Both bags change or neither does." },
  "money.move.to": { es: "A qué cliente", en: "To which client" },
  "money.move.pick": { es: "Elige un cliente", en: "Choose a client" },
  "money.move.amount": { es: "Cuánto, en {currency}", en: "How much, in {currency}" },
  "money.move.tooMuch": { es: "Como mucho {amount}, lo que le queda.", en: "At most {amount}, what it has left." },
  "money.move.receives": { es: "{name} recibe {amount}", en: "{name} receives {amount}" },
  "money.move.nobody": { es: "No hay otro cliente con bolsa al que moverlo.", en: "There is no other client with a bag to move it to." },
  "money.move.submit": { es: "Mover saldo", en: "Move balance" },
  "money.move.done": { es: "Movidos {amount} de {from} a {to}.", en: "{amount} moved from {from} to {to}." },
  "money.refill.title": { es: "Relleno mensual de {name}", en: "{name}’s monthly top-up" },
  "money.refill.body": {
    es: "Si tu cuenta no llega para todas, se rellenan primero las bolsas con menos días de saldo y te avisamos de lo que faltó.",
    en: "If your account cannot cover them all, the bags with fewest days left go first and we tell you what was missing.",
  },
  "money.refill.submit": { es: "Guardar el relleno", en: "Save the top-up" },
  "money.refill.saved": { es: "{name} se rellenará cada mes hasta {amount}.", en: "{name} will be topped up to {amount} every month." },
  "money.refill.removed": { es: "{name} ya no se rellena cada mes.", en: "{name} is no longer topped up every month." },
  "money.currency.title": { es: "Moneda de la bolsa de {name}", en: "Currency of {name}’s bag" },
  "money.currency.body": {
    es: "Hoy va en {current}. Si tiene saldo, se convierte al cambio del BCE de hoy y te lo enseñamos antes.",
    en: "It is in {current} today. If it has a balance, it is converted at today’s ECB rate and shown to you first.",
  },
  "money.currency.legend": { es: "Moneda", en: "Currency" },
  "money.currency.submit": { es: "Cambiar la moneda", en: "Change the currency" },
  "money.currency.confirm": { es: "Sus {from} pasarán a ser {to}.", en: "Their {from} will become {to}." },
  "money.currency.confirmSubmit": { es: "Convertir a {currency}", en: "Convert to {currency}" },
  "money.currency.done": { es: "La bolsa de {name} va ahora en esa moneda. Le quedan {amount}.", en: "{name}’s bag is now in that currency. It has {amount} left." },

  // ── «Pedir saldo» (45.7) ──
  "money.request.cta": { es: "Pedir saldo", en: "Request balance" },
  "money.request.title": { es: "Pedir saldo para {name}", en: "Request balance for {name}" },
  "money.request.body": {
    es: "Avisamos a los owners y admins de tu equipo con el saldo de {name} y los días que le quedan. Se puede pedir una vez al día por cliente.",
    en: "We tell the owners and admins of your team, with {name}’s balance and the days it has left. It can be requested once a day per client.",
  },
  "money.request.note": { es: "Nota", en: "Note" },
  "money.request.note.count": { es: "{n} de {max} caracteres", en: "{n} of {max} characters" },
  "money.request.note.tooLong": { es: "La nota admite hasta {max} caracteres.", en: "The note takes up to {max} characters." },
  "money.request.submit": { es: "Pedir saldo", en: "Request balance" },
  "money.request.sent": { es: "Pedido. Avisamos a los owners y admins para {name}.", en: "Requested. We told the owners and admins about {name}." },
  "money.request.justNow": { es: "Pedido hace un momento", en: "Requested a moment ago" },
  "money.request.ago": { es: "Pedido {ago}", en: "Requested {ago}" },
  "money.request.today": { es: "Pedido hoy", en: "Requested today" },
  "money.request.again": { es: "Mañana se puede volver a pedir.", en: "It can be requested again tomorrow." },
  "money.request.already": { es: "Ya se pidió hoy para este cliente.", en: "It was already requested today for this client." },
  "money.request.canAssign": { es: "Tú puedes asignar saldo directamente.", en: "You can assign balance yourself." },

  // ── archivar con saldo (43.13) ──
  "money.return.title": { es: "Devolver a la cuenta", en: "Return to the account" },
  "money.return.body": { es: "A {name} le quedan {amount} en su bolsa. ¿Los devuelves a tu cuenta?", en: "{name} has {amount} left in its bag. Return it to your account?" },
  "money.return.confirm": { es: "Devolver a la cuenta", en: "Return to the account" },
  "money.return.keep": { es: "Dejarlo en su bolsa", en: "Keep it in the bag" },
  "money.return.done": { es: "Devueltos {amount} de {name} a tu cuenta.", en: "{amount} from {name} returned to your account." },

  // ── el tope del agente (44.1) ──
  "money.advanced.title": { es: "Avanzado", en: "Advanced" },
  "money.cap.title": { es: "Tope mensual de {name}", en: "{name}’s monthly cap" },
  "money.cap.body": {
    es: "Lo más que puede gastar este agente en un mes. Al 80 % te avisamos, al 100 % se pausa hasta el mes siguiente. Los demás agentes siguen.",
    en: "The most this agent can spend in a month. At 80 % we tell you, at 100 % it pauses until next month. The other agents carry on.",
  },
  "money.cap.label": { es: "Tope mensual, en {currency}", en: "Monthly cap, in {currency}" },
  "money.cap.hint": {
    es: "En {currency}, la moneda de la bolsa del cliente. Puede ser más que lo que hay en la bolsa: manda lo que antes se acabe. Vacío, sin tope.",
    en: "In {currency}, the currency of the client’s bag. It can be more than the bag holds: whichever runs out first wins. Empty, no cap.",
  },
  "money.cap.placeholder": { es: "Sin tope", en: "No cap" },
  "money.cap.save": { es: "Guardar el tope", en: "Save the cap" },
  "money.cap.remove": { es: "Quitar el tope", en: "Remove the cap" },
  "money.cap.current": { es: "Tope de hoy: {amount} al mes.", en: "Cap today: {amount} a month." },
  "money.cap.none": { es: "Sin tope: gasta de la bolsa del cliente hasta que se acabe.", en: "No cap: it spends from the client’s bag until it runs out." },
  "money.cap.unknown": {
    es: "No podemos leer el tope de hoy. Si guardas uno, sustituye al que tenga.",
    en: "We cannot read today’s cap. Saving one replaces whatever it has.",
  },
  "money.cap.noneShort": { es: "Sin tope", en: "No cap" },
  "money.cap.spent": { es: "Este mes lleva {amount}.", en: "{amount} spent this month." },
  "money.cap.set": { es: "Poner tope", en: "Set a cap" },
  "money.cap.edit.aria": { es: "Cambiar el tope de {name}", en: "Change {name}’s cap" },
  "money.cap.saved": { es: "Tope de {name}: {amount} al mes.", en: "{name}’s cap: {amount} a month." },
  "money.cap.removed": { es: "{name} ya no tiene tope.", en: "{name} no longer has a cap." },

  // ── el Panel del cliente ──
  "money.panel.refill": { es: "Se rellena cada mes hasta {amount}.", en: "Topped up every month to {amount}." },

  // ── Consumo (46) ──
  "money.usage.description": {
    es: "Lo que tienes, lo que has repartido entre tus clientes y en qué se va, en la moneda de tu cuenta.",
    en: "What you have, what you have shared out among your clients and where it goes, in your account’s currency.",
  },
  "money.usage.error": { es: "No pudimos leer tu saldo. Vuelve a intentarlo en un momento.", en: "We could not read your balance. Try again in a moment." },
  "money.figures": { es: "Tu saldo", en: "Your balance" },
  "money.figure.available": { es: "Saldo disponible", en: "Available balance" },
  "money.figure.available.hint": {
    es: "Lo que puedes asignar. No cuenta lo incluido para el Companion.",
    en: "What you can assign. The Companion’s included allowance does not count.",
  },
  "money.figure.inBags": { es: "En bolsas de clientes", en: "In client bags" },
  "money.figure.inBags.hint": { es: "Lo que les queda a tus clientes.", en: "What your clients have left." },
  "money.figure.inBags.approx": {
    es: "Lo que les queda a tus clientes. Hay bolsas en otra moneda, convertidas al cambio de hoy.",
    en: "What your clients have left. Some bags are in another currency, converted at today’s rate.",
  },
  "money.figure.month": { es: "Gasto del mes", en: "This month’s spend" },
  "money.figure.month.hint": { es: "A fin de mes, unos {amount} al ritmo de los últimos 7 días.", en: "About {amount} by month end at the last 7 days’ pace." },
  "money.table.title": { es: "Saldo por cliente", en: "Balance by client" },
  "money.table.description": {
    es: "Cada bolsa va en la moneda de su cliente. Lo gastado, en la de tu cuenta.",
    en: "Each bag is in its client’s currency. Spend is in your account’s currency.",
  },
  "money.table.empty": { es: "Todavía no tienes clientes.", en: "You have no clients yet." },
  "money.table.client": { es: "Cliente", en: "Client" },
  "money.table.bag": { es: "Bolsa", en: "Bag" },
  "money.table.spent": { es: "Gastado este mes", en: "Spent this month" },
  "money.table.days": { es: "Le dura", en: "Lasts" },
  "money.table.refill": { es: "Relleno mensual", en: "Monthly top-up" },
  "money.table.refillUpTo": { es: "Hasta {amount}", en: "Up to {amount}" },
  "money.table.actions": { es: "Acciones", en: "Actions" },
  "money.table.actions.aria": { es: "Acciones de {name}", en: "Actions for {name}" },
  "money.table.noBalance": { es: "Sin saldo", en: "No balance" },
  "money.table.change": { es: "Cambiar saldo", en: "Change balance" },
  "money.table.move": { es: "Mover saldo a otro cliente", en: "Move balance to another client" },
  "money.table.see": { es: "Ver su gasto", en: "See their spend" },
  "money.table.currency": { es: "Cambiar la moneda", en: "Change the currency" },

  "money.chart.title": { es: "Gasto por día", en: "Spend per day" },
  "money.chart.period": { es: "Periodo", en: "Period" },
  "money.chart.days": { es: "{n} días", en: "{n} days" },
  "money.chart.client": { es: "Cliente", en: "Client" },
  "money.chart.allClients": { es: "Todos los clientes", en: "All clients" },
  "money.chart.line": { es: "Partida", en: "Line" },
  "money.chart.partnerPays": { es: "Lo que pagas tú", en: "What you pay" },
  "money.chart.partnerPaysNote": {
    es: "Lo que sale de tu dinero: las conversaciones y el Companion. Elige una partida para ver Meta o «Construcción y pruebas».",
    en: "What comes out of your money: conversations and the Companion. Choose a line to see Meta or “Building and testing”.",
  },
  "money.chart.approxNote": { es: "Es una estimación.", en: "It is an estimate." },
  "money.chart.total": { es: "{amount} en {days} días", en: "{amount} in {days} days" },
  "money.chart.today": { es: "Hoy", en: "Today" },
  "money.chart.day": { es: "Día", en: "Day" },
  "money.chart.columnTotal": { es: "Total", en: "Total" },
  "money.chart.top": { es: "Con más gasto", en: "Highest spend" },
  "money.chart.noData": { es: "Sin datos", en: "No data" },
  "money.chart.empty": { es: "Sin gasto en este periodo.", en: "No spend in this period." },
  "money.chart.error": { es: "No pudimos leer el gasto por día.", en: "We could not read the spend per day." },

  "money.lines.title": { es: "Partidas", en: "Lines" },
  "money.lines.description": { es: "En qué se va este mes y quién paga cada cosa.", en: "Where this month goes and who pays for each thing." },
  "money.line.conversations": { es: "Conversaciones", en: "Conversations" },
  "money.line.meta": { es: "Mensajes de Meta", en: "Meta messages" },
  "money.line.build": { es: "Construcción y pruebas", en: "Building and testing" },
  "money.line.companion": { es: "Companion y teammates", en: "Companion and teammates" },
  "money.line.conversations.payer": {
    es: "La paga la bolsa de cada cliente: la IA de sus conversaciones y lo que cuelga de ellas.",
    en: "Paid by each client’s bag: the AI of their conversations and everything around them.",
  },
  "money.line.meta.payer": {
    es: "La paga el negocio, a Meta: plantillas y mensajes de servicio por encima de los 1.000 gratis al mes. Es una estimación y no sale de la bolsa.",
    en: "Paid by the business, to Meta: templates and service messages beyond the free 1,000 a month. It is an estimate and does not come out of the bag.",
  },
  "money.line.build.payer": {
    es: "La paga Auphere hasta tu tope del mes: el constructor, el playground, las pruebas, la lectura de webs y documentos y las sugerencias.",
    en: "Paid by Auphere up to your monthly cap: the builder, the playground, tests, reading sites and documents and suggestions.",
  },
  "money.line.companion.payer": {
    es: "La paga tu cuenta, después de lo incluido: el asistente de la consola y los teammates.",
    en: "Paid by your account, after the included allowance: the console assistant and teammates.",
  },
  "money.build.cap.label": { es: "Construcción y pruebas este mes", en: "Building and testing this month" },
  "money.build.cap.value": { es: "{spent} de {cap} · {pct} %", en: "{spent} of {cap} · {pct} %" },
  "money.build.warning": {
    es: "Va por más del 80 % del tope de este mes. Al llegar al 100 % se paran el constructor, las pruebas y el playground.",
    en: "Over 80 % of this month’s cap. At 100 % the builder, tests and playground stop.",
  },
  "money.build.exhausted": {
    es: "Se acabó este mes. El constructor, las pruebas y el playground se paran hasta el día 1. La edición a mano sigue.",
    en: "Used up this month. The builder, tests and playground stop until the 1st. Editing by hand carries on.",
  },
  "money.build.blocked": {
    es: "Se acabó la partida «Construcción y pruebas» de este mes. Pide más en Consumo › «Pedir ampliación». La edición a mano sigue disponible.",
    en: "This month’s “Building and testing” line is used up. Ask for more in Usage › “Ask for more”. Editing by hand is still available.",
  },
  "money.build.ask": { es: "Pedir ampliación", en: "Ask for more" },
  "money.build.requested": { es: "Pedido a Auphere. Te avisamos cuando suba el tope.", en: "Asked Auphere. We will tell you when the cap goes up." },
  "money.build.already": { es: "Ya se pidió hoy. Mañana se puede volver a pedir.", en: "Already asked today. It can be asked again tomorrow." },

  "money.detail.title": { es: "Detalle técnico", en: "Technical detail" },
  "money.detail.hint": {
    es: "Los medidores por cliente, agente, partida y origen.",
    en: "The meters by client, agent, line and source.",
  },
  "money.detail.period": { es: "Últimos {days} días", en: "Last {days} days" },
  "money.detail.csv": { es: "Descargar CSV", en: "Download CSV" },
  "money.detail.agent": { es: "Agente", en: "Agent" },
  "money.detail.line": { es: "Partida", en: "Line" },
  "money.detail.unpriced": { es: "Sin precio aún", en: "Not priced yet" },
  "money.detail.unpricedNote": { es: "{n} registros aún no tienen precio: no cuentan en el gasto.", en: "{n} records are not priced yet: they do not count towards spend." },
  "money.detail.empty": { es: "Nada medido en este periodo.", en: "Nothing measured in this period." },
  "money.detail.error": { es: "No pudimos leer el detalle.", en: "We could not read the detail." },

  // ── Facturación (49.3) ──
  "money.billing.title": { es: "Tu cuenta", en: "Your account" },
  "money.billing.currency": { es: "Moneda de la cuenta", en: "Account currency" },
  "money.billing.hint": {
    es: "Lo que puedes asignar a tus clientes. La moneda de la cuenta la cambia Auphere.",
    en: "What you can assign to your clients. Auphere changes the account currency.",
  },

  // ── «Repartir tu saldo en bolsas» (55.3) ──
  "money.migration.title": { es: "Repartir tu saldo en bolsas", en: "Share your balance into bags" },
  "money.migration.cta": { es: "Repartir tu saldo en bolsas", en: "Share your balance into bags" },
  "money.migration.description": {
    es: "Con la consola nueva, cada cliente tiene su bolsa. Te proponemos lo que le queda este mes a cada uno con su límite de hoy.",
    en: "With the new console, each client has its bag. We propose what each one has left this month under today’s limit.",
  },
  "money.migration.banner": {
    es: "Cada cliente pasa a tener su bolsa. Revisa la propuesta y confírmala. Hasta entonces tus clientes siguen como hoy.",
    en: "Each client now gets its own bag. Review the proposal and confirm it. Until then your clients carry on as today.",
  },
  "money.migration.step1": {
    es: "Mira lo que le queda este mes a cada cliente y, si quieres, cámbialo.",
    en: "See what each client has left this month and change it if you like.",
  },
  "money.migration.step2": { es: "Al confirmar, eso pasa a su bolsa.", en: "When you confirm, that goes into their bag." },
  "money.migration.step3": {
    es: "Después lo cambias cuando quieras desde Consumo con «Cambiar saldo».",
    en: "Afterwards change it whenever you like from Usage with “Change balance”.",
  },
  "money.migration.table": { es: "La propuesta por cliente", en: "The proposal by client" },
  "money.migration.amount": { es: "Pasa a su bolsa", en: "Goes into their bag" },
  "money.migration.proposed": { es: "Le queda este mes", en: "Left this month" },
  "money.migration.adjust": { es: "Lo que pasa a la bolsa de {name}, en {currency}", en: "What goes into {name}’s bag, in {currency}" },
  "money.migration.invalidAdjust": {
    es: "Uno de los importes no vale. Revísalo y vuelve a confirmar.",
    en: "One of the amounts is not valid. Check it and confirm again.",
  },
  "money.migration.total": { es: "Total", en: "Total" },
  "money.migration.until": {
    es: "Hasta que confirmes, tus clientes siguen respondiendo con el límite de hoy.",
    en: "Until you confirm, your clients keep answering under today’s limit.",
  },
  "money.migration.confirm": { es: "Confirmar el reparto", en: "Confirm the split" },
  "money.migration.later": { es: "Ahora no", en: "Not now" },
  "money.migration.ownersOnly": { es: "Lo confirma un owner o un admin de tu equipo.", en: "An owner or an admin of your team confirms it." },
  "money.migration.done": { es: "Listo: {n} clientes tienen ya su bolsa.", en: "Done: {n} clients now have their bag." },
  "money.migration.confirmed.title": { es: "Tu saldo ya está en bolsas", en: "Your balance is already in bags" },
  "money.migration.confirmed.body": { es: "El reparto ya se confirmó. Cada cliente gasta de su bolsa.", en: "The split was already confirmed. Each client spends from its bag." },
  "money.migration.nothing.title": { es: "No hay nada que repartir", en: "There is nothing to share out" },
  "money.migration.nothing.body": { es: "Tus clientes ya usan bolsas. Asígnales saldo desde Consumo.", en: "Your clients already use bags. Assign them balance from Usage." },
  "money.migration.first.title": { es: "Antes, reparte tu saldo en bolsas", en: "First, share your balance into bags" },
  "money.migration.first.body": {
    es: "Tus clientes aún usan el límite de antes. Confirma el reparto y después podrás asignar saldo a cada bolsa.",
    en: "Your clients still use the old limit. Confirm the split and then you can assign balance to each bag.",
  },
  "money.migration.toUsage": { es: "Ir a Consumo", en: "Go to Usage" },
  "money.migration.error": { es: "No pudimos leer la propuesta. Vuelve a intentarlo en un momento.", en: "We could not read the proposal. Try again in a moment." },

  // ── los avisos (49.6): su enlace ──
  "notif.open": { es: "Abrir", en: "Open" },

  // ── el aviso de «Pedir saldo» (45.7) ──
  "notif.kind.client.balance_request": { es: "Te piden saldo para {client}.", en: "Balance requested for {client}." },
  "notif.kind.client.balance_request.note": { es: "Te piden saldo para {client}: «{note}»", en: "Balance requested for {client}: “{note}”" },
  "notif.kind.client.balance_request.by": { es: "{by} pide saldo para {client}.", en: "{by} asks for balance for {client}." },
  "notif.kind.client.balance_request.by.note": { es: "{by} pide saldo para {client}: «{note}»", en: "{by} asks for balance for {client}: “{note}”" },

  // ── errores ──
  "money.error.insufficient": { es: "No hay saldo suficiente en tu cuenta.", en: "There is not enough balance in your account." },
  "money.error.bag_below_spent": { es: "Solo puedes devolver hasta {amount}, lo que le queda.", en: "You can only return up to {amount}, what it has left." },
  "money.error.bag_below_spent.generic": { es: "No puedes devolver más de lo que le queda.", en: "You cannot return more than it has left." },
  "money.error.currency_mismatch": {
    es: "La moneda de su bolsa ha cambiado. Cierra y vuelve a abrir para ver la de ahora.",
    en: "Their bag’s currency changed. Close and open again to see the current one.",
  },
  "money.error.bags_not_active": {
    es: "Antes de asignar, confirma el reparto de tu saldo en bolsas.",
    en: "Before assigning, confirm sharing your balance into bags.",
  },
  "money.error.fx_unavailable": {
    es: "Hoy no tenemos el cambio del BCE. Inténtalo más tarde.",
    en: "We do not have today’s ECB rate. Try again later.",
  },
  "money.error.notFound": { es: "Ese cliente ya no existe.", en: "That client no longer exists." },
  "money.error.generic": { es: "No se pudo hacer. Inténtalo de nuevo.", en: "It could not be done. Try again." },
} as const;
