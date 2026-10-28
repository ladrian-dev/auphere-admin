import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { endpoints, type Hours } from "@/api/endpoints";
import { keys } from "@/api/query";
import { useT } from "@/i18n/t";
import { checkWeek, DAYS, layoutFor, normalizeTime, sameWeek, weekOf, type Week, type WeekProblem } from "@/lib/business-model";
import { useDraft } from "@/lib/drafts";
import { Card } from "@/ui/card";
import { Text } from "@/ui/text";

import { HoursEditor } from "./hours-editor";
import { ConflictNotice, SaveBar, SwitchRow } from "./parts";
import { useSectionWrite } from "./use-section-write";

const normalized = (w: Week): Week => Object.fromEntries(DAYS.map((d) => [d, w[d].map((s) => ({ open: normalizeTime(s.open), close: normalizeTime(s.close) }))])) as Week;

/**
 * The week of the business or of one location (spec 047; requirements 9, 10,
 * 13.4, 50.4, 50.5). A location's week is its own or the business's it
 * inherits; the API keeps it with the Sedes, so its save carries that
 * revision. What is typed stays in a draft per place until it is saved;
 * without a connection nothing is sent or queued.
 */
export function WeekPane({ place, hours }: { place: string | null; hours: Hours }) {
  const t = useT();
  const qc = useQueryClient();
  const write = useSectionWrite(place ? "locations" : "hours");
  const [draft, setDraft] = useDraft<Week>(place ? `negocio.hours.${place}` : "negocio.hours");
  const [inherit, setInherit] = useDraft<boolean>(`negocio.hours.${place ?? "business"}.inherit`);
  const [problem, setProblem] = useState<WeekProblem | null>(null);
  const base = weekOf(hours);
  const week = draft ?? base;
  const inherits = place !== null && (inherit ?? hours.inherits);
  const dirty = (draft !== null && !sameWeek(draft, base)) || (place !== null && inherit !== null && inherit !== hours.inherits);

  const reset = () => {
    setDraft(null);
    setInherit(null);
    setProblem(null);
    write.reset();
  };

  const save = async () => {
    const next = normalized(week);
    if (!inherits) {
      setDraft(next);
      const p = checkWeek(next);
      setProblem(p);
      if (p) return;
    }
    const saved = { saved: t("business.section.saved") };
    const out =
      place === null
        ? await write.run((rev, key) => endpoints.putHours(next, layoutFor(next, hours.layout), rev, key), saved)
        : await write.run((rev, key) => endpoints.putLocationHours(place, inherits ? { inherit: true } : { days: next, layout: layoutFor(next, hours.layout) }, rev, key), {
            ...saved,
            into: "hours",
            revisionNow: () => qc.getQueryData<Hours>(keys.locationHours(place))?.revision ?? hours.revision,
            keep: (answer) => qc.setQueryData(keys.locationHours(place), answer),
          });
    if (out === "saved") {
      setDraft(null);
      setInherit(null);
    }
  };

  return (
    <View style={styles.stack}>
      {place !== null ? (
        <Card testID="hours-inherit">
          <SwitchRow
            label={t("business.hours.inherit")}
            value={inherits}
            onChange={(v) => {
              setInherit(v);
              write.reset();
            }}
          />
        </Card>
      ) : null}
      {inherits ? (
        <Card testID="hours-phrase">
          <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
            {t("business.hours.phrase")}
          </Text>
          <Text variant="body">{dirty ? t("business.hours.phrase.unsaved") : (hours.label ?? t("business.hours.phrase.none"))}</Text>
        </Card>
      ) : (
        <HoursEditor
          hours={hours}
          week={week}
          dirty={dirty}
          problem={problem}
          onWeek={(w) => {
            setDraft(w);
            setProblem(null);
            write.reset();
          }}
          t={t}
        />
      )}
      {write.conflict ? (
        <ConflictNotice busy={write.busy} onMine={() => void save()} onTheirs={reset} t={t} />
      ) : dirty ? (
        <SaveBar
          label={t("business.hours.save")}
          busy={write.busy}
          online={write.online}
          error={problem ? t("negocio.hours.check") : write.error}
          onSave={() => void save()}
          onCancel={reset}
          t={t}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
});
