import { Pressable, StyleSheet, View } from "react-native";

import type { AgentCard } from "@/api/endpoints";
import type { T } from "@/i18n/t";
import { agentStateLabel, toneOf } from "@/lib/agents-model";
import { TOUCH, useTheme } from "@/theme/theme";
import { Badge } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Group } from "@/ui/group";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

/** The agents' read, as Inicio holds it: absent without the module, then loading, failed or there. */
export type AgentsRead = { state: "loading" } | { state: "error"; retry: () => void } | { state: "ready"; items: AgentCard[] };

/**
 * «Agentes» on Inicio (spec 047, T169, 50.1): one row per agent with its
 * state in the console's words and tone (25.5), and the way into it. A row
 * says its state in words, never in colour alone, and is one button with one
 * spoken sentence.
 */
export function AgentsGroup({ read, onAgent, t }: { read: AgentsRead; onAgent: (id: string) => void; t: T }) {
  if (read.state === "loading") {
    return (
      <Group title={t("agentes.title")} testID="home-agents">
        <View style={styles.pad} accessible accessibilityRole="progressbar" accessibilityLabel={t("agentes.loading")} accessibilityState={{ busy: true }}>
          <Text variant="callout" tone="mutedForeground">
            {t("app.loading")}
          </Text>
        </View>
      </Group>
    );
  }
  if (read.state === "error") {
    return (
      <Group title={t("agentes.title")} testID="home-agents">
        <View style={styles.pad}>
          <Text variant="callout" tone="mutedForeground" accessibilityRole="alert">
            {t("agentes.error")}
          </Text>
          <Button label={t("app.retry")} icon={icons.retry} variant="secondary" compact onPress={read.retry} />
        </View>
      </Group>
    );
  }
  if (read.items.length === 0) {
    return (
      <Group title={t("agentes.title")} testID="home-agents">
        <View style={styles.pad}>
          <Text variant="callout" tone="mutedForeground">
            {t("agentes.empty")}
          </Text>
        </View>
      </Group>
    );
  }
  return (
    <Group title={t("agentes.title")} testID="home-agents">
      {read.items.map((a) => (
        <AgentRow key={a.id} agent={a} onPress={() => onAgent(a.id)} t={t} />
      ))}
    </Group>
  );
}

function AgentRow({ agent, onPress, t }: { agent: AgentCard; onPress: () => void; t: T }) {
  const { colors } = useTheme();
  const state = agentStateLabel(agent.visible_state, t);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[agent.name, state].filter(Boolean).join(". ")}
      accessibilityHint={t("agentes.open")}
      onPress={onPress}
      android_ripple={{ color: colors.muted }}
      style={({ pressed }) => [styles.row, pressed ? { backgroundColor: colors.muted } : null]}
      testID={`agent-${agent.id}`}
    >
      <Icon name={icons.bot} size={20} tone="mutedForeground" />
      <View style={styles.text}>
        <Text variant="body">{agent.name}</Text>
        {state ? <Badge label={state} tone={toneOf(agent.visible_state.tone)} /> : null}
      </View>
      <Icon name={icons.chevron} size={14} tone="subtle" />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pad: { paddingHorizontal: 16, paddingVertical: 12, gap: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingHorizontal: 16, paddingVertical: 12 },
  text: { flex: 1, minWidth: 0, gap: 6 },
});
