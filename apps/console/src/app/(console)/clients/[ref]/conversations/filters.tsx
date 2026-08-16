"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";

export function ConversationFilters({ escalated, withErrors }: { escalated: boolean; withErrors: boolean }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  function toggle(key: "escalated" | "with_errors", on: boolean) {
    const next = new URLSearchParams(params.toString());
    if (on) next.delete(key);
    else next.set(key, "true");
    next.delete("page");
    router.push(`${pathname}?${next.toString()}`);
  }
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={t("conv.title")}>
      <Button size="sm" variant={escalated ? "secondary" : "outline"} aria-pressed={escalated} onClick={() => toggle("escalated", escalated)}>
        {t("conv.filter.escalated")}
      </Button>
      <Button size="sm" variant={withErrors ? "secondary" : "outline"} aria-pressed={withErrors} onClick={() => toggle("with_errors", withErrors)}>
        {t("conv.filter.errors")}
      </Button>
    </div>
  );
}
