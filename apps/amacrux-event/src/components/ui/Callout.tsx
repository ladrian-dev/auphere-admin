import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

import { AlertIcon, SparkIcon } from "./icons";

type Tone = "info" | "warning" | "success";

const tones: Record<Tone, string> = {
  info: "border-electric/30 bg-electric/8 text-ink",
  warning: "border-warning/40 bg-warning/10 text-ink",
  success: "border-success/40 bg-success/10 text-ink",
};

export function Callout({ tone = "info", title, children, className }: { tone?: Tone; title?: string; children: ReactNode; className?: string }) {
  const Icon = tone === "warning" ? AlertIcon : SparkIcon;
  return (
    <div role={tone === "warning" ? "alert" : undefined} className={cx("flex gap-3 rounded-md border p-4 text-sm leading-relaxed", tones[tone], className)}>
      <Icon className="mt-0.5 shrink-0 text-ink-muted" />
      <div className="min-w-0">
        {title ? <p className="mb-0.5 font-semibold">{title}</p> : null}
        <div>{children}</div>
      </div>
    </div>
  );
}
