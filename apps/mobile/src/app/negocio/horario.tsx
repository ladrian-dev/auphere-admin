import { Stack } from "expo-router";
import { useState } from "react";
import { Alert, StyleSheet, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { endpoints, type SpecialDate } from "@/api/endpoints";
import { useBusiness, useLocationHours } from "@/api/hooks";
import { ConflictNotice, LastChange, SaveBar } from "@/features/business/parts";
import { checkSpecial, SpecialDatesSection, type SpecialForm } from "@/features/business/special-dates";
import { useSectionWrite } from "@/features/business/use-section-write";
import { WeekPane } from "@/features/business/week-pane";
import { useLocale, useT } from "@/i18n/t";
import { lastUndoable, normalizeTime, todayLocal } from "@/lib/business-model";
import { useDraft } from "@/lib/drafts";
import { clock } from "@/lib/format";
import { useTheme } from "@/theme/theme";
import { Card } from "@/ui/card";
import { Chip } from "@/ui/chip";
import { ErrorState, OfflineBanner, Skeleton } from "@/ui/states";
import { Text } from "@/ui/text";

/**
 * Negocio › Horario (spec 047, T169; requirements 10, 13, 50.4, 50.5): the
 * week and the special dates. What is typed lives in a draft (memory only)
 * until it is saved: without a connection the bar says so and nothing is
 * sent or queued; leaving and coming back finds it as it was. A save carries
 * the revision; if someone saved first, the person chooses (13.4). Saved, the
 * agent uses it from the next message, and «Deshacer» is one tap away. With
 * locations, «Horario de» picks whose week: a location has its own or uses
 * the business's (9, 10).
 */

export default function Horario() {
  const t = useT();
  const locale = useLocale();
  const { colors } = useTheme();
  const business = useBusiness();
  const hours = useSectionWrite("hours");
  const specials = useSectionWrite("special_dates");
  const [form, setForm] = useDraft<SpecialForm>("negocio.special");
  const [specialProblem, setSpecialProblem] = useState<ReturnType<typeof checkSpecial>>(null);
  const [undoing, setUndoing] = useState(false);
  const data = business.data;
  const live = data ? data.locations.items.filter((l) => !l.archived) : [];
  const [chosen, setChosen] = useState<string | null>(null);
  // A location archived meanwhile goes back to the whole business.
  const place = chosen !== null && live.some((l) => l.id === chosen) ? chosen : null;
  const placeHours = useLocationHours(place);
  const today = todayLocal();
  const last = data ? lastUndoable(data.history, ["hours", "special_dates"]) : null;

  const saveSpecial = async () => {
    if (!form) return;
    const f = { ...form, shifts: form.shifts.map((s) => ({ open: normalizeTime(s.open), close: normalizeTime(s.close) })) };
    setForm(f);
    const p = checkSpecial(f);
    setSpecialProblem(p);
    if (p) return;
    const body = { name: f.name.trim() || null, from: f.from, to: f.to, closed: f.closed, shifts: f.closed ? [] : f.shifts, location_id: f.location_id };
    const out = await specials.run(
      (rev, key) => (f.id ? endpoints.editSpecialDate(f.id, body, rev, key) : endpoints.addSpecialDate(body, rev, key)),
      { saved: t("negocio.special.saved") },
    );
    if (out === "saved") setForm(null);
  };

  const remove = (s: SpecialDate) => {
    const name = s.name || t("negocio.special.unnamed");
    Alert.alert(t("negocio.special.remove.confirm", { name }), t("negocio.special.remove.body"), [
      { text: t("app.cancel"), style: "cancel" },
      {
        text: t("business.special.remove", { name }),
        style: "destructive",
        onPress: () => void specials.run((rev, key) => endpoints.archiveSpecialDate(s.id, rev, key), { saved: t("negocio.special.removed") }),
      },
    ]);
  };

  return (
    <>
      <Stack.Screen options={{ title: t("business.hours.title") }} />
      <KeyboardAwareScrollView
        testID="horario"
        style={{ backgroundColor: colors.background }}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
        bottomOffset={24}
      >
        {!hours.online && data ? <OfflineBanner since={clock(new Date(business.dataUpdatedAt), locale)} /> : null}
        {data ? (
          <>
            {live.length > 0 ? (
              <View style={styles.where} accessibilityRole="radiogroup" accessibilityLabel={t("business.hours.of")}>
                <Text variant="subhead">{t("business.hours.of")}</Text>
                <View style={styles.chips}>
                  <Chip label={t("business.hours.of.business")} on={place === null} onPress={() => setChosen(null)} />
                  {live.map((l) => (
                    <Chip key={l.id} label={l.name} on={place === l.id} onPress={() => setChosen(l.id)} />
                  ))}
                </View>
              </View>
            ) : null}
            {place === null ? (
              <WeekPane key="business" place={null} hours={data.hours} />
            ) : placeHours.data ? (
              <WeekPane key={place} place={place} hours={placeHours.data} />
            ) : placeHours.isError ? (
              <ErrorState body={t("business.section.error")} onRetry={() => void placeHours.refetch()} />
            ) : (
              <Skeleton rows={3} label={t("negocio.loading")} />
            )}
            <View style={styles.gap} />
            <SpecialDatesSection
              items={data.special_dates.items}
              locations={data.locations.items}
              form={form}
              onForm={(f) => {
                setForm(f);
                setSpecialProblem(null);
                specials.reset();
              }}
              onRemove={remove}
              problem={specialProblem}
              today={today}
              t={t}
              locale={locale}
              saveBar={
                specials.conflict ? (
                  <ConflictNotice
                    busy={specials.busy}
                    onMine={() => void saveSpecial()}
                    onTheirs={() => {
                      setForm(null);
                      specials.reset();
                    }}
                    t={t}
                  />
                ) : (
                  <SaveBar
                    label={t("business.special.save")}
                    busy={specials.busy}
                    online={specials.online}
                    error={specials.error}
                    onSave={() => void saveSpecial()}
                    onCancel={() => {
                      setForm(null);
                      specials.reset();
                    }}
                    t={t}
                  />
                )
              }
            />
            {last ? (
              <Card>
                <LastChange
                  change={last}
                  busy={undoing}
                  online={hours.online}
                  onUndo={(id) => {
                    setUndoing(true);
                    void hours.undo(id).finally(() => setUndoing(false));
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
  gap: { height: 12 },
  where: { gap: 8 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
});
