"use client";

/**
 * Channel preview selector — dropdown (list, NOT a switch).
 *
 * Decision congelada en ADR-020 / Fase 0: lista, no switch. Lista
 * escala a Instagram, Messenger, voz sin tocar la UI; switch limitaría
 * a 2.
 *
 * Only ``web`` and ``whatsapp`` are wired today; the list is ordered
 * so adding instagram / messenger / voice is a one-line change.
 */
export type ChannelKind = "web" | "whatsapp";

const OPTIONS: { value: ChannelKind; label: string; hint?: string }[] = [
  { value: "web", label: "Web", hint: "Playground" },
  { value: "whatsapp", label: "WhatsApp", hint: "Cloud API preview" },
  // Future channels live here. Add a renderer in `thread-pane.tsx` first.
];

export function ChannelKindSelector({
  value,
  onChange,
}: {
  value: ChannelKind;
  onChange: (next: ChannelKind) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Preview as
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as ChannelKind)}
        className="rounded border border-border bg-background px-2 py-1 text-sm"
      >
        {OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
            {opt.hint ? ` — ${opt.hint}` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
