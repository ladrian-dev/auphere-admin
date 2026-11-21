import { Image } from "expo-image";
import { router } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { use, useRef, useState, type ComponentRef } from "react";
import { StyleSheet, TextInput, View, useWindowDimensions } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { SafeAreaInsetsContext } from "react-native-safe-area-context";

import { useAppConfig } from "@/api/hooks";
import { useSession } from "@/auth/session";
import type { SignInOutcome } from "@/auth/sign-in";
import { EntryNotice } from "@/features/entry";
import { EntryField } from "@/features/entry/entry-field";
import { LiquidHero } from "@/features/entry/liquid-backdrop";
import { useT, type MessageKey } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { RADII, themeFor, useTheme } from "@/theme/theme";
import { GoogleMark } from "@/ui/brand-icons";
import { Button, IconButton } from "@/ui/button";
import { icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { Text } from "@/ui/text";

const CLOSED: Record<string, MessageKey> = {
  signed_out: "app.closed.signed_out",
  closed_by_person: "app.closed.closed_by_person",
  closed_by_auphere: "app.closed.closed_by_auphere",
  access_disabled: "app.closed.access_disabled",
  member_removed: "app.closed.member_removed",
  password_reset: "app.closed.password_reset",
  abandoned: "app.closed.abandoned",
  refresh_reused: "app.closed.refresh_reused",
};

/** What a finished attempt says on this screen (R1.2, R1.3, R1.9). `null`: it moved on. */
export function messageFor(outcome: SignInOutcome["kind"]): MessageKey | null {
  switch (outcome) {
    case "cancelled":
      return "app.signIn.cancelled";
    case "offline":
      return "app.signIn.offline";
    case "invalid-credentials":
      return "app.signIn.invalid";
    case "rate-limited":
      return "app.signIn.rateLimited";
    case "google-mismatch":
      return "app.signIn.googleMismatch";
    case "google-unavailable":
      return "app.signIn.googleUnavailable";
    case "failed":
      return "app.signIn.failed";
    default:
      return null;
  }
}

const DANGER = new Set<MessageKey>(["app.signIn.failed", "app.signIn.invalid", "app.signIn.googleMismatch"]);

/** The design's check (§3.1): something@something.something. The API decides the rest. */
const EMAIL = /^\S+@\S+\.\S+$/;

type FieldErrors = { email: MessageKey | null; password: MessageKey | null };

/** What each field lacks (spec 069, R5.4). The screen shows it only after the first attempt. */
export function fieldErrors(email: string, password: string): FieldErrors {
  return {
    email: EMAIL.test(email.trim()) ? null : "v13.entrar.error.email",
    password: password ? null : "v13.entrar.error.password",
  };
}

/**
 * «Entrar» (spec 031, R1 as amended on 2026-10-20; spec 069, R5): the app's
 * own way in, on the living liquid of the console's sign-in. The email and
 * password the system can fill, or Google — with the account of the email
 * Auphere gave access to. A closed session lands here with its reason (R7.2);
 * every failed attempt says what happened, in the card (R1.9).
 *
 * Each field's error goes under it, and only once the person has tried
 * (R5.4); from then on it follows what is typed. Without a connection the
 * card says so and nothing is tried (R5.5).
 */
export default function SignIn() {
  const t = useT();
  const online = useOnline();
  const config = useAppConfig();
  const { colors } = useTheme();
  const { height } = useWindowDimensions();
  // The insets without demanding a provider (a screen rendered alone, in a test, has none: 0).
  const insets = use(SafeAreaInsetsContext) ?? { top: 0, bottom: 0, left: 0, right: 0 };
  const { state, signInWithPassword, signInWithGoogle } = useSession();
  const emailRef = useRef<ComponentRef<typeof TextInput>>(null);
  const passwordRef = useRef<ComponentRef<typeof TextInput>>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState<"password" | "google" | null>(null);
  const [message, setMessage] = useState<MessageKey | null>(null);

  const closed = state.status === "signed-out" && state.closedReason ? (CLOSED[state.closedReason] ?? "app.closed.unknown") : null;
  const shown = message ?? (online ? closed : "app.signIn.offline");
  const google = config.data?.sign_in.google === true;
  const errors = tried ? fieldErrors(email, password) : { email: null, password: null };

  async function settle(outcome: SignInOutcome) {
    if (outcome.kind === "ok") {
      haptics.success();
      return;
    }
    if (outcome.kind === "not-a-client") return router.push("/not-a-client");
    if (outcome.kind === "no-access") return router.push("/no-access");
    const next = messageFor(outcome.kind);
    if (next) {
      if (outcome.kind !== "cancelled") haptics.warning();
      setMessage(next);
    }
  }

  async function withPassword() {
    if (!online) {
      haptics.warning();
      return setMessage("app.signIn.offline");
    }
    setTried(true);
    const wrong = fieldErrors(email, password);
    if (wrong.email || wrong.password) {
      haptics.warning();
      setMessage(null);
      // Straight to the first field to fix; its error is read with it.
      (wrong.email ? emailRef : passwordRef).current?.focus();
      return;
    }
    setBusy("password");
    setMessage(null);
    const outcome = await signInWithPassword(email.trim(), password);
    setBusy(null);
    // The password stays: a typo is fixed in place (with «Mostrar»), not typed again.
    await settle(outcome);
  }

  async function withGoogle() {
    if (!online) {
      haptics.warning();
      return setMessage("app.signIn.offline");
    }
    haptics.light();
    setBusy("google");
    setMessage(null);
    const outcome = await signInWithGoogle();
    setBusy(null);
    await settle(outcome);
  }

  // The hero is the brand's dark ground in both themes: what sits on it uses the dark palette.
  const onHero = themeFor("dark").colors;
  const heroMin = Math.round(Math.min(420, Math.max(300, height * 0.45)));

  return (
    <View style={[styles.fill, { backgroundColor: colors.background }]}>
      {/* Light status bar over the dark hero; the screens pushed on top set their own. */}
      <StatusBar style="light" />
      <KeyboardAwareScrollView
        contentContainerStyle={styles.scroll}
        bounces={false}
        bottomOffset={112}
        keyboardShouldPersistTaps="handled"
        testID="entry-scroll"
      >
        <LiquidHero style={{ minHeight: heroMin }}>
          {/* Under the status bar the liquid goes on; the brand starts below it. */}
          <View style={[styles.hero, { paddingTop: insets.top + 12 }]}>
            <View style={styles.brand} accessible accessibilityLabel={t("v13.entrar.brand")}>
              <Image
                source={require("@/assets/images/mark.png")}
                tintColor={onHero.highlight}
                style={styles.mark}
                contentFit="contain"
                accessibilityIgnoresInvertColors
                accessible={false}
              />
              <Text variant="sheetTitle" style={{ color: onHero.foreground }} importantForAccessibility="no">
                {t("v13.entrar.brand")}
              </Text>
            </View>
            <Text variant="screenTitle" accessibilityRole="header" style={[styles.headline, { color: onHero.foreground }]}>
              {t("v13.entrar.headline")}
            </Text>
          </View>
        </LiquidHero>
        <View style={[styles.card, { backgroundColor: colors.background, paddingBottom: insets.bottom + 16 }]} testID="entry-card">
          {shown ? <EntryNotice text={t(shown)} tone={shown === "app.signIn.offline" ? "offline" : DANGER.has(shown) ? "danger" : "info"} /> : null}
          <EntryField
            ref={emailRef}
            label={t("app.signIn.email")}
            icon={icons.mail}
            error={errors.email ? t(errors.email) : null}
            value={email}
            onChangeText={setEmail}
            autoComplete="email"
            textContentType="username"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="next"
            submitBehavior="submit"
            onSubmitEditing={() => passwordRef.current?.focus()}
            editable={busy === null}
            testID="sign-in-email"
          />
          <EntryField
            ref={passwordRef}
            label={t("app.signIn.password")}
            icon={icons.lock}
            error={errors.password ? t(errors.password) : null}
            value={password}
            onChangeText={setPassword}
            secureTextEntry={!reveal}
            autoComplete="current-password"
            textContentType="password"
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="go"
            onSubmitEditing={() => void withPassword()}
            editable={busy === null}
            testID="sign-in-password"
            trailing={
              <IconButton
                icon={reveal ? icons.hide : icons.show}
                label={reveal ? t("app.signIn.hide") : t("app.signIn.show")}
                tone="mutedForeground"
                onPress={() => {
                  haptics.select();
                  setReveal((v) => !v);
                }}
              />
            }
          />
          {/* A text button whose label lines up with the fields above it. */}
          <View style={styles.forgot}>
            <Button
              label={t("app.signIn.forgot")}
              variant="ghost"
              compact
              disabled={busy !== null}
              onPress={() => router.push({ pathname: "/forgot-password", params: { email: email.trim() } })}
            />
          </View>
          <Button
            label={busy === "password" ? t("app.signIn.busy") : t("app.signIn.cta")}
            accessibilityLabel={t("app.signIn.cta")}
            busy={busy === "password"}
            disabled={busy === "google"}
            full
            onPress={() => void withPassword()}
            testID="sign-in"
          />
          {google ? (
            <>
              <View style={styles.or} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
                <View style={[styles.rule, { backgroundColor: colors.border }]} />
                <Text variant="footnote" tone="mutedForeground">
                  {t("app.signIn.or")}
                </Text>
                <View style={[styles.rule, { backgroundColor: colors.border }]} />
              </View>
              <Button
                label={t("app.signIn.google")}
                variant="secondary"
                full
                busy={busy === "google"}
                disabled={busy === "password"}
                leading={<GoogleMark size={20} />}
                onPress={() => void withGoogle()}
                testID="sign-in-google"
              />
              {/* Which account, and whom to ask (spec 044, R15.2): said before the window opens, not after it fails. */}
              <Text variant="footnote" tone="mutedForeground" style={styles.center}>
                {t("avisos.signIn.googleNote")}
              </Text>
            </>
          ) : (
            <Text variant="footnote" tone="mutedForeground" style={styles.center}>
              {t("app.signIn.footnote")}
            </Text>
          )}
        </View>
      </KeyboardAwareScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  scroll: { flexGrow: 1 },
  // The card rises 28 pt over the hero; the headline keeps clear of it.
  hero: { flex: 1, justifyContent: "space-between", paddingHorizontal: 24, paddingBottom: 56, gap: 24 },
  brand: { flexDirection: "row", alignItems: "center", gap: 10, alignSelf: "flex-start" },
  mark: { width: 32, height: 32 },
  headline: { maxWidth: 330 },
  card: {
    flexGrow: 1,
    marginTop: -28,
    borderTopLeftRadius: RADII.sheet,
    borderTopRightRadius: RADII.sheet,
    borderCurve: "continuous",
    paddingHorizontal: 20,
    paddingTop: 24,
    gap: 16,
  },
  forgot: { alignItems: "flex-start", marginLeft: -12, marginVertical: -8 },
  or: { flexDirection: "row", alignItems: "center", gap: 12 },
  rule: { flex: 1, height: StyleSheet.hairlineWidth },
  center: { textAlign: "center" },
});
