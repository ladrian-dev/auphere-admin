"use client";

import { useRouter } from "next/navigation";
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
} from "@nexus/ui";
import type { DeploymentStatus } from "@/lib/backend-models";

import { STATUS_LABEL } from "../../models/labels";
import { calibrateJudgeAction } from "../actions";
import { formatShare } from "../labels";

export type JudgeDeployment = { uuid: string; key: string; status: DeploymentStatus };

/**
 * Spec 047 (T087, 21.8): calibrate a deployment as the judge. It runs that
 * model over the labelled set — one call per example, paid by Auphere — and
 * waits for the result.
 */
export function RunCalibration({ deployments }: { deployments: JudgeDeployment[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [deployment, setDeployment] = useState(deployments[0]?.uuid ?? "");
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function run() {
    setFailure(null);
    if (!deployment) {
      setFailure("Elige un despliegue.");
      return;
    }
    setPending(true);
    try {
      const result = await calibrateJudgeAction(deployment);
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      const verdict = result.data.passed ? "aprobada" : "suspendida";
      toast.success(`Calibración ${verdict}: ${formatShare(result.data.agreement)} de acuerdo`);
      setOpen(false);
      router.replace(`/builder/judge-calibration?deployment=${encodeURIComponent(deployment)}`);
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return;
        setOpen(next);
        if (!next) setFailure(null);
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant="outline" disabled={!deployments.length}>
            Calibrar un despliegue
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Calibrar un despliegue como juez</DialogTitle>
          <DialogDescription>
            Corre su juez sobre el conjunto etiquetado a mano en español y guarda el acuerdo como la certificación de la tarea
            judge. Hace una llamada al modelo por ejemplo, la paga Auphere y la pantalla espera a que termine.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
        >
          <Field label="Despliegue" hint="El juez tiene que ser de otra familia que los modelos de los agentes que juzga.">
            {(a11y) => (
              <NativeSelect {...a11y} value={deployment} onChange={(e) => setDeployment(e.target.value)}>
                {deployments.map((d) => (
                  <option key={d.uuid} value={d.uuid}>
                    {d.key}
                    {d.status === "active" ? "" : ` · ${STATUS_LABEL[d.status] ?? d.status}`}
                  </option>
                ))}
              </NativeSelect>
            )}
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
              {pending ? "Calibrando…" : "Calibrar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
