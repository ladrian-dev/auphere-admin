import { SectionTabs } from "@/components/shell/section-tabs";

const TABS = [
  { href: "/builder/sector-tests", label: "Pruebas del sector" },
  { href: "/builder/judge-calibration", label: "Calibración del juez" },
  { href: "/builder/eval", label: "Evaluación" },
] as const;

/** Spec 047 (T087, T090, T100): the quality of the agent builder, in three views. */
export function BuilderTabs({ current }: { current: (typeof TABS)[number]["href"] }) {
  return <SectionTabs label="Constructor" tabs={TABS} current={current} />;
}
