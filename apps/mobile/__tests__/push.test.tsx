import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { ensureCategories } from "@/push/categories";
import { CHANNELS, ensureChannels } from "@/push/channels";
import { setOpenConversation, shouldPresent } from "@/push/handler";
import { registerDevice } from "@/push/register";
import { routeFor } from "@/push/routing";
import { redirectSystemPath } from "@/app/+native-intent";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 031 (T089, R8.6, R8.7, R8.9, R8.10, R8.12, R10.1): normal notices on
 * the phone.
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);
const mockRegister = jest.fn(async (..._args: unknown[]) => undefined);
jest.mock("@/api/endpoints", () => ({ endpoints: { registerPush: (...a: unknown[]) => mockRegister(...a) } }));
jest.mock("expo-notifications", () => ({
  AndroidImportance: { HIGH: 4, DEFAULT: 3 },
  AndroidNotificationVisibility: { PRIVATE: 0 },
  setNotificationChannelAsync: jest.fn(async () => null),
  setNotificationCategoryAsync: jest.fn(async () => null),
  getDevicePushTokenAsync: jest.fn(async () => ({ type: "ios", data: "apns-token-1" })),
  requestPermissionsAsync: jest.fn(async () => ({ granted: true, canAskAgain: true })),
}));

const ID = "6f1c1b7e-2a2b-4c4d-8e8f-000000000001";

describe("channels and categories", () => {
  it("Android: one PRIVATE channel per kind, with the API's ids", async () => {
    Platform.OS = "android";
    await ensureChannels(t);
    expect(CHANNELS.map((c) => c.id)).toEqual(["waiting_v1", "messages_v1", "balance_v1"]);
    for (const c of CHANNELS) {
      expect(Notifications.setNotificationChannelAsync).toHaveBeenCalledWith(c.id, expect.objectContaining({ lockscreenVisibility: 0 }));
    }
  });

  it("iOS: categories with a neutral placeholder and no actions (nothing is answered from a notice)", async () => {
    Platform.OS = "ios";
    await ensureCategories(t);
    const calls = (Notifications.setNotificationCategoryAsync as jest.Mock).mock.calls;
    expect(calls.map((c) => c[0])).toEqual(["inbox_waiting", "inbox_message", "client_balance"]);
    for (const [, actions, options] of calls) {
      expect(actions).toEqual([]);
      expect(options.previewPlaceholder).toBeTruthy();
    }
  });
});

describe("the device token", () => {
  it("is registered with its provider, and again when the system rotates it", async () => {
    Platform.OS = "ios";
    await registerDevice();
    expect(mockRegister).toHaveBeenLastCalledWith(expect.objectContaining({ provider: "apns", token: "apns-token-1" }));
    await registerDevice({ type: "ios", data: "apns-token-2" });
    expect(mockRegister).toHaveBeenLastCalledWith(expect.objectContaining({ token: "apns-token-2" }));
  });
});

describe("in front and on tap", () => {
  it("the open conversation's own notice is not shown; any other is", () => {
    setOpenConversation(ID);
    expect(shouldPresent({ url: `auphere-customers://inbox/${ID}` }, "active")).toBe(false);
    expect(shouldPresent({ url: "auphere-customers://inbox/6f1c1b7e-2a2b-4c4d-8e8f-000000000002" }, "active")).toBe(true);
    expect(shouldPresent({ url: "auphere-customers://usage" }, "active")).toBe(true);
    expect(shouldPresent({ url: `auphere-customers://inbox/${ID}` }, "background")).toBe(true);
    setOpenConversation(null);
  });

  it("a tap opens the conversation or Consumo, and nothing it does not know", () => {
    // Above the tabs, like any chat: the composer owns the bottom of the screen.
    expect(routeFor({ url: `auphere-customers://inbox/${ID}` })).toBe(`/conversacion/${ID}`);
    expect(routeFor({ url: "auphere-customers://usage" })).toBe("/consumo");
    expect(routeFor({ url: "https://evil.example/x" })).toBeNull();
    expect(routeFor({ url: "auphere-customers://inbox/../../ajustes" })).toBeNull();
  });

  it("a link the system hands the app lands on the same screens, and an unknown one goes home", () => {
    expect(redirectSystemPath({ path: `auphere-customers://inbox/${ID}`, initial: true })).toBe(`/conversacion/${ID}`);
    expect(redirectSystemPath({ path: "auphere-customers://inbox", initial: false })).toBe("/bandeja");
    expect(redirectSystemPath({ path: "auphere-customers://usage", initial: true })).toBe("/consumo");
    expect(redirectSystemPath({ path: "auphere-customers://auth/callback?code=x", initial: false })).toBe("/sign-in");
    expect(redirectSystemPath({ path: "auphere-customers://nada", initial: true })).toBe("/");
  });
});

describe("the permission screen (R10.1)", () => {
  const mockEnable = jest.fn(async () => "granted");
  const mockBack = jest.fn();
  jest.mock("@/push/provider", () => ({ usePush: () => ({ permission: "undetermined", enable: mockEnable }) }));
  jest.mock("@/api/hooks", () => ({ useMe: () => ({ data: { nav: ["panel", "inbox"] } }) }));
  jest.mock("expo-router", () => ({ router: { back: () => mockBack(), canGoBack: () => true } }));
  jest.mock("expo-image", () => ({ Image: () => null }));

  it("explains first, «Ahora no» does not open the system dialog, and says how to hide previews", async () => {
    const Screen = require("@/app/notices-permission").default;
    await render(<Screen />);
    expect(screen.getByText("Una conversación espera a una persona")).toBeTruthy();
    expect(screen.getByText(/Mostrar previsualizaciones/)).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Ahora no" }));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockEnable).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByRole("button", { name: "Activar avisos" }));
    await waitFor(() => expect(mockEnable).toHaveBeenCalled());
  });
});
