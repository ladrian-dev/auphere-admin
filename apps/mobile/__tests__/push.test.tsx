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
    expect(CHANNELS.map((c) => c.id)).toEqual(["waiting_v1", "messages_v1", "balance_v1", "reservations_v1"]);
    // Spec 044 (R14.6): Reservas' notices are not urgent — the system's default importance.
    expect(CHANNELS.find((c) => c.id === "reservations_v1")?.importance).toBe(Notifications.AndroidImportance.DEFAULT);
    for (const c of CHANNELS) {
      expect(Notifications.setNotificationChannelAsync).toHaveBeenCalledWith(c.id, expect.objectContaining({ lockscreenVisibility: 0 }));
    }
  });

  it("iOS: categories with a neutral placeholder and no actions (nothing is answered from a notice)", async () => {
    Platform.OS = "ios";
    await ensureCategories(t);
    const calls = (Notifications.setNotificationCategoryAsync as jest.Mock).mock.calls;
    expect(calls.map((c) => c[0])).toEqual(["inbox_waiting", "inbox_message", "client_balance", "reservations"]);
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

  it("a Reservas notice opens that reservation on its day (spec 044, R14.5), and is not a conversation", () => {
    // 043 §1: the push carries `auphere-customers://reservas/{booking_id}`; the sheet reads the booking by id.
    const url = "auphere-customers://reservas/r-2026-10-23-17";
    expect(routeFor({ url })).toBe("/reservas?open=r-2026-10-23-17");
    expect(routeFor({ url: "auphere-customers://reservations/r1" })).toBeNull();
    expect(routeFor({ url: "auphere-customers://reservations/r1?date=mañana" })).toBeNull();
    expect(routeFor({ url: "auphere-customers://reservations/../ajustes?date=2026-10-23" })).toBeNull();
    setOpenConversation("r-2026-10-23-17");
    expect(shouldPresent({ url }, "active")).toBe(true);
    setOpenConversation(null);
  });

  it("a link the system hands the app lands on the same screens, and an unknown one goes home", () => {
    expect(redirectSystemPath({ path: `auphere-customers://inbox/${ID}`, initial: true })).toBe(`/conversacion/${ID}`);
    expect(redirectSystemPath({ path: "auphere-customers://inbox", initial: false })).toBe("/bandeja");
    // Spec 044, R14.5 (043 §1): a Reservas link from the system opens that reservation.
    expect(redirectSystemPath({ path: "auphere-customers://reservas/r-42", initial: true })).toBe("/reservas?open=r-42");
    expect(redirectSystemPath({ path: "auphere-customers://reservas/r-42?date=2026-10-23", initial: true })).toBe("/reservas?date=2026-10-23&open=r-42");
    expect(redirectSystemPath({ path: "auphere-customers://reservas?date=2026-13-99", initial: true })).toBe("/reservas");
    expect(redirectSystemPath({ path: "auphere-customers://usage", initial: true })).toBe("/consumo");
    expect(redirectSystemPath({ path: "auphere-customers://auth/callback?code=x", initial: false })).toBe("/sign-in");
    expect(redirectSystemPath({ path: "auphere-customers://nada", initial: true })).toBe("/");
  });
});

describe("the permission screen (R10.1)", () => {
  const mockEnable = jest.fn(async () => "granted");
  const mockBack = jest.fn();
  jest.mock("@/push/provider", () => ({ usePush: () => ({ permission: "undetermined", enable: mockEnable }) }));
  let mockNav = ["panel", "inbox"];
  jest.mock("@/api/hooks", () => ({ useMe: () => ({ data: { nav: mockNav } }) }));
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

  it("shows an example notice first, and one line per kind of what the client has (spec 044, R14.4)", async () => {
    mockNav = ["panel", "inbox", "reservas", "usage"];
    const Screen = require("@/app/notices-permission").default;
    await render(<Screen />);
    expect(screen.getByLabelText(/^Ejemplo de aviso: Lucía Fernández espera a una persona/)).toBeTruthy();
    expect(screen.getByText("Cambios en las reservas de hoy")).toBeTruthy();
    expect(screen.getByText("Saldo bajo o agotado")).toBeTruthy();
    mockNav = ["panel", "inbox"];
  });

  it("without Reservas, no line about it", async () => {
    const Screen = require("@/app/notices-permission").default;
    await render(<Screen />);
    expect(screen.queryByText("Cambios en las reservas de hoy")).toBeNull();
  });

  it("«Ahora no» is pinned under what scrolls, never below the fold (closes 042 H15)", async () => {
    const { within } = require("@testing-library/react-native");
    const Screen = require("@/app/notices-permission").default;
    await render(<Screen />);
    const scroll = screen.getByTestId("entry-scroll");
    const foot = screen.getByTestId("entry-footer");
    expect(within(scroll).queryByRole("button", { name: "Ahora no" })).toBeNull();
    expect(within(foot).getByRole("button", { name: "Ahora no" })).toBeTruthy();
    expect(within(foot).getByRole("button", { name: "Activar avisos" })).toBeTruthy();
    // The privacy note still reads, inside what scrolls.
    expect(within(scroll).getByText(/Mostrar previsualizaciones/)).toBeTruthy();
  });
});
