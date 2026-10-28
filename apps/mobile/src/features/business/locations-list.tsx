import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import type { Location, LocationBody } from "@/api/endpoints";
import type { T } from "@/i18n/t";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Field } from "@/ui/field";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

/** A location being written: a new one (`id` null) or a change to one that exists. */
export type LocationForm = { id: string | null; name: string; address: string; phone: string };

export function newLocation(): LocationForm {
  return { id: null, name: "", address: "", phone: "" };
}

export function locationForm(l: Location): LocationForm {
  return { id: l.id, name: l.name, address: l.address ?? "", phone: l.phone_e164 ?? "" };
}

const E164 = /^\+[1-9]\d{6,14}$/;

/** What the API would refuse (`locations.validate`), before sending. Spaces in a phone are the person's, not an error. */
export function checkLocation(f: LocationForm): "name_required" | "phone_invalid" | null {
  if (!f.name.trim()) return "name_required";
  const phone = f.phone.replace(/[\s()-]/g, "");
  if (phone && !E164.test(phone)) return "phone_invalid";
  return null;
}

export function locationBody(f: LocationForm): LocationBody {
  const phone = f.phone.replace(/[\s()-]/g, "");
  return { name: f.name.trim(), address: f.address.trim() || null, phone_e164: phone || null };
}

/**
 * Sedes (spec 047, T169; requirement 9): each with its address, its phone
 * and whose hours it uses; «Editar» opens its form in place, and archiving
 * one asks first and can be undone from the brief notice.
 */
export function LocationsList({
  items,
  form,
  onForm,
  onArchive,
  saveBar,
  problem,
  t,
}: {
  items: Location[];
  form: LocationForm | null;
  onForm: (f: LocationForm | null) => void;
  onArchive: (l: Location) => void;
  saveBar: ReactNode;
  problem: ReturnType<typeof checkLocation>;
  t: T;
}) {
  const shown = items.filter((l) => !l.archived);
  const editor = (f: LocationForm, l: Location | null) => (
    <Card key={f.id ?? "new"} testID={f.id ? `location-form-${f.id}` : "location-form-new"}>
      <Field label={t("business.locations.name")} value={f.name} onChangeText={(name) => onForm({ ...f, name })} maxLength={80} autoFocus={!l} />
      <Field label={t("business.locations.address")} value={f.address} onChangeText={(address) => onForm({ ...f, address })} maxLength={300} multiline textContentType="fullStreetAddress" />
      <Field label={t("business.locations.phone")} value={f.phone} onChangeText={(phone) => onForm({ ...f, phone })} keyboardType="phone-pad" textContentType="telephoneNumber" maxLength={20} />
      <Text variant="footnote" tone="mutedForeground">
        {t("business.locations.phone.hint")}
      </Text>
      {problem ? (
        <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
          {t(`business.locations.error.${problem}`)}
        </Text>
      ) : null}
      {saveBar}
      {l ? <Button label={t("business.locations.archive", { name: l.name })} icon={icons.archive} variant="destructive" full onPress={() => onArchive(l)} /> : null}
    </Card>
  );

  return (
    <View style={styles.stack} testID="locations">
      <Text variant="callout" tone="mutedForeground">
        {t("business.locations.intro")}
      </Text>
      {form?.id === null ? editor(form, null) : <Button label={t("business.locations.add")} icon={icons.plus} variant="secondary" full onPress={() => onForm(newLocation())} />}
      {shown.length === 0 && form?.id !== null ? (
        <Text variant="callout" tone="mutedForeground">
          {t("business.locations.empty")}
        </Text>
      ) : null}
      {shown.map((l) => {
        if (form && form.id === l.id) return editor(form, l);
        const hours = l.own_hours ? t("business.locations.own_hours") : t("business.locations.inherits");
        return (
          <Card key={l.id} testID={`location-${l.id}`}>
            <View accessible accessibilityLabel={[l.name, l.address, l.phone_e164, hours, l.label].filter(Boolean).join(". ")} style={styles.read}>
              <Text variant="headline">{l.name}</Text>
              {l.address ? <Text variant="callout">{l.address}</Text> : null}
              {l.phone_e164 ? (
                <Text variant="callout" tone="mutedForeground">
                  {l.phone_e164}
                </Text>
              ) : null}
              <Text variant="footnote" tone="mutedForeground">
                {l.label ? `${hours} · ${l.label}` : hours}
              </Text>
            </View>
            <Button
              label={t("business.section.edit")}
              accessibilityLabel={`${t("business.section.edit")} ${l.name}`}
              icon={icons.edit}
              variant="secondary"
              compact
              onPress={() => onForm(locationForm(l))}
            />
          </Card>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  read: { gap: 4 },
});
