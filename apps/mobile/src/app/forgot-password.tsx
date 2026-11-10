import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";

import { endpoints } from "@/api/endpoints";
import { EntryFrame, EntryNotice } from "@/features/entry";
import { useT, type MessageKey } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { Button } from "@/ui/button";
import { Field } from "@/ui/field";
import { useOnline } from "@/ui/online";

/**
 * «¿Olvidaste tu contraseña?» (spec 031, R1.7). Sends the link to create a new
 * one — the page that opens is the web's — and says the same whether or not
 * the email has access: this screen cannot tell anyone who is registered.
 */
export default function ForgotPassword() {
  const t = useT();
  const online = useOnline();
  const params = useLocalSearchParams<{ email?: string }>();
  const [email, setEmail] = useState(typeof params.email === "string" ? params.email : "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<MessageKey | null>(null);
  const sent = message === "app.forgot.sent";

  async function send() {
    if (!online) return setMessage("app.signIn.offline");
    const address = email.trim();
    if (!address) {
      haptics.warning();
      return setMessage("app.forgot.missing");
    }
    setBusy(true);
    setMessage(null);
    try {
      await endpoints.passwordReset(address);
      haptics.success();
      setMessage("app.forgot.sent");
    } catch {
      haptics.warning();
      setMessage("app.forgot.failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <EntryFrame
      title={t("app.forgot.title")}
      body={t("app.forgot.body")}
      notice={message ? <EntryNotice text={t(message)} tone={message === "app.forgot.failed" ? "danger" : "info"} /> : null}
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
        returnKeyType="send"
        onSubmitEditing={() => void send()}
        editable={!busy}
      />
      <Button label={t("app.forgot.cta")} variant={sent ? "secondary" : "primary"} busy={busy} full onPress={() => void send()} />
      <Button label={t("app.forgot.back")} variant={sent ? "primary" : "ghost"} full onPress={() => router.back()} />
    </EntryFrame>
  );
}
