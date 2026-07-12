"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { PartnerOut, SeedTemplate } from "@/lib/backend";

import { updatePartnerAction } from "../../actions";

// Sentinel del Select — el backend limpia el campo con "".
const NONE = "__none__";

const schema = z.object({
  default_seed_template: z.string(),
  default_connector_slug: z
    .string()
    .max(80, "Máximo 80 caracteres")
    .regex(/^[a-z0-9_]*$/, "Solo minúsculas, dígitos y _"),
  auto_activate: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

/**
 * Blueprint de auto-provisión (Fase 2b): con esto configurado, cada
 * ``POST /v1/partners/clients`` del partner deja un agente promovido
 * (clon del seed) + el connector instalado, y el signup de WhatsApp
 * activa el tenant sin operador en el loop.
 */
export function BlueprintForm({
  partner,
  seedTemplates,
}: {
  partner: PartnerOut;
  seedTemplates: SeedTemplate[];
}) {
  const [submitting, setSubmitting] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      default_seed_template: partner.default_seed_template ?? NONE,
      default_connector_slug: partner.default_connector_slug ?? "",
      auto_activate: partner.auto_activate,
    },
  });

  async function onSubmit(values: FormValues) {
    setSubmitting(true);
    try {
      const result = await updatePartnerAction(partner.id, {
        default_seed_template:
          values.default_seed_template === NONE ? "" : values.default_seed_template,
        default_connector_slug: values.default_connector_slug,
        auto_activate: values.auto_activate,
      });
      if (!result.ok) {
        toast.error("No se pudo guardar el blueprint", {
          description: result.error,
        });
        return;
      }
      toast.success("Blueprint actualizado");
      form.reset({
        default_seed_template: result.data.default_seed_template ?? NONE,
        default_connector_slug: result.data.default_connector_slug ?? "",
        auto_activate: result.data.auto_activate,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="grid gap-6 max-w-2xl"
        noValidate
      >
        <div className="grid gap-4 md:grid-cols-2">
          <FormField
            control={form.control}
            name="default_seed_template"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Seed template del agente</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Sin auto-agente" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value={NONE}>Sin auto-agente</SelectItem>
                    {seedTemplates.map((tpl) => (
                      <SelectItem key={tpl.name} value={tpl.name}>
                        {tpl.display_name}{" "}
                        <span className="text-muted-foreground font-mono text-xs">
                          {tpl.name}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>
                  Se clona (prompt + tools + policies) como v1 promovida en
                  cada cliente que el partner provisiona.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="default_connector_slug"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Connector por defecto</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    placeholder="amigable_cobro"
                    className="font-mono"
                  />
                </FormControl>
                <FormDescription>
                  Connector api_key que se instala con las credenciales que
                  el partner envía al provisionar. Vacío = ninguno.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="auto_activate"
          render={({ field }) => (
            <FormItem className="flex flex-row items-start gap-3 space-y-0">
              <FormControl>
                <Checkbox
                  checked={field.value}
                  onCheckedChange={(checked) => field.onChange(checked === true)}
                />
              </FormControl>
              <div className="grid gap-1 leading-none">
                <FormLabel>Auto-activar al conectar WhatsApp</FormLabel>
                <FormDescription>
                  El tenant pasa de provisioning a ACTIVE al completar el
                  Embedded Signup, solo si ya tiene un agente promovido.
                  Desmarcado = un operador revisa y activa a mano.
                </FormDescription>
              </div>
              <FormMessage />
            </FormItem>
          )}
        />

        <div>
          <Button type="submit" disabled={submitting || !form.formState.isDirty}>
            {submitting ? "Guardando…" : "Guardar blueprint"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
