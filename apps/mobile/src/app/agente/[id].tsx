import { useQueryClient } from "@tanstack/react-query";
import { Stack, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert } from "react-native";

import { endpoints, type AgentCard, type AgentChannel } from "@/api/endpoints";
import { useAgents, useMe } from "@/api/hooks";
import { invalidateAgents, keys } from "@/api/query";
import { AgentView } from "@/features/agents/agent-view";
import { useLocale, useT } from "@/i18n/t";
import { agentErrorText, confirmRequired, partnerOf, withCard, withChannel } from "@/lib/agents-model";
import { clock } from "@/lib/format";
import { useNowMs } from "@/lib/use-now";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { haptics } from "@/motion/haptics";
import { icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { ScrollScreen } from "@/ui/screen";
import { EmptyState, ErrorState, OfflineBanner, Skeleton } from "@/ui/states";
import { useToast } from "@/ui/toast";

/**
 * Agentes › un agente (spec 047, T169; 27, 50.1, 50.2): opened from Inicio
 * and from a notice about it (T170). The API has no read of one agent: it is
 * the list's, so the card and Inicio stay one source. Pausing an agent with
 * conversations in progress asks first and says how many (27.8); everything
 * else acts at once and the screen shows the new state.
 */
type Agents = { items: AgentCard[] };

export default function AgentScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const toast = useToast();
  const qc = useQueryClient();
  const me = useMe();
  const agents = useAgents();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pull = usePullRefresh(() => agents.refetch());
  // «En pausa desde hace 5 min» moves with the clock (a ticking clock is state: 044 R1).
  const now = useNowMs();
  const partner = partnerOf(me.data?.balance_contact);
  const card = agents.data?.items.find((a) => a.id === id) ?? null;

  const done = (next: AgentCard, text: string) => {
    qc.setQueryData<Agents>(keys.agents, (list) => withCard(list, next));
    invalidateAgents(qc);
    haptics.success();
    toast.show({ text });
  };

  const fail = (e: unknown) => {
    haptics.warning();
    setError(agentErrorText(e, partner, t));
    void agents.refetch();
  };

  const pause = async (confirm = false) => {
    if (!card) return;
    setBusy(card.id);
    setError(null);
    try {
      done(await endpoints.pauseAgent(card.id, confirm), t("builder.life.paused.toast", { name: card.name }));
    } catch (e) {
      const open = confirmRequired(e);
      if (open !== null) {
        // 27.8: only with conversations in progress, and saying how many.
        Alert.alert(
          t("builder.life.pause.title", { name: card.name }),
          open === 1 ? t("builder.life.pause.open.one") : t("builder.life.pause.open.other", { n: open }),
          [
            { text: t("app.cancel"), style: "cancel" },
            { text: t("builder.life.pause.confirm"), style: "destructive", onPress: () => void pause(true) },
          ],
        );
      } else fail(e);
    } finally {
      setBusy(null);
    }
  };

  const resume = async () => {
    if (!card) return;
    setBusy(card.id);
    setError(null);
    try {
      done(await endpoints.resumeAgent(card.id), t("builder.life.resumed", { name: card.name }));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  };

  const channel = async (c: AgentChannel, action: "pause" | "resume") => {
    setBusy(c.id);
    setError(null);
    try {
      const next = action === "pause" ? await endpoints.pauseChannel(c.id) : await endpoints.resumeChannel(c.id);
      qc.setQueryData<Agents>(keys.agents, (list) => withChannel(list, next));
      invalidateAgents(qc);
      haptics.success();
      toast.show({ text: t(action === "pause" ? "agentes.channel.paused" : "agentes.channel.resumed", { number: c.identifier }) });
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <Stack.Screen options={{ title: card?.name ?? t("agentes.title") }} />
      <ScrollScreen refreshing={pull.refreshing} onRefresh={pull.onRefresh} testID="agente">
        {!online && agents.data ? <OfflineBanner since={clock(new Date(agents.dataUpdatedAt), locale)} /> : null}
        {card ? (
          <AgentView
            card={card}
            partner={partner}
            online={online}
            busy={busy}
            error={error}
            onPause={() => void pause()}
            onResume={() => void resume()}
            onChannel={(c, a) => void channel(c, a)}
            t={t}
            locale={locale}
            now={new Date(now)}
          />
        ) : agents.data ? (
          <EmptyState icon={icons.bot} title={t("agentes.gone")} body={t("agentes.gone.body")} />
        ) : agents.isError ? (
          <ErrorState body={t("agentes.error")} onRetry={() => void agents.refetch()} />
        ) : (
          <Skeleton rows={3} label={t("agentes.loading")} />
        )}
      </ScrollScreen>
    </>
  );
}
