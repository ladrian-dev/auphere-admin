import { useEffect, useRef, useState, type ComponentRef } from "react";
import { StyleSheet, TextInput, View } from "react-native";

import type { SavedReply } from "@/api/endpoints";
import type { T } from "@/i18n/t";
import { TOUCH, useTheme } from "@/theme/theme";
import { IconButton } from "@/ui/button";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import type { ComposerMode } from "../model";

/**
 * The box (R6.3, R6.5). Only when this person answers. If WhatsApp would
 * refuse — the 24 h window closed, the number disconnected — it says why
 * instead of a box that cannot send. A saved reply lands in the box, never
 * sent on its own. Offline, nothing that writes is offered (R14.2).
 */
export function Composer({
  mode,
  online,
  focusSignal,
  replies,
  t,
  onSend,
  onAttach,
  onReplies,
}: {
  mode: Extract<ComposerMode, { kind: "mine" }>;
  online: boolean;
  /** Bumps when this person just took control: focus the box. */
  focusSignal: number;
  replies: SavedReply[] | null;
  t: T;
  onSend: (text: string) => void;
  onAttach: () => void;
  onReplies: (insert: (body: string) => void) => void;
}) {
  const { colors, radius } = useTheme();
  const [draft, setDraft] = useState("");
  const input = useRef<ComponentRef<typeof TextInput>>(null);

  useEffect(() => {
    if (focusSignal > 0) {
      const id = setTimeout(() => input.current?.focus(), 250);
      return () => clearTimeout(id);
    }
  }, [focusSignal]);

  if (mode.blocked) {
    return (
      <View
        accessible
        accessibilityRole="alert"
        style={[styles.blocked, { backgroundColor: colors.warningBg, borderColor: colors.warningSolid, borderRadius: radius.md }]}
      >
        <Text variant="callout" tone="warningText">
          {t(`inbox.composer.${mode.blocked}`)}
        </Text>
      </View>
    );
  }

  const canSend = online && draft.trim().length > 0;
  const send = () => {
    if (!canSend) return;
    onSend(draft.trim());
    setDraft("");
  };

  return (
    <View style={[styles.wrap, { backgroundColor: colors.card, borderColor: colors.input, borderRadius: radius.md * 2 }]}>
      {!online ? (
        <Text variant="footnote" tone="warningText" style={styles.offline}>
          {t("app.offline.actions")}
        </Text>
      ) : null}
      <TextInput
        ref={input}
        value={draft}
        onChangeText={setDraft}
        placeholder={t("inbox.composer.placeholder")}
        placeholderTextColor={colors.subtle}
        accessibilityLabel={t("inbox.composer")}
        multiline
        maxLength={4096}
        editable={online}
        style={[styles.input, { color: colors.foreground }]}
        testID="composer-input"
      />
      <View style={styles.actions}>
        <IconButton icon={icons.attach} label={t("inbox.composer.attach")} disabled={!online} onPress={onAttach} />
        {replies && replies.length > 0 ? (
          <IconButton
            icon={icons.replies}
            label={t("app.inbox.replies.pick")}
            disabled={!online}
            onPress={() =>
              onReplies((body) => {
                setDraft((d) => (d.trim() ? `${d.trimEnd()}\n${body}` : body));
                input.current?.focus();
              })
            }
          />
        ) : null}
        <View style={styles.spacer} />
        <IconButton icon={icons.send} label={t("inbox.composer.send")} tone={canSend ? "primaryText" : "subtle"} disabled={!canSend} onPress={send} testID="send" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderWidth: StyleSheet.hairlineWidth * 2, paddingHorizontal: 8, paddingTop: 6 },
  input: { minHeight: TOUCH, maxHeight: 160, fontSize: 16, lineHeight: 22, paddingHorizontal: 8, paddingVertical: 8, textAlignVertical: "top" },
  actions: { flexDirection: "row", alignItems: "center" },
  spacer: { flex: 1 },
  blocked: { padding: 12, borderWidth: StyleSheet.hairlineWidth * 2 },
  offline: { paddingHorizontal: 8, paddingTop: 4 },
});
