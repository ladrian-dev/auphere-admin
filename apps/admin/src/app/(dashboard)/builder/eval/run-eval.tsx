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
  Input,
} from "@nexus/ui";

import { runEvalAction } from "../actions";
import { BANK_SIZE, formatPct, parseEvalLimit } from "../labels";

/**
 * Spec 047 (T100, 54.4): run the builder over the bank. One call to the
 * builder's model per description, paid by Auphere; it writes nothing in any
 * client, and the screen waits until it ends.
 */
export function RunEval() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [limit, setLimit] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function run() {
    setFailure(null);
    const parsed = parseEvalLimit(limit);
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }
    setError(null);
    setPending(true);
    try {
      const result = await runEvalAction(parsed.limit);
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(`Evaluación guardada: ${formatPct(result.data.validator_first_pass_pct)} pasa el validador a la primera`);
      setOpen(false);
      setLimit("");
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
        if (!next) {
          setError(null);
          setFailure(null);
        }
      }}
    >
      <DialogTrigger render={<Button size="sm" variant="outline">Correr la evaluación</Button>} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Correr la evaluación del constructor</DialogTitle>
          <DialogDescription>
            Pasa cada descripción del banco por el constructor, con el catálogo de un cliente sin integraciones conectadas, y no
            escribe nada en ningún cliente. Una llamada al modelo por descripción, la paga Auphere: con las {BANK_SIZE} tarda
            varios minutos y la pantalla espera a que termine.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
        >
          <Field
            label="Descripciones"
            optionalLabel="Opcional"
            hint={`Vacío: las ${BANK_SIZE} del banco. Una tanda corta sirve para comprobar que funciona, pero entra en el historial y en la comparación con la siguiente.`}
            error={error ?? undefined}
          >
            {(a11y) => (
              <Input {...a11y} inputMode="numeric" placeholder={String(BANK_SIZE)} value={limit} onChange={(e) => setLimit(e.target.value)} />
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
              {pending ? "Evaluando…" : "Correr"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
