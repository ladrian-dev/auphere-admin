"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";

import { inviteAction } from "./actions";

const schema = z.object({
  email: z.string().trim().min(1, "Obligatorio").email("Correo inválido").max(255),
  name: z.string().trim().max(255).optional(),
});
type Values = z.infer<typeof schema>;

/**
 * Spec 030 (R1.4): invite a person of the client. The link goes by e-mail and
 * is also shown once here, so the operator can pass it on by hand if the
 * e-mail does not arrive.
 */
export function InviteForm({ tenantId, disabled }: { tenantId: string; disabled: boolean }) {
  const router = useRouter();
  const [link, setLink] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", name: "" } });

  async function onSubmit(values: Values) {
    const res = await inviteAction(tenantId, { email: values.email, name: values.name || null });
    if (!res.ok) {
      toast.error("No se pudo invitar", { description: res.error });
      return;
    }
    setLink(res.data.accept_path);
    toast.success(res.data.email_sent ? `Invitación enviada a ${res.data.email}` : "Invitación creada (el correo no salió)");
    form.reset();
    router.refresh();
  }

  if (disabled) {
    return <p className="text-sm text-muted-foreground">Enciende el acceso para poder invitar a sus personas.</p>;
  }

  return (
    <div className="grid gap-3">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end" noValidate>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Correo</FormLabel>
                <FormControl>
                  <Input {...field} type="email" autoComplete="off" placeholder="persona@negocio.com" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Nombre (opcional)</FormLabel>
                <FormControl>
                  <Input {...field} autoComplete="off" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Invitando…" : "Invitar"}
          </Button>
        </form>
      </Form>
      {link ? (
        <p className="text-xs text-muted-foreground">
          Enlace de la invitación, por si el correo no llega: <code className="break-all">{link}</code>
        </p>
      ) : null}
    </div>
  );
}
