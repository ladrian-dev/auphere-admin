import { Image } from "expo-image";
import { useState } from "react";
import { Linking, Pressable, StyleSheet, View } from "react-native";

import { useCommentPost } from "@/api/v13-bandeja-hooks";
import type { T } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * The post a comment was left on, above the comment (spec 049 R4, spec 069
 * R11.6; the console's `comment-post.tsx`). If Meta does not give it, nothing
 * shows and the comment still reads on its own. Its picture is decorative —
 * the words and the link say what it is — and kept in memory only, like
 * everything about a business's customers (031). The link is the business's
 * own post on Meta, and says it leaves the app.
 */
export function CommentPost({ conversationId, messageId, t }: { conversationId: string; messageId: string; t: T }) {
  const { colors, radius } = useTheme();
  const post = useCommentPost(conversationId, messageId, true).data ?? null;
  const [broken, setBroken] = useState(false);
  if (!post) return null;
  return (
    <View style={styles.line} testID={`comment-post-${messageId}`}>
      <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border, borderRadius: radius.md }]}>
        {post.image_url && !broken ? (
          <Image
            source={{ uri: post.image_url }}
            style={[styles.image, { borderRadius: radius.sm, backgroundColor: colors.muted }]}
            contentFit="cover"
            cachePolicy="memory"
            accessible={false}
            onError={() => setBroken(true)}
          />
        ) : null}
        <View style={styles.text}>
          <Text variant="caption" tone="mutedForeground">
            {t("inbox.comment.on")}
          </Text>
          {post.text ? (
            <Text variant="footnote" numberOfLines={2}>
              {post.text}
            </Text>
          ) : null}
          {post.permalink ? (
            <Pressable
              accessibilityRole="link"
              accessibilityLabel={t("inbox.comment.open")}
              onPress={() => void Linking.openURL(post.permalink as string)}
              hitSlop={{ top: 10, bottom: 10 }}
              style={styles.link}
            >
              <Text variant="footnote" tone="primaryText">
                {t("inbox.comment.open")}
              </Text>
              <Icon name={icons.external} size={14} tone="primaryText" />
            </Pressable>
          ) : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  line: { paddingHorizontal: 12, paddingTop: 6, paddingBottom: 2, flexDirection: "row" },
  card: { flexDirection: "row", gap: 10, padding: 8, borderWidth: StyleSheet.hairlineWidth * 2, maxWidth: "82%" },
  image: { width: 56, height: 56 },
  text: { flexShrink: 1, minWidth: 0, gap: 2, justifyContent: "center" },
  link: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 28 },
});
