"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { toast } from "sonner";

import {
  Button,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Field,
  Input,
  Label,
  Textarea,
  cn,
} from "@nexus/ui";
import type { AuphereChannelUpdateInput, AuphereOwnerChannelOut } from "@/lib/backend";
import { FOCUS_RING } from "@/lib/focus-ring";

import { createNumberAction, deactivateNumberAction, updateNumberAction } from "./actions";
import { REASON_MAX, countryError, nameError, phoneError, reasonError } from "./labels";

const TOKEN_HINT =
  "El token del usuario del sistema de Meta con permiso para enviar desde este número. Se guarda cifrado y no se vuelve a mostrar.";
const META_ID_HINT =
  "El identificador que Meta da a este número en WhatsApp Manager («Phone number ID»). Sin él, el número no puede enviar.";

function Failure({ text }: { text: string | null }) {
  return text ? (
    <p role="alert" className="text-sm text-destructive text-pretty">
      {text}
    </p>
  ) : null;
}

function ReasonField({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
  return (
    <Field label="Motivo" required requiredLabel="Obligatorio" hint="Queda en la auditoría con tu nombre." error={error}>
      {(a11y) => <Textarea {...a11y} rows={2} maxLength={REASON_MAX} className={FOCUS_RING} value={value} onChange={(e) => onChange(e.target.value)} />}
    </Field>
  );
}

/**
 * Spec 059 (6.1, 6.5): register one of Auphere's own WhatsApp numbers. No
 * webhook secret (5.1): Meta signs with the app's secret.
 */
export function CreateNumberDialog() {
  const router = useRouter();
  const principalId = useId();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({ name: "", phone: "", country: "", metaId: "", token: "" });
  const [principal, setPrincipal] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<"name" | "phone" | "country", string>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const set = (key: keyof typeof values) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  function reset() {
    setValues({ name: "", phone: "", country: "", metaId: "", token: "" });
    setPrincipal(false);
    setErrors({});
    setFailure(null);
  }

  async function submit() {
    setFailure(null);
    const next = {
      name: nameError(values.name) ?? undefined,
      phone: phoneError(values.phone) ?? undefined,
      country: countryError(values.country) ?? undefined,
    };
    setErrors(next);
    if (next.name || next.phone || next.country) return;
    setPending(true);
    try {
      const result = await createNumberAction({
        phone_e164: values.phone.trim(),
        display_name: values.name.trim(),
        country_code: values.country.trim().toUpperCase() || null,
        provider: "meta",
        provider_phone_id: values.metaId.trim() || null,
        access_token: values.token.trim() || null,
        is_default: principal,
      });
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(`${result.data.display_name} registrado`);
      setOpen(false);
      reset();
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
        if (!next) reset();
      }}
    >
      <DialogTrigger render={<Button size="sm">Registrar un número</Button>} />
      {/* `max-h-svh` + scroll: at 360 px or 200 % zoom the whole dialog can be reached (WCAG 1.4.10). */}
      <DialogContent className="max-h-svh overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Registrar un número de Auphere</DialogTitle>
          <DialogDescription>
            Un número de WhatsApp de la cuenta de Meta de Auphere, desde el que Auphere escribe a los dueños de los negocios.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <Field label="Nombre visible" required requiredLabel="Obligatorio" hint="Para reconocerlo en el panel, por ejemplo «Auphere Chile»." error={errors.name}>
            {(a11y) => <Input {...a11y} autoComplete="off" maxLength={120} className={FOCUS_RING} value={values.name} onChange={set("name")} />}
          </Field>
          <Field
            label="Número de teléfono"
            required
            requiredLabel="Obligatorio"
            hint="Con el prefijo del país y sin espacios, por ejemplo +34600111222."
            error={errors.phone}
          >
            {(a11y) => (
              <Input {...a11y} autoComplete="off" inputMode="tel" className={cn("font-mono", FOCUS_RING)} value={values.phone} onChange={set("phone")} />
            )}
          </Field>
          <Field label="País" optionalLabel="Opcional" hint="El código de dos letras, por ejemplo ES o CL." error={errors.country}>
            {(a11y) => (
              <Input {...a11y} autoComplete="off" maxLength={2} className={cn("w-24 font-mono uppercase", FOCUS_RING)} value={values.country} onChange={set("country")} />
            )}
          </Field>
          <Field label="Identificador del número en Meta" optionalLabel="Opcional" hint={META_ID_HINT}>
            {(a11y) => <Input {...a11y} autoComplete="off" className={cn("font-mono", FOCUS_RING)} value={values.metaId} onChange={set("metaId")} />}
          </Field>
          <Field label="Token de acceso de Meta" optionalLabel="Opcional" hint={TOKEN_HINT}>
            {(a11y) => (
              <Input {...a11y} type="password" autoComplete="off" className={cn("font-mono", FOCUS_RING)} value={values.token} onChange={set("token")} />
            )}
          </Field>
          <div className="flex items-start gap-3">
            <Checkbox
              id={principalId}
              checked={principal}
              onCheckedChange={(value) => setPrincipal(value === true)}
              aria-labelledby={`${principalId}-label`}
              aria-describedby={`${principalId}-description`}
              className={cn("mt-1", FOCUS_RING)}
            />
            <div className="flex min-w-0 flex-col gap-1">
              <Label id={`${principalId}-label`} htmlFor={principalId} className="text-sm font-medium">
                Número principal
              </Label>
              <p id={`${principalId}-description`} className="text-xs text-pretty text-muted-foreground">
                Desde él salen los avisos de Auphere y las consultas a los dueños que no tienen un número asignado. Solo puede haber
                uno.
              </p>
            </div>
          </div>
          <Failure text={failure} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={pending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Registrando…" : "Registrar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type RowDialogProps = { number: AuphereOwnerChannelOut; open: boolean; onOpenChange: (open: boolean) => void };

/**
 * Spec 059 (6.2): change the token and the Meta number id of a number, with a
 * reason. An empty token keeps the one saved; only what changed is sent.
 */
export function EditNumberDialog({ number, open, onOpenChange }: RowDialogProps) {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [metaId, setMetaId] = useState(number.provider_phone_id ?? "");
  const [reason, setReason] = useState("");
  const [reasonErr, setReasonErr] = useState<string | undefined>();
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit() {
    setFailure(null);
    const why = reasonError(reason) ?? undefined;
    setReasonErr(why);
    if (why) return;
    const body: AuphereChannelUpdateInput = { reason: reason.trim() };
    if (token.trim()) body.access_token = token.trim();
    const nextId = metaId.trim() || null;
    if (nextId !== (number.provider_phone_id ?? null)) body.provider_phone_id = nextId;
    if (body.access_token === undefined && body.provider_phone_id === undefined) {
      setFailure("No has cambiado nada: escribe un token nuevo o cambia el identificador.");
      return;
    }
    setPending(true);
    try {
      const result = await updateNumberAction(number.id, body);
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(`${number.display_name} actualizado`);
      onOpenChange(false);
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (pending ? undefined : onOpenChange(next))}>
      <DialogContent className="max-h-svh overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Editar {number.display_name}</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{number.phone_e164}</span>. Lo que cambies se aplica al siguiente envío desde este número.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          {/* The label is the field's name and truncates; what an empty token does goes in its hint. */}
          <Field
            label="Token de acceso de Meta"
            optionalLabel={number.has_access_token ? "Opcional" : "Falta"}
            hint={number.has_access_token ? `Déjalo vacío para conservar el actual. ${TOKEN_HINT}` : TOKEN_HINT}
          >
            {(a11y) => (
              <Input
                {...a11y}
                type="password"
                autoComplete="off"
                className={cn("font-mono", FOCUS_RING)}
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
            )}
          </Field>
          <Field label="Identificador del número en Meta" hint={META_ID_HINT}>
            {(a11y) => (
              <Input {...a11y} autoComplete="off" className={cn("font-mono", FOCUS_RING)} value={metaId} onChange={(e) => setMetaId(e.target.value)} />
            )}
          </Field>
          <ReasonField value={reason} onChange={setReason} error={reasonErr} />
          <Failure text={failure} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={pending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export type NumberChange = "promote" | "demote" | "reactivate" | "deactivate";

const CHANGE: Record<NumberChange, { title: (n: string) => string; confirm: string; pending: string; done: (n: string) => string }> = {
  promote: {
    title: (n) => `Marcar ${n} como principal`,
    confirm: "Marcar como principal",
    pending: "Guardando…",
    done: (n) => `${n} es ahora el número principal`,
  },
  demote: {
    title: (n) => `Quitar ${n} como principal`,
    confirm: "Quitar como principal",
    pending: "Guardando…",
    done: (n) => `${n} ya no es el número principal`,
  },
  reactivate: {
    title: (n) => `Reactivar ${n}`,
    confirm: "Reactivar",
    pending: "Reactivando…",
    done: (n) => `${n} reactivado`,
  },
  deactivate: {
    title: (n) => `Desactivar ${n}`,
    confirm: "Desactivar",
    pending: "Desactivando…",
    done: (n) => `${n} desactivado`,
  },
};

function changeDescription(change: NumberChange, n: AuphereOwnerChannelOut): string {
  switch (change) {
    case "promote":
      return "Desde él saldrán los avisos de Auphere y las consultas a los dueños que no tienen un número asignado.";
    case "demote":
      return "Hasta que marques otro, Auphere no envía avisos por WhatsApp ni consultas a los dueños sin un número asignado.";
    case "reactivate":
      return "Vuelve a poder enviar, y los dueños que lo tengan asignado vuelven a recibir desde él.";
    case "deactivate":
      return `Deja de enviar desde ${n.phone_e164}. Los dueños que lo tengan asignado pasan al número principal en el siguiente envío. Se puede reactivar.`;
  }
}

/**
 * Spec 059 (6.3, 6.4): the changes of a row, confirmed inside the page and
 * with a reason — never `window.confirm` or `prompt`.
 */
export function ChangeNumberDialog({ number, change, open, onOpenChange }: RowDialogProps & { change: NumberChange }) {
  const router = useRouter();
  const words = CHANGE[change];
  const [reason, setReason] = useState("");
  const [reasonErr, setReasonErr] = useState<string | undefined>();
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit() {
    setFailure(null);
    const why = reasonError(reason) ?? undefined;
    setReasonErr(why);
    if (why) return;
    const text = reason.trim();
    setPending(true);
    try {
      const result =
        change === "deactivate"
          ? await deactivateNumberAction(number.id, text)
          : await updateNumberAction(
              number.id,
              change === "reactivate" ? { active: true, reason: text } : { is_default: change === "promote", reason: text },
            );
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(words.done(number.display_name));
      onOpenChange(false);
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (pending ? undefined : onOpenChange(next))}>
      <DialogContent className="max-h-svh overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{words.title(number.display_name)}</DialogTitle>
          <DialogDescription>{changeDescription(change, number)}</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          {change === "deactivate" && number.is_default ? (
            <p className="text-sm text-pretty text-status-warning-text">
              Es el número principal: hasta que marques otro, Auphere no envía avisos por WhatsApp.
            </p>
          ) : null}
          <ReasonField value={reason} onChange={setReason} error={reasonErr} />
          <Failure text={failure} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={pending}>
              Cancelar
            </Button>
            <Button type="submit" variant={change === "deactivate" ? "destructive" : "default"} disabled={pending}>
              {pending ? words.pending : words.confirm}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
