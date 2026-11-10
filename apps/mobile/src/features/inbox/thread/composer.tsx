import { useEffect, useRef, useState, type ComponentRef } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";

import type { SavedReply } from "@/api/endpoints";
import type { T } from "@/i18n/t";
import { concentric, TOUCH, useTheme } from "@/theme/theme";
import { Button, IconButton } from "@/ui/button";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import type { ComposerMode } from "../model";
import { FOOT_RADIUS } from "./foot-radius";

/**
 * The box (R6.3, R6.5 of the 031; spec 042 R2.1, R7.1; spec 044 R11.4, R11.5:
 * who answers and «Devolver» one tap away, the saved replies as chips with the
 * draft empty). Only when this person
 * answers. Content only — the surface is `ThreadFoot`'s. If WhatsApp would
 * refuse — the 24 h window closed, the number disconnected — it says why
 * instead of a box that cannot send. A saved reply lands in the box, never
 * sent on its own. Offline, nothing that writes is offered (R14.2). The send
 * button is a solid circle whose corners are concentric with the surface's.
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
  onGiveBack,
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
  /** Spec 044, R11.4: give it back in one tap, not only from the menu. */
  onGiveBack?: () => void;
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
      <View accessible accessibilityRole="alert" style={styles.blocked} testID="blocked">
        <Icon name={icons.warning} size={18} tone="warningText" />
        <Text variant="callout" tone="warningText" style={styles.flex}>
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

  // Spec 044, R11.5: with the draft empty, the saved replies are in view as chips that fill it.
  const chips = draft.trim() === "" && online && replies && replies.length > 0 ? replies.slice(0, 8) : null;
  return (
    <View style={styles.wrap}>
      {onGiveBack ? (
        <View style={styles.mine}>
          <View style={[styles.dot, { backgroundColor: colors.primary }]} />
          <Text variant="footnote" tone="mutedForeground" style={styles.flex} numberOfLines={2}>
            {mode.agent ? t("app.inbox.mineLine", { agent: mode.agent }) : t("app.inbox.mineLine.noAgent")}
          </Text>
          <Button label={t("app.inbox.giveBack.short")} icon={icons.giveBack} variant="secondary" compact disabled={!online} onPress={onGiveBack} />
        </View>
      ) : null}
      {chips ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.chips} accessibilityLabel={t("app.inbox.replies.chips")}>
          {chips.map((r) => (
            <Pressable
              key={r.id}
              accessibilityRole="button"
              accessibilityLabel={r.title}
              onPress={() => {
                setDraft(r.body);
                input.current?.focus();
              }}
              android_ripple={{ color: colors.muted }}
              hitSlop={CHIP_SLOP}
              style={({ pressed }) => [styles.chip, { borderRadius: radius.full, borderColor: colors.border, backgroundColor: pressed ? colors.muted : colors.card }]}
            >
              <Text variant="subhead" numberOfLines={1}>
                {r.title.length > 28 ? `${r.title.slice(0, 27)}…` : r.title}
              </Text>
            </Pressable>
          ))}
        </ScrollView>
      ) : null}
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
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("inbox.composer.send")}
          accessibilityState={{ disabled: !canSend }}
          disabled={!canSend}
          onPress={send}
          hitSlop={6}
          style={({ pressed }) => [
            styles.send,
            { borderRadius: concentric(FOOT_RADIUS, SEND_INSET), backgroundColor: canSend ? (pressed ? colors.primaryDeep : colors.primary) : colors.muted },
          ]}
          testID="send"
        >
          <Icon name={icons.arrowUp} size={20} tone={canSend ? "primaryForeground" : "mutedForeground"} />
        </Pressable>
      </View>
    </View>
  );
}

/** The send button sits this far from the surface's edge: its radius is concentric with FOOT_RADIUS. */
const SEND_INSET = 4;

/** 36 pt chips reach the app's 48 pt target with the space around them (gate review). */
const CHIP_SLOP = { top: 6, bottom: 6 };

const styles = StyleSheet.create({
  wrap: { paddingHorizontal: 12, paddingTop: 6, paddingBottom: SEND_INSET },
  flex: { flex: 1, minWidth: 0 },
  input: { minHeight: TOUCH, maxHeight: 160, fontSize: 17, lineHeight: 22, paddingHorizontal: 4, paddingVertical: 8, textAlignVertical: "top" },
  actions: { flexDirection: "row", alignItems: "center", gap: 4 },
  spacer: { flex: 1 },
  send: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  blocked: { flexDirection: "row", alignItems: "center", gap: 10, padding: 16 },
  offline: { paddingHorizontal: 4, paddingTop: 4 },
  mine: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 4, paddingBottom: 4 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  chips: { gap: 8, paddingHorizontal: 4, paddingVertical: 4 },
  chip: { minHeight: 36, maxWidth: 240, paddingHorizontal: 14, borderWidth: 1, justifyContent: "center" },
});
