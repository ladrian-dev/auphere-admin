/** Spec 069 — Inicio: the app's own words, Spanish. Spread into `app.es.ts`. */
export const v13InicioEs = {
  // The business and who answers (R8.1): the agent's name comes from `/me.agents`, never from a text.
  "v13.home.biz.agent": "{business} · {agent} atiende",
  "v13.home.biz.agents": "{business} · {n} agentes atienden",

  // The four tiles (R8.1, R8.2)
  "v13.home.tiles": "Resumen del día",
  "v13.home.tile.today": "Hoy",
  "v13.home.tile.today.unit": "reservas",
  "v13.home.tile.today.unit.one": "reserva",
  "v13.home.tile.today.next": "Siguiente {time} · {name}",
  "v13.home.tile.today.none": "No quedan más hoy",
  "v13.home.tile.today.empty": "Sin reservas hoy",
  "v13.home.tile.today.unconfirmed": "{n} sin confirmar",
  "v13.home.tile.today.inside": "de {capacity} dentro ahora",
  "v13.home.tile.conversations.unit": "en 7 días",
  "v13.home.tile.conversations.unread": "{n} sin leer",
  "v13.home.tile.conversations.unread.one": "1 sin leer",
  "v13.home.tile.conversations.allRead": "Nada sin leer",
  "v13.home.tile.conversations.none": "Aún nadie escribió esta semana",
  "v13.home.tile.balance": "Saldo",
  "v13.home.tile.balance.months": "Para unos {n} meses",
  "v13.home.tile.balance.days": "Para unos {n} días",
  "v13.home.tile.balance.day": "Para 1 día",
  "v13.home.tile.balance.lessThanDay": "Para menos de un día",
  "v13.home.tile.month": "Este mes",
  "v13.home.tile.month.since": "Desde el 1 de {month}",

  // «Lo último en la Bandeja» (R8.3)
  "v13.home.latest": "Lo último en la Bandeja",
  "v13.home.latest.empty": "Cuando alguien escriba a tu negocio, aquí verás sus últimas conversaciones.",
  "v13.home.latest.error": "No pudimos cargar la Bandeja.",
  "v13.home.latest.loading": "Cargando la Bandeja",
  "v13.home.preview.agent": "{agent}: {text}",
  "v13.home.preview.person": "{name}: {text}",

  // Whoever waits for a person (R8.4)
  "v13.home.wait.group": "Espera a una persona",
  "v13.home.wait.since": "Espera a una persona · hace {time}",
  "v13.home.wait.more": "{text} · +{n} más",
  "v13.home.wait.attend": "Atender a {name}",

  // The calm card (R8.5, micro 8)
  "v13.home.calm.title": "Todo en orden",
  "v13.home.calm.body": "Nadie espera a una persona y el saldo alcanza para el mes.",
  "v13.home.calm.body.noBalance": "Nadie espera a una persona.",
} as const;
