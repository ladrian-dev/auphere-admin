import { ScrollView, StyleSheet, Switch, View } from "react-native";

import type { Block, ConfigPatch, ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { hhmm } from "@/lib/reservas-model";
import { TOUCH, useTheme } from "@/theme/theme";
import { Button, IconButton } from "@/ui/button";
import { Chip } from "@/ui/chip";
import { Group, Row } from "@/ui/group";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";
import { switchColors } from "@/ui/switch-colors";

import { dayTitle, duration, price } from "./format";

const STAYS = [60, 90, 120, 150];
const LEADS = [1, 2, 4, 24];

/**
 * «Ajustes de reservas» (spec 044, Requisito 8): the mode (from the admin),
 * the business hours (from the profile; edited on the web), and what the API
 * lets this person change from the console customers — and therefore from
 * here (clarification 1): in Aforo the capacity, the table time, the maximum
 * per booking and the seats kept for walk-ins; the waitlist and its notice;
 * the confirmation; and the blocks. What it does not let change is read, with
 * where it changes, never a control that does nothing. In Servicios the team
 * (with its Google Calendar) and the services are read here and edited on the
 * web.
 */
export function ReservasSettings({
  config,
  online,
  saving,
  onPatch,
  onUnblock,
  onBlock,
  t,
  locale,
}: {
  config: ResConfig;
  online: boolean;
  saving: boolean;
  onPatch: (p: ConfigPatch) => void;
  onUnblock: (b: Block) => void;
  onBlock: () => void;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const cap = config.capacity;
  // Editable is the API's word and the network; saving only disables — the controls stay
  // mounted so the screen reader keeps its place (WCAG 2.4.3, gate review).
  const capEditable = !!cap?.editable && online;
  const waitEditable = config.waitlist.editable && online;
  const confEditable = config.confirmation.editable && online;
  const unit = cap?.unit ?? "";

  return (
    <View style={styles.stack}>
      <Group>
        <Row
          label={t("reservas.settings.mode")}
          value={t(config.mode === "capacity" ? "reservas.settings.mode.capacity" : "reservas.settings.mode.services")}
          hint={t("reservas.settings.mode.hint")}
        />
      </Group>

      {cap ? (
        <Group title={t("reservas.settings.capacity")}>
          <NumberRow
            label={t("reservas.settings.capacity.max")}
            value={cap.capacity}
            shown={`${cap.capacity} ${unit}`}
            step={2}
            min={10}
            editable={capEditable} busy={saving}
            onChange={(v) => onPatch({ capacity: { capacity: v } })}
            t={t}
          />
          <View style={styles.block}>
            <Text variant="body">{t("reservas.settings.capacity.stay")}</Text>
            {capEditable ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup">
                {STAYS.map((m) => (
                  <Chip key={m} label={duration(m, t)} on={cap.stayMin === m} disabled={saving} onPress={() => onPatch({ capacity: { stayMin: m } })} />
                ))}
              </ScrollView>
            ) : (
              <Text variant="bodyStrong">{duration(cap.stayMin, t)}</Text>
            )}
          </View>
          <NumberRow label={t("reservas.settings.capacity.maxParty")} value={cap.maxParty} shown={`${cap.maxParty} ${unit}`} step={1} min={1} editable={capEditable} busy={saving} onChange={(v) => onPatch({ capacity: { maxParty: v } })} t={t} />
          <NumberRow
            label={t("reservas.settings.capacity.walkin")}
            hint={t("reservas.settings.capacity.walkin.hint")}
            value={cap.walkinReserved}
            shown={`${cap.walkinReserved} ${unit}`}
            step={1}
            min={0}
            editable={capEditable} busy={saving}
            onChange={(v) => onPatch({ capacity: { walkinReserved: v } })}
            t={t}
          />
          {!cap.editable ? <Row label={t("reservas.settings.readOnly")} tone="mutedForeground" /> : null}
        </Group>
      ) : null}

      <Group title={t("reservas.settings.hours")}>
        {hourRuns(config, t).map((run) =>
          // Aforo's shifts are long: under the days, not squeezed beside them (first iOS pass).
          cap && run.text !== t("reservas.settings.closed") ? (
            <Row key={run.from} label={run.days} hint={run.text} />
          ) : (
            <Row key={run.from} label={run.days} value={run.text} />
          ),
        )}
        <Row label={t("reservas.settings.hours.hint")} tone="mutedForeground" />
      </Group>

      {config.services ? (
        <>
          <Group title={t("reservas.settings.team")}>
            {config.services.team.map((p) => (
              <Row key={p.id} label={p.name} hint={t(p.calendar === "google" ? "reservas.settings.team.google" : "reservas.settings.team.none")} />
            ))}
          </Group>
          <Group title={t("reservas.settings.services")}>
            {config.services.catalog.map((s) => (
              <Row key={s.id} label={s.name} value={s.price === null ? duration(s.durationMin, t) : `${duration(s.durationMin, t)} · ${price(s.price, config.currency, locale)}`} />
            ))}
            <Row label={t("reservas.settings.readOnly")} tone="mutedForeground" />
          </Group>
        </>
      ) : null}

      <Group title={t("reservas.settings.waitlist")}>
        <SwitchRow
          label={t("reservas.settings.waitlist.toggle")}
          value={config.waitlist.enabled}
          editable={waitEditable}
          busy={saving}
          onChange={(v) => onPatch({ waitlist: { enabled: v } })}
          t={t}
        />
        <View style={styles.block}>
          <Text variant="body">{t("reservas.settings.waitlist.lead")}</Text>
          {waitEditable ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup">
              {LEADS.map((h) => (
                <Chip key={h} label={t("reservas.settings.hoursN", { h })} on={config.waitlist.leadHours === h} disabled={saving} onPress={() => onPatch({ waitlist: { leadHours: h } })} />
              ))}
            </ScrollView>
          ) : (
            <Text variant="bodyStrong">{t("reservas.settings.hoursN", { h: config.waitlist.leadHours })}</Text>
          )}
          <Text variant="footnote" tone="mutedForeground">
            {t("reservas.settings.waitlist.lead.hint")}
          </Text>
        </View>
        <SwitchRow
          label={t("reservas.settings.confirmation")}
          hint={t(`reservas.settings.confirmation.${config.confirmation.when}`)}
          value={config.confirmation.enabled}
          editable={confEditable}
          busy={saving}
          onChange={(v) => onPatch({ confirmation: { enabled: v } })}
          t={t}
        />
        {!config.waitlist.editable || !config.confirmation.editable ? <Row label={t("reservas.settings.readOnly")} tone="mutedForeground" /> : null}
      </Group>

      {cap ? (
        <View style={styles.stackSmall}>
          <Group title={t("reservas.settings.blocks")}>
            {cap.blocks.length === 0 ? (
              <Row label={t("reservas.settings.blocks.empty")} tone="mutedForeground" />
            ) : (
              cap.blocks.map((b) => (
                <View key={b.id} style={styles.blockRow}>
                  <View style={styles.flex}>
                    <Text variant="body">{`${dayTitle(b.date, locale)} · ${b.shift ?? `${hhmm(b.from)}–${hhmm(b.until)}`}`}</Text>
                    <Text variant="footnote" tone="mutedForeground">
                      {b.reason}
                    </Text>
                  </View>
                  {capEditable ? <Button label={t("reservas.settings.blocks.remove")} variant="ghost" compact onPress={() => onUnblock(b)} /> : null}
                </View>
              ))
            )}
          </Group>
          {online ? <Button label={t("reservas.menu.block")} variant="secondary" icon={icons.block} onPress={onBlock} /> : null}
        </View>
      ) : null}
      <View style={{ height: 8, backgroundColor: colors.background }} />
    </View>
  );
}

function NumberRow({
  label,
  hint,
  value,
  shown,
  step,
  min,
  editable,
  busy,
  onChange,
  t,
}: {
  label: string;
  hint?: string;
  value: number;
  shown: string;
  step: number;
  min: number;
  editable: boolean;
  busy: boolean;
  onChange: (v: number) => void;
  t: T;
}) {
  if (!editable) return <Row label={label} value={shown} hint={hint} />;
  return (
    <View style={styles.numberRow}>
      <View style={styles.flex}>
        <Text variant="body">{label}</Text>
        {hint ? (
          <Text variant="footnote" tone="mutedForeground">
            {hint}
          </Text>
        ) : null}
      </View>
      <IconButton icon={icons.minus} label={`${label}: ${t("reservas.stepper.minus").toLocaleLowerCase()}`} disabled={busy || value - step < min} onPress={() => onChange(value - step)} />
      <Text variant="bodyStrong" style={styles.num} accessibilityLabel={`${label}: ${shown}`}>
        {String(value)}
      </Text>
      <IconButton icon={icons.plus} label={`${label}: ${t("reservas.stepper.plus").toLocaleLowerCase()}`} disabled={busy} onPress={() => onChange(value + step)} />
    </View>
  );
}

function SwitchRow({ label, hint, value, editable, busy, onChange, t }: { label: string; hint?: string; value: boolean; editable: boolean; busy: boolean; onChange: (v: boolean) => void; t: T }) {
  const { colors } = useTheme();
  if (!editable) return <Row label={label} value={t(value ? "reservas.settings.yes" : "reservas.settings.no")} hint={hint} />;
  return (
    <View style={styles.numberRow}>
      <View style={styles.flex}>
        <Text variant="body">{label}</Text>
        {hint ? (
          <Text variant="footnote" tone="mutedForeground">
            {hint}
          </Text>
        ) : null}
      </View>
      <Switch
        accessibilityLabel={label}
        value={value}
        disabled={busy}
        onValueChange={onChange}
        {...switchColors(colors)}
      />
    </View>
  );
}

/** The week's hours as runs of days that say the same: «Lunes a sábado», «Domingo». */
type Weekday = 1 | 2 | 3 | 4 | 5 | 6 | 7;

function hourRuns(config: ResConfig, t: T): { from: Weekday; days: string; text: string }[] {
  const cap = config.capacity;
  const textOf = (wd: Weekday): string => {
    const spans = config.hours.filter((h) => h.weekday === wd);
    if (spans.length === 0) return t("reservas.settings.closed");
    if (!cap) return spans.map((s) => `${hhmm(s.open)}–${hhmm(s.close)}`).join(", ");
    return (
      cap.shifts
        .filter((s) => !cap.closed.some((c) => c.weekday === wd && (c.shift === null || c.shift === s.name)))
        .map((s) => t("reservas.settings.shift", { name: s.name, from: hhmm(s.from), to: hhmm(s.to) }))
        .join(" · ") || t("reservas.settings.closed")
    );
  };
  const runs: { from: Weekday; to: Weekday; text: string }[] = [];
  for (const wd of [1, 2, 3, 4, 5, 6, 7] as const) {
    const text = textOf(wd);
    const last = runs[runs.length - 1];
    if (last && last.text === text) last.to = wd;
    else runs.push({ from: wd, to: wd, text });
  }
  return runs.map((r) => ({
    from: r.from,
    text: r.text,
    days:
      r.from === r.to
        ? t(`reservas.weekday.${r.from}`)
        : t("reservas.settings.days", { from: t(`reservas.weekday.${r.from}`), to: t(`reservas.weekday.${r.to}`).toLocaleLowerCase() }),
  }));
}

const styles = StyleSheet.create({
  stack: { gap: 20 },
  stackSmall: { gap: 12 },
  block: { gap: 8, paddingHorizontal: 16, paddingVertical: 12 },
  chips: { gap: 8, paddingVertical: 2 },
  numberRow: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: TOUCH, paddingLeft: 16, paddingRight: 8, paddingVertical: 6 },
  num: { minWidth: 32, textAlign: "center", fontVariant: ["tabular-nums"] },
  blockRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingLeft: 16, paddingRight: 8, paddingVertical: 10 },
  flex: { flex: 1, minWidth: 0 },
});
