"use client";

import { Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Checkbox, EmptyState, Label, StatusBadge } from "@nexus/ui";

import { saveSkillsAction } from "@/app/(console)/clients/[ref]/skills/actions";
import { useT } from "@/i18n/client";
import type { SkillsOut } from "@/lib/backend/agent-tools-types";

type Props = { refId: string; data: SkillsOut; canWrite: boolean };

/**
 * Vertical skills as cards with a toggle (CP-14). Non-activatable skills
 * render disabled with a hint; a marker shows what the ACTIVE version has.
 * Save writes the draft; the toast links to publish.
 */
export function SkillsGrid({ refId, data, canWrite }: Props) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const initial = React.useMemo(() => new Set(data.skills.filter((s) => s.enabled).map((s) => s.name)), [data]);
  const [selected, setSelected] = React.useState<Set<string>>(initial);
  // Re-sync when the server data changes (after refresh) — derived-state pattern, no effect.
  const [seen, setSeen] = React.useState(initial);
  if (seen !== initial) {
    setSeen(initial);
    setSelected(initial);
  }
  const dirty = selected.size !== initial.size || Array.from(selected).some((n) => !initial.has(n));
  const base = `/clients/${encodeURIComponent(refId)}`;

  function toggle(name: string, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(name);
      else next.delete(name);
      return next;
    });
  }

  function save() {
    startTransition(async () => {
      const res = await saveSkillsAction({ ref: refId, skills: Array.from(selected) });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("skills.saved", { v: res.data.version ?? 0 }), {
        action: { label: t("agentSettings.draft.publishLink"), onClick: () => router.push(`${base}/agent`) },
      });
      router.refresh();
    });
  }

  if (data.skills.length === 0) {
    return <EmptyState icon={Sparkles} title={t("skills.empty.title")} description={t("skills.empty.body")} readonly />;
  }

  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
      {!canWrite ? <p className="text-xs text-muted-foreground">{t("skills.readonly")}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
          {t("skills.selected", { n: selected.size, total: data.skills.length })}
        </span>
        {canWrite ? (
          <Button size="sm" className="ml-auto" onClick={save} disabled={pending || !dirty}>
            {t("skills.save")}
          </Button>
        ) : null}
      </div>
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" aria-label={t("skills.title")}>
        {data.skills.map((skill) => {
          const id = `skill-${skill.name}`;
          const on = selected.has(skill.name);
          const disabled = !canWrite || !skill.activatable;
          return (
            <li key={skill.name} className="flex min-w-0 flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10" aria-disabled={!skill.activatable || undefined}>
              <div className="flex items-start gap-3">
                <Checkbox id={id} checked={on} disabled={disabled} onCheckedChange={(c) => toggle(skill.name, c)} className="mt-1" aria-label={t("skills.enable", { name: skill.name })} />
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <Label htmlFor={id} className="min-w-0 truncate text-sm font-medium" title={skill.name}>
                    {skill.name}
                  </Label>
                  <span className="font-mono text-xs text-muted-foreground">{t("skills.version", { v: skill.version })}</span>
                </div>
                {skill.enabled_in_active ? <StatusBadge tone="positive" dot={false}>{t("skills.inActive")}</StatusBadge> : null}
              </div>
              <p className="line-clamp-3 text-xs text-pretty text-muted-foreground" title={skill.description}>
                {skill.description}
              </p>
              {!skill.activatable ? <p className="text-xs text-status-warning">{t("skills.notActivatable")}</p> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
