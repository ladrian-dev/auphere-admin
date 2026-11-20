"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button, Form, FormControl, FormField, FormItem, FormLabel, FormMessage, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { requestPasswordResetAction } from "@/lib/auth-actions";

type Values = { email: string };

/**
 * **El éxito es siempre el mismo, tenga cuenta la dirección o no** (R1.3).
 *
 * Y también cuando el envío se cae, y también pasado el tope. Esta pantalla no
 * puede ser más amable con quien sí tiene cuenta, porque serlo reabriría desde
 * el navegador el oráculo que la API cierra: bastaría comparar dos respuestas
 * para saber qué direcciones están registradas. Es la única ruta del producto
 * que acepta la dirección de cualquiera.
 *
 * El único error que se enseña es el de no poder hablar con el servidor, que no
 * depende de la dirección y le pasa igual a todas.
 */
export function ForgotForm() {
  const t = useT();
  const [pending, startTransition] = React.useTransition();
  const [sent, setSent] = React.useState(false);
  // El fallo se dice **en la página**, no solo en un aviso flotante que se va
  // solo. Un `toast` desaparece y no vuelve; quien está intentando recuperar su
  // cuenta necesita poder releer qué ha pasado. No va en el campo del correo a
  // propósito: marcar ese campo insinuaría que la dirección es el problema, y
  // aquí la dirección nunca lo es.
  const [failed, setFailed] = React.useState(false);
  const schema = React.useMemo(
    () => z.object({ email: z.string().email(t("validation.email")) }),
    [t],
  );
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "" } });

  function submit(values: Values) {
    startTransition(async () => {
      const result = await requestPasswordResetAction({ email: values.email });
      if (!result.ok) {
        setFailed(true);
        toast.error(t("common.error.backend"));
        return;
      }
      setFailed(false);
      setSent(true);
    });
  }

  if (sent) {
    // §V — la ausencia se diseña. Mientras el enlace no llega, la pantalla no
    // finge que ya está: dice qué mirar, en cuánto tiempo, y qué hacer si no
    // llega. Un «listo» a secas deja a la persona mirando una bandeja vacía
    // sin saber si esperar o volver a intentarlo.
    return (
      <div className="flex min-w-0 flex-col gap-3" role="status" aria-live="polite">
        <h2 className="text-balance text-xl font-semibold">{t("forgot.sent.title")}</h2>
        <p className="text-pretty text-muted-foreground">{t("forgot.sent.body")}</p>
        <p className="text-pretty text-sm text-muted-foreground">{t("forgot.sent.late")}</p>
        <Link href="/login" className="text-sm underline underline-offset-4">
          {t("forgot.backToLogin")}
        </Link>
      </div>
    );
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(submit)} noValidate className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem className="min-w-0">
              <FormLabel>{t("login.email")}</FormLabel>
              <FormControl>
                <Input type="email" autoComplete="email" inputMode="email" autoFocus {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        {failed ? (
          <p role="alert" className="text-pretty text-sm text-destructive">
            {t("common.error.backend")}
          </p>
        ) : null}
        <Button type="submit" size="lg" disabled={pending}>
          {pending ? t("forgot.submitting") : t("forgot.submit")}
        </Button>
        <Link href="/login" className="text-sm text-muted-foreground underline underline-offset-4">
          {t("forgot.backToLogin")}
        </Link>
      </form>
    </Form>
  );
}
