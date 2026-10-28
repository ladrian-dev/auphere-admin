import type { NoticeKind } from "@/api/endpoints";
import type { MessageKey } from "@/i18n/t";
import { icons, type IconName } from "@/ui/icon";

/**
 * The kinds of notice (031 R8.1; spec 044, R14.1, R14.2; spec 047, T170),
 * grouped by the module they come from, and which ones a person can get: the
 * inbox ones only with the Bandeja (031 R9.3), Reservas' only with Reservas,
 * the agents' only with Agentes. Same words in the
 * permission screen and in Ajustes.
 */
export type NoticeGroup = "inbox" | "reservas" | "agents" | "balance";

export type NoticeKindInfo = { kind: NoticeKind; group: NoticeGroup; label: MessageKey; hint: MessageKey; icon: IconName; needs: string | null };

export const NOTICE_KINDS: NoticeKindInfo[] = [
  { kind: "inbox.waiting", group: "inbox", label: "app.notices.kind.inbox.waiting", hint: "app.notices.kind.inbox.waiting.hint", icon: icons.hand, needs: "inbox" },
  {
    kind: "inbox.message_for_you",
    group: "inbox",
    label: "app.notices.kind.inbox.message_for_you",
    hint: "app.notices.kind.inbox.message_for_you.hint",
    icon: icons.chat,
    needs: "inbox",
  },
  {
    kind: "reservas.agent_change",
    group: "reservas",
    label: "avisos.kind.reservations.changed",
    hint: "avisos.kind.reservations.changed.hint",
    icon: icons.calendar,
    needs: "reservas",
  },
  {
    kind: "reservas.cancelled_today",
    group: "reservas",
    label: "avisos.kind.reservations.cancelled_today",
    hint: "avisos.kind.reservations.cancelled_today.hint",
    icon: icons.calendar,
    needs: "reservas",
  },
  {
    // Off unless the API says on (R14.2): it is the one most people do not need.
    kind: "reservas.waitlist_accepted",
    group: "reservas",
    label: "avisos.kind.reservations.waitlist_accepted",
    hint: "avisos.kind.reservations.waitlist_accepted.hint",
    icon: icons.waitlist,
    needs: "reservas",
  },
  {
    // Spec 047 (T170, events.md §3.1): on from the start, and switched on in the phones that existed (API migration).
    kind: "agents.state",
    group: "agents",
    label: "avisos.kind.agents.state",
    hint: "avisos.kind.agents.state.hint",
    icon: icons.bot,
    needs: "agents",
  },
  { kind: "client.balance", group: "balance", label: "app.notices.kind.client.balance", hint: "app.notices.kind.client.balance.hint", icon: icons.wallet, needs: null },
];

export const NOTICE_GROUPS: { group: NoticeGroup; label: MessageKey }[] = [
  { group: "inbox", label: "avisos.group.inbox" },
  { group: "reservas", label: "avisos.group.reservas" },
  { group: "agents", label: "avisos.group.agents" },
  { group: "balance", label: "avisos.group.balance" },
];

export function kindsFor(modules: readonly string[]) {
  return NOTICE_KINDS.filter((k) => k.needs === null || modules.includes(k.needs));
}

/** The kinds a person can get, by group, in the order Ajustes shows them; empty groups are left out. */
export function groupsFor(modules: readonly string[]): { group: NoticeGroup; label: MessageKey; kinds: NoticeKindInfo[] }[] {
  const kinds = kindsFor(modules);
  return NOTICE_GROUPS.map((g) => ({ ...g, kinds: kinds.filter((k) => k.group === g.group) })).filter((g) => g.kinds.length > 0);
}

/**
 * The permission screen's lines (R14.4): the inbox kinds one by one, Reservas'
 * three said as one, and the balance — what the design shows before asking.
 */
export function permissionLines(modules: readonly string[]): { key: string; label: MessageKey; hint: MessageKey; icon: IconName }[] {
  const out: { key: string; label: MessageKey; hint: MessageKey; icon: IconName }[] = [];
  for (const g of groupsFor(modules)) {
    if (g.group === "reservas") out.push({ key: "reservas", label: "avisos.permission.reservas", hint: "avisos.permission.reservas.hint", icon: icons.calendar });
    else out.push(...g.kinds.map((k) => ({ key: k.kind, label: k.label, hint: k.hint, icon: k.icon })));
  }
  return out;
}
