"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  Button,
  buttonVariants,
  Callout,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
} from "@nexus/ui";

import type { PartnerCreatedOut } from "@/lib/backend";

import { FIELD_OF_CODE, OWNER_EMAIL_BAD_SHAPE, OWNER_EMAIL_REQUIRED, SENDING_HINT } from "../_invitation/messages";
import { InvitationResult } from "../_invitation/invitation-result";
import { createPartnerAction } from "../actions";

// Mirror of the backend pattern (apps/api/.../schemas/partner.py).
const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

const schema = z.object({
  name: z.string().min(1, "Obligatorio").max(255),
  slug: z
    .string()
    .min(2, "Mínimo 2 caracteres")
    .max(80)
    .regex(SLUG_RE, "Solo minúsculas, dígitos y guiones (ej. acme-crm)"),
  owner_email: z.string().trim().min(1, OWNER_EMAIL_REQUIRED).max(255).email(OWNER_EMAIL_BAD_SHAPE),
});

type FormValues = z.infer<typeof schema>;

/**
 * Spec 052: el alta invita al propietario. Al terminar, el resultado se pinta
 * aquí mismo, en la misma URL: el enlace no puede viajar por una dirección del
 * panel (R6.6), y la salida es un enlace limpio a la ficha (R2.1).
 */
export function NewPartnerForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ partner: PartnerCreatedOut; replaced: boolean; dead: string | null } | null>(
    null,
  );
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", slug: "", owner_email: "" },
  });

  async function onSubmit(values: FormValues) {
    setSubmitting(true);
    setFormError(null);
    try {
      const result = await createPartnerAction({
        name: values.name,
        slug: values.slug,
        owner_email: values.owner_email,
      });
      if (result.ok) {
        setCreated({ partner: result.data, replaced: false, dead: null });
        return;
      }
      const field = result.code ? FIELD_OF_CODE[result.code] : undefined;
      if (field === "slug") {
        form.setError("slug", { message: result.error }, { shouldFocus: true });
      } else if (field === "email") {
        form.setError("owner_email", { message: result.error }, { shouldFocus: true });
      } else {
        setFormError(result.error);
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (created) {
    const { partner } = created;
    // Un enlace de verdad: lleva a otra página, y solo con su propio identificador.
    const toFile = (
      <Link
        href={`/partners/${partner.id}`}
        className={buttonVariants({ variant: created.dead || partner.invitation.email_sent ? "default" : "outline" })}
      >
        Ir a la ficha del partner
      </Link>
    );
    if (created.dead) {
      return (
        <div className="grid min-w-0 gap-(--space-stack)">
          <Callout tone="info">{created.dead}</Callout>
          <div className="flex flex-wrap gap-2">{toFile}</div>
        </div>
      );
    }
    return (
      <InvitationResult
        partnerId={partner.id}
        partnerName={partner.name}
        result={partner.invitation}
        replacedPrevious={created.replaced}
        onReplaced={(next) => setCreated({ partner: { ...partner, invitation: next }, replaced: true, dead: null })}
        onDead={(message) => setCreated({ partner, replaced: false, dead: message })}
        lead={<p className="text-sm text-pretty wrap-anywhere">{partner.name} ya existe, con la consola encendida.</p>}
      >
        {toFile}
      </InvitationResult>
    );
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-6" noValidate>
        <div className="grid gap-4 md:grid-cols-2">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Nombre</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="Acme CRM" autoComplete="off" />
                </FormControl>
                <FormDescription>Nombre comercial del partner.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="slug"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Identificador (slug)</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    placeholder="acme-crm"
                    className="font-mono"
                    autoComplete="off"
                    autoCapitalize="off"
                    spellCheck={false}
                  />
                </FormControl>
                <FormDescription>Único, y no se puede cambiar después.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        <FormField
          control={form.control}
          name="owner_email"
          render={({ field }) => (
            <FormItem className="md:max-w-sm">
              <FormLabel>Correo del propietario</FormLabel>
              <FormControl>
                <Input {...field} type="email" inputMode="email" placeholder="persona@acme.com" autoComplete="off" />
              </FormControl>
              <FormDescription>
                Al crear el partner se enciende su consola y esta persona recibe una invitación como propietaria. Queda
                también como correo de contacto, que se edita luego en la ficha.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        {formError ? <Callout tone="danger">{formError}</Callout> : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" loading={submitting}>
            {submitting ? "Creando…" : "Crear partner"}
          </Button>
          <Button type="button" variant="outline" disabled={submitting} onClick={() => router.push("/partners")}>
            Cancelar
          </Button>
        </div>
        {submitting ? (
          <p role="status" className="text-xs text-pretty text-muted-foreground">
            {SENDING_HINT}
          </p>
        ) : null}
      </form>
    </Form>
  );
}
