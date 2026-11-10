import * as Crypto from "expo-crypto";
import { router } from "expo-router";
import { useState } from "react";
import { StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { useBizToday, useBlock, useReservasConfig } from "@/api/reservas-hooks";
import { BlockForm } from "@/features/reservas/block";
import { dayTitle } from "@/features/reservas/format";
import { errorText } from "@/features/reservas/screen";
import { useLocale, useT } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { glassAvailable } from "@/theme/glass";
import { useTheme } from "@/theme/theme";
import { useOnline } from "@/ui/online";
import { ErrorState, Skeleton } from "@/ui/states";
import { useToast } from "@/ui/toast";

/** «Bloquear horas», as a sheet (spec 044, R8.7, D5). */
export default function BloquearRoute() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const toast = useToast();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  const block = useBlock();
  const [error, setError] = useState<string | null>(null);
  return (
    <KeyboardAwareScrollView
      style={glassAvailable() ? undefined : { backgroundColor: colors.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      bottomOffset={24}
    >
      {config.data && today ? (
        <BlockForm
          config={config.data}
          today={today}
          saving={block.isPending}
          error={error}
          online={online}
          t={t}
          locale={locale}
          onSave={(b) => {
            setError(null);
            block.mutate({ ...b, key: Crypto.randomUUID() }, {
              onSuccess: () => {
                haptics.success();
                toast.show({ text: t("reservas.block.done", { day: dayTitle(b.date, locale).toLocaleLowerCase(locale) }) });
                router.back();
              },
              onError: (e) => setError(errorText(e, t)),
            });
          }}
        />
      ) : config.isError ? (
        <ErrorState onRetry={() => void config.refetch()} />
      ) : (
        <Skeleton rows={3} />
      )}
    </KeyboardAwareScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingTop: 28, paddingBottom: 48 },
});
