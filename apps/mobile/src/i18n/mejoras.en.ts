import type { mejorasEs } from "./mejoras.es";

/** Spec 044 (mejoras), English. Every Spanish key must exist here (`tsc` checks it). */
export const mejorasEn: Record<keyof typeof mejorasEs, string> = {
  "app.contact.next": "Next booking",
  "app.contact.next.value": "{day} at {time} · {label}",
  "app.contact.next.hint": "Opens the booking in Bookings",
  "app.usage.runsOut": "It lasts until {date}",
  "app.usage.runsOut.pace": "At the pace of the last 7 days.",
  "app.usage.recharge.auphere": "To top up, talk to whoever manages your business at Auphere.",
  "app.usage.recharge.partner": "To top up, talk to {name}.",
  "app.usage.spend.title": "Spend over the last {days} days",
};
