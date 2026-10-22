import { Image } from "expo-image";
import { memo, useEffect, useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import Animated from "react-native-reanimated";

import type { ThreadItem } from "@/api/endpoints";
import type { Locale, MessageKey, T } from "@/i18n/t";
import { clock } from "@/lib/format";
import { useMotion } from "@/motion/use-motion";
import { useTheme } from "@/theme/theme";
import { Icon, icons, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

import { eventText, whoOf } from "../model";
import { mediaHeaders, mediaUrl } from "./media";

const MEDIA_ICON: Record<string, IconName> = {
  image: icons.image,
  document: icons.document,
  audio: icons.audio,
  video: icons.video,
};

const DELIVERY: Record<string, MessageKey> = {
  pending: "inbox.delivery.pending",
  sent: "inbox.delivery.sent",
  delivered: "inbox.delivery.delivered",
  read: "inbox.delivery.read",
};

/** A message not yet confirmed by the API: shown at once, kept if it fails (R6.6). */
export type Pending = {
  key: string;
  /** A text is retried with the same key; a file is picked again. */
  kind: "text" | "file";
  text: string;
  at: string;
  status: "sending" | "failed";
  /** What the failure was, for the line under the bubble. */
  reason: string | null;
};

/**
 * One message (R5.3). The contact's on the left, the business's on the right
 * — the agent's and the people's alike, each one named. Files open in the
 * system's viewer. An outgoing message says how it went, in words.
 */
export const MessageBubble = memo(function MessageBubble({
  item,
  t,
  locale,
  onOpen,
}: {
  item: ThreadItem;
  t: T;
  locale: Locale;
  onOpen: (messageId: string, mime: string | null) => void;
}) {
  const { colors, radius } = useTheme();
  const out = item.direction === "outbound";
  const who = out ? whoOf(item.author, t) : null;
  const media = item.media ?? null;
  const delivery = item.delivery ?? null;
  const status =
    delivery === "failed"
      ? item.failure_reason
        ? t("inbox.delivery.failed.reason", { reason: item.failure_reason })
        : t("inbox.delivery.failed")
      : delivery && DELIVERY[delivery]
        ? t(DELIVERY[delivery])
        : null;
  const spoken = [who ?? t("inbox.who.contact"), item.text, media ? t(`inbox.media.${media.kind ?? "document"}` as "inbox.media.document") : null, clock(item.at, locale), status]
    .filter(Boolean)
    .join(". ");
  return (
    <View style={[styles.line, out ? styles.right : styles.left]}>
      <View
        accessible
        accessibilityLabel={spoken}
        style={[
          styles.bubble,
          {
            backgroundColor: out ? colors.positiveBg : colors.card,
            borderColor: out ? colors.positiveBg : colors.border,
            borderRadius: radius.md * 2,
          },
          out ? { borderBottomRightRadius: radius.sm } : { borderBottomLeftRadius: radius.sm },
        ]}
      >
        {who ? (
          <Text variant="caption" tone="primaryText">
            {who}
          </Text>
        ) : null}
        {media ? <MediaChip id={item.id} kind={media.kind ?? null} name={media.filename ?? null} t={t} onOpen={onOpen} /> : null}
        {media?.transcript ? (
          <Text variant="footnote" tone="mutedForeground">
            {t("inbox.media.transcript", { text: media.transcript })}
          </Text>
        ) : null}
        {item.text ? (
          <Text variant="body" selectable>
            {item.text}
          </Text>
        ) : null}
        <View style={styles.meta}>
          <Text variant="caption" tone="mutedForeground">
            {clock(item.at, locale)}
          </Text>
          {out && status ? (
            <Text variant="caption" tone={delivery === "failed" ? "dangerText" : "mutedForeground"}>
              {`· ${status}`}
            </Text>
          ) : null}
        </View>
      </View>
    </View>
  );
});

function MediaChip({
  id,
  kind,
  name,
  t,
  onOpen,
}: {
  id: string;
  kind: string | null;
  name: string | null;
  t: T;
  onOpen: (messageId: string, mime: string | null) => void;
}) {
  const { colors, radius } = useTheme();
  const label = name ?? t(`inbox.media.${kind ?? "document"}` as "inbox.media.document");
  const [headers, setHeaders] = useState<Record<string, string> | null>(null);
  useEffect(() => {
    if (kind === "image") void mediaHeaders().then(setHeaders);
  }, [kind]);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={t("inbox.media.open", { name: label })}
      onPress={() => onOpen(id, kind === "document" ? "application/pdf" : null)}
      android_ripple={{ color: colors.scrim }}
      style={{ borderRadius: radius.md, overflow: "hidden" }}
    >
      {({ pressed }) => (
        <>
          {kind === "image" && headers ? (
            <Image
              source={{ uri: mediaUrl(id), headers }}
              style={[styles.image, { borderRadius: radius.md, backgroundColor: colors.muted }]}
              contentFit="cover"
              transition={120}
              accessible={false}
            />
          ) : (
            <View style={[styles.file, { backgroundColor: colors.muted, borderRadius: radius.md }]}>
              <Icon name={MEDIA_ICON[kind ?? ""] ?? icons.document} size={20} tone="primaryText" />
              <Text variant="subhead" numberOfLines={2} style={styles.fileName}>
                {label}
              </Text>
            </View>
          )}
          {/* The press is a scrim over the attachment, never a drop in opacity (spec 042, R7.2). */}
          {pressed ? <View pointerEvents="none" style={[StyleSheet.absoluteFill, { backgroundColor: colors.scrim }]} /> : null}
        </>
      )}
    </Pressable>
  );
}

/** What happened to the conversation, in one centred line (R5.3). */
export const EventLine = memo(function EventLine({ item, t }: { item: ThreadItem; t: T }) {
  const { colors, radius } = useTheme();
  const escalated = item.kind === "escalated";
  return (
    <View style={styles.event}>
      <View style={[styles.eventPill, { backgroundColor: escalated ? colors.warningBg : colors.muted, borderRadius: radius.full }]}>
        <Text variant="caption" tone={escalated ? "warningText" : "mutedForeground"} style={styles.eventText}>
          {eventText(item.kind ?? null, item.author ?? null, item.detail ?? null, t)}
        </Text>
      </View>
    </View>
  );
});

/** The day between messages: «Hoy», «Ayer» or the date. */
export function DayLine({ label }: { label: string }) {
  return (
    <View style={styles.event} accessibilityRole="header">
      <Text variant="caption" tone="mutedForeground">
        {label}
      </Text>
    </View>
  );
}

/** A message on its way, or one that did not go: tap to retry, the text is never lost (R6.4, R6.6). */
export function PendingBubble({ p, t, onRetry, onDismiss }: { p: Pending; t: T; onRetry: (key: string) => void; onDismiss: (key: string) => void }) {
  const { colors, radius } = useTheme();
  const motion = useMotion();
  const failed = p.status === "failed";
  const body = (
    <View
      style={[
        styles.bubble,
        {
          backgroundColor: failed ? colors.dangerBg : colors.positiveBg,
          borderColor: failed ? colors.danger : colors.positiveBg,
          borderRadius: radius.md * 2,
          borderBottomRightRadius: radius.sm,
          opacity: failed ? 1 : 0.85,
        },
      ]}
    >
      <Text variant="body">{p.text}</Text>
      <View style={styles.meta}>
        {failed ? <Icon name={icons.failed} size={14} tone="dangerText" /> : null}
        <Text variant="caption" tone={failed ? "dangerText" : "mutedForeground"}>
          {failed ? (p.reason ?? t("app.inbox.sendFailed")) : t("inbox.delivery.pending")}
        </Text>
      </View>
    </View>
  );
  return (
    <Animated.View entering={motion.enter} style={[styles.line, styles.right]}>
      {failed ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${p.text}. ${p.reason ?? t("app.inbox.sendFailed")}`}
          accessibilityHint={p.kind === "text" ? t("app.inbox.retry") : t("app.close")}
          onPress={() => (p.kind === "text" ? onRetry(p.key) : onDismiss(p.key))}
        >
          {body}
        </Pressable>
      ) : (
        <View accessible accessibilityLabel={`${p.text}. ${t("inbox.delivery.pending")}`} accessibilityState={{ busy: true }}>
          {body}
        </View>
      )}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  line: { paddingHorizontal: 12, paddingVertical: 3, flexDirection: "row" },
  left: { justifyContent: "flex-start" },
  right: { justifyContent: "flex-end" },
  bubble: { maxWidth: "82%", paddingHorizontal: 12, paddingVertical: 8, gap: 4, borderWidth: StyleSheet.hairlineWidth * 2 },
  meta: { flexDirection: "row", alignItems: "center", gap: 4, flexWrap: "wrap", alignSelf: "flex-end" },
  image: { width: 220, height: 220, maxWidth: "100%" },
  file: { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, minHeight: 48, minWidth: 180 },
  fileName: { flex: 1, minWidth: 0 },
  event: { alignItems: "center", paddingVertical: 8, paddingHorizontal: 24 },
  eventPill: { paddingHorizontal: 12, paddingVertical: 6 },
  eventText: { textAlign: "center" },
});
