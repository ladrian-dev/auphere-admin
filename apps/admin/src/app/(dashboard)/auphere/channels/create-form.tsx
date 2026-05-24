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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { createChannelAction } from "./actions";

const E164_RE = /^\+[1-9]\d{1,14}$/;
const ISO2_RE = /^[A-Za-z]{2}$/;

const schema = z.object({
  phone_e164: z.string().regex(E164_RE, "E.164 obligatorio"),
  display_name: z.string().min(1, "Requerido").max(120),
  country_code: z
    .string()
    .regex(ISO2_RE, "2 letras ISO (ej. CL)")
    .optional()
    .or(z.literal("")),
  provider: z.enum(["ycloud", "meta"]),
  provider_phone_id: z.string().max(120).optional().or(z.literal("")),
  webhook_secret: z.string().max(200).optional().or(z.literal("")),
});

type FormValues = z.infer<typeof schema>;
type Action = typeof createChannelAction;

export function CreateChannelForm({ createAction }: { createAction: Action }) {
  const [submitting, setSubmitting] = useState(false);
  const [isDefault, setIsDefault] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      phone_e164: "",
      display_name: "",
      country_code: "",
      provider: "ycloud",
      provider_phone_id: "",
      webhook_secret: "",
    },
  });

  async function onSubmit(values: FormValues) {
    setSubmitting(true);
    try {
      const result = await createAction({
        phone_e164: values.phone_e164,
        display_name: values.display_name,
        country_code: values.country_code || null,
        provider: values.provider,
        provider_phone_id: values.provider_phone_id || null,
        is_default: isDefault,
        webhook_secret: values.webhook_secret || null,
      });
      if (!result.ok) {
        toast.error("No se pudo crear el canal", {
          description: result.error,
        });
        return;
      }
      toast.success(`Canal ${result.data.display_name} creado`);
      form.reset();
      setIsDefault(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="grid gap-4 md:grid-cols-3"
        noValidate
      >
        <FormField
          control={form.control}
          name="phone_e164"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Teléfono E.164</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  className="font-mono"
                  placeholder="+56912345678"
                  autoComplete="off"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="display_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Nombre visible</FormLabel>
              <FormControl>
                <Input {...field} placeholder="Auphere CL" autoComplete="off" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="country_code"
          render={({ field }) => (
            <FormItem>
              <FormLabel>País (opcional)</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  maxLength={2}
                  placeholder="CL"
                  className="font-mono uppercase"
                  autoComplete="off"
                />
              </FormControl>
              <FormDescription>ISO 3166 — 2 letras.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="provider"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Provider</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="ycloud">YCloud</SelectItem>
                  <SelectItem value="meta">Meta</SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="provider_phone_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Provider phone_id (opcional)</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  className="font-mono"
                  placeholder="YCloud number_id / Meta phone_number_id"
                  autoComplete="off"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="webhook_secret"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Webhook secret (opcional)</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="password"
                  className="font-mono"
                  placeholder="Per-channel HMAC"
                  autoComplete="off"
                />
              </FormControl>
              <FormDescription>
                Vacío = usa el shared secret del provider.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="md:col-span-3 flex items-center justify-between gap-3 border-t border-border pt-3">
          <div className="flex items-center gap-2">
            <Checkbox
              id="is-default"
              checked={isDefault}
              onCheckedChange={(v) => setIsDefault(v === true)}
            />
            <Label
              htmlFor="is-default"
              className="text-sm font-normal cursor-pointer"
            >
              Marcar como <strong>default</strong> del provider
            </Label>
          </div>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creando…" : "Crear canal"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
