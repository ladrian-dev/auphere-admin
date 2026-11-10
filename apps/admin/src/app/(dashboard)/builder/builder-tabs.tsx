import { SectionTabs } from "@/components/shell/section-tabs";

const TABS = [
  { href: "/builder/sector-tests", label: "Pruebas del sector" },
  { href: "/builder/judge-calibration", label: "Calibración del juez" },
  { href: "/builder/eval", label: "Evaluación" },
  { href: "/builder/sector-guides", label: "Sectores sin guía" },
] as const;

/**
 * Spec 047 (T087, T090, T100): the quality of the agent builder, in three
 * views; T201 (58.5) adds the sectors without an Auphere guide.
 */
export function BuilderTabs({ current }: { current: (typeof TABS)[number]["href"] }) {
  return <SectionTabs label="Constructor" tabs={TABS} current={current} />;
}
