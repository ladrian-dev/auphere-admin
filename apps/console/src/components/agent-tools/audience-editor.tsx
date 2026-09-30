"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";

import { Button, Input, Label, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { AudienceMode } from "@/lib/backend/agent-tools-types";

import { normalisePhone, parseAudienceLines } from "./audience-lines";

/**
 * Spec 024 · «A quién responde».
 *
 * Two option cards, each saying what it means, and under the second one a
 * list of rows: a phone, an optional name, and a way to remove the row.
 * Nothing to learn: no separators, no format to remember. A bad phone is
 * pointed at on its own row, in words, when the partner tries to save.
 * Pasting several numbers into a phone box makes one row per number.
 */

export type AudienceRow = { id: string; phone: string; name: string; error: string | null };

let seq = 0;
export function newRow(phone = "", name = ""): AudienceRow {
  seq += 1;
  return { id: `row-${seq}`, phone, name, error: null };
}

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

  function update(id: string, patch: Partial<AudienceRow>) {
    onRows(rows.map((r) => (r.id === id ? { ...r, ...patch, error: null } : r)));
  }
  function remove(id: string) {
    const next = rows.filter((r) => r.id !== id);
    onRows(next.length ? next : [newRow()]);
  }
  function add() {
    onRows([...rows, newRow()]);
  }
  /** A pasted list ("+34…, +56…" or one per line) becomes one row each. */
  function paste(id: string, e: React.ClipboardEvent<HTMLInputElement>) {
    const text = e.clipboardData.getData("text");
    const parsed = parseAudienceLines(text);
    if (parsed.numbers.length + parsed.errors.length <= 1) return; // a single number: let the input take it
    e.preventDefault();
    const fresh = parsed.numbers.map((n) => newRow(n.phone, n.name ?? ""));
    const others = rows.filter((r) => r.id !== id && (r.phone.trim() || r.name.trim()));
    onRows([...others, ...fresh]);
  }
  function blur(id: string, phone: string) {
    const e164 = normalisePhone(phone);
    if (e164 && e164 !== phone) update(id, { phone: e164 });
  }

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
  const filled = rows.filter((r) => r.phone.trim()).length;

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
        <div className="grid gap-3" data-slot="audience-list">
          <div className="flex items-baseline justify-between gap-2">
            <Label>{t("agentSettings.audience.numbers")}</Label>
            <span className="text-xs text-muted-foreground" aria-live="polite">
              {t("agentSettings.audience.count", { n: filled })}
            </span>
          </div>
          <ul className="grid gap-2" aria-label={t("agentSettings.audience.numbers")}>
            {rows.map((row, index) => (
              <li key={row.id} className="grid gap-1">
                <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-2">
                  <Input
                    type="tel"
                    inputMode="tel"
                    autoComplete="off"
                    aria-label={t("agentSettings.audience.phone", { n: index + 1 })}
                    aria-invalid={row.error ? true : undefined}
                    placeholder={t("agentSettings.audience.numbers.eg")}
                    value={row.phone}
                    disabled={disabled}
                    onChange={(e) => update(row.id, { phone: e.target.value })}
                    onBlur={(e) => blur(row.id, e.target.value)}
                    onPaste={(e) => paste(row.id, e)}
                    className="font-mono"
                  />
                  <Input
                    aria-label={t("agentSettings.audience.name", { n: index + 1 })}
                    placeholder={t("agentSettings.audience.name.eg")}
                    maxLength={120}
                    value={row.name}
                    disabled={disabled}
                    onChange={(e) => update(row.id, { name: e.target.value })}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("agentSettings.audience.remove", { n: index + 1 })}
                    disabled={disabled}
                    onClick={() => remove(row.id)}
                  >
                    <X aria-hidden="true" />
                  </Button>
                </div>
                {row.error ? (
                  <p role="alert" className="text-sm text-destructive">
                    {row.error}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={add}>
              <Plus aria-hidden="true" />
              {t("agentSettings.audience.add")}
            </Button>
            <p className="text-xs text-muted-foreground">{t("agentSettings.audience.numbers.hint")}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
