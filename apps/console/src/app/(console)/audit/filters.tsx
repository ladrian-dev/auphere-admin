"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { Button, Input, NativeSelect, SegmentedControl } from "@nexus/ui";

import { PERIODS, type AuditFilterState } from "@/components/audit/audit-query";
import { useLocale, useT } from "@/i18n/client";
import type { AuditFilters as Options } from "@/lib/backend/home-usage";


/**
 * Spec 029: every filter applies the moment it changes. There was an «OK»
 * button, and a filter you set and forgot to confirm showed the old list
 * under the new choice. Each choice is a link in the URL, so a filtered view
 * can be shared and survives a reload.
 */
export function AuditFilters({ state, options }: { state: AuditFilterState; options: Options }) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const custom = state.days === "custom";
  const active = Boolean(state.client || state.actor || state.category || state.days || state.after || state.before);

  const go = React.useCallback(
    (patch: Partial<Record<keyof AuditFilterState | "person", string>>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      const qs = next.toString();
      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  const period = (days: string) => go({ days, after: "", before: "" });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select label={t("hu.audit.client")} all={t("hu.audit.client.all")} value={state.client} options={options.clients} onChange={(client) => go({ client })} />
        <Select label={t("hu.audit.person")} all={t("hu.audit.person.all")} value={state.actor} options={options.people} onChange={(person) => go({ person, actor: "" })} />
        <Select label={t("hu.audit.category")} all={t("hu.audit.category.all")} value={state.category} options={options.categories} onChange={(category) => go({ category })} />
        {/* El conmutador de vidrio del prototipo. `pressed`: cada opción navega,
            así que las flechas solo mueven el foco y elegir es Enter o Espacio. */}
        <SegmentedControl
          type="pressed"
          aria-label={t("hu.audit.period")}
          value={state.days || "all"}
          onValueChange={(v) => period(v === "all" ? "" : v)}
          options={[
            { value: "all", label: t("hu.audit.period.all") },
            ...PERIODS.map((d) => ({ value: String(d), label: t("hu.audit.period.days", { n: d }) })),
            { value: "custom", label: t("hu.audit.period.custom") },
          ]}
        />
        {active ? (
          <Button type="button" variant="link" size="sm" className="px-1" onClick={() => router.push(pathname, { scroll: false })}>
            {t("hu.audit.clear")}
          </Button>
        ) : null}
      </div>
      {custom ? (
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            {t("hu.audit.after")}
            <Input
              type="date"
              lang={locale === "es" ? "es-ES" : "en-GB"}
              value={state.after}
              max={state.before || undefined}
              onChange={(e) => go({ after: e.target.value })}
              className="w-40"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            {t("hu.audit.before")}
            <Input
              type="date"
              lang={locale === "es" ? "es-ES" : "en-GB"}
              value={state.before}
              min={state.after || undefined}
              onChange={(e) => go({ before: e.target.value })}
              className="w-40"
            />
          </label>
        </div>
      ) : null}
    </div>
  );
}

function Select({
  label,
  all,
  value,
  options,
  onChange,
}: {
  label: string;
  all: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <NativeSelect wrapperClassName="w-full sm:w-auto sm:max-w-56" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{all}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </NativeSelect>
  );
}
