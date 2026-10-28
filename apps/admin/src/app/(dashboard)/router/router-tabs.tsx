import { SectionTabs } from "@/components/shell/section-tabs";

const TABS = [
  { href: "/router", label: "Perfiles y vista previa" },
  { href: "/router/anomalies", label: "Anomalías" },
] as const;

/** Spec 047 (T150): the two views of the router. */
export function RouterTabs({ current }: { current: (typeof TABS)[number]["href"] }) {
  return <SectionTabs label="Router" tabs={TABS} current={current} />;
}
