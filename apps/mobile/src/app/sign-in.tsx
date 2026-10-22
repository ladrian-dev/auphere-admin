import { Image } from "expo-image";
import { router } from "expo-router";
import { useRef, useState, type ComponentRef } from "react";
import { StyleSheet, TextInput, View } from "react-native";

import { useAppConfig } from "@/api/hooks";
import { useSession } from "@/auth/session";
import type { SignInOutcome } from "@/auth/sign-in";
import { EntryFrame, EntryNotice } from "@/features/entry";
import { useT, type MessageKey } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { useTheme } from "@/theme/theme";
import { Button, IconButton } from "@/ui/button";
import { Field } from "@/ui/field";
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

/**
 * «Entrar» (spec 031, R1 as amended on 2026-10-20): the app's own way in. The
 * email and password the system can fill, or Google — with the account of the
 * email Auphere gave access to. A closed session lands here with its reason
 * (R7.2); every failed attempt says what happened, in place (R1.9).
 */
export default function SignIn() {
  const t = useT();
  const online = useOnline();
  const config = useAppConfig();
  const { colors } = useTheme();
  const { state, signInWithPassword, signInWithGoogle } = useSession();
  const passwordRef = useRef<ComponentRef<typeof TextInput>>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState<"password" | "google" | null>(null);
  const [message, setMessage] = useState<MessageKey | null>(null);

  const closed = state.status === "signed-out" && state.closedReason ? (CLOSED[state.closedReason] ?? "app.closed.unknown") : null;
  const shown = message ?? (online ? closed : "app.signIn.offline");
  const google = config.data?.sign_in.google === true;

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
    if (!online) return setMessage("app.signIn.offline");
    const address = email.trim();
    if (!address || !password) {
      haptics.warning();
      return setMessage("app.signIn.missing");
    }
    setBusy("password");
    setMessage(null);
    const outcome = await signInWithPassword(address, password);
    setBusy(null);
    // The password stays: a typo is fixed in place (with «Mostrar»), not typed again.
    await settle(outcome);
  }

  async function withGoogle() {
    if (!online) return setMessage("app.signIn.offline");
    setBusy("google");
    setMessage(null);
    const outcome = await signInWithGoogle();
    setBusy(null);
    await settle(outcome);
  }

  return (
    <EntryFrame
      title={t("app.signIn.title")}
      body={t("app.signIn.body")}
      notice={shown ? <EntryNotice text={t(shown)} tone={DANGER.has(shown) ? "danger" : "info"} /> : null}
    >
      <Field
        label={t("app.signIn.email")}
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
      <Field
        ref={passwordRef}
        label={t("app.signIn.password")}
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
            onPress={() => setReveal((v) => !v)}
          />
        }
      />
      <Button
        label={busy === "password" ? t("app.signIn.busy") : t("app.signIn.cta")}
        accessibilityLabel={t("app.signIn.cta")}
        busy={busy === "password"}
        disabled={busy === "google"}
        full
        onPress={() => void withPassword()}
        testID="sign-in"
      />
      <Button
        label={t("app.signIn.forgot")}
        variant="ghost"
        full
        disabled={busy !== null}
        onPress={() => router.push({ pathname: "/forgot-password", params: { email: email.trim() } })}
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
            leading={<Image source={require("@/assets/images/google-g.png")} style={styles.mark} contentFit="contain" accessible={false} />}
            onPress={() => void withGoogle()}
            testID="sign-in-google"
          />
          {/* Which account, and whom to ask (spec 044, R15.2): said before the window opens, not after it fails. */}
          <Text variant="footnote" tone="mutedForeground" style={styles.center}>
            {t("avisos.signIn.googleNote")}
          </Text>
        </>
      ) : null}
      <Text variant="footnote" tone="mutedForeground" style={styles.center}>
        {t("app.signIn.footnote")}
      </Text>
    </EntryFrame>
  );
}

const styles = StyleSheet.create({
  or: { flexDirection: "row", alignItems: "center", gap: 12 },
  rule: { flex: 1, height: StyleSheet.hairlineWidth },
  mark: { width: 18, height: 18 },
  center: { textAlign: "center" },
});
