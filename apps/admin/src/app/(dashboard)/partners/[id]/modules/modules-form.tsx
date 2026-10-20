"use client";

import { Check } from "lucide-react";
import { useMemo, useState, useTransition } from "react";
import { toast } from "sonner";

import { Button, Switch, cn } from "@nexus/ui";

import type { PartnerAccessOut, PartnerModule } from "@/lib/backend";

import { setPartnerAccessAction } from "./actions";
import { MODULE_GROUPS, MODULE_INFO, canonical, hasView } from "./catalog";

type Filter = "all" | "on" | "off";

/**
 * Spec 032 — which views and services the partner's console has. One tile
 * per module, grouped like Chatwoot's account features; a filter and a count
 * per group. No tile is ever disabled: with the console off the choice is
 * kept and applies when it is switched on (§V).
 */
export function ModulesForm({ partnerId, access }: { partnerId: string; access: PartnerAccessOut }) {
  const [enabled, setEnabled] = useState(access.console_enabled);
  const [selected, setSelected] = useState<PartnerModule[]>(canonical(access.modules));
  const [saved, setSaved] = useState({ enabled: access.console_enabled, modules: canonical(access.modules) });
  const [filter, setFilter] = useState<Filter>("all");
  const [pending, start] = useTransition();

  const dirty = enabled !== saved.enabled || selected.join(",") !== saved.modules.join(",");
  const invalid = enabled && !hasView(selected);
  const counts = useMemo(
    () => ({ all: MODULE_GROUPS.flatMap((g) => g.modules).length, on: selected.length }),
    [selected],
  );

  function toggle(m: PartnerModule) {
    setSelected((cur) => canonical(cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m]));
  }

  function save() {
    if (invalid || !dirty) return;
    start(async () => {
      const r = await setPartnerAccessAction(partnerId, { console_enabled: enabled, modules: selected });
      if (!r.ok) {
        toast.error("No se pudieron guardar los módulos", { description: r.error });
        return;
      }
      setSaved({ enabled: r.data.console_enabled, modules: canonical(r.data.modules) });
      setSelected(canonical(r.data.modules));
      toast.success("Módulos guardados", { description: "El partner los verá en su próxima carga de la consola." });
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4 rounded-md bg-card p-4 ring-1 ring-foreground/10">
        <div className="flex flex-col gap-1">
          <label htmlFor="console-on" className="text-sm font-medium">
            Consola encendida
          </label>
          <p className="text-sm text-pretty text-muted-foreground">
            {enabled
              ? "Las personas del partner entran y ven las secciones marcadas abajo."
              : "Nadie del partner puede entrar. Lo que marques abajo se aplicará al encenderla."}
          </p>
        </div>
        <Switch id="console-on" checked={enabled} onCheckedChange={setEnabled} />
      </div>

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filtrar módulos">
        {(
          [
            ["all", `Todos · ${counts.all}`],
            ["on", `Activos · ${counts.on}`],
            ["off", `Inactivos · ${counts.all - counts.on}`],
          ] as const
        ).map(([key, label]) => (
          <Button
            key={key}
            type="button"
            size="sm"
            variant={filter === key ? "secondary" : "ghost"}
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
          >
            {label}
          </Button>
        ))}
      </div>

      {MODULE_GROUPS.map((group) => {
        const shown = group.modules.filter((m) =>
          filter === "all" ? true : filter === "on" ? selected.includes(m) : !selected.includes(m),
        );
        if (shown.length === 0) return null;
        const on = group.modules.filter((m) => selected.includes(m)).length;
        return (
          <fieldset key={group.id} className="flex flex-col gap-3">
            <legend className="mb-3 flex items-baseline gap-2 text-sm font-semibold">
              {group.label}
              <span className="text-xs font-normal text-muted-foreground tabular-nums">
                {on} de {group.modules.length} activos
              </span>
            </legend>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {shown.map((m) => {
                const info = MODULE_INFO[m];
                const Icon = info.icon;
                const checked = selected.includes(m);
                return (
                  <label
                    key={m}
                    className={cn(
                      "relative flex cursor-pointer items-start gap-3 rounded-md p-4 ring-1 transition-colors",
                      "focus-within:ring-2 focus-within:ring-ring",
                      checked ? "bg-primary/10 ring-primary/40" : "bg-card ring-foreground/10 hover:bg-muted/40",
                    )}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={checked}
                      onChange={() => toggle(m)}
                      aria-label={info.label}
                      aria-describedby={`mod-${m}-desc`}
                    />
                    <span
                      aria-hidden="true"
                      className="grid size-8 shrink-0 place-items-center rounded-md bg-primary/15 text-primary [&_svg]:size-4"
                    >
                      <Icon />
                    </span>
                    <span className="flex min-w-0 flex-col gap-1">
                      <span className="text-sm font-medium">{info.label}</span>
                      <span id={`mod-${m}-desc`} className="text-xs text-pretty text-muted-foreground">
                        {info.description}
                      </span>
                    </span>
                    <span
                      aria-hidden="true"
                      className={cn(
                        "ml-auto grid size-5 shrink-0 place-items-center rounded-full",
                        checked ? "bg-primary text-primary-foreground" : "ring-1 ring-foreground/20",
                      )}
                    >
                      {checked ? <Check className="size-3" /> : null}
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        );
      })}

      {invalid ? (
        <p role="alert" className="text-sm text-destructive">
          Con la consola encendida hace falta al menos una sección (el Companion solo no basta).
        </p>
      ) : null}

      <div>
        <Button type="button" onClick={save} disabled={!dirty || invalid || pending}>
          {pending ? "Guardando…" : "Guardar módulos"}
        </Button>
      </div>
    </div>
  );
}
