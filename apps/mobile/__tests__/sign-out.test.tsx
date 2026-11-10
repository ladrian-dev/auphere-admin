import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as SecureStore from "expo-secure-store";
import { Pressable, Text } from "react-native";

import { emitSessionEvent } from "@/auth/events";
import { SessionProvider, useSession } from "@/auth/session";
import { prepareInstall, readSession, writeSession } from "@/auth/store";

/**
 * Spec 031 (T055, R7.1, R7.2, R11.3): signing out of this phone, and a phone
 * closed from somewhere else.
 */
const mockSignOut = jest.fn(async () => undefined);
jest.mock("@/api/endpoints", () => ({
  endpoints: {
    config: async () => ({ min_version: { ios: "0.0.0", android: "0.0.0" }, reason: null, console_url: "x" }),
    signOut: () => mockSignOut(),
  },
}));
jest.mock("expo-web-browser", () => ({ openAuthSessionAsync: jest.fn() }));
jest.mock("expo-splash-screen", () => ({ hideAsync: jest.fn(async () => undefined), preventAutoHideAsync: jest.fn(async () => undefined) }));

function Probe() {
  const { state, signOut } = useSession();
  return (
    <>
      <Text testID="status">{state.status === "signed-out" ? `out:${state.closedReason ?? ""}` : state.status}</Text>
      <Pressable accessibilityRole="button" onPress={() => void signOut()}>
        <Text>salir</Text>
      </Pressable>
    </>
  );
}

async function signedIn() {
  (SecureStore as unknown as { __store: Map<string, string> }).__store.clear();
  await prepareInstall();
  await writeSession({ phoneId: "p1", accessToken: "a", accessExpiresAt: Date.now() + 3_600_000, refreshToken: "r" });
  await render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { gcTime: Infinity, retry: false } } })}>
      <SessionProvider>
        <Probe />
      </SessionProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByTestId("status").props.children).toBe("signed-in"));
}

it("«Cerrar sesión» tells the API, empties the store and goes back to «Entrar»", async () => {
  await signedIn();
  await fireEvent.press(screen.getByRole("button"));
  await waitFor(() => expect(screen.getByTestId("status").props.children).toBe("out:"));
  expect(mockSignOut).toHaveBeenCalledTimes(1);
  expect(await readSession()).toBeNull();
});

it("a phone_closed from any request lands on «Entrar» with the reason", async () => {
  await signedIn();
  await act(async () => emitSessionEvent({ type: "closed", reason: "member_removed" }));
  expect(screen.getByTestId("status").props.children).toBe("out:member_removed");
});

it("a fresh install does not wake up as whoever had the phone before (R2.3)", async () => {
  (SecureStore as unknown as { __store: Map<string, string> }).__store.set("session", JSON.stringify({ phoneId: "x" }));
  const fs = require("expo-file-system") as { __files: Map<string, string> };
  fs.__files.clear();
  let fresh: typeof prepareInstall = prepareInstall;
  jest.isolateModules(() => {
    fresh = require("@/auth/store").prepareInstall;
  });
  await fresh();
  expect(await SecureStore.getItemAsync("session", {})).toBeNull();
});
