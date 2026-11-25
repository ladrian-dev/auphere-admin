/** ES/EN of the public «Pago recibido» page (spec 077, 7.9). Spread in `i18n/messages.ts`. */
export const paymentReturnMessages = {
  "payReturn.title.paid": { es: "Pago recibido", en: "Payment received" },
  "payReturn.body.paid": {
    es: "La membresía queda activa en unos segundos. Puedes cerrar esta página.",
    en: "The membership becomes active in a few seconds. You can close this page.",
  },
  "payReturn.title.canceled": { es: "No se completó el pago", en: "The payment was not completed" },
  "payReturn.body.canceled": {
    es: "No se cobró nada. Si quieres pagar, vuelve a abrir el enlace que te enviaron.",
    en: "Nothing was charged. To pay, open the link you were sent again.",
  },
} as const;
