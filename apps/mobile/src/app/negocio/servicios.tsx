import { Stack } from "expo-router";
import { useState } from "react";
import { Alert, StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { endpoints, type Service } from "@/api/endpoints";
import { useBusiness, useMe } from "@/api/hooks";
import { ConflictNotice, LastChange, SaveBar } from "@/features/business/parts";
import { checkService, serviceBody, ServicesList, type ServiceForm } from "@/features/business/services-list";
import { useSectionWrite } from "@/features/business/use-section-write";
import { useLocale, useT } from "@/i18n/t";
import { partnerOf } from "@/lib/agents-model";
import { lastUndoable } from "@/lib/business-model";
import { useDraft } from "@/lib/drafts";
import { clock } from "@/lib/format";
import { useTheme } from "@/theme/theme";
import { Card } from "@/ui/card";
import { ErrorState, OfflineBanner, Skeleton } from "@/ui/states";

/**
 * Negocio › Servicios (spec 047, T169; requirement 11, 50.1, 50.4, 50.5):
 * price, duration, description and whether it is booked; a new service;
 * archiving one. One form open at a time, kept in memory until saved.
 */
export default function Servicios() {
  const t = useT();
  const locale = useLocale();
  const { colors } = useTheme();
  const me = useMe();
  const business = useBusiness();
  const write = useSectionWrite("services");
  const [form, setForm] = useDraft<ServiceForm>("negocio.service");
  const [problem, setProblem] = useState<ReturnType<typeof checkService>>(null);
  const [undoing, setUndoing] = useState(false);
  const data = business.data;
  const last = data ? lastUndoable(data.history, "services") : null;

  const save = async () => {
    if (!form || !data) return;
    const p = checkService(form, data.services.exponent);
    setProblem(p);
    if (p) return;
    const body = serviceBody(form, data.services.exponent);
    const { name: _name, ...patch } = body;
    const out = await write.run((rev, key) => (form.id ? endpoints.editService(form.id, patch, rev, key) : endpoints.addService(body, rev, key)), {
      saved: t("negocio.services.saved"),
    });
    if (out === "saved") setForm(null);
  };

  const archive = (s: Service) =>
    Alert.alert(t("negocio.services.archive.confirm", { name: s.name }), t("negocio.services.archive.body"), [
      { text: t("app.cancel"), style: "cancel" },
      {
        text: t("business.services.archive", { name: s.name }),
        style: "destructive",
        onPress: () =>
          void write.run((rev, key) => endpoints.archiveService(s.id, rev, key), { saved: t("business.services.archived") }).then((out) => {
            if (out === "saved") setForm(null);
          }),
      },
    ]);

  const cancel = () => {
    setForm(null);
    setProblem(null);
    write.reset();
  };

  return (
    <>
      <Stack.Screen options={{ title: t("business.services.title") }} />
      <KeyboardAwareScrollView
        testID="servicios"
        style={{ backgroundColor: colors.background }}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
        bottomOffset={24}
      >
        {!write.online && data ? <OfflineBanner since={clock(new Date(business.dataUpdatedAt), locale)} /> : null}
        {data ? (
          <>
            <ServicesList
              services={data.services}
              form={form}
              onForm={(f) => {
                setForm(f);
                setProblem(null);
                write.reset();
              }}
              onArchive={archive}
              problem={problem}
              partner={partnerOf(me.data?.balance_contact)}
              t={t}
              locale={locale}
              saveBar={
                write.conflict ? (
                  <ConflictNotice busy={write.busy} onMine={() => void save()} onTheirs={cancel} t={t} />
                ) : (
                  <SaveBar label={t("business.services.save")} busy={write.busy} online={write.online} error={write.error} onSave={() => void save()} onCancel={cancel} t={t} />
                )
              }
            />
            {last ? (
              <Card>
                <LastChange
                  change={last}
                  busy={undoing}
                  online={write.online}
                  onUndo={(id) => {
                    setUndoing(true);
                    void write.undo(id).finally(() => setUndoing(false));
                  }}
                  t={t}
                  locale={locale}
                />
              </Card>
            ) : null}
          </>
        ) : business.isError ? (
          <ErrorState body={t("business.section.error")} onRetry={() => void business.refetch()} />
        ) : (
          <Skeleton rows={4} label={t("negocio.loading")} />
        )}
      </KeyboardAwareScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12, paddingBottom: 48 },
});
