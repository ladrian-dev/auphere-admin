/**
 * The panel's breadcrumb trail, worked out from the address alone. Pure, so
 * it is tested on its own; the names of records (a client, a partner, a
 * channel) come from the pages that know them, through `crumb-names`.
 *
 * The trail lives in the top bar and the page title says what the page is,
 * so nothing is said twice: no slug in capitals, no «Cliente» over the name.
 */
export type Crumb = { label: string; href: string | null };

/** Top-level sections, as the sidebar names them. */
const SECTION: Record<string, string> = {
  partners: "Partners",
  tenants: "Clientes",
  signups: "Altas",
  tickets: "Tickets",
  channels: "Canales",
  connectors: "Conectores",
  qa: "Playground QA",
  status: "Estado",
};

/** Tabs and sub-pages, by the section they hang from. */
const CHILD: Record<string, Record<string, string>> = {
  tenants: {
    agent: "Agente",
    capabilities: "Habilidades",
    playground: "Playground",
    conversations: "Conversaciones",
    channels: "Canales",
    connectors: "Conectores",
    backchannel: "Canal del dueño",
    access: "Acceso",
    isolation: "Aislamiento",
    billing: "Facturación",
    audit: "Auditoría",
  },
  partners: {
    clients: "Clientes",
    team: "Equipo",
    modules: "Módulos",
    money: "Dinero",
    settings: "Configuración",
    knowledge: "Conocimiento",
    audit: "Auditoría",
  },
};

const NEW_LABEL: Record<string, string> = {
  tenants: "Nuevo cliente",
  partners: "Nuevo partner",
  channels: "Añadir canal",
};

const CHANNEL_NAME: Record<string, string> = {
  whatsapp: "WhatsApp",
  tiktok: "TikTok",
  instagram: "Instagram",
  telegram: "Telegram",
  x: "X",
  threads: "Threads",
};

export function crumbsFor(pathname: string, names: Record<string, string>): Crumb[] {
  const segs = pathname.split("/").filter(Boolean).map(decodeURIComponent);
  if (segs.length === 0) return [{ label: "Panel", href: null }];
  // `/auphere/channels` is one place: the platform's own numbers.
  if (segs[0] === "auphere") return [{ label: "Números de Auphere", href: null }];

  const out: Crumb[] = [];
  const href = (i: number) => `/${segs.slice(0, i + 1).map(encodeURIComponent).join("/")}`;
  const name = (seg: string, fallback: string) => names[seg] ?? fallback;
  const section = segs[0]!;
  out.push({ label: SECTION[section] ?? section, href: href(0) });

  for (let i = 1; i < segs.length; i++) {
    const seg = segs[i]!;
    const parent = segs[i - 1]!;
    if (seg === "new") {
      out.push({ label: NEW_LABEL[parent] ?? "Nuevo", href: href(i) });
      continue;
    }
    if (i === 1) {
      // The record under a section: a client, a partner, a ticket, a connector.
      const fallback = section === "tickets" ? "Ticket" : section === "connectors" ? seg : "…";
      out.push({ label: name(seg, fallback), href: href(i) });
      continue;
    }
    if (section === "qa") {
      // `/qa/{client}/chat`: the chat is the client's playground, not a step.
      if (seg === "chat") continue;
      out.push({ label: name(seg, "…"), href: href(i) });
      continue;
    }
    const tab = CHILD[section]?.[seg];
    if (tab && i === 2) {
      out.push({ label: tab, href: href(i) });
      continue;
    }
    if (parent === "new" && segs[i - 2] === "channels") {
      out.push({ label: CHANNEL_NAME[seg] ?? seg, href: href(i) });
      // The wizard's own rail says which step this is.
      break;
    }
    if (parent === "conversations") {
      out.push({ label: "Conversación", href: href(i) });
      continue;
    }
    out.push({ label: name(seg, parent === "channels" ? "Canal" : seg), href: href(i) });
  }
  out[out.length - 1] = { ...out[out.length - 1]!, href: null };
  return out;
}
