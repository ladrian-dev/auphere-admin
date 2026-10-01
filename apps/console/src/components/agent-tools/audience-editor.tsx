"use client";

import { cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { AudienceMode } from "@/lib/backend/agent-tools-types";

import { PhoneRows, newRow, type PhoneRow, type PhoneRowsLabels } from "./phone-rows";

/**
 * Spec 024 · «A quién responde».
 *
 * Two option cards, each saying what it means, and under the second one a
 * list of rows: a phone, an optional name, and a way to remove the row.
 * Nothing to learn: no separators, no format to remember. A bad phone is
 * pointed at on its own row, in words, when the partner tries to save.
 * Pasting several numbers into a phone box makes one row per number.
 */

export type AudienceRow = PhoneRow;
export { newRow };

const AUDIENCE_LABELS: PhoneRowsLabels = {
  list: "agentSettings.audience.numbers",
  count: "agentSettings.audience.count",
  phone: "agentSettings.audience.phone",
  name: "agentSettings.audience.name",
  remove: "agentSettings.audience.remove",
  add: "agentSettings.audience.add",
  hint: "agentSettings.audience.numbers.hint",
  phoneEg: "agentSettings.audience.numbers.eg",
  nameEg: "agentSettings.audience.name.eg",
};

export function AudienceEditor({
  mode,
  rows,
  locked,
  disabled,
  onMode,
  onRows,
}: {
  mode: AudienceMode;
  rows: AudienceRow[];
  locked: boolean;
  disabled: boolean;
  onMode: (mode: AudienceMode) => void;
  onRows: (rows: AudienceRow[]) => void;
}) {
  const t = useT();

  const options: Array<{ value: AudienceMode; title: string; help: string; blocked: boolean }> = [
    {
      value: "everyone",
      title: t("agentSettings.audience.everyone"),
      help: t("agentSettings.audience.everyone.help"),
      blocked: disabled || locked,
    },
    {
      value: "list",
      title: t("agentSettings.audience.list"),
      help: t("agentSettings.audience.list.help"),
      blocked: disabled,
    },
  ];

  return (
    <div className="grid gap-4">
      <div role="radiogroup" aria-label={t("agentSettings.section.audience")} className="grid gap-2 sm:grid-cols-2">
        {options.map((o) => {
          const selected = mode === o.value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={o.blocked}
              onClick={() => onMode(o.value)}
              className={cn(
                "flex flex-col items-start gap-1 rounded-md border p-3 text-left text-sm transition-colors",
                selected ? "border-foreground" : "border-border hover:border-foreground/40",
                o.blocked && "cursor-not-allowed opacity-70",
              )}
            >
              <span className="font-medium">{o.title}</span>
              <span className="text-xs text-muted-foreground">{o.help}</span>
            </button>
          );
        })}
      </div>

      {locked ? (
        <p className="text-sm text-muted-foreground" data-slot="audience-locked">
          {t("agentSettings.audience.locked")}
        </p>
      ) : null}

      {mode === "list" ? (
        <PhoneRows rows={rows} disabled={disabled} onRows={onRows} labels={AUDIENCE_LABELS} />
      ) : null}
    </div>
  );
}
