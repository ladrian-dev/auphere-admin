"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";

import { Button, Callout, Field, Input, NativeSelect, Section } from "@nexus/ui";

import { removeBlockAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { CapacitySchedule, CapacitySettings, ConfirmationWhen } from "@/lib/backend/reservas";

import { useReservas, useWords } from "../context";
import { formatMinutes } from "../model/dates";
import { scheduleValid, timeOptions } from "../model/hours";
import { seatsStep } from "../model/occupancy";
import { kindOf, stayOptions, stayTitleKey } from "../model/vocab";
import { Segmented, Stepper, useWrite } from "../shared";
import { BusinessHoursSection, SwitchRow, WaitlistSettings, useSettingsPatch } from "./shared-sections";

const STEPS = [15, 30, 60, 90, 120] as const;
const WHEN: readonly ConfirmationWhen[] = ["24h", "same_day_12", "3h"];
const TIMES = timeOptions(15, 0, 23 * 60 + 45);

/**
 * Ajustes of Aforo (spec 043, T025): the mode note (Auphere sets it), the
 * capacity numbers, the booking hours (shifts or slots), the business hours,
 * WhatsApp confirmation and «liberar», the waitlist, and the blocks.
 */
export function CapacitySettings() {
  const { t, settings } = useReservas();
  const words = useWords();
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <Callout tone="info">{t("reservas.cset.mode", { unit: words.unit })}</Callout>
      <div className="grid min-w-0 gap-6 xl:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-6">
          {/* A new version (saved here or elsewhere) starts the drafts from what is true now. */}
          <CapacityNumbers key={`n${settings.version}`} />
          <ScheduleSection key={`s${settings.version}`} />
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          <ConfirmationSection />
          <WaitlistSettings />
          <BusinessHoursSection />
          <BlocksSection />
        </div>
      </div>
    </div>
  );
}

function CapacityNumbers() {
  const { t, settings } = useReservas();
  const cap = settings.capacity!;
  const kind = kindOf(settings);
  const { patch, busy } = useSettingsPatch();
  const [draft, setDraft] = React.useState<Pick<CapacitySettings, "seats" | "stay_minutes" | "max_party" | "walkin_hold">>({
    seats: cap.seats,
    stay_minutes: cap.stay_minutes,
    max_party: cap.max_party,
    walkin_hold: cap.walkin_hold,
  });
  const dirty =
    draft.seats !== cap.seats || draft.stay_minutes !== cap.stay_minutes || draft.max_party !== cap.max_party || draft.walkin_hold !== cap.walkin_hold;
  const maxHold = Math.floor(draft.seats / 2);
  const set = (patchDraft: Partial<typeof draft>) =>
    setDraft((d) => {
      const next = { ...d, ...patchDraft };
      return { ...next, max_party: Math.min(next.max_party, next.seats), walkin_hold: Math.min(next.walkin_hold, Math.floor(next.seats / 2)) };
    });

  return (
    <Section
      title={t("reservas.cset.capacity.title")}
      actions={
        <Button size="sm" disabled={!dirty} loading={busy} onClick={() => void patch({ capacity: draft })}>
          {t("reservas.settings.save")}
        </Button>
      }
    >
      <NumberRow label={t("reservas.cset.seats")} hint={t("reservas.cset.seats.hint")}>
        <Stepper label={t("reservas.cset.seats")} value={draft.seats} min={1} step={seatsStep(draft.seats)} onChange={(v) => set({ seats: v })} />
      </NumberRow>
      <Field label={t(stayTitleKey(kind))} hint={t("reservas.cset.stay.hint")}>
        {(a11y) => (
          <NativeSelect {...a11y} value={draft.stay_minutes} onChange={(e) => set({ stay_minutes: Number(e.target.value) })} wrapperClassName="w-48">
            {stayOptions(kind, draft.stay_minutes).map((m) => (
              <option key={m} value={m}>
                {formatMinutes(m)}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <NumberRow label={t("reservas.cset.maxParty")} hint={t("reservas.cset.maxParty.hint")}>
        <Stepper label={t("reservas.cset.maxParty")} value={draft.max_party} min={1} max={draft.seats} onChange={(v) => set({ max_party: v })} />
      </NumberRow>
      <NumberRow label={t("reservas.cset.hold")} hint={t("reservas.cset.hold.hint")}>
        <Stepper
          label={t("reservas.cset.hold")}
          value={draft.walkin_hold}
          min={0}
          max={maxHold}
          onChange={(v) => set({ walkin_hold: v })}
          display={draft.walkin_hold === 0 ? t("reservas.cset.hold.none") : undefined}
        />
      </NumberRow>
    </Section>
  );
}

function NumberRow({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div className="flex min-w-0 flex-1 basis-48 flex-col gap-1">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-xs text-pretty text-muted-foreground">{hint}</span>
      </div>
      {children}
    </div>
  );
}

function ScheduleSection() {
  const { t, settings } = useReservas();
  const { patch, busy } = useSettingsPatch();
  const saved = settings.capacity!.schedule;
  const [draft, setDraft] = React.useState<CapacitySchedule>(saved);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const valid = scheduleValid(draft);

  const toModel = (model: CapacitySchedule["model"]) => {
    if (model === draft.model) return;
    setDraft(
      model === "slots"
        ? { model: "slots", step_minutes: 60, from: "12:00", to: "22:00" }
        : { model: "shifts", step_minutes: 30, shifts: [{ name: t("reservas.cset.shift.default", { n: 1 }), from: "13:00", to: "15:00" }] },
    );
  };

  return (
    <Section
      title={t("reservas.cset.schedule.title")}
      description={t("reservas.cset.schedule.days")}
      actions={
        <Button size="sm" disabled={!dirty || !valid} loading={busy} onClick={() => void patch({ capacity: { schedule: draft } })}>
          {t("reservas.settings.save")}
        </Button>
      }
    >
      <div className="flex flex-col gap-2">
        <Segmented<CapacitySchedule["model"]>
          label={t("reservas.cset.schedule.model")}
          value={draft.model}
          onChange={toModel}
          options={[
            { value: "shifts", label: t("reservas.cset.schedule.shifts") },
            { value: "slots", label: t("reservas.cset.schedule.slots") },
          ]}
        />
        <p className="text-xs text-pretty text-muted-foreground">
          {t(draft.model === "shifts" ? "reservas.cset.schedule.shifts.hint" : "reservas.cset.schedule.slots.hint")}
        </p>
      </div>

      {draft.model === "shifts" ? (
        <ul className="flex flex-col gap-3">
          {draft.shifts.map((s, i) => {
            const update = (p: Partial<typeof s>) =>
              setDraft({ ...draft, shifts: draft.shifts.map((x, j) => (j === i ? { ...x, ...p } : x)) });
            return (
              <li key={i} className="flex min-w-0 flex-wrap items-end gap-2">
                <Field label={t("reservas.cset.shift.name")} className="min-w-32 flex-1">
                  {(a11y) => <Input {...a11y} value={s.name} onChange={(e) => update({ name: e.target.value })} maxLength={40} />}
                </Field>
                <TimeField label={t("reservas.cset.shift.from")} value={s.from} onChange={(v) => update({ from: v })} />
                <TimeField label={t("reservas.cset.shift.to")} value={s.to} onChange={(v) => update({ to: v })} />
                {draft.shifts.length > 1 ? (
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={t("reservas.cset.shift.remove", { name: s.name })}
                    onClick={() => setDraft({ ...draft, shifts: draft.shifts.filter((_, j) => j !== i) })}
                  >
                    <X aria-hidden="true" />
                  </Button>
                ) : null}
              </li>
            );
          })}
          {draft.shifts.length < 6 ? (
            <li>
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  setDraft({
                    ...draft,
                    shifts: [...draft.shifts, { name: t("reservas.cset.shift.default", { n: draft.shifts.length + 1 }), from: "20:00", to: "22:00" }],
                  })
                }
              >
                <Plus aria-hidden="true" />
                {t("reservas.cset.shift.add")}
              </Button>
            </li>
          ) : null}
        </ul>
      ) : (
        <div className="flex flex-wrap gap-2">
          <TimeField label={t("reservas.cset.shift.from")} value={draft.from} onChange={(v) => setDraft({ ...draft, from: v })} />
          <TimeField label={t("reservas.cset.shift.to")} value={draft.to} onChange={(v) => setDraft({ ...draft, to: v })} />
        </div>
      )}

      <Field label={t("reservas.cset.step")}>
        {(a11y) => (
          <NativeSelect {...a11y} value={draft.step_minutes} onChange={(e) => setDraft({ ...draft, step_minutes: Number(e.target.value) })} wrapperClassName="w-40">
            {STEPS.map((m) => (
              <option key={m} value={m}>
                {formatMinutes(m)}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      {!valid ? (
        <p role="alert" className="text-xs text-destructive text-pretty">
          {t("reservas.cset.schedule.invalid")}
        </p>
      ) : null}
    </Section>
  );
}

function TimeField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const options = TIMES.includes(value) ? TIMES : [...TIMES, value].sort();
  return (
    <Field label={label} className="w-32">
      {(a11y) => (
        <NativeSelect {...a11y} value={value} onChange={(e) => onChange(e.target.value)} wrapperClassName="w-full">
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </NativeSelect>
      )}
    </Field>
  );
}

function ConfirmationSection() {
  const { t, settings } = useReservas();
  const { patch, busy } = useSettingsPatch();
  return (
    <Section title={t("reservas.cset.confirm.title")}>
      <SwitchRow
        id="reservas-confirm"
        label={t("reservas.cset.confirm.switch")}
        checked={settings.confirmation.enabled}
        disabled={busy}
        onChange={(on) => void patch({ confirmation: { enabled: on } })}
      />
      {settings.confirmation.enabled ? (
        <Field label={t("reservas.cset.confirm.when")}>
          {(a11y) => (
            <NativeSelect
              {...a11y}
              value={settings.confirmation.when}
              disabled={busy}
              onChange={(e) => void patch({ confirmation: { when: e.target.value as ConfirmationWhen } })}
              wrapperClassName="w-60"
            >
              {WHEN.map((w) => (
                <option key={w} value={w}>
                  {t(`reservas.cset.when.${w}` as MessageKey)}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
      ) : null}
      <SwitchRow
        id="reservas-release"
        label={t("reservas.cset.release")}
        hint={t("reservas.cset.release.hint")}
        checked={settings.release_unconfirmed}
        disabled={busy}
        onChange={(on) => void patch({ release_unconfirmed: on })}
      />
    </Section>
  );
}

function BlocksSection() {
  const { t, data, open, today } = useReservas();
  const words = useWords();
  const write = useWrite();
  const items = (data.blocks ?? []).filter((b) => b.date >= today);
  return (
    <Section
      title={t("reservas.blocks.settings.title")}
      description={t("reservas.blocks.settings.body")}
      actions={
        <Button size="sm" variant="outline" onClick={() => open({ kind: "block", prefill: {} })}>
          {t("reservas.blocks.add")}
        </Button>
      }
    >
      {data.blocks === null ? (
        <p className="text-sm text-muted-foreground">{t("reservas.settings.partError")}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("reservas.blocks.emptyUpcoming")}</p>
      ) : (
        <ul className="flex min-w-0 flex-col divide-y divide-border">
          {items.map((b) => (
            <li key={b.id} className="flex min-w-0 flex-wrap items-center gap-3 py-2">
              <span className="flex min-w-0 flex-1 basis-40 flex-col">
                <span className="truncate text-sm" title={b.label}>
                  {words.dayTitle(b.date)} · {t("reservas.blocks.item", { from: b.from, until: b.until, label: b.label })}
                </span>
                {b.created_by_name ? <span className="truncate text-xs text-muted-foreground">{t("reservas.blocks.by", { name: b.created_by_name })}</span> : null}
              </span>
              <Button
                size="xs"
                variant="ghost"
                aria-label={t("reservas.blocks.remove.aria", { label: b.label })}
                onClick={() => void write(() => removeBlockAction({ id: b.id }), { success: t("reservas.blocks.removed") })}
              >
                {t("reservas.blocks.remove")}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
