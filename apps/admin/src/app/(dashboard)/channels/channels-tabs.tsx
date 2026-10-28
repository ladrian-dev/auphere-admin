import { SectionTabs } from "@/components/shell/section-tabs";

const TABS = [
  { href: "/channels", label: "Canales de los clientes" },
  // Spec 047 (T117, 31.5, 54.7).
  { href: "/channels/whatsapp-login", label: "Beta «WhatsApp login»" },
] as const;

/** The views of Canales: every client's channels, and the beta by country. */
export function ChannelsTabs({ current }: { current: (typeof TABS)[number]["href"] }) {
  return <SectionTabs label="Canales" tabs={TABS} current={current} />;
}
