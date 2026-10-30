"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
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
  Textarea,
} from "@nexus/ui";
import type { ClientDataFinding, GeneratedGuide } from "@/lib/backend-sector-guides";
import { REASON_MAX } from "@/lib/levers";

import { TESTS_PER_SECTOR } from "../sector-tests/sector-tests";
import { promoteGeneratedGuideAction } from "./actions";
import { LABEL_MAX, checkPromote, suggestKey, type PromoteForm } from "./sector-guides";

type Props = {
  guide: GeneratedGuide;
  /** Keys that already have a guide (the template sectors, the converted ones) and `otro`. */
  takenKeys: readonly string[];
  /** The API found client data in the saved guide: the page marks it. */
  onFindings: (findings: ClientDataFinding[]) => void;
};

/**
 * Spec 047 (T201, 58.5, D66): «Convertir en guía de Auphere». Only on a guide
 * the API calls `promotable`: reviewed, without client data and with its 12
 * tests. Key, label and reason, checked here as the API checks them.
 */
export function PromoteDialog({ guide, takenKeys, onFindings }: Props) {
  const router = useRouter();
  const initial = (): PromoteForm => ({ key: suggestKey(guide.label_key), label: guide.sector_label.slice(0, LABEL_MAX), reason: "" });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<PromoteForm>(initial);
  const [errors, setErrors] = useState<Partial<Record<keyof PromoteForm, string>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const busy = useRef(false);

  async function promote() {
    if (busy.current) return;
    setFailure(null);
    const checked = checkPromote(form, takenKeys);
    if (!checked.ok) {
      setErrors(checked.errors);
      return;
    }
    setErrors({});
    busy.current = true;
    setPending(true);
    try {
      const result = await promoteGeneratedGuideAction(guide.tenant_id, guide.guide_id, checked.body);
      if (!result.ok) {
        setFailure(result.error);
        if (result.findings?.length) onFindings(result.findings);
        return;
      }
      toast.success(`«${result.data.label}» ya es guía de Auphere`);
      setOpen(false);
      router.refresh();
    } finally {
      busy.current = false;
      setPending(false);
    }
  }

  const set = (patch: Partial<PromoteForm>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return;
        setOpen(next);
        if (!next) {
          setForm(initial());
          setErrors({});
          setFailure(null);
        }
      }}
    >
      <DialogTrigger render={<Button>Convertir en guía de Auphere</Button>} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Convertir en guía de Auphere</DialogTitle>
          <DialogDescription>
            La guía pasa a la plataforma con una clave nueva y sus {TESTS_PER_SECTOR} pruebas entran en el catálogo de pruebas del
            sector como versión 1. Desde entonces, cada cliente de «Otro» con la etiqueta «{guide.sector_label}» recibe esta guía en
            lugar de generar la suya. Su ficha sigue diciendo «Otro».
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void promote();
          }}
        >
          <Field
            label="Clave"
            required
            requiredLabel="Obligatoria"
            hint="Minúsculas y «_», de 2 a 40. No puede ser la de un sector, «otro» ni la de otra guía de Auphere."
            error={errors.key}
          >
            {(a11y) => (
              <Input {...a11y} maxLength={40} spellCheck={false} className="font-mono" value={form.key} onChange={(e) => set({ key: e.target.value })} />
            )}
          </Field>
          <Field label="Etiqueta" required requiredLabel="Obligatoria" hint="Como la verán los partners. Hasta 40 caracteres." error={errors.label}>
            {(a11y) => <Input {...a11y} maxLength={LABEL_MAX} value={form.label} onChange={(e) => set({ label: e.target.value })} />}
          </Field>
          <Field label="Motivo" required requiredLabel="Obligatorio" hint="Queda en la auditoría. De 3 a 300 caracteres." error={errors.reason}>
            {(a11y) => (
              <Textarea {...a11y} rows={3} maxLength={REASON_MAX} value={form.reason} onChange={(e) => set({ reason: e.target.value })} />
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
            <Button type="submit" disabled={pending} aria-busy={pending || undefined}>
              {pending ? "Convirtiendo…" : "Convertir"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
