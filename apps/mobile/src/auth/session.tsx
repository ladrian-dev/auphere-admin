import { useQueryClient } from "@tanstack/react-query";
import * as SplashScreen from "expo-splash-screen";
import { createContext, use, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AppState } from "react-native";

import { endSession, loadSession, startSession } from "@/api/client";
import { endpoints } from "@/api/endpoints";
import { APP_VERSION, PLATFORM } from "@/config";
import { useLocale } from "@/i18n/t";
import { isOlder } from "@/lib/version";

import { onSessionEvent } from "./events";
import { signInWithGoogle as runGoogle, signInWithPassword as runPassword, type SignInOutcome } from "./sign-in";
import { prepareInstall } from "./store";

/**
 * The session of this phone (spec 031, R1, R2, R7, R13), as one small state
 * machine the root layout reads to decide which screens exist:
 *
 * booting → signed-out | signed-in | update-required
 *
 * - **closed** from the network (`phone_closed`) lands on «Entrar» with the
 *   reason, and drops everything cached about the business (R7.1).
 * - **update-required** blocks the app until it is updated (R13.1); the
 *   minimum is re-read on every return to the foreground (R13.2).
 */
export type SessionState =
  | { status: "booting" }
  | { status: "signed-out"; closedReason: string | null }
  | { status: "signed-in" }
  | { status: "update-required"; reason: string | null };

type SessionApi = {
  state: SessionState;
  signInWithPassword: (email: string, password: string) => Promise<SignInOutcome>;
  signInWithGoogle: () => Promise<SignInOutcome>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<SessionApi | null>(null);

const CONFIG_EVERY_MS = 5 * 60_000;

async function minimumReached(): Promise<{ blocked: boolean; reason: string | null }> {
  try {
    const config = await endpoints.config();
    const minimum = (config.min_version as Record<string, string | undefined>)[PLATFORM];
    return { blocked: isOlder(APP_VERSION, minimum), reason: config.reason ?? null };
  } catch {
    // No network at launch: let the person in; the API still refuses an old version per request.
    return { blocked: false, reason: null };
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "booting" });
  const installId = useRef<string | null>(null);
  const lastConfig = useRef(0);
  const queryClient = useQueryClient();
  const locale = useLocale();

  useEffect(() => {
    let alive = true;
    void (async () => {
      installId.current = await prepareInstall();
      const [session, gate] = await Promise.all([loadSession(), minimumReached()]);
      lastConfig.current = Date.now();
      if (!alive) return;
      setState(
        gate.blocked
          ? { status: "update-required", reason: gate.reason }
          : session
            ? { status: "signed-in" }
            : { status: "signed-out", closedReason: null },
      );
      void SplashScreen.hideAsync().catch(() => undefined);
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(
    () =>
      onSessionEvent((e) => {
        if (e.type === "closed") {
          queryClient.clear();
          setState({ status: "signed-out", closedReason: e.reason ?? "unknown" });
        } else {
          setState({ status: "update-required", reason: e.reason });
        }
      }),
    [queryClient],
  );

  // R13.2: a raised minimum reaches a running app the next time it comes forward.
  useEffect(() => {
    const sub = AppState.addEventListener("change", (s) => {
      if (s !== "active" || Date.now() - lastConfig.current < CONFIG_EVERY_MS) return;
      lastConfig.current = Date.now();
      void minimumReached().then((gate) => {
        if (gate.blocked) setState({ status: "update-required", reason: gate.reason });
      });
    });
    return () => sub.remove();
  }, []);

  /** The end of either way in: the same for the password and for Google. */
  const finish = useCallback(
    async (outcome: SignInOutcome) => {
      if (outcome.kind === "ok") {
        queryClient.clear();
        await startSession(outcome.session);
        setState({ status: "signed-in" });
      } else if (outcome.kind === "update-required") {
        setState({ status: "update-required", reason: outcome.reason });
      }
      return outcome;
    },
    [queryClient],
  );

  const signInWithPassword = useCallback(
    async (email: string, password: string) => {
      const id = installId.current ?? (await prepareInstall());
      return finish(await runPassword(email, password, id, locale));
    },
    [finish, locale],
  );

  const signInWithGoogle = useCallback(async () => {
    const id = installId.current ?? (await prepareInstall());
    return finish(await runGoogle(id, locale));
  }, [finish, locale]);

  const signOut = useCallback(async () => {
    // The API first, so the phone stops getting notifications; locally in any case (R7.1).
    await endpoints.signOut().catch(() => undefined);
    await endSession();
    queryClient.clear();
    setState({ status: "signed-out", closedReason: null });
  }, [queryClient]);

  const value = useMemo(
    () => ({ state, signInWithPassword, signInWithGoogle, signOut }),
    [state, signInWithPassword, signInWithGoogle, signOut],
  );
  return <Ctx value={value}>{children}</Ctx>;
}

export function useSession(): SessionApi {
  const ctx = use(Ctx);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}
