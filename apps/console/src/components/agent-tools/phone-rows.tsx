"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";

import { Button, Input, Label } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";

import { normalisePhone, parseAudienceLines } from "./audience-lines";

/**
 * A list of phones with an optional name each (spec 024, reused by spec 025).
 *
 * One row per number: a phone, a name, a way to remove it. Pasting several
 * numbers into a phone box makes one row per number; leaving a phone box
 * normalises it. A bad phone is pointed at on its own row, in words.
 */

export type PhoneRow = { id: string; phone: string; name: string; error: string | null };

let seq = 0;
export function newRow(phone = "", name = ""): PhoneRow {
  seq += 1;
  return { id: `row-${seq}`, phone, name, error: null };
}

export type PhoneRowsLabels = {
  list: MessageKey;
  count: MessageKey;
  phone: MessageKey;
  name: MessageKey;
  remove: MessageKey;
  add: MessageKey;
  hint: MessageKey;
  phoneEg: MessageKey;
  nameEg: MessageKey;
};

export function PhoneRows({
  rows,
  disabled,
  onRows,
  labels,
  slot = "audience-list",
}: {
  rows: PhoneRow[];
  disabled: boolean;
  onRows: (rows: PhoneRow[]) => void;
  labels: PhoneRowsLabels;
  slot?: string;
}) {
  const t = useT();

  function update(id: string, patch: Partial<PhoneRow>) {
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

  const filled = rows.filter((r) => r.phone.trim()).length;

  return (
    <div className="grid gap-3" data-slot={slot}>
      <div className="flex items-baseline justify-between gap-2">
        <Label>{t(labels.list)}</Label>
        <span className="text-xs text-muted-foreground" aria-live="polite">
          {t(labels.count, { n: filled })}
        </span>
      </div>
      <ul className="grid gap-2" aria-label={t(labels.list)}>
        {rows.map((row, index) => (
          <li key={row.id} className="grid gap-1">
            <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-center gap-2">
              <Input
                type="tel"
                inputMode="tel"
                autoComplete="off"
                aria-label={t(labels.phone, { n: index + 1 })}
                aria-invalid={row.error ? true : undefined}
                placeholder={t(labels.phoneEg)}
                value={row.phone}
                disabled={disabled}
                onChange={(e) => update(row.id, { phone: e.target.value })}
                onBlur={(e) => blur(row.id, e.target.value)}
                onPaste={(e) => paste(row.id, e)}
                className="font-mono"
              />
              <Input
                aria-label={t(labels.name, { n: index + 1 })}
                placeholder={t(labels.nameEg)}
                maxLength={120}
                value={row.name}
                disabled={disabled}
                onChange={(e) => update(row.id, { name: e.target.value })}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t(labels.remove, { n: index + 1 })}
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
          {t(labels.add)}
        </Button>
        <p className="text-xs text-muted-foreground">{t(labels.hint)}</p>
      </div>
    </div>
  );
}
