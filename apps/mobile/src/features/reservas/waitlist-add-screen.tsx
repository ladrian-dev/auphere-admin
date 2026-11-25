import * as Crypto from "expo-crypto";
import { router, Stack } from "expo-router";
import { useRef, useState } from "react";
import { StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { useBizToday, useJoinWaitlist, useReservasConfig } from "@/api/reservas-hooks";
import { useLocale, useT } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { useTheme } from "@/theme/theme";
import { useOnline } from "@/ui/online";
import { ErrorState, Skeleton } from "@/ui/states";
import { useToast } from "@/ui/toast";

import { errorText } from "./screen";
import { WaitlistAddForm } from "./waitlist-add";

/**
 * «Apuntar en la lista de espera», stacked in the Reservas tab from the list
 * (spec 069, R16.1). One key per attempt, so a double tap never adds twice.
 */
export default function WaitlistAddScreen() {
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const toast = useToast();
  const { colors } = useTheme();
  const config = useReservasConfig();
  const today = useBizToday(config.data);
  const join = useJoinWaitlist();
  const key = useRef(Crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);

  return (
    <>
      <Stack.Screen options={{ title: t("reservas.wl.add.title"), headerLargeTitleEnabled: false }} />
      <KeyboardAwareScrollView
        style={{ backgroundColor: colors.background }}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
        bottomOffset={24}
        testID="apuntar"
      >
        {config.data && today ? (
          <WaitlistAddForm
            config={config.data}
            today={today}
            saving={join.isPending}
            error={error}
            online={online}
            t={t}
            locale={locale}
            onSave={(body) => {
              setError(null);
              join.mutate(
                { ...body, key: key.current },
                {
                  onSuccess: () => {
                    haptics.success();
                    toast.show({ text: t("reservas.wl.add.done", { name: body.name ?? "" }), tone: "ok" });
                    router.back();
                  },
                  onError: (e) => {
                    haptics.warning();
                    key.current = Crypto.randomUUID();
                    setError(errorText(e, t));
                  },
                },
              );
            }}
          />
        ) : config.isError ? (
          <ErrorState onRetry={() => void config.refetch()} />
        ) : (
          <Skeleton rows={4} />
        )}
      </KeyboardAwareScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, paddingBottom: 48 },
});
