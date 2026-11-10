import { fireEvent, render, screen } from "@testing-library/react-native";
import { Platform } from "react-native";

import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 042 (T062, T065, R1.4, R2.9): on iOS the conversation's menu is the
 * system's own bar menu, with «Devolver al agente» first (031 R6.7). Android
 * keeps the action sheet behind a headerRight button.
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);

jest.mock("expo-router", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  function Toolbar(p: { children?: React.ReactNode; placement?: string }) {
    return <RN.View testID={`toolbar-${p.placement}`}>{p.children}</RN.View>;
  }
  Toolbar.Button = function ToolbarButton(p: { accessibilityLabel?: string; onPress?: () => void }) {
    return <RN.Pressable testID="toolbar-button" accessibilityRole="button" accessibilityLabel={p.accessibilityLabel} onPress={p.onPress} />;
  };
  Toolbar.Menu = function ToolbarMenu(p: { children?: React.ReactNode; accessibilityLabel?: string }) {
    return (
      <RN.View testID="toolbar-menu" accessibilityLabel={p.accessibilityLabel}>
        {p.children}
      </RN.View>
    );
  };
  Toolbar.MenuAction = function ToolbarMenuAction(p: { children?: string; onPress?: () => void; disabled?: boolean; destructive?: boolean }) {
    return (
      <RN.Pressable testID="toolbar-menu-action" accessibilityRole="menuitem" accessibilityLabel={p.children} accessibilityState={{ disabled: !!p.disabled }} onPress={p.onPress}>
        <RN.Text>{p.children}</RN.Text>
      </RN.Pressable>
    );
  };
  return { Stack: { Toolbar, Screen: () => null }, router: { push: jest.fn(), back: jest.fn() } };
});

const { ConversationToolbar } = require("@/features/inbox/thread/toolbar") as typeof import("@/features/inbox/thread/toolbar");

const actions = () => ({ onGiveBack: jest.fn(), onContact: jest.fn(), onUnread: jest.fn(), onResolve: jest.fn(), onReopen: jest.fn() });

it("iOS, answering: the menu starts with «Devolver a <agente>», then the contact, unread and resolve", async () => {
  const a = actions();
  await render(<ConversationToolbar mine agentName="Recepción" resolved={false} online {...a} />);
  expect(screen.getByTestId("toolbar-right")).toBeTruthy();
  const items = screen.getAllByTestId("toolbar-menu-action").map((n) => n.props.accessibilityLabel);
  expect(items[0]).toBe("Devolver a Recepción");
  expect(items).toEqual(["Devolver a Recepción", t("inbox.action.panel"), t("inbox.action.unread"), t("inbox.action.resolve")]);
  await fireEvent.press(screen.getAllByTestId("toolbar-menu-action")[0]!);
  expect(a.onGiveBack).toHaveBeenCalled();
});

it("iOS, not answering: no «Devolver»; resolved offers «Reabrir»; offline disables what writes", async () => {
  const a = actions();
  await render(<ConversationToolbar mine={false} agentName={null} resolved online={false} {...a} />);
  const items = screen.getAllByTestId("toolbar-menu-action");
  expect(items.map((n) => n.props.accessibilityLabel)).toEqual([t("inbox.action.panel"), t("inbox.action.unread"), t("inbox.action.reopen")]);
  expect(items[0]!.props.accessibilityState.disabled).toBe(false);
  expect(items[1]!.props.accessibilityState.disabled).toBe(true);
  expect(items[2]!.props.accessibilityState.disabled).toBe(true);
});

it("Android: nothing in the toolbar — the headerRight button and the action sheet stay", async () => {
  const os = jest.replaceProperty(Platform, "OS", "android");
  await render(<ConversationToolbar mine agentName="Recepción" resolved={false} online {...actions()} />);
  expect(screen.queryByTestId("toolbar-right")).toBeNull();
  os.restore();
});

describe("the conversation's title in the bar (spec 042, R4.6, H24)", () => {
  const { ConversationTitle } = require("@/features/inbox/thread/toolbar") as typeof import("@/features/inbox/thread/toolbar");

  it("iOS: the inline title stays at its size, as Apple's own do — the bar cannot grow", async () => {
    await render(<ConversationTitle name="Lucía Fernández" line="Nadie la atiende todavía" hint="Datos del contacto" onPress={jest.fn()} />);
    expect(screen.getByText("Lucía Fernández").props.maxFontSizeMultiplier).toBe(1);
    expect(screen.getByText("Nadie la atiende todavía").props.maxFontSizeMultiplier).toBe(1);
  });

  it("Android: it grows with the text size, up to what the 64 dp bar holds", async () => {
    const os = jest.replaceProperty(Platform, "OS", "android");
    const onPress = jest.fn();
    await render(<ConversationTitle name="Lucía Fernández" line="Nadie la atiende todavía" hint="Datos del contacto" onPress={onPress} />);
    expect(screen.getByText("Lucía Fernández").props.maxFontSizeMultiplier).toBe(1.3);
    await fireEvent.press(screen.getByRole("button", { name: "Lucía Fernández. Nadie la atiende todavía" }));
    expect(onPress).toHaveBeenCalled();
    os.restore();
  });
});
