import { Fragment } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import type { Conversation } from "@/api/endpoints";
import { useAvatarSource } from "@/api/v13-bandeja-hooks";
import type { T } from "@/i18n/t";
import { CARD_RADIUS, RADII, useTheme } from "@/theme/theme";
import { Avatar } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { initialsOf } from "../inbox/model";
import { channelOf, latestOf, previewLine } from "./model";
import type { InboxPeek } from "./reads";

/**
 * «Lo último en la Bandeja» (spec 069, R8.3): the open conversations nobody
 * waits on — two when someone waits (the card below needs the room), four
 * when not. Each row is one button that opens the conversation in the
 * Bandeja's tab (log, decision 3). The unread dot is said, never only shown.
 */
export function Latest({
  peek,
  someoneWaits,
  agents,
  t,
  onOpen,
}: {
  peek: InboxPeek;
  someoneWaits: boolean;
  agents: readonly { name: string }[] | undefined;
  t: T;
  onOpen: (id: string) => void;
}) {
  const { colors } = useTheme();
  const rows = peek.state === "ready" ? latestOf(peek.items, someoneWaits) : [];
  // Everything open is waiting: the card below already says all of it.
  if (peek.state === "ready" && rows.length === 0 && peek.items.length > 0) return null;
  const surface = [styles.card, { backgroundColor: colors.card, borderColor: colors.border }];
  return (
    <View style={styles.section} testID="home-latest">
      <Text variant="subhead" tone="mutedForeground" accessibilityRole="header" style={styles.title}>
        {t("v13.home.latest")}
      </Text>
      {peek.state === "loading" ? (
        <View style={surface} accessible accessibilityRole="progressbar" accessibilityLabel={t("v13.home.latest.loading")} accessibilityState={{ busy: true }}>
          {Array.from({ length: someoneWaits ? 2 : 4 }, (_, i) => (
            <View key={i} style={styles.row}>
              <View style={[styles.ghostAvatar, { backgroundColor: colors.muted }]} />
              <View style={styles.body}>
                <View style={[styles.ghostLine, { width: "45%", backgroundColor: colors.muted }]} />
                <View style={[styles.ghostLine, { width: "80%", backgroundColor: colors.muted }]} />
              </View>
            </View>
          ))}
        </View>
      ) : peek.state === "error" ? (
        <View style={[surface, styles.padded]}>
          <Text variant="callout" tone="mutedForeground" accessibilityRole="alert">
            {t("v13.home.latest.error")}
          </Text>
          <Button label={t("app.retry")} icon={icons.retry} variant="secondary" compact onPress={peek.retry} />
        </View>
      ) : rows.length === 0 ? (
        <View style={[surface, styles.padded]}>
          <Text variant="callout" tone="mutedForeground">
            {t("v13.home.latest.empty")}
          </Text>
        </View>
      ) : (
        <View style={surface}>
          {rows.map((c, i) => (
            <Fragment key={c.id}>
              {i > 0 ? <View style={[styles.separator, { backgroundColor: colors.border }]} /> : null}
              <LatestRow c={c} agents={agents} t={t} onOpen={onOpen} />
            </Fragment>
          ))}
        </View>
      )}
    </View>
  );
}

function LatestRow({ c, agents, t, onOpen }: { c: Conversation; agents: readonly { name: string }[] | undefined; t: T; onOpen: (id: string) => void }) {
  const { colors } = useTheme();
  // The contact's photo when the API has one (Instagram, Messenger), with the phone's credential; else the initials.
  const photo = useAvatarSource(c.id, c.contact.has_avatar === true);
  const preview = previewLine(c, agents, t);
  const spoken = [c.contact.name, c.unread ? t("inbox.row.unread") : null, preview].filter(Boolean).join(". ");
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={spoken}
      onPress={() => onOpen(c.id)}
      android_ripple={{ color: colors.muted }}
      style={({ pressed }) => [styles.row, pressed ? { backgroundColor: colors.muted } : null]}
      testID={`home-latest-${c.id}`}
    >
      <Avatar initials={c.contact.initials || initialsOf(c.contact.name)} size={36} channel={channelOf(c)} photo={photo} />
      <View style={styles.body}>
        <Text variant="bodyStrong" numberOfLines={2}>
          {c.contact.name}
        </Text>
        {preview ? (
          <Text variant="footnote" tone="mutedForeground" numberOfLines={1}>
            {preview}
          </Text>
        ) : null}
      </View>
      {c.unread ? (
        <View testID="home-latest-unread" style={[styles.halo, { backgroundColor: colors.highlightSoft }]}>
          <View style={[styles.dot, { backgroundColor: colors.highlightInk }]} />
        </View>
      ) : null}
      <Icon name={icons.chevron} size={18} tone="subtle" />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: { gap: 8 },
  title: { paddingHorizontal: 4 },
  card: { borderRadius: CARD_RADIUS, borderWidth: StyleSheet.hairlineWidth * 2, overflow: "hidden" },
  padded: { padding: 16, gap: 12, alignItems: "flex-start" },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 12, paddingVertical: 10, minHeight: 56 },
  body: { flex: 1, minWidth: 0, gap: 2 },
  // The separator starts after the avatar, as the grouped lists do.
  separator: { height: StyleSheet.hairlineWidth, marginLeft: 60 },
  halo: { width: 14, height: 14, borderRadius: 7, alignItems: "center", justifyContent: "center" },
  dot: { width: 8, height: 8, borderRadius: 4 },
  ghostAvatar: { width: 36, height: 36, borderRadius: 18 },
  ghostLine: { height: 10, borderRadius: RADII.sm, marginVertical: 3 },
});
