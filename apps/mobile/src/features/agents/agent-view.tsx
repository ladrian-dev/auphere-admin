import { StyleSheet, View } from "react-native";

import type { AgentCard, AgentChannel } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { agentActions, agentStateLabel, agentStateSentence, channelName, channelStateLabel, pausedBy, pausedSince, toneOf, whyNoResume } from "@/lib/agents-model";
import { useTheme } from "@/theme/theme";
import { Badge, Divider } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { Notice } from "../business/parts";

/**
 * One agent (spec 047, T169; requirements 25, 27, 50.1–50.3): its state in
 * the console's words and tone, what that means for the people who write,
 * and — paused — why and who paused it. Then the one thing the person can do
 * with it, «Pausar» or «Reanudar», only when the API allows it; a pause the
 * system or the partner put says why there is no button and whom to talk to.
 * Its numbers below, each with its own state and its own pause. What the
 * person cannot do from here (create, publish, connect) is said once, at the
 * foot, never offered as a button that refuses.
 */
export function AgentView({
  card,
  partner,
  online,
  busy,
  error,
  onPause,
  onResume,
  onChannel,
  t,
  locale,
  now = new Date(),
}: {
  card: AgentCard;
  /** Whom to talk to: the partner, or Auphere. */
  partner: string;
  online: boolean;
  /** What is being written now: the agent's id or a number's. */
  busy: string | null;
  error: string | null;
  onPause: () => void;
  onResume: () => void;
  onChannel: (channel: AgentChannel, action: "pause" | "resume") => void;
  t: T;
  locale: Locale;
  now?: Date;
}) {
  const state = agentStateLabel(card.visible_state, t);
  const sentence = agentStateSentence(card.visible_state, t);
  const paused = card.visible_state.code === "paused";
  const who = paused ? pausedBy(card, partner, t) : null;
  // `paused_at` is null when the system paused it: the reason below says the rest.
  const since = paused ? pausedSince(card.paused_at, now, locale, t) : null;
  const can = agentActions(card);
  const open = card.open_conversations;

  return (
    <View style={styles.stack}>
      <Card testID="agent-state">
        <View style={styles.badges}>
          {state ? <Badge label={state} tone={toneOf(card.visible_state.tone)} /> : null}
          {card.is_default ? <Badge label={t("agentes.default")} tone="neutral" /> : null}
        </View>
        {sentence ? <Text variant="body">{sentence}</Text> : null}
        {who || since ? (
          <Text variant="callout" tone="mutedForeground" testID="agent-paused-by">
            {[who, since].filter(Boolean).join(" ")}
          </Text>
        ) : null}
        {open > 0 ? (
          <Text variant="callout" tone="mutedForeground">
            {open === 1 ? t("agentes.inProgress.one") : t("agentes.inProgress", { n: open })}
          </Text>
        ) : null}
        {can.blocked !== null ? (
          <>
            <Divider />
            <Text variant="callout" testID="agent-why">
              {whyNoResume(can.blocked, partner, t)}
            </Text>
          </>
        ) : null}
      </Card>

      {!online && (can.pause || can.resume) ? <Notice tone="warning" icon={icons.offline} text={t("agentes.offline")} /> : null}
      {error && online ? <Notice tone="danger" icon={icons.warning} text={error} /> : null}

      {can.resume ? (
        <Button label={t("builder.life.action.resume")} icon={icons.resume} full busy={busy === card.id} disabled={!online || (busy !== null && busy !== card.id)} onPress={onResume} />
      ) : can.pause ? (
        <Button
          label={t("builder.life.action.pause")}
          icon={icons.pause}
          variant="secondary"
          full
          busy={busy === card.id}
          disabled={!online || (busy !== null && busy !== card.id)}
          onPress={onPause}
        />
      ) : null}

      <View style={styles.section}>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header" style={styles.title}>
          {t("agentes.channels")}
        </Text>
        {card.channels.length === 0 ? (
          <Card>
            <Text variant="callout" tone="mutedForeground">
              {t("agentes.channels.none")}
            </Text>
          </Card>
        ) : (
          <Card style={styles.channels}>
            {card.channels.map((c, i) => (
              <View key={c.id}>
                {i > 0 ? <Divider /> : null}
                <ChannelRow channel={c} online={online} busy={busy} onChannel={onChannel} t={t} />
              </View>
            ))}
          </Card>
        )}
        {card.channels.length > 0 ? (
          <Text variant="footnote" tone="mutedForeground" style={styles.title}>
            {t("agentes.channels.hint")}
          </Text>
        ) : null}
      </View>

      <Text variant="footnote" tone="mutedForeground" style={styles.title}>
        {t("agentes.limits", { partner })}
      </Text>
    </View>
  );
}

function ChannelRow({
  channel,
  online,
  busy,
  onChannel,
  t,
}: {
  channel: AgentChannel;
  online: boolean;
  busy: string | null;
  onChannel: (channel: AgentChannel, action: "pause" | "resume") => void;
  t: T;
}) {
  const { colors } = useTheme();
  const name = channelName(channel);
  const state = channelStateLabel(channel.visible_state, t);
  const action: "pause" | "resume" | null = channel.allowed.includes("resume") ? "resume" : channel.allowed.includes("pause") ? "pause" : null;
  return (
    <View style={[styles.channel, { borderColor: colors.border }]} testID={`channel-${channel.id}`}>
      <View style={styles.channelText} accessible accessibilityLabel={[name, state].filter(Boolean).join(". ")}>
        <Text variant="body">{name}</Text>
        {state ? <Badge label={state} tone={toneOf(channel.visible_state.tone)} /> : null}
      </View>
      {action ? (
        <Button
          label={t(action === "pause" ? "builder.life.action.pause" : "builder.life.action.resume")}
          accessibilityLabel={t(action === "pause" ? "agentes.channel.pause" : "agentes.channel.resume", { number: channel.identifier })}
          variant={action === "resume" ? "primary" : "secondary"}
          compact
          busy={busy === channel.id}
          disabled={!online || (busy !== null && busy !== channel.id)}
          onPress={() => onChannel(channel, action)}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  badges: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  section: { gap: 8 },
  title: { paddingHorizontal: 4 },
  channels: { paddingVertical: 4, gap: 0 },
  channel: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 12, paddingVertical: 10 },
  channelText: { flex: 1, minWidth: 160, gap: 6 },
});
