import type { v13InicioEs } from "./v13-inicio.es";

/** Spec 069 — Inicio, English. Every Spanish key must exist here (`tsc` checks it). */
export const v13InicioEn: Record<keyof typeof v13InicioEs, string> = {
  "v13.home.biz.agent": "{business} · {agent} answers",
  "v13.home.biz.agents": "{business} · {n} agents answer",

  "v13.home.tiles": "Today at a glance",
  "v13.home.tile.today": "Today",
  "v13.home.tile.today.unit": "bookings",
  "v13.home.tile.today.unit.one": "booking",
  "v13.home.tile.today.next": "Next {time} · {name}",
  "v13.home.tile.today.none": "No more today",
  "v13.home.tile.today.empty": "No bookings today",
  "v13.home.tile.today.unconfirmed": "{n} unconfirmed",
  "v13.home.tile.today.inside": "of {capacity} inside now",
  "v13.home.tile.conversations.unit": "in 7 days",
  "v13.home.tile.conversations.unread": "{n} unread",
  "v13.home.tile.conversations.unread.one": "1 unread",
  "v13.home.tile.conversations.allRead": "Nothing unread",
  "v13.home.tile.conversations.none": "Nobody wrote yet this week",
  "v13.home.tile.balance": "Balance",
  "v13.home.tile.balance.months": "About {n} months left",
  "v13.home.tile.balance.days": "About {n} days left",
  "v13.home.tile.balance.day": "1 day left",
  "v13.home.tile.balance.lessThanDay": "Less than a day left",
  "v13.home.tile.month": "This month",
  "v13.home.tile.month.since": "Since {month} 1",

  "v13.home.latest": "Latest in the Inbox",
  "v13.home.latest.empty": "When someone writes to your business, their latest conversations show up here.",
  "v13.home.latest.error": "We couldn't load the Inbox.",
  "v13.home.latest.loading": "Loading the Inbox",
  "v13.home.preview.agent": "{agent}: {text}",
  "v13.home.preview.person": "{name}: {text}",

  "v13.home.wait.group": "Waits for a person",
  "v13.home.wait.since": "Waits for a person · {time}",
  "v13.home.wait.more": "{text} · +{n} more",
  "v13.home.wait.attend": "Answer {name}",

  "v13.home.calm.title": "All in order",
  "v13.home.calm.body": "Nobody is waiting for a person and the balance lasts the month.",
  "v13.home.calm.body.noBalance": "Nobody is waiting for a person.",
};
