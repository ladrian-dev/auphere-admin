"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";

type Props = { days: number; client: string; source: string; clients: { ref: string; name: string }[]; csv: string };

export function UsageControls({ days, client, source, clients, csv }: Props) {
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
  function download() {
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `usage-${days}d.csv`;
    a.click();
    URL.revokeObjectURL(url);
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
      <Button variant="outline" size="sm" className="ml-auto" onClick={download}>
        {t("usage.export")}
      </Button>
    </div>
  );
}
