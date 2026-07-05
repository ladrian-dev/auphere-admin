"use client";

import { useState } from "react";
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

import { linkPartnerTenantAction } from "../../actions";

const schema = z.object({
  external_client_ref: z.string().min(1, "Obligatorio").max(255),
  tenant_id: z.string().uuid("UUID inválido"),
  client_name: z.string().max(255).optional().or(z.literal("")),
});

type FormValues = z.infer<typeof schema>;

export function LinkTenantForm({ partnerId }: { partnerId: string }) {
  const [submitting, setSubmitting] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { external_client_ref: "", tenant_id: "", client_name: "" },
  });

  async function onSubmit(values: FormValues) {
    setSubmitting(true);
    try {
      const result = await linkPartnerTenantAction(partnerId, {
        external_client_ref: values.external_client_ref,
        tenant_id: values.tenant_id,
        client_name: values.client_name || null,
      });
      if (!result.ok) {
        toast.error("No se pudo mapear", { description: result.error });
        return;
      }
      toast.success(
        `Mapeado ${result.data.external_client_ref} → tenant ${result.data.tenant_id.slice(0, 8)}…`,
      );
      form.reset();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="grid gap-4 md:grid-cols-[1fr_1.5fr_1fr_auto] md:items-end"
        noValidate
      >
        <FormField
          control={form.control}
          name="external_client_ref"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Ref del partner</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  placeholder="cliente-123"
                  className="font-mono"
                  autoComplete="off"
                  autoCapitalize="off"
                  spellCheck={false}
                />
              </FormControl>
              <FormDescription>
                Identificador que usa el partner.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="tenant_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Tenant ID</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  placeholder="00000000-0000-0000-0000-000000000000"
                  className="font-mono"
                  autoComplete="off"
                  autoCapitalize="off"
                  spellCheck={false}
                />
              </FormControl>
              <FormDescription>UUID del tenant Nexus.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="client_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Nombre (opcional)</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  placeholder="Barbería El Corte"
                  autoComplete="off"
                />
              </FormControl>
              <FormDescription>Solo visible en este panel.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={submitting}>
          {submitting ? "Mapeando…" : "Mapear"}
        </Button>
      </form>
    </Form>
  );
}
