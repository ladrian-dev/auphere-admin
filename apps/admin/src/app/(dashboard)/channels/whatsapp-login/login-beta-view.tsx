"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
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
  EmptyState,
  Field,
  NativeSelect,
  Section,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
} from "@nexus/ui";
import type { LoginBetaCountry } from "@/lib/backend-whatsapp-beta";

import { setLoginBetaCountryAction } from "./actions";
import { EU_WHY, REASON_MAX, countryName, countryOptions, enabledByLabel, isEuEea, reasonError } from "./countries";

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

type Props = { countries: LoginBetaCountry[]; operatorId: string };

/**
 * Spec 047 (T117, 31.5, 54.7): where the owner's link offers «Conectar con
 * WhatsApp, sin cuenta de Meta», and the form to turn it on in a country —
 * never in the EU or the EEA. Every change carries its reason.
 */
export function LoginBetaView({ countries, operatorId }: Props) {
  return (
    <div className="flex flex-col gap-6">
      <Section
        title="Activada en"
        description="El enlace del dueño ofrece «Conectar con WhatsApp, sin cuenta de Meta» a los negocios de estos países, y explica que la verificación del negocio llega después."
      >
        {countries.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>País</TableHead>
                <TableHead>Desde</TableHead>
                <TableHead>Quién</TableHead>
                <TableHead className="text-right">
                  <span className="sr-only">Acciones</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {countries.map((c) => (
                <TableRow key={c.country}>
                  <TableCell className="font-medium">
                    {countryName(c.country)} <code className="text-xs text-muted-foreground">{c.country}</code>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm">{DATE.format(new Date(c.enabled_at))}</TableCell>
                  <TableCell className="text-sm" title={c.enabled_by}>
                    {enabledByLabel(c.enabled_by, operatorId)}
                  </TableCell>
                  <TableCell className="text-right">
                    <RemoveCountry country={c.country} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <EmptyState
            readonly
            title="La beta no está activada en ningún país"
            description="Ningún enlace del dueño ofrece «Conectar con WhatsApp, sin cuenta de Meta». Actívala abajo cuando Meta la dé a la app de Auphere en un país."
          />
        )}
      </Section>
      <Section
        title="Activar en un país"
        description="Solo cuando Meta haya habilitado la beta para la app de Auphere en ese país. Se aplica a los enlaces que se creen desde ahora."
      >
        <EnableForm enabled={countries.map((c) => c.country)} />
      </Section>
    </div>
  );
}

function EnableForm({ enabled }: { enabled: string[] }) {
  const router = useRouter();
  const { available, blocked } = useMemo(() => countryOptions(enabled), [enabled]);
  const [country, setCountry] = useState("");
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<{ country?: string; reason?: string }>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit() {
    setFailure(null);
    const next: { country?: string; reason?: string } = {};
    if (!country) next.country = "Elige un país.";
    else if (isEuEea(country)) next.country = EU_WHY;
    const why = reasonError(reason);
    if (why) next.reason = why;
    setErrors(next);
    if (next.country || next.reason) return;
    setPending(true);
    try {
      const result = await setLoginBetaCountryAction(country, { enabled: true, reason: reason.trim() });
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(`Beta activada en ${countryName(country)}`);
      setCountry("");
      setReason("");
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      className="flex flex-col gap-4"
      aria-label="Activar la beta en un país"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <Field
        label="País"
        required
        requiredLabel="Obligatorio"
        hint={`Los de la UE y del EEE aparecen al final y no se pueden elegir. ${EU_WHY}`}
        error={errors.country}
      >
        {(a11y) => (
          <NativeSelect {...a11y} wrapperClassName="sm:w-96" value={country} onChange={(e) => setCountry(e.target.value)}>
            <option value="">Elige un país…</option>
            <optgroup label="Se puede activar">
              {available.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name} ({c.code})
                </option>
              ))}
            </optgroup>
            <optgroup label="UE y EEE: nunca">
              {blocked.map((c) => (
                <option key={c.code} value={c.code} disabled>
                  {c.name} ({c.code}) · UE/EEE
                </option>
              ))}
            </optgroup>
          </NativeSelect>
        )}
      </Field>
      <Field
        label="Motivo"
        required
        requiredLabel="Obligatorio"
        hint="Queda en la auditoría con tu nombre. Por ejemplo: «Meta habilitó la beta para la app en México»."
        error={errors.reason}
      >
        {(a11y) => (
          <Textarea {...a11y} rows={2} maxLength={REASON_MAX} value={reason} onChange={(e) => setReason(e.target.value)} />
        )}
      </Field>
      {failure ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {failure}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button type="submit" disabled={pending}>
          {pending ? "Activando…" : "Activar la beta"}
        </Button>
      </div>
    </form>
  );
}

function RemoveCountry({ country }: { country: string }) {
  const router = useRouter();
  const name = countryName(country);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit() {
    setFailure(null);
    const why = reasonError(reason);
    setError(why);
    if (why) return;
    setPending(true);
    try {
      const result = await setLoginBetaCountryAction(country, { enabled: false, reason: reason.trim() });
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(`Beta quitada en ${name}`);
      setOpen(false);
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setReason("");
          setError(null);
          setFailure(null);
        }
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant="outline" aria-label={`Quitar la beta en ${name}`}>
            Quitar
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Quitar la beta en {name}</DialogTitle>
          <DialogDescription>
            Los enlaces del dueño que se creen desde ahora dejan de ofrecer «Conectar con WhatsApp, sin cuenta de Meta» a los negocios de {name}.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <Field label="Motivo" required requiredLabel="Obligatorio" hint="Queda en la auditoría con tu nombre." error={error ?? undefined}>
            {(a11y) => (
              <Textarea {...a11y} rows={2} maxLength={REASON_MAX} value={reason} onChange={(e) => setReason(e.target.value)} />
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
            <Button type="submit" variant="destructive" disabled={pending}>
              {pending ? "Quitando…" : "Quitar la beta"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
