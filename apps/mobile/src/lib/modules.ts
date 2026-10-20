import { icons, type IconName } from "@/ui/icon";

/**
 * The client's modules as tabs (spec 031, R3). The list and its order come
 * from the API (`/me.nav`, the same source as the web's sidebar); this only
 * says how a module the app knows is drawn. A module this version does not
 * know is skipped, never painted empty (R3.6).
 */
export type Route = "inicio" | "bandeja" | "consumo";

export const MODULES = {
  panel: { route: "inicio", label: "app.tab.panel", icon: icons.home, selected: { ios: "house.fill", android: "home" } },
  inbox: { route: "bandeja", label: "app.tab.inbox", icon: icons.inbox, selected: { ios: "tray.fill", android: "inbox" } },
  usage: { route: "consumo", label: "app.tab.usage", icon: icons.usage, selected: { ios: "chart.bar.fill", android: "bar_chart" } },
} as const satisfies Record<string, { route: Route; label: string; icon: IconName; selected: IconName }>;

export type KnownModule = keyof typeof MODULES;

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
