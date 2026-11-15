import { SectionTabs } from "@/components/shell/section-tabs";

const TABS = [
  { href: "/channels", label: "Canales de los clientes" },
  // Spec 047 (T117, 31.5, 54.7).
  { href: "/channels/whatsapp-login", label: "Beta «WhatsApp login»" },
] as const;

/**
 * The views of Canales: every client's channels, and the beta by country.
 * Spec 059 (5.3): the beta only when the deployment has Meta's configuration
 * for it (`beta`); without it the tab is not there at all.
 */
export function ChannelsTabs({ current, beta }: { current: (typeof TABS)[number]["href"]; beta: boolean }) {
  const tabs = beta ? TABS : TABS.filter((t) => t.href !== "/channels/whatsapp-login");
  return <SectionTabs label="Canales" tabs={tabs} current={current} />;
}
