/** ES/EN del carril `ads` — la pestaña «Anuncios» de un cliente en la consola de
 *  partners (spec 076, requisito 3): qué anuncios traen conversaciones y reservas.
 *  La pestaña (`clients.v2.tab.ads`) vive en el carril `business`. Sin punto y
 *  coma (`words.test.ts`). */
export const adsMessages = {
  "ads.page.title": { es: "Anuncios", en: "Ads" },
  "ads.title": { es: "Anuncios que traen clientes", en: "Ads that bring customers" },
  "ads.intro": {
    es: "Las conversaciones que empezaron desde un anuncio de clic a WhatsApp y las reservas que hizo el agente en ellas.",
    en: "Conversations that started from a click-to-WhatsApp ad and the bookings the agent made in them.",
  },
  "ads.loading": { es: "Cargando el informe de anuncios", en: "Loading the ads report" },
  "ads.period": { es: "Periodo", en: "Period" },
  "ads.period.days": { es: "{n} días", en: "{n} days" },
  "ads.col.ad": { es: "Anuncio", en: "Ad" },
  "ads.col.conversations": { es: "Conversaciones", en: "Conversations" },
  "ads.col.bookings": { es: "Reservas", en: "Bookings" },
  "ads.col.amount": { es: "Importe", en: "Amount" },
  "ads.help.conversations": {
    es: "Conversaciones: conversaciones que empezaron desde el anuncio en el periodo.",
    en: "Conversations: conversations that started from the ad in the period.",
  },
  "ads.help.bookings": {
    es: "Reservas: reservas que hizo el agente en el periodo, sin las canceladas, de personas cuyo último anuncio antes de reservar fue este.",
    en: "Bookings: bookings the agent made in the period, cancelled ones left out, by people whose last ad before booking was this one.",
  },
  "ads.unnamed.ad": { es: "Anuncio sin titular", en: "Ad without a headline" },
  "ads.unnamed.post": { es: "Publicación sin titular", en: "Post without a headline" },
  "ads.opens": { es: "se abre en otra pestaña", en: "opens in a new tab" },
  "ads.empty.title": {
    es: "Ninguna conversación ha llegado de un anuncio en estos días",
    en: "No conversation has come from an ad in these days",
  },
  "ads.empty.hint": {
    es: "El informe se llena solo cuando alguien escribe desde un anuncio de clic a WhatsApp de este cliente.",
    en: "The report fills on its own when someone writes from one of this client’s click-to-WhatsApp ads.",
  },
  "ads.error": { es: "No se pudo cargar el informe de anuncios", en: "We could not load the ads report" },
  "ads.error.hint": { es: "No se ha cambiado nada. Vuelve a intentarlo en un momento.", en: "Nothing has changed. Try again in a moment." },
  "ads.retry": { es: "Reintentar", en: "Try again" },
} as const;
