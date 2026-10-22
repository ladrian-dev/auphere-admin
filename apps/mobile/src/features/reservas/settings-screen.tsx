import { router, Stack } from "expo-router";
import { RefreshControl, ScrollView, StyleSheet } from "react-native";

import { demo } from "@/api/reservas";
import { usePatchReservasConfig, useReservasConfig, useUnblock } from "@/api/reservas-hooks";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { haptics } from "@/motion/haptics";
import { useTheme } from "@/theme/theme";
import { useOnline } from "@/ui/online";
import { useToast } from "@/ui/toast";

import { ReservasBody } from "./body";
import { errorText } from "./screen";
import { ReservasSettings } from "./settings";

/** «Ajustes de reservas», stacked inside the Reservas tab (spec 044, Requisito 8, D5). */
export default function SettingsScreen() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const toast = useToast();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const patch = usePatchReservasConfig();
  const unblock = useUnblock();
  const state = config.isError && !config.data ? "error" : config.data ? "ready" : "loading";
  const pull = usePullRefresh(() => config.refetch());

  return (
    <>
      <Stack.Screen options={{ title: t("reservas.settings.title"), headerLargeTitleEnabled: false }} />
      <ScrollView
        style={{ backgroundColor: colors.background }}
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={pull.refreshing} onRefresh={pull.onRefresh} tintColor={colors.primaryText} />}
      >
        <ReservasBody
          state={state}
          offline={!online}
          demo={demo !== null}
          offlineSince={!online && config.data ? clock(new Date(config.dataUpdatedAt), locale) : null}
          partial={false}
          onRetry={() => void config.refetch()}
          t={t}
        >
          {config.data ? (
            <ReservasSettings
              config={config.data}
              online={online}
              saving={patch.isPending}
              t={t}
              locale={locale}
              onPatch={(p) =>
                patch.mutate({ patch: p, version: config.data!.version }, {
                  onSuccess: () => haptics.light(),
                  onError: (e) => toast.show({ text: errorText(e, t) }),
                })
              }
              onUnblock={(b) =>
                unblock.mutate(b.id, {
                  onSuccess: () => toast.show({ text: t("reservas.settings.blocks.removed") }),
                  onError: (e) => toast.show({ text: errorText(e, t) }),
                })
              }
              onBlock={() => router.push("/reserva/bloquear")}
            />
          ) : null}
        </ReservasBody>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, paddingBottom: 48 },
});
