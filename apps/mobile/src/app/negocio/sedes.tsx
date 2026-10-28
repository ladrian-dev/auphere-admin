import { Stack } from "expo-router";
import { useState } from "react";
import { Alert, StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { endpoints, type Location } from "@/api/endpoints";
import { useBusiness } from "@/api/hooks";
import { checkLocation, locationBody, LocationsList, type LocationForm } from "@/features/business/locations-list";
import { ConflictNotice, LastChange, SaveBar } from "@/features/business/parts";
import { useSectionWrite } from "@/features/business/use-section-write";
import { useLocale, useT } from "@/i18n/t";
import { lastUndoable } from "@/lib/business-model";
import { useDraft } from "@/lib/drafts";
import { clock } from "@/lib/format";
import { useTheme } from "@/theme/theme";
import { Card } from "@/ui/card";
import { ErrorState, OfflineBanner, Skeleton } from "@/ui/states";

/**
 * Negocio › Sedes (spec 047, T169; requirement 9, 50.4, 50.5): add, change
 * and archive a location. The list the API sends leaves archived ones out, so
 * «Restaurar» lives in the brief notice right after archiving (an API gap,
 * listed in the report); the history's «Deshacer» brings it back too.
 */
export default function Sedes() {
  const t = useT();
  const locale = useLocale();
  const { colors } = useTheme();
  const business = useBusiness();
  const write = useSectionWrite("locations");
  const [form, setForm] = useDraft<LocationForm>("negocio.location");
  const [problem, setProblem] = useState<ReturnType<typeof checkLocation>>(null);
  const [undoing, setUndoing] = useState(false);
  const data = business.data;
  const last = data ? lastUndoable(data.history, "locations") : null;

  const save = async () => {
    if (!form) return;
    const p = checkLocation(form);
    setProblem(p);
    if (p) return;
    const body = locationBody(form);
    const out = await write.run((rev, key) => (form.id ? endpoints.editLocation(form.id, body, rev, key) : endpoints.addLocation(body, rev, key)), {
      saved: t("negocio.locations.saved"),
    });
    if (out === "saved") setForm(null);
  };

  const archive = (l: Location) =>
    Alert.alert(t("negocio.locations.archive.confirm", { name: l.name }), t("negocio.locations.archive.body"), [
      { text: t("app.cancel"), style: "cancel" },
      {
        text: t("business.locations.archive", { name: l.name }),
        style: "destructive",
        onPress: () =>
          void write
            .run((rev, key) => endpoints.archiveLocation(l.id, rev, key), {
              saved: t("negocio.locations.archived", { name: l.name }),
              // Archived locations are not listed: the way back is here, right after.
              action: { label: t("business.history.undo"), onPress: () => void restore(l) },
            })
            .then((out) => {
              if (out === "saved") setForm(null);
            }),
      },
    ]);

  const restore = (l: Location) =>
    write.run((rev, key) => endpoints.restoreLocation(l.id, rev, key), { saved: t("negocio.locations.restored", { name: l.name }), undoable: false });

  const cancel = () => {
    setForm(null);
    setProblem(null);
    write.reset();
  };

  return (
    <>
      <Stack.Screen options={{ title: t("business.locations.title") }} />
      <KeyboardAwareScrollView
        testID="sedes"
        style={{ backgroundColor: colors.background }}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
        bottomOffset={24}
      >
        {!write.online && data ? <OfflineBanner since={clock(new Date(business.dataUpdatedAt), locale)} /> : null}
        {data ? (
          <>
            <LocationsList
              items={data.locations.items}
              form={form}
              onForm={(f) => {
                setForm(f);
                setProblem(null);
                write.reset();
              }}
              onArchive={archive}
              problem={problem}
              t={t}
              saveBar={
                write.conflict ? (
                  <ConflictNotice busy={write.busy} onMine={() => void save()} onTheirs={cancel} t={t} />
                ) : (
                  <SaveBar label={t("business.locations.save")} busy={write.busy} online={write.online} error={write.error} onSave={() => void save()} onCancel={cancel} t={t} />
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
          <Skeleton rows={3} label={t("negocio.loading")} />
        )}
      </KeyboardAwareScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12, paddingBottom: 48 },
});
