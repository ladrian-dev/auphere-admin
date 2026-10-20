import { QueryClientProvider } from "@tanstack/react-query";
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo, useState } from "react";
import { Platform } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { makeQueryClient, wireQueryManagers } from "@/api/query";
import { SessionProvider, useSession } from "@/auth/session";
import { useHeaderOptions } from "@/features/tab-stack";
import { useT } from "@/i18n/t";
import { PushProvider } from "@/push/provider";
import { SHEET_RADIUS, useTheme } from "@/theme/theme";
import { ActionsProvider } from "@/ui/actions";

void SplashScreen.preventAutoHideAsync().catch(() => undefined);

/**
 * A link opened with the app closed (`auphere-customers://inbox/<id>`) lands on
 * its conversation with `index` beneath it, so «atrás» goes to the person's
 * first module instead of out of the app.
 */
export const unstable_settings = { anchor: "index" };

/**
 * Auphere Customers (spec 031). The providers, and which screens exist for
 * the state of the session: an update gate (R13), the signed-in app, or the
 * way in (R1). Flipping a guard moves the person to `index`, which sends them
 * where they belong — no screen that should not be there stays reachable.
 */
export default function RootLayout() {
  const [client] = useState(makeQueryClient);
  useEffect(() => wireQueryManagers(), []);
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <KeyboardProvider>
        <QueryClientProvider client={client}>
          <SessionProvider>
            <Themed>
              <ActionsProvider>
                <PushProvider>
                  <Screens />
                </PushProvider>
              </ActionsProvider>
            </Themed>
          </SessionProvider>
        </QueryClientProvider>
        </KeyboardProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

/** React Navigation's theme from the app's tokens, so native headers and sheets match. */
function Themed({ children }: { children: React.ReactNode }) {
  const { scheme, colors } = useTheme();
  const theme = useMemo(() => {
    const base = scheme === "dark" ? DarkTheme : DefaultTheme;
    return {
      ...base,
      colors: {
        ...base.colors,
        primary: colors.primaryText,
        background: colors.background,
        card: colors.card,
        text: colors.foreground,
        border: colors.border,
        notification: colors.danger,
      },
    };
  }, [scheme, colors]);
  return (
    <ThemeProvider value={theme}>
      <StatusBar style={scheme === "dark" ? "light" : "dark"} />
      {children}
    </ThemeProvider>
  );
}

function Screens() {
  const { state } = useSession();
  const t = useT();
  const header = useHeaderOptions();
  if (state.status === "booting") return null; // the splash stays up
  const update = state.status === "update-required";
  const signedIn = state.status === "signed-in";
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Protected guard={update}>
        <Stack.Screen name="update-required" options={{ gestureEnabled: false }} />
      </Stack.Protected>
      <Stack.Protected guard={!update && signedIn}>
        <Stack.Screen name="(app)" />
        {/* A conversation opens above the tabs; its contact is a sheet over it (R12). */}
        <Stack.Screen name="conversacion/[id]/index" options={{ ...header, headerShown: true, title: "" }} />
        <Stack.Screen
          name="conversacion/[id]/contacto"
          options={{
            presentation: "formSheet",
            sheetAllowedDetents: [0.6, 1],
            sheetGrabberVisible: true,
            // Android draws it square; iOS keeps the system's own corners.
            sheetCornerRadius: Platform.OS === "android" ? SHEET_RADIUS : undefined,
            headerShown: false,
          }}
        />
        <Stack.Screen
          name="ajustes"
          options={{
            ...header,
            headerShown: true,
            title: t("app.settings"),
            presentation: Platform.OS === "ios" ? "modal" : "card",
          }}
        />
        <Stack.Screen name="notices-permission" options={{ presentation: "modal", gestureEnabled: false }} />
      </Stack.Protected>
      <Stack.Protected guard={!update && !signedIn}>
        <Stack.Screen name="sign-in" />
        <Stack.Screen name="forgot-password" />
        <Stack.Screen name="not-a-client" />
        <Stack.Screen name="no-access" />
      </Stack.Protected>
    </Stack>
  );
}
