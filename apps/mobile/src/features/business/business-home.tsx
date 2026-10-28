import { StyleSheet, View } from "react-native";

import type { BusinessChange, BusinessSections } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { lastUndoable, provenanceText, sectionProvenance } from "@/lib/business-model";
import { Card } from "@/ui/card";
import { Group, Row } from "@/ui/group";
import { Text } from "@/ui/text";

import { LastChange } from "./parts";

/**
 * Negocio (spec 047, T169, 50.1): what the agents know about the business,
 * in three ways in — the hours (with the special dates), the services and the
 * locations — each saying what it holds and where its data came from (13.1).
 * Under them, the last change with «Deshacer» while it can be (13.3).
 */
export function BusinessHome({
  data,
  online,
  undoing,
  onHours,
  onServices,
  onLocations,
  onUndo,
  t,
  locale,
  now,
}: {
  data: BusinessSections;
  online: boolean;
  undoing: boolean;
  onHours: () => void;
  onServices: () => void;
  onLocations: () => void;
  onUndo: (change: BusinessChange) => void;
  t: T;
  locale: Locale;
  now?: Date;
}) {
  const specials = data.special_dates.items.filter((s) => !s.archived).length;
  const services = data.services.items.filter((s) => !s.archived).length;
  const locations = data.locations.items.filter((l) => !l.archived).length;
  const prov = (s: "hours" | "services" | "locations") => {
    const p = sectionProvenance(data.provenance, s);
    return p ? provenanceText(p, t) : undefined;
  };
  const count = (n: number, one: Parameters<T>[0], many: Parameters<T>[0]) => (n === 0 ? t("negocio.none") : n === 1 ? t(one) : t(many, { n }));
  const hoursHint = [data.hours.label ?? t("business.hours.phrase.none"), specials > 0 ? count(specials, "negocio.special.count.one", "negocio.special.count") : null, prov("hours")]
    .filter(Boolean)
    .join("\n");
  const last = lastUndoable(data.history);

  return (
    <View style={styles.stack}>
      <Text variant="callout" tone="mutedForeground">
        {t("negocio.intro")}
      </Text>
      <Group testID="business-sections">
        <Row label={t("business.hours.title")} hint={hoursHint} kind="push" onPress={onHours} testID="business-hours" />
        <Row
          label={t("business.services.title")}
          value={count(services, "negocio.services.count.one", "negocio.services.count")}
          hint={prov("services")}
          kind="push"
          onPress={onServices}
          testID="business-services"
        />
        <Row
          label={t("business.locations.title")}
          value={count(locations, "negocio.locations.count.one", "negocio.locations.count")}
          hint={prov("locations")}
          kind="push"
          onPress={onLocations}
          testID="business-locations"
        />
      </Group>
      {last ? (
        <Card>
          <LastChange change={last} busy={undoing} online={online} onUndo={() => onUndo(last)} t={t} locale={locale} now={now} />
        </Card>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
});
