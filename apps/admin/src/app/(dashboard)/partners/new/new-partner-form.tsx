"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";

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
  contact_email: z
    .string()
    .email("Email inválido")
    .optional()
    .or(z.literal("")),
});

type FormValues = z.infer<typeof schema>;

export function NewPartnerForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", slug: "", contact_email: "" },
  });

  async function onSubmit(values: FormValues) {
    setSubmitting(true);
    try {
      const result = await createPartnerAction({
        name: values.name,
        slug: values.slug,
        contact_email: values.contact_email || null,
      });
      if (!result.ok) {
        // 409 = slug tomado; el backend habla claro, lo mostramos verbatim.
        toast.error("No se pudo crear el partner", {
          description: result.error,
        });
        return;
      }
      toast.success(`Partner ${result.data.name} creado`, {
        description: "Ahora crea su primera API key en la pestaña Keys.",
      });
      router.push(`/partners/${result.data.id}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="grid gap-6"
        noValidate
      >
        <div className="grid gap-4 md:grid-cols-2">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Nombre</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    placeholder="Acme CRM"
                    autoComplete="off"
                  />
                </FormControl>
                <FormDescription>
                  Nombre comercial del partner.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="slug"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Slug</FormLabel>
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
                <FormDescription>
                  Identificador único e inmutable. 409 si ya está tomado.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        <FormField
          control={form.control}
          name="contact_email"
          render={({ field }) => (
            <FormItem className="md:max-w-sm">
              <FormLabel>Email de contacto (opcional)</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="email"
                  placeholder="dev@acme.com"
                  autoComplete="off"
                />
              </FormControl>
              <FormDescription>
                Contacto técnico para avisos de rotación de keys.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="flex items-center gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creando…" : "Crear partner"}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={submitting}
            onClick={() => router.push("/partners")}
          >
            Cancelar
          </Button>
        </div>
      </form>
    </Form>
  );
}
