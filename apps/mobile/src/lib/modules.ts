import { icons, type IconName } from "@/ui/icon";

/**
 * The client's modules as tabs (spec 031, R3). The list and its order come
 * from the API (`/me.nav`, the same source as the web's sidebar); this only
 * says how a module the app knows is drawn. A module this version does not
 * know is skipped, never painted empty (R3.6).
 */
export type Route = "inicio" | "bandeja" | "reservas" | "consumo";

export const MODULES = {
  panel: { route: "inicio", label: "app.tab.panel", icon: icons.home, selected: { ios: "house.fill", android: "home" } },
  inbox: { route: "bandeja", label: "app.tab.inbox", icon: icons.inbox, selected: { ios: "tray.fill", android: "inbox" } },
  // Spec 044, R1.1: the calendar of each platform; SF Symbols has no filled calendar, so it stays the same when selected.
  reservas: { route: "reservas", label: "app.tab.reservas", icon: icons.calendar, selected: icons.calendar },
  usage: { route: "consumo", label: "app.tab.usage", icon: icons.usage, selected: { ios: "chart.bar.fill", android: "bar_chart" } },
} as const satisfies Record<string, { route: Route; label: string; icon: IconName; selected: IconName }>;

export type KnownModule = keyof typeof MODULES;

/**
 * The tab bar stays whole while scrolling (spec 042, H22, R1.5). Minimized, iOS
 * 26 shows only the current tab, so the Bandeja's badge disappears, and with
 * real drags the bar only came back at the very top.
 */
export const TAB_BAR_MINIMIZE = "never" as const;

/**
 * The tab labels at the bar's own size on iOS (spec 044, R16.3, D13; 042 H25):
 * left to the phone's text size they grew and were clipped, and with four tabs
 * they lost their baseline. Apple's bar does not scale its labels either — the
 * large content viewer is its accessible alternative. Android's bar scales in
 * sp by itself.
 */
export function tabLabelStyle(os: string, pass = 0): { fontSize: number; fontWeight: "500" } | undefined {
  // `pass` re-sends the style when the tabs show again (see `useTabRelayout`): a
  // hundredth of a point the eye cannot see, enough for the bar to lay out anew.
  return os === "ios" ? { fontSize: 10 + (pass % 2) * 0.01, fontWeight: "500" } : undefined;
}

export function knownModules(nav: readonly string[]): KnownModule[] {
  return nav.filter((m): m is KnownModule => m in MODULES).filter((m, i, all) => all.indexOf(m) === i);
}

/** Where a person lands: the first module, in the API's order. */
export function firstRoute(nav: readonly string[]): `/${Route}` | null {
  const first = knownModules(nav)[0];
  return first ? `/${MODULES[first].route}` : null;
}

/** The triggers in the order to declare them: the visible ones in `nav` order, then the rest hidden. */
export function tabPlan(nav: readonly string[]): { module: KnownModule; hidden: boolean }[] {
  const visible = knownModules(nav);
  const rest = (Object.keys(MODULES) as KnownModule[]).filter((m) => !visible.includes(m));
  return [...visible.map((module) => ({ module, hidden: false })), ...rest.map((module) => ({ module, hidden: true }))];
}
