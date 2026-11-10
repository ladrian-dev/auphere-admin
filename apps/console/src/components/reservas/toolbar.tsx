"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import type * as React from "react";

import { Button, NativeSelect } from "@nexus/ui";

import type { MessageKey } from "@/i18n/messages";
import type { StaffMember } from "@/lib/backend/reservas";

import { useReservas } from "./context";
import { periodLabel, periodRange, shiftPeriod, type Period } from "./model/dates";
import type { View } from "./model/url-state";
import { Segmented } from "./shared";

/**
 * «Hoy», ‹ ›, the date label, and the two separate controls of Requisito 8.2:
 * the period (Día · Semana · Mes) and the view (Cuadrícula · Lista). With more
 * than one professional, the team filter. Every change is a URL.
 */
export function Toolbar({ staff, extra }: { staff?: StaffMember[] | null; extra?: React.ReactNode }) {
  const { t, locale, url, today, go } = useReservas();
  const period = url.period;
  const range = periodRange(period, url.date);
  const showsToday = today >= range.from && today <= range.to;
  const showStaffFilter = !!staff && staff.length > 1 && !(url.view === "grid" && period === "week");

  return (
    <div role="toolbar" aria-label={t("reservas.toolbar.label")} className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex min-w-0 items-center gap-2">
        <Button variant="outline" size="sm" disabled={showsToday} onClick={() => go({ date: today })}>
          {t(`reservas.toolbar.today.${period}` as MessageKey)}
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t(`reservas.toolbar.prev.${period}` as MessageKey)}
          onClick={() => go({ date: shiftPeriod(period, url.date, -1) })}
        >
          <ChevronLeft aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t(`reservas.toolbar.next.${period}` as MessageKey)}
          onClick={() => go({ date: shiftPeriod(period, url.date, 1) })}
        >
          <ChevronRight aria-hidden="true" />
        </Button>
        <h2 className="min-w-0 truncate text-base font-medium" aria-live="polite">
          {periodLabel(period, url.date, locale)}
        </h2>
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-2 md:ml-auto">
        {showStaffFilter ? (
          <NativeSelect
            size="sm"
            aria-label={t("reservas.staff.filter")}
            value={url.staff ?? ""}
            onChange={(e) => go({ staff: e.target.value || null })}
            wrapperClassName="max-w-48"
          >
            <option value="">{t("reservas.staff.all")}</option>
            {staff!.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </NativeSelect>
        ) : null}
        {extra}
        <Segmented<Period>
          label={t("reservas.period.label")}
          value={period}
          onChange={(p) => go({ period: p })}
          options={[
            { value: "day", label: t("reservas.period.day") },
            { value: "week", label: t("reservas.period.week") },
            { value: "month", label: t("reservas.period.month") },
          ]}
        />
        <Segmented<View>
          label={t("reservas.view.label")}
          value={url.view}
          onChange={(v) => go({ view: v })}
          options={[
            { value: "grid", label: t("reservas.view.grid") },
            { value: "list", label: t("reservas.view.list") },
          ]}
        />
      </div>
    </div>
  );
}
