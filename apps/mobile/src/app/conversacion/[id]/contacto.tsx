import { useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";

import { endpoints, type Detail } from "@/api/endpoints";
import { useConversation, useSuggestedTags } from "@/api/hooks";
import { keys } from "@/api/query";
import { attendsLine, eventText, initialsOf } from "@/features/inbox/model";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { haptics } from "@/motion/haptics";
import { glassAvailable } from "@/theme/glass";
import { TOUCH, useTheme } from "@/theme/theme";
import { Avatar, Divider } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Icon, icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { ErrorState, Skeleton } from "@/ui/states";
import { Text } from "@/ui/text";

const MAX_TAGS = 20;

/**
 * The contact, as a sheet over the conversation (spec 031, R12): who they are,
 * the agent's summary, the team's tags and internal note — editable, and the
 * web sees it on its next read (R12.2) — and what happened.
 */
export default function Contacto() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const { colors, radius } = useTheme();
  const qc = useQueryClient();
  const detail = useConversation(id);
  const suggested = useSuggestedTags(true);
  const d = detail.data;

  /** The person's edit of the note; `null` while they have not touched it. */
  const [draft, setDraft] = useState<string | null>(null);
  const [noteState, setNoteState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [tagDraft, setTagDraft] = useState("");
  const [tagError, setTagError] = useState(false);

  if (!d) {
    return (
      <View style={[styles.fill, glassAvailable() ? null : { backgroundColor: colors.background }]}>
        {detail.isError ? <ErrorState onRetry={() => void detail.refetch()} /> : <View style={styles.pad}><Skeleton rows={3} /></View>}
      </View>
    );
  }

  const note = draft ?? d.note.body;
  const patch = (next: Partial<Detail>) => qc.setQueryData<Detail>(keys.conversation(id), (cur) => (cur ? { ...cur, ...next } : cur));

  const setTags = async (tags: string[]) => {
    const before = d.tags;
    patch({ tags });
    setTagError(false);
    try {
      const r = await endpoints.setTags(id, tags);
      patch({ tags: r.tags });
      void qc.invalidateQueries({ queryKey: keys.tags });
      void qc.invalidateQueries({ queryKey: keys.inboxLists });
    } catch {
      patch({ tags: before });
      setTagError(true);
      haptics.warning();
    }
  };

  const addTag = (raw: string) => {
    const tag = raw.trim();
    if (!tag || d.tags.includes(tag) || d.tags.length >= MAX_TAGS) return;
    setTagDraft("");
    void setTags([...d.tags, tag]);
  };

  const saveNote = async () => {
    setNoteState("saving");
    try {
      const r = await endpoints.setNote(id, note);
      patch({ note: { body: r.body, updated_at: r.updated_at } });
      setDraft(null);
      setNoteState("saved");
      haptics.success();
    } catch {
      setNoteState("error");
      haptics.warning();
    }
  };

  const offer = (suggested.data?.tags ?? []).filter((s) => !d.tags.includes(s)).slice(0, 8);
  const noteDirty = draft !== null && draft !== d.note.body;

  return (
    // With Liquid Glass the sheet's own material shows through (spec 042, R1.7); the content is opaque cards either way.
    <ScrollView
      testID="contact-scroll"
      style={glassAvailable() ? undefined : { backgroundColor: colors.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
    >
      <View style={styles.who}>
        <Avatar initials={initialsOf(d.contact.name)} size={56} />
        <Text variant="title" accessibilityRole="header" style={styles.center}>
          {d.contact.name}
        </Text>
        <Text variant="subhead" tone="mutedForeground" style={styles.center}>
          {attendsLine(d, t)}
        </Text>
      </View>

      {d.summary ? (
        <Card>
          <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
            {t("inbox.panel.summary")}
          </Text>
          <Text variant="body">{d.summary}</Text>
        </Card>
      ) : null}

      <Card>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("inbox.panel.data")}
        </Text>
        <Field label={t("inbox.panel.phone")} value={d.contact.handle} selectable />
        <Field label={t("inbox.panel.channel")} value={t("inbox.channel.whatsapp")} />
        {d.contact.first_message_at ? (
          <Field label={t("inbox.panel.first")} value={new Date(d.contact.first_message_at).toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" })} />
        ) : null}
        <Field label={t("inbox.panel.conversations")} value={String(d.contact.conversations)} />
      </Card>

      <Card>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("inbox.panel.tags")}
        </Text>
        <View style={styles.tags}>
          {d.tags.map((tag) => (
            <Pressable
              key={tag}
              accessibilityRole="button"
              accessibilityLabel={t("inbox.panel.tags.remove", { tag })}
              disabled={!online}
              onPress={() => void setTags(d.tags.filter((x) => x !== tag))}
              style={[styles.tag, { backgroundColor: colors.accentSoft, borderRadius: radius.full }]}
            >
              <Text variant="subhead" tone="accentDeep">
                {tag}
              </Text>
              <Icon name={icons.close} size={12} tone="accentDeep" />
            </Pressable>
          ))}
        </View>
        {d.tags.length < MAX_TAGS ? (
          <TextInput
            value={tagDraft}
            onChangeText={setTagDraft}
            onSubmitEditing={() => addTag(tagDraft)}
            placeholder={t("inbox.panel.tags.add")}
            placeholderTextColor={colors.subtle}
            accessibilityLabel={t("inbox.panel.tags.add")}
            editable={online}
            returnKeyType="done"
            maxLength={40}
            style={[styles.input, { color: colors.foreground, borderColor: colors.input, borderRadius: radius.md }]}
          />
        ) : (
          <Text variant="footnote" tone="mutedForeground">
            {t("inbox.panel.tags.max")}
          </Text>
        )}
        {offer.length > 0 && online ? (
          <View style={styles.tags} accessibilityLabel={t("inbox.panel.tags.suggested")}>
            {offer.map((s) => (
              <Pressable
                key={s}
                accessibilityRole="button"
                accessibilityLabel={`${t("inbox.panel.tags.add")}: ${s}`}
                onPress={() => addTag(s)}
                style={[styles.tag, { borderColor: colors.border, borderWidth: 1, borderRadius: radius.full }]}
              >
                <Text variant="subhead" tone="mutedForeground">
                  {`+ ${s}`}
                </Text>
              </Pressable>
            ))}
          </View>
        ) : null}
        {tagError ? (
          <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
            {t("inbox.error.action")}
          </Text>
        ) : null}
      </Card>

      <Card>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("inbox.panel.note")}
        </Text>
        <TextInput
          value={note}
          onChangeText={(v) => {
            setDraft(v);
            setNoteState("idle");
          }}
          placeholder={t("inbox.panel.note.placeholder")}
          placeholderTextColor={colors.subtle}
          accessibilityLabel={t("inbox.panel.note")}
          editable={online}
          multiline
          maxLength={4000}
          style={[styles.input, styles.note, { color: colors.foreground, borderColor: colors.input, borderRadius: radius.md }]}
        />
        <View style={styles.noteRow}>
          <Text
            variant="footnote"
            tone={noteState === "error" ? "dangerText" : "mutedForeground"}
            accessibilityLiveRegion="polite"
            style={styles.flex}
          >
            {noteState === "saving"
              ? t("inbox.panel.note.saving")
              : noteState === "saved"
                ? t("inbox.panel.note.saved")
                : noteState === "error"
                  ? t("inbox.panel.note.error")
                  : ""}
          </Text>
          <Button
            label={t("inbox.panel.note.save")}
            variant="secondary"
            compact
            disabled={!online || !noteDirty}
            busy={noteState === "saving"}
            onPress={() => void saveNote()}
          />
        </View>
      </Card>

      <Card>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("inbox.panel.activity")}
        </Text>
        {d.activity.length === 0 ? (
          <Text variant="callout" tone="mutedForeground">
            {t("inbox.panel.activity.empty")}
          </Text>
        ) : (
          d.activity.map((a, i) => (
            <View key={`${a.kind}-${a.at}-${i}`} style={styles.activity}>
              {i > 0 ? <Divider /> : null}
              <Text variant="callout">{eventText(a.kind, a.actor, a.detail ?? null, t)}</Text>
              <Text variant="caption" tone="mutedForeground">
                {`${new Date(a.at).toLocaleDateString(locale, { day: "numeric", month: "short" })} · ${clock(a.at, locale)}`}
              </Text>
            </View>
          ))
        )}
      </Card>
    </ScrollView>
  );
}

function Field({ label, value, selectable = false }: { label: string; value: string; selectable?: boolean }) {
  return (
    <View style={styles.field} accessible accessibilityLabel={`${label}: ${value}`}>
      <Text variant="footnote" tone="mutedForeground">
        {label}
      </Text>
      <Text variant="body" selectable={selectable}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  pad: { padding: 16 },
  content: { padding: 16, gap: 16, paddingBottom: 40 },
  who: { alignItems: "center", gap: 6, paddingVertical: 8 },
  center: { textAlign: "center" },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  tag: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, minHeight: 36 },
  input: { borderWidth: 1, paddingHorizontal: 12, minHeight: TOUCH, fontSize: 16 },
  note: { minHeight: 96, paddingVertical: 10, textAlignVertical: "top" },
  noteRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  flex: { flex: 1, minWidth: 0 },
  field: { gap: 2, paddingVertical: 4 },
  activity: { gap: 2, paddingVertical: 4 },
});
