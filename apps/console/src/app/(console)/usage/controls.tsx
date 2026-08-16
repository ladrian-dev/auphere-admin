"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";

type Props = {
  days: number;
  client: string;
  source: string;
  meter: string;
  clients: { ref: string; name: string }[];
  /** Server-side CSV (route handler → API streaming). */
  csvHref: string;
};

const METER_OPTIONS = ["channel.message", "llm", "media", "voice"] as const;

export function UsageControls({ days, client, source, meter, clients, csvHref }: Props) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  function set(patch: Record<string, string | undefined>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    router.push(`${pathname}?${next.toString()}`);
  }
  const selectClass = "h-8 rounded-md border border-input bg-transparent px-3 text-sm focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div role="group" aria-label={t("usage.period", { days })} className="flex gap-1">
        {[7, 30, 90].map((d) => (
          <Button key={d} size="sm" variant={days === d ? "secondary" : "ghost"} aria-pressed={days === d} onClick={() => set({ days: String(d) })}>
            {d}d
          </Button>
        ))}
      </div>
      {clients.length ? (
        <select className={selectClass} value={client} onChange={(e) => set({ client: e.target.value || undefined })} aria-label={t("usage.client")}>
          <option value="">{t("usage.all")}</option>
          {clients.map((c) => (
            <option key={c.ref} value={c.ref}>
              {c.name}
            </option>
          ))}
        </select>
      ) : null}
      <select className={selectClass} value={source} onChange={(e) => set({ source: e.target.value || undefined })} aria-label={t("usage.source")}>
        <option value="">{t("usage.source")}: —</option>
        <option value="channel">{t("usage.source.channel")}</option>
        <option value="qa">{t("usage.source.qa")}</option>
      </select>
      <select className={selectClass} value={meter} onChange={(e) => set({ meter: e.target.value || undefined })} aria-label={t("hu.usage.meter.filter")}>
        <option value="">{t("hu.usage.meter.all")}</option>
        {METER_OPTIONS.map((m) => (
          <option key={m} value={m}>
            {t(`hu.usage.meter.${m}` as "hu.usage.meter.llm")}
          </option>
        ))}
      </select>
      <Button nativeButton={false} variant="outline" size="sm" className="ml-auto" render={<a href={csvHref} download />}>
        {t("hu.usage.export.server")}
      </Button>
    </div>
  );
}
