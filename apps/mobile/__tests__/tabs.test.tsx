import { render, renderHook, screen } from "@testing-library/react-native";
import { Platform } from "react-native";

import { firstRoute, knownModules, tabPlan } from "@/lib/modules";
import { tokens } from "@/theme/tokens.gen";
import { type } from "@/theme/type";

let mockGlass = false;
jest.mock("expo-glass-effect", () => ({ isLiquidGlassAvailable: () => mockGlass }));
jest.mock("expo-router", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  function Toolbar(p: { children?: React.ReactNode; placement?: string }) {
    return <RN.View testID={`toolbar-${p.placement}`}>{p.children}</RN.View>;
  }
  Toolbar.Button = function ToolbarButton(p: { accessibilityLabel?: string; icon?: string }) {
    return <RN.View testID="toolbar-button" accessibilityLabel={p.accessibilityLabel} accessibilityHint={p.icon} />;
  };
  Toolbar.Menu = function ToolbarMenu(p: { children?: React.ReactNode }) {
    return <RN.View testID="toolbar-menu">{p.children}</RN.View>;
  };
  Toolbar.MenuAction = function ToolbarMenuAction() {
    return null;
  };
  return { Stack: { Toolbar, Screen: () => null }, router: { push: jest.fn() } };
});

describe("the header on iOS 26 (spec 042, T060, T061, R1.1, R1.4, R3.1, R4.6)", () => {
  const { useHeaderOptions, useTabStackOptions, SettingsToolbar } = require("@/features/tab-stack") as typeof import("@/features/tab-stack");

  it("with glass available the header has no background of its own; without it, today's", async () => {
    mockGlass = true;
    const glass = (await renderHook(() => useHeaderOptions())).result.current as Record<string, unknown>;
    expect(glass.headerStyle).toBeUndefined();
    expect(glass.headerLargeStyle).toBeUndefined();
    expect(glass.contentStyle).toBeUndefined();
    expect(glass.headerTintColor).toBe(tokens.light.primaryText);
    mockGlass = false;
    const plain = (await renderHook(() => useHeaderOptions())).result.current as Record<string, { backgroundColor?: string }>;
    expect(plain.headerStyle?.backgroundColor).toBe(tokens.light.background);
    expect(plain.headerLargeStyle?.backgroundColor).toBe(tokens.light.background);
  });

  it("iOS: large titles on the tabs and the settings button as a native bar button", async () => {
    mockGlass = true;
    const opts = (await renderHook(() => useTabStackOptions())).result.current as Record<string, unknown>;
    expect(opts.headerLargeTitleEnabled).toBe(true);
    expect(opts.headerRight).toBeUndefined();
    await render(<SettingsToolbar />);
    expect(screen.getByTestId("toolbar-right")).toBeTruthy();
    expect(screen.getByTestId("toolbar-button").props.accessibilityLabel).toBe("Abrir ajustes");
  });

  it("Android: the title's size follows the type scale and the settings button stays in headerRight", async () => {
    const os = jest.replaceProperty(Platform, "OS", "android");
    const opts = (await renderHook(() => useTabStackOptions())).result.current as Record<string, unknown>;
    expect((opts.headerTitleStyle as { fontSize?: number }).fontSize).toBe(type.title.fontSize);
    expect(opts.headerRight).toBeDefined();
    await render(<SettingsToolbar />);
    expect(screen.queryByTestId("toolbar-right")).toBeNull();
    os.restore();
  });
});

/**
 * Spec 031 (T043, R3.1–R3.7): the tabs are the client's modules, in the API's
 * order, from `/me.nav` — never a fixed list in the app.
 */
describe("tabs from /me.nav", () => {
  it("follow the order of nav", () => {
    expect(tabPlan(["usage", "panel", "inbox"]).map((t) => t.module)).toEqual(["usage", "panel", "inbox"]);
    expect(tabPlan(["inbox", "panel"]).filter((t) => !t.hidden).map((t) => t.module)).toEqual(["inbox", "panel"]);
  });

  it("declare the absent modules too, hidden and last (native tabs cannot be added later)", () => {
    expect(tabPlan(["panel"])).toEqual([
      { module: "panel", hidden: false },
      { module: "inbox", hidden: true },
      { module: "usage", hidden: true },
    ]);
  });

  it("with one module there is one visible tab — the layout hides the bar", () => {
    expect(tabPlan(["usage"]).filter((t) => !t.hidden)).toHaveLength(1);
  });

  it("ignore a module this version does not know, without an empty tab", () => {
    expect(knownModules(["bookings", "panel"])).toEqual(["panel"]);
    expect(tabPlan(["bookings", "panel"]).map((t) => t.module)).not.toContain("bookings");
  });

  it("land on the first module of nav", () => {
    expect(firstRoute(["inbox", "panel"])).toBe("/bandeja");
    expect(firstRoute(["usage"])).toBe("/consumo");
  });

  it("a different nav is a different key: the bar remounts on the first module (R3.3, R3.5)", () => {
    const key = (nav: string[]) => knownModules(nav).join(",");
    expect(key(["panel", "inbox", "usage"])).not.toBe(key(["panel", "usage"]));
    expect(firstRoute(["panel", "usage"])).toBe("/inicio");
  });

  it("no module the app can show is no access (R3.7)", () => {
    expect(firstRoute([])).toBeNull();
    expect(firstRoute(["bookings"])).toBeNull();
  });
});
