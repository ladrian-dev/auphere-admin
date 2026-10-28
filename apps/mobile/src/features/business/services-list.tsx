import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import type { Service, ServiceBody, Services } from "@/api/endpoints";
import type { Locale, MessageKey, T } from "@/i18n/t";
import { amountField, parseAmount, parseMinutes, priceOf, priceText } from "@/lib/business-model";
import { Segmented } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Field } from "@/ui/field";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { SwitchRow } from "./parts";

/** A service being written: a new one (`id` null) or a change to one that exists (its name is the partner's to change). */
export type ServiceForm = {
  id: string | null;
  name: string;
  description: string;
  bookable: boolean;
  duration: string;
  priceKind: "none" | "free" | "amount";
  amount: string;
};

export function newService(): ServiceForm {
  return { id: null, name: "", description: "", bookable: true, duration: "30", priceKind: "none", amount: "" };
}

export function serviceForm(s: Service, exponent: number, locale: Locale): ServiceForm {
  const price = priceOf(s);
  return {
    id: s.id,
    name: s.name,
    description: s.description ?? "",
    bookable: s.bookable,
    duration: s.duration_min != null ? String(s.duration_min) : "",
    priceKind: price.kind,
    amount: price.kind === "amount" ? amountField(price.amount_minor, exponent, locale) : "",
  };
}

const DURATION = { min: 5, max: 480, step: 5 };

/** What the API would refuse (`services_catalog.validate`), before sending: its codes. */
export function checkService(f: ServiceForm, exponent: number): "name_required" | "duration_required" | "duration_invalid" | "price_amount_required" | "price_invalid" | null {
  if (f.id === null && !f.name.trim()) return "name_required";
  if (f.bookable) {
    const m = parseMinutes(f.duration);
    if (m === null) return "duration_required";
    if (Number.isNaN(m) || m < DURATION.min || m > DURATION.max || m % DURATION.step !== 0) return "duration_invalid";
  }
  if (f.priceKind === "amount") {
    if (!f.amount.trim()) return "price_amount_required";
    if (parseAmount(f.amount, exponent) === null) return "price_invalid";
  }
  return null;
}

/** The body for the API: a service that is not booked carries no duration (`duration_not_allowed`). */
export function serviceBody(f: ServiceForm, exponent: number): ServiceBody {
  const price: ServiceBody["price"] =
    f.priceKind === "amount" ? { kind: "amount", amount_minor: parseAmount(f.amount, exponent) } : { kind: f.priceKind, amount_minor: null };
  return {
    name: f.name.trim(),
    description: f.description.trim() || null,
    bookable: f.bookable,
    duration_min: f.bookable ? parseMinutes(f.duration) : null,
    price,
  };
}

/**
 * Servicios (spec 047, T169; requirement 11, 50.1): each service with its
 * price, its duration and whether it is booked; «Editar» opens its form in
 * place. Who does it and which agents offer it are the partner's (50.3): they
 * are read here, never offered as controls.
 */
export function ServicesList({
  services,
  form,
  onForm,
  onArchive,
  saveBar,
  problem,
  partner,
  t,
  locale,
}: {
  services: Services;
  form: ServiceForm | null;
  onForm: (f: ServiceForm | null) => void;
  onArchive: (s: Service) => void;
  saveBar: ReactNode;
  problem: ReturnType<typeof checkService>;
  /** Whom the rest belongs to: who does it and which agents offer it (50.3). */
  partner: string;
  t: T;
  locale: Locale;
}) {
  const items = services.items.filter((s) => !s.archived);
  const { currency, exponent } = services;
  const editor = (f: ServiceForm, s: Service | null) => (
    <Card key={f.id ?? "new"} testID={f.id ? `service-form-${f.id}` : "service-form-new"}>
      {s ? (
        <Text variant="headline" accessibilityRole="header">
          {s.name}
        </Text>
      ) : (
        <Field label={t("business.services.name")} value={f.name} onChangeText={(name) => onForm({ ...f, name })} maxLength={120} autoFocus />
      )}
      <Text variant="subhead">{t("business.services.price")}</Text>
      <Segmented
        label={t("business.services.price")}
        value={f.priceKind}
        onChange={(priceKind) => onForm({ ...f, priceKind })}
        options={[
          { value: "none", label: t("business.services.price.none") },
          { value: "free", label: t("business.services.price.free") },
          { value: "amount", label: t("business.services.price.amount") },
        ]}
      />
      {f.priceKind === "amount" ? (
        <Field
          label={t("business.services.price.amount_in", { currency })}
          value={f.amount}
          onChangeText={(amount) => onForm({ ...f, amount })}
          keyboardType={exponent > 0 ? "decimal-pad" : "number-pad"}
        />
      ) : f.priceKind === "none" ? (
        <Text variant="footnote" tone="mutedForeground">
          {t("business.services.price.none.hint")}
        </Text>
      ) : null}
      <SwitchRow label={t("business.services.bookable")} value={f.bookable} onChange={(bookable) => onForm({ ...f, bookable, duration: bookable ? f.duration || "30" : f.duration })} />
      {f.bookable ? (
        <Field label={t("negocio.services.minutes.field")} value={f.duration} onChangeText={(duration) => onForm({ ...f, duration })} keyboardType="number-pad" maxLength={3} />
      ) : null}
      <Field label={t("business.services.description")} value={f.description} onChangeText={(description) => onForm({ ...f, description })} multiline maxLength={1000} />
      {problem ? (
        <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
          {t(`business.services.error.${problem}` as MessageKey)}
        </Text>
      ) : null}
      {saveBar}
      {s ? <Button label={t("business.services.archive", { name: s.name })} icon={icons.archive} variant="destructive" full onPress={() => onArchive(s)} /> : null}
    </Card>
  );

  return (
    <View style={styles.stack} testID="services">
      <Text variant="callout" tone="mutedForeground">
        {t("negocio.services.intro", { partner })}
      </Text>
      {form?.id === null ? editor(form, null) : <Button label={t("business.services.add")} icon={icons.plus} variant="secondary" full onPress={() => onForm(newService())} />}
      {items.length === 0 && form?.id !== null ? (
        <Text variant="callout" tone="mutedForeground">
          {t("negocio.services.empty")}
        </Text>
      ) : null}
      {items.map((s) => {
        if (form && form.id === s.id) return editor(form, s);
        const price = priceText(priceOf(s), currency, exponent, locale, t);
        const facts = [s.bookable && s.duration_min != null ? t("business.services.minutes", { n: s.duration_min }) : null, s.bookable ? t("business.services.bookable") : t("business.services.not_bookable")]
          .filter(Boolean)
          .join(" · ");
        const usedBy = s.used_by.length > 0 ? `${t("business.services.used_by")}: ${s.used_by.map((a) => a.name).join(", ")}` : t("business.services.used_by.nobody");
        return (
          <Card key={s.id} testID={`service-${s.id}`}>
            <View accessible accessibilityLabel={[s.name, price, facts, s.description, usedBy].filter(Boolean).join(". ")} style={styles.read}>
              <View style={styles.title}>
                <Text variant="headline" style={styles.flex}>
                  {s.name}
                </Text>
                <Text variant="bodyStrong">{price}</Text>
              </View>
              <Text variant="callout" tone="mutedForeground">
                {facts}
              </Text>
              {s.description ? (
                <Text variant="callout" numberOfLines={3}>
                  {s.description}
                </Text>
              ) : null}
              <Text variant="footnote" tone="mutedForeground">
                {usedBy}
              </Text>
            </View>
            <Button
              label={t("business.section.edit")}
              accessibilityLabel={t("business.services.edit", { name: s.name })}
              icon={icons.edit}
              variant="secondary"
              compact
              onPress={() => onForm(serviceForm(s, exponent, locale))}
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
  title: { flexDirection: "row", alignItems: "baseline", gap: 12, flexWrap: "wrap" },
  flex: { flex: 1, minWidth: 0 },
});
