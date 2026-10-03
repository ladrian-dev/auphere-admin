/**
 * What stands between a client and «atendiendo», with the one click that
 * fixes it (spec 016, R2.1/R2.4/R4.4). Pure: no React, no i18n calls — the
 * page translates the keys and gates each link by permission.
 *
 * ``activation`` has no href: the lifecycle buttons on the same card are the
 * action, and they already know the confirmation rules.
 */
import type { ClientHealth } from "@/lib/backend";
import type { Permission } from "@/lib/permissions";

export type MissingKey = "agent" | "whatsapp" | "quota" | "activation";

export type MissingItem = {
  key: MissingKey;
  /** ``clients.detail.missing.*`` — the noun («cupo»). */
  label: `clients.detail.missing.${MissingKey}`;
  /** ``clients.health.fix.*`` — the verb («Asignar cupo»). */
  fix: `clients.health.fix.${MissingKey}`;
  /** Where the fix lives; ``null`` when the action is on the card itself. */
  href: string | null;
  /** Who may follow the link. */
  permission: Permission;
  /** ``quota`` does not block ``ready``; the others do. */
  blocking: boolean;
};

const ORDER: MissingKey[] = ["agent", "whatsapp", "quota", "activation"];

export function isMissingKey(value: string): value is MissingKey {
  return (ORDER as string[]).includes(value);
}

export function missingItems(health: Pick<ClientHealth, "missing">, ref: string): MissingItem[] {
  const base = `/clients/${encodeURIComponent(ref)}`;
  const present = new Set(health.missing.filter(isMissingKey));
  return ORDER.filter((key) => present.has(key)).map((key) => {
    switch (key) {
      case "agent":
        return { key, label: "clients.detail.missing.agent", fix: "clients.health.fix.agent", href: `${base}/agent`, permission: "agents:write", blocking: true };
      case "whatsapp":
        return { key, label: "clients.detail.missing.whatsapp", fix: "clients.health.fix.whatsapp", href: `${base}/channels`, permission: "channels:write", blocking: true };
      case "quota":
        return { key, label: "clients.detail.missing.quota", fix: "clients.health.fix.quota", href: `/usage?client=${encodeURIComponent(ref)}`, permission: "usage:write", blocking: false };
      case "activation":
        return { key, label: "clients.detail.missing.activation", fix: "clients.health.fix.activation", href: null, permission: "clients:write", blocking: true };
    }
  });
}
