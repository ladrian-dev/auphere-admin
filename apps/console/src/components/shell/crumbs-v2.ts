import type { MessageKey } from "@/i18n/messages";

/**
 * Spec 047 (R47.1; `01` §1.4) — las migas de la consola nueva, como función
 * pura de la ruta. El último elemento nunca es un enlace (`href: null`).
 *
 * Los nombres (un cliente, un agente, un canal) los anuncia su página con
 * `<CrumbName>`; mientras no llegan, la miga del cliente usa su referencia
 * (que el partner eligió y reconoce) y la del agente, la palabra «Agente».
 * Un uuid nunca sale en pantalla.
 *
 * Un cliente se lee «Clientes › {cliente}» en todas sus pestañas; un agente,
 * «Clientes › {cliente} › {agente}», y pulsar el cliente lleva a su pestaña
 * Agentes, de donde se viene.
 */
export type CrumbLabel = { key: MessageKey; vars?: Record<string, string> } | { text: string };
export type Crumb = { href: string | null; label: CrumbLabel };

/** Las secciones de primer nivel y su nombre. */
const SECTION: Record<string, MessageKey> = {
  usage: "nav.usage",
  audit: "nav.audit",
  knowledge: "nav.knowledge",
  workstation: "nav.workstation",
  team: "nav.team",
  billing: "nav.billing",
  keys: "nav.keys",
  notifications: "notif.title",
};

/** Subpáginas con nombre propio dentro de una sección. */
const SUBPAGE: Record<string, Record<string, MessageKey>> = {
  usage: { alerts: "shell.crumbs.usageAlerts", repartir: "money.migration.title" },
};

function decode(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function lastIsHere(crumbs: Crumb[]): Crumb[] {
  const last = crumbs[crumbs.length - 1];
  if (last) crumbs[crumbs.length - 1] = { ...last, href: null };
  return crumbs;
}

export function crumbsFor(pathname: string, names: Readonly<Record<string, string>>): Crumb[] {
  const segments = pathname.split("/").filter(Boolean);
  const [first, ...rest] = segments;
  if (!first) return [{ href: null, label: { key: "nav.home" } }];

  if (first === "clients") {
    const out: Crumb[] = [{ href: "/clients", label: { key: "nav.clients" } }];
    const [ref, tab, agentId, sub, channelId] = rest;
    if (!ref) return lastIsHere(out);
    if (ref === "new") return lastIsHere([...out, { href: null, label: { key: "shell.crumbs.newClient" } }]);
    const base = `/clients/${ref}`;
    const client: CrumbLabel = { text: names[decode(ref)] ?? decode(ref) };
    if (tab !== "agents" || !agentId) return lastIsHere([...out, { href: base, label: client }]);

    out.push({ href: `${base}/agents`, label: client });
    const agentName = names[decode(agentId)];
    out.push({ href: `${base}/agents/${agentId}`, label: agentName ? { text: agentName } : { key: "shell.crumbs.agent" } });
    if (sub === "channels" && channelId) {
      const channel = names[decode(channelId)];
      out.push({
        href: null,
        label: channel ? { key: "shell.crumbs.channel", vars: { name: channel } } : { key: "shell.crumbs.channelUnnamed" },
      });
    }
    return lastIsHere(out);
  }

  const section = SECTION[first];
  if (!section) return [];
  const out: Crumb[] = [{ href: `/${first}`, label: { key: section } }];
  const subpage = rest[0] ? SUBPAGE[first]?.[rest[0]] : undefined;
  if (subpage) out.push({ href: null, label: { key: subpage } });
  return lastIsHere(out);
}
