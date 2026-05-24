"use client";

import { useState, useTransition } from "react";
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
import type { AuphereOwnerChannelOut, OwnerPhoneIndexOut } from "@/lib/backend";

import type { registerOwnerAction } from "./actions";

// Mirror of the backend regex (apps/api/.../schemas/auphere_channels.py).
const E164_RE = /^\+[1-9]\d{1,14}$/;

const schema = z.object({
  phone_e164: z
    .string()
    .regex(E164_RE, "E.164 obligatorio (ej. +56912345678)"),
  user_label: z.string().max(120).optional().or(z.literal("")),
  auphere_channel_id: z.string().uuid().optional().or(z.literal("")),
});

type FormValues = z.infer<typeof schema>;

type Action = typeof registerOwnerAction;

const _SENTINEL_DEFAULT = "__default__";

export function RegisterOwnerForm({
  tenantId,
  channels,
  registerAction,
}: {
  tenantId: string;
  channels: AuphereOwnerChannelOut[];
  registerAction: Action;
}) {
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      phone_e164: "",
      user_label: "",
      auphere_channel_id: "",
    },
  });

  async function onSubmit(values: FormValues) {
    setSubmitting(true);
    try {
      const channelId =
        values.auphere_channel_id && values.auphere_channel_id !== _SENTINEL_DEFAULT
          ? values.auphere_channel_id
          : null;
      const result = await registerAction(tenantId, {
        phone_e164: values.phone_e164,
        user_label: values.user_label || null,
        auphere_channel_id: channelId,
      });
      if (!result.ok) {
        toast.error("No se pudo registrar", { description: result.error });
        return;
      }
      const row: OwnerPhoneIndexOut = result.data;
      toast.success(`Registrado ${row.phone_e164}`, {
        description: row.user_label
          ? `Etiqueta: ${row.user_label}`
          : "Sin etiqueta",
      });
      form.reset();
      startTransition(() => {
        // Reset triggers nothing else — the page revalidates via the
        // server action's revalidatePath; the table refreshes
        // automatically on the next render.
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="grid gap-4 md:grid-cols-[1fr_1fr_1.5fr_auto] md:items-end"
        noValidate
      >
        <FormField
          control={form.control}
          name="phone_e164"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Teléfono</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  placeholder="+56912345678"
                  className="font-mono"
                  autoComplete="off"
                />
              </FormControl>
              <FormDescription>Formato E.164.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="user_label"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Etiqueta (opcional)</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  placeholder="Luis (dueño)"
                  autoComplete="off"
                />
              </FormControl>
              <FormDescription>Solo visible en este panel.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="auphere_channel_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Canal Auphere</FormLabel>
              <Select
                value={field.value || _SENTINEL_DEFAULT}
                onValueChange={(v) =>
                  field.onChange(!v || v === _SENTINEL_DEFAULT ? "" : v)
                }
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Provider default" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value={_SENTINEL_DEFAULT}>
                    Default del provider
                  </SelectItem>
                  {channels.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.display_name} · {c.phone_e164}
                      {c.is_default ? " ★" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                Pin opcional. Vacío = fallback al default.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={submitting || pending}>
          {submitting ? "Registrando…" : "Registrar"}
        </Button>
      </form>
    </Form>
  );
}
