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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { PartnerOut, PartnerStatus } from "@/lib/backend";

import { updatePartnerAction } from "../../actions";

// Rangos espejo del backend (PartnerUpdateIn en schemas/partner.py).
const schema = z.object({
  broadcast_recipient_cap: z.coerce
    .number()
    .int("Entero")
    .min(1, "Mínimo 1")
    .max(10_000, "Máximo 10 000"),
  rate_limit_mint_per_min: z.coerce
    .number()
    .int("Entero")
    .min(1, "Mínimo 1")
    .max(10_000, "Máximo 10 000"),
  rate_limit_embed_per_min: z.coerce
    .number()
    .int("Entero")
    .min(1, "Mínimo 1")
    .max(100_000, "Máximo 100 000"),
  status: z.enum(["active", "suspended"]),
});

type FormValues = z.infer<typeof schema>;

export function LimitsForm({ partner }: { partner: PartnerOut }) {
  const [submitting, setSubmitting] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      broadcast_recipient_cap: partner.broadcast_recipient_cap,
      rate_limit_mint_per_min: partner.rate_limit_mint_per_min,
      rate_limit_embed_per_min: partner.rate_limit_embed_per_min,
      status: partner.status,
    },
  });

  async function onSubmit(values: FormValues) {
    setSubmitting(true);
    try {
      const result = await updatePartnerAction(partner.id, {
        broadcast_recipient_cap: values.broadcast_recipient_cap,
        rate_limit_mint_per_min: values.rate_limit_mint_per_min,
        rate_limit_embed_per_min: values.rate_limit_embed_per_min,
        status: values.status as PartnerStatus,
      });
      if (!result.ok) {
        toast.error("No se pudieron guardar los límites", {
          description: result.error,
        });
        return;
      }
      toast.success("Límites actualizados", {
        description:
          result.data.status === "suspended"
            ? "Partner SUSPENDIDO — todas sus keys dejan de autenticar."
            : undefined,
      });
      form.reset({
        broadcast_recipient_cap: result.data.broadcast_recipient_cap,
        rate_limit_mint_per_min: result.data.rate_limit_mint_per_min,
        rate_limit_embed_per_min: result.data.rate_limit_embed_per_min,
        status: result.data.status,
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
        <div className="grid gap-4 md:grid-cols-3">
          <FormField
            control={form.control}
            name="broadcast_recipient_cap"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Cap de broadcast</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="number"
                    min={1}
                    max={10_000}
                    className="tabular-nums"
                  />
                </FormControl>
                <FormDescription>
                  Destinatarios máx. por envío.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="rate_limit_mint_per_min"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Mint / min</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="number"
                    min={1}
                    max={10_000}
                    className="tabular-nums"
                  />
                </FormControl>
                <FormDescription>
                  Session tokens por minuto.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="rate_limit_embed_per_min"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Embed / min</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="number"
                    min={1}
                    max={100_000}
                    className="tabular-nums"
                  />
                </FormControl>
                <FormDescription>
                  Llamadas del widget por minuto.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="status"
          render={({ field }) => (
            <FormItem className="md:max-w-xs">
              <FormLabel>Estado</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="active">Activo</SelectItem>
                  <SelectItem value="suspended">
                    Suspendido — kill-switch
                  </SelectItem>
                </SelectContent>
              </Select>
              <FormDescription>
                Suspendido corta todas las keys sin revocarlas; reactivar
                las devuelve tal cual estaban.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div>
          <Button
            type="submit"
            disabled={submitting || !form.formState.isDirty}
          >
            {submitting ? "Guardando…" : "Guardar cambios"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
