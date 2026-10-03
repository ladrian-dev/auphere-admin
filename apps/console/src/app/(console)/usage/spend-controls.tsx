"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { NativeSelect, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";

const PERIODS = [7, 30, 90] as const;

/** Period and client for the spend chart: links, so the URL says what you see. */
export function SpendControls({ days, client, clients }: { days: number; client: string; clients: Array<{ ref: string; name: string }> }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const go = (next: Record<string, string>) => {
    const sp = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(next)) {
      if (v) sp.set(k, v);
      else sp.delete(k);
    }
    router.push(`${pathname}?${sp.toString()}#gasto`, { scroll: false });
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div role="group" aria-label={t("hu.usage.spend.period")} className="inline-flex rounded-md bg-muted p-1">
        {PERIODS.map((d) => (
          <button
            key={d}
            type="button"
            aria-pressed={days === d}
            onClick={() => go({ days: String(d) })}
            className={cn("rounded-sm px-3 py-1 text-xs font-medium", days === d ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
          >
            {t("hu.usage.spend.days", { n: d })}
          </button>
        ))}
      </div>
      <NativeSelect wrapperClassName="max-w-56" aria-label={t("usage.client")} value={client} onChange={(e) => go({ client: e.target.value })}>
        <option value="">{t("hu.usage.spend.allClients")}</option>
        {clients.map((c) => (
          <option key={c.ref} value={c.ref}>
            {c.name}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
