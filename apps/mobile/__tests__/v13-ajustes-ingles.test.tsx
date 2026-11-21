import { fireEvent, render, screen } from "@testing-library/react-native";
import { Alert } from "react-native";

/**
 * Spec 069, R19.1 and R19.3 in English: the privacy policy the web publishes
 * in English (`/en/privacy`, checked 2026-11-21) and the design's words.
 */
const mockOpen = jest.fn();
jest.mock("expo-localization", () => ({ getLocales: () => [{ languageCode: "en" }], useLocales: () => [{ languageCode: "en" }] }));
jest.mock("@/push/provider", () => ({ usePush: () => ({ permission: "granted", enable: jest.fn() }) }));
jest.mock("@/auth/session", () => ({ useSession: () => ({ signOut: jest.fn() }) }));
jest.mock("@/api/hooks", () => ({
  useMe: () => ({
    data: {
      user: { name: "Valeria Ríos", email: "valeria@flor.test" },
      client: { name: "Flor y Encanto" },
      nav: ["panel", "inbox"],
      agents: [{ id: "a1", name: "Recepción" }],
      channels: [{ kind: "instagram", connected: true }],
      business: { timezone: "America/Santiago", hours: null, hours_label: null },
    },
  }),
  useNotices: () => ({ data: { kinds: ["inbox.waiting"] } }),
}));
jest.mock("@/api/v13-ajustes-hooks", () => ({ useInboxAutoclose: () => ({ state: "ready", hours: null, status: "idle", save: jest.fn() }) }));
jest.mock("@/api/endpoints", () => ({ endpoints: { setNotices: jest.fn(), requestDeletion: jest.fn() } }));
jest.mock("@/api/reservas", () => ({ demo: null }));
jest.mock("@/ui/online", () => ({ useOnline: () => true }));
jest.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ setQueryData: jest.fn() }) }));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: (url: string) => mockOpen(url) }));

const Ajustes = require("@/app/ajustes").default;

it("the English policy, the channel's state and the close choices in English", async () => {
  await render(<Ajustes />);
  await fireEvent.press(screen.getByRole("button", { name: /^Privacy policy/ }));
  expect(mockOpen).toHaveBeenCalledWith("https://www.auphere.com/en/privacy");
  expect(screen.getByLabelText("Instagram: Connected")).toBeTruthy();
  expect(screen.getByText("Recepción answers on all of them")).toBeTruthy();
  expect(screen.getByRole("radio", { name: "Never" }).props.accessibilityState).toMatchObject({ checked: true });
});

it("signing out in the design's words", async () => {
  const alert = jest.spyOn(Alert, "alert");
  await render(<Ajustes />);
  await fireEvent.press(screen.getByRole("button", { name: "Sign out on this phone" }));
  const [title, body] = alert.mock.calls.at(-1)!;
  expect(title).toBe("Sign out?");
  expect(body).toBe("Recepción keeps answering. You stop getting notifications on this phone. Your other phones stay as they are.");
});

it("the urgent notice asks in English", async () => {
  const alert = jest.spyOn(Alert, "alert");
  await render(<Ajustes />);
  await fireEvent(screen.getByRole("switch", { name: "A conversation is waiting for a person" }), "valueChange", false);
  const [title, body, buttons] = alert.mock.calls.at(-1)!;
  expect(title).toBe("Turn off the urgent notice?");
  expect(body).toBe("You won't know on this phone when someone waits for a person.");
  expect((buttons as { text: string }[]).map((b) => b.text)).toEqual(["Keep it on", "Turn off"]);
});
