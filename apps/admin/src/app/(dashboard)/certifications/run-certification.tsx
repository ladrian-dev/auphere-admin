"use client";

import { useState } from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Field,
  NativeSelect,
  Textarea,
} from "@nexus/ui";

import { launchCertificationAction } from "./actions";

type Props = { deployments: { uuid: string; key: string }[]; tasks: string[] };

/**
 * Spec 047 (T150, 42.6, 54.3): launch a certification paid by Auphere — of a
 * deployment by task (the common battery) or for some agents (their suite).
 * Until the runners have their job, the API says so and nothing is queued.
 */
export function RunCertification({ deployments, tasks }: Props) {
  const [open, setOpen] = useState(false);
  const [deployment, setDeployment] = useState(deployments[0]?.uuid ?? "");
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [agents, setAgents] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const agentIds = agents
    .split(/[\s,]+/)
    .map((a) => a.trim())
    .filter(Boolean);

  async function launch() {
    setFailure(null);
    if (!chosen.size && !agentIds.length) {
      setFailure("Elige al menos una tarea o un agente.");
      return;
    }
    setPending(true);
    try {
      const result = await launchCertificationAction({
        deployment_id: deployment,
        ...(chosen.size ? { tasks: [...chosen] } : { agent_ids: agentIds }),
      });
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(`Lanzadas ${result.data.jobs.length} certificaciones`);
      setOpen(false);
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" disabled={!deployments.length}>Lanzar una certificación</Button>} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Lanzar una certificación</DialogTitle>
          <DialogDescription>La paga Auphere, fuera de las partidas del partner. El juez es siempre de otra familia.</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void launch();
          }}
        >
          <Field label="Despliegue">
            {(a11y) => (
              <NativeSelect {...a11y} value={deployment} onChange={(e) => setDeployment(e.target.value)}>
                {deployments.map((d) => (
                  <option key={d.uuid} value={d.uuid}>
                    {d.key}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">Por clase: las tareas de la batería común</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {tasks.map((t) => (
                <label key={t} className="flex min-h-6 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4 accent-primary"
                    checked={chosen.has(t)}
                    onChange={(e) =>
                      setChosen((s) => {
                        const next = new Set(s);
                        if (e.target.checked) next.add(t);
                        else next.delete(t);
                        return next;
                      })
                    }
                  />
                  {t}
                </label>
              ))}
            </div>
          </fieldset>
          <Field label="O por agente: sus identificadores" hint="Uno por línea. Sin tareas marcadas, se certifica para estos agentes.">
            {(a11y) => <Textarea {...a11y} rows={2} value={agents} onChange={(e) => setAgents(e.target.value)} />}
          </Field>
          {failure ? (
            <p role="alert" className="text-sm text-destructive text-pretty">
              {failure}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={pending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Lanzando…" : "Lanzar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
