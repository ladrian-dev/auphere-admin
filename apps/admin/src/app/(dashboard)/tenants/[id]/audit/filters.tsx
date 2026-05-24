"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * Filter form for the audit timeline (Bloque B4).
 *
 * Filters live in the URL search params — submitting builds a new URL
 * and navigates, which re-runs the server component with fresh data.
 * That keeps filter state shareable (deep links) and avoids the
 * client-side fetch + render double-loop. ``startTransition`` so the
 * UI feels instant even on slow networks.
 */
export function AuditFilters({
  tenantId,
  actions,
  current,
}: {
  tenantId: string;
  actions: string[];
  current: {
    actor: string;
    action: string;
    target: string;
    after: string;
    before: string;
  };
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [actor, setActor] = useState(current.actor);
  const [action, setAction] = useState(current.action);
  const [target, setTarget] = useState(current.target);
  const [after, setAfter] = useState(current.after);
  const [before, setBefore] = useState(current.before);

  function apply() {
    const qs = new URLSearchParams();
    if (actor) qs.set("actor", actor);
    if (action) qs.set("action", action);
    if (target) qs.set("target", target);
    if (after) qs.set("after", new Date(after).toISOString());
    if (before) qs.set("before", new Date(before).toISOString());
    startTransition(() => {
      router.push(
        qs.toString()
          ? `/tenants/${tenantId}/audit?${qs.toString()}`
          : `/tenants/${tenantId}/audit`,
      );
    });
  }

  function clear() {
    setActor("");
    setAction("");
    setTarget("");
    setAfter("");
    setBefore("");
    startTransition(() => {
      router.push(`/tenants/${tenantId}/audit`);
    });
  }

  return (
    <div className="grid gap-3 rounded-md border border-border bg-muted/30 p-3">
      <div className="grid gap-3 md:grid-cols-5">
        <div className="grid gap-1">
          <Label htmlFor="audit-actor" className="text-xs">
            Actor
          </Label>
          <Input
            id="audit-actor"
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="luis, admin:..."
            className="font-mono text-xs"
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="audit-action" className="text-xs">
            Acción
          </Label>
          <Select
            value={action || "__all__"}
            onValueChange={(v) =>
              setAction(!v || v === "__all__" ? "" : v)
            }
          >
            <SelectTrigger id="audit-action" className="text-xs">
              <SelectValue placeholder="Todas" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Todas</SelectItem>
              {actions.map((a) => (
                <SelectItem key={a} value={a} className="font-mono text-xs">
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1">
          <Label htmlFor="audit-target" className="text-xs">
            Target contiene
          </Label>
          <Input
            id="audit-target"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="connector:woo..."
            className="font-mono text-xs"
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="audit-after" className="text-xs">
            Desde
          </Label>
          <Input
            id="audit-after"
            type="datetime-local"
            value={after}
            onChange={(e) => setAfter(e.target.value)}
            className="text-xs"
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="audit-before" className="text-xs">
            Hasta
          </Label>
          <Input
            id="audit-before"
            type="datetime-local"
            value={before}
            onChange={(e) => setBefore(e.target.value)}
            className="text-xs"
          />
        </div>
      </div>
      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={clear}
          disabled={pending}
        >
          Limpiar
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={apply}
          disabled={pending}
        >
          {pending ? "Aplicando…" : "Aplicar filtros"}
        </Button>
      </div>
    </div>
  );
}
