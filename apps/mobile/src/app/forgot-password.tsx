import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState, type ComponentRef, type ReactNode } from "react";
import { StyleSheet, TextInput, View } from "react-native";

import { endpoints } from "@/api/endpoints";
import { EntryFrame, EntryNotice } from "@/features/entry";
import { EntryField } from "@/features/entry/entry-field";
import { useT, type MessageKey, type T } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { RADII, useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Icon, icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { Text } from "@/ui/text";

/** How long before another link can be asked for (R6.2): enough not to fill the mailbox. */
export const RESEND_AFTER_S = 30;

/** «0:30», «0:05»: the countdown as the design writes it. */
export function countdown(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * «¿Olvidaste tu contraseña?» (spec 031, R1.7; spec 069, R6). Sends the link
 * to create a new one — the page that opens is the web's — and then says where
 * it went: «Revisa tu correo» with the address written, «Cambiar» to fix it,
 * what comes next, and another link after 30 s with the countdown in sight.
 *
 * It says the same whether or not the email has access (spec 011, R1.3):
 * this screen cannot tell anyone who is registered, so it never claims a link
 * was sent — only that one was, if that address has access.
 */
export default function ForgotPassword() {
  const t = useT();
  const online = useOnline();
  const params = useLocalSearchParams<{ email?: string }>();
  const field = useRef<ComponentRef<typeof TextInput>>(null);
  const [email, setEmail] = useState(typeof params.email === "string" ? params.email : "");
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<MessageKey | null>(null);
  /** The address the last link went to, and when: the second screen exists while this is set. */
  const [sent, setSent] = useState<{ to: string; at: number } | null>(null);
  const [resent, setResent] = useState(false);

  const missing = tried && !email.trim() ? t("app.forgot.missing") : null;

  async function request(address: string): Promise<boolean> {
    if (!online) {
      haptics.warning();
      setMessage("app.signIn.offline");
      return false;
    }
    setBusy(true);
    setMessage(null);
    try {
      await endpoints.passwordReset(address);
      haptics.success();
      return true;
    } catch {
      haptics.warning();
      setMessage("app.forgot.failed");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    setTried(true);
    const address = email.trim();
    if (!address) {
      haptics.warning();
      field.current?.focus();
      return;
    }
    if (await request(address)) {
      setResent(false);
      setSent({ to: address, at: Date.now() });
    }
  }

  async function resend() {
    if (!sent) return;
    if (await request(sent.to)) {
      setResent(true);
      setSent({ to: sent.to, at: Date.now() });
    }
  }

  function change() {
    haptics.light();
    setSent(null);
    setMessage(null);
    setResent(false);
    // Back on the form, straight into the address to fix it.
    setTimeout(() => field.current?.focus(), 0);
  }

  const notice = message ? (
    <EntryNotice text={t(message)} tone={message === "app.signIn.offline" ? "offline" : message === "app.forgot.failed" ? "danger" : "info"} />
  ) : null;

  if (sent) {
    return <Sent t={t} to={sent.to} at={sent.at} busy={busy} resent={resent} notice={notice} onChange={change} onResend={() => void resend()} />;
  }

  return (
    <EntryFrame
      title={t("app.forgot.title")}
      body={t("v13.entrar.forgot.body")}
      onBack={() => router.back()}
      notice={notice}
      footer={<Button label={t("app.forgot.cta")} busy={busy} full onPress={() => void send()} />}
    >
      <EntryField
        ref={field}
        label={t("app.signIn.email")}
        icon={icons.mail}
        error={missing}
        value={email}
        onChangeText={setEmail}
        autoComplete="email"
        textContentType="username"
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        returnKeyType="send"
        onSubmitEditing={() => void send()}
        editable={!busy}
      />
    </EntryFrame>
  );
}

/** The seconds left before another link, from when it was sent; the clock ticks once a second until zero. */
function useSecondsLeft(at: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => {
      const tick = Date.now();
      setNow(tick);
      if (tick - at >= RESEND_AFTER_S * 1000) clearInterval(id);
    }, 1000);
    return () => clearInterval(id);
  }, [at]);
  // A link sent after the last tick starts the full wait, never more.
  return Math.min(RESEND_AFTER_S, Math.max(0, RESEND_AFTER_S - (now - at) / 1000));
}

function Sent({
  t,
  to,
  at,
  busy,
  resent,
  notice,
  onChange,
  onResend,
}: {
  t: T;
  to: string;
  at: number;
  busy: boolean;
  resent: boolean;
  notice: ReactNode;
  onChange: () => void;
  onResend: () => void;
}) {
  const { colors } = useTheme();
  const seconds = useSecondsLeft(at);
  const waiting = Math.ceil(seconds) > 0;
  const resendLabel = waiting ? t("v13.entrar.resend.wait", { time: countdown(seconds) }) : t("v13.entrar.resend.cta");
  const steps: { title: string; hint?: string }[] = [
    { title: t("v13.entrar.step1") },
    { title: t("v13.entrar.step2"), hint: t("v13.entrar.step2.hint") },
    { title: t("v13.entrar.step3"), hint: t("v13.entrar.step3.hint") },
  ];
  return (
    <EntryFrame
      title={t("v13.entrar.sent.title")}
      center
      onBack={() => router.back()}
      art={<SentArt />}
      notice={notice}
      lead={
        <View style={styles.sentHead}>
          <View
            style={[styles.address, { backgroundColor: colors.card, borderColor: colors.border }]}
            accessible
            accessibilityLabel={t("v13.entrar.sent.address", { email: to })}
          >
            <Icon name={icons.mail} size={16} tone="mutedForeground" />
            <Text variant="subhead" style={styles.addressText} numberOfLines={1} ellipsizeMode="middle">
              {to}
            </Text>
          </View>
          <Button label={t("v13.entrar.sent.change")} accessibilityLabel={t("v13.entrar.sent.changeA11y")} variant="ghost" compact onPress={onChange} />
          <Text variant="body" tone="mutedForeground" style={styles.centerText}>
            {t("v13.entrar.sent.body")}
          </Text>
        </View>
      }
      footer={
        <>
          <Button label={t("app.forgot.back")} full onPress={() => router.back()} />
          <Button
            label={resendLabel}
            icon={waiting ? undefined : icons.retry}
            variant="ghost"
            full
            busy={busy}
            disabled={waiting}
            onPress={onResend}
            testID="forgot-resend"
          />
        </>
      }
    >
      {/* A list of steps, each one read whole with its hint (review H12, WCAG 1.3.1). */}
      <View style={[styles.steps, { backgroundColor: colors.card }]} accessibilityRole="list">
        {steps.map((s, i) => (
          <View
            key={s.title}
            accessible
            accessibilityLabel={t(s.hint ? "v13.entrar.step.a11y.hint" : "v13.entrar.step.a11y", { n: i + 1, title: s.title, hint: s.hint ?? "" })}
            style={[styles.step, i > 0 ? { borderTopColor: colors.border, borderTopWidth: StyleSheet.hairlineWidth } : null]}
          >
            <View style={[styles.number, { backgroundColor: colors.selection }]}>
              <Text variant="footnote" tone="onSelection" style={styles.strong}>
                {String(i + 1)}
              </Text>
            </View>
            <View style={styles.stepText}>
              <Text variant="bodyStrong">{s.title}</Text>
              {s.hint ? (
                <Text variant="footnote" tone="mutedForeground">
                  {s.hint}
                </Text>
              ) : null}
            </View>
          </View>
        ))}
      </View>
      {resent ? (
        <View accessible accessibilityRole="alert" accessibilityLiveRegion="polite" style={styles.help}>
          <Icon name={icons.circleCheck} size={16} tone="positiveText" />
          <Text variant="footnote" tone="foreground" style={styles.helpText}>
            {t("v13.entrar.resend.done")}
          </Text>
        </View>
      ) : null}
      <View style={styles.help}>
        <Icon name={icons.info} size={16} tone="mutedForeground" />
        <Text variant="footnote" tone="mutedForeground" style={styles.helpText}>
          {t("v13.entrar.sent.help")}
        </Text>
      </View>
    </EntryFrame>
  );
}

/** The calm confirmation of the design: the envelope with its check, on the highlight, inside two rings. */
function SentArt() {
  const { colors } = useTheme();
  return (
    <View style={styles.art} accessible={false} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
      <View style={[styles.ring, styles.ringOuter, { borderColor: colors.highlightSoft }]} />
      <View style={[styles.ring, styles.ringInner, { borderColor: colors.highlightSoft }]} />
      <View style={[styles.artTile, { backgroundColor: colors.highlight }]}>
        <Icon name={icons.mailCheck} size={52} tone="onHighlight" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sentHead: { alignItems: "center", gap: 8, alignSelf: "stretch" },
  address: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    maxWidth: "100%",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: RADII.pill,
    borderWidth: StyleSheet.hairlineWidth,
  },
  addressText: { flexShrink: 1, minWidth: 0, fontWeight: "600" },
  centerText: { textAlign: "center" },
  steps: { borderRadius: RADII.lg, borderCurve: "continuous", paddingHorizontal: 16 },
  step: { flexDirection: "row", alignItems: "flex-start", gap: 14, paddingVertical: 12 },
  number: { width: 26, height: 26, borderRadius: RADII.pill, alignItems: "center", justifyContent: "center", marginTop: 1 },
  stepText: { flex: 1, minWidth: 0, gap: 2 },
  strong: { fontWeight: "600" },
  help: { flexDirection: "row", alignItems: "flex-start", gap: 8, paddingHorizontal: 4 },
  helpText: { flex: 1, minWidth: 0 },
  art: { width: 168, height: 168, alignItems: "center", justifyContent: "center", alignSelf: "center" },
  ring: { position: "absolute", borderWidth: 1.5 },
  ringOuter: { width: 168, height: 168, borderRadius: 56 },
  ringInner: { width: 140, height: 140, borderRadius: 44 },
  artTile: { width: 112, height: 112, borderRadius: 34, borderCurve: "continuous", alignItems: "center", justifyContent: "center" },
});
