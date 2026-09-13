"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button, Form, FormControl, FormField, FormItem, FormLabel, FormMessage, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { signUpAction } from "@/lib/auth-actions";

type Values = { email: string };

/**
 * **El éxito es siempre el mismo, exista el correo o no** (Requisito 1.2).
 *
 * Esta pantalla no puede ser más amable con quien ya tiene cuenta, porque
 * serlo reabriría desde el navegador el oráculo que la API cierra: bastaría
 * comparar dos respuestas para saber qué direcciones están registradas. La
 * diferencia la ve quien abre el buzón, que es el dueño de la dirección.
 */
export function SignupForm() {
  const t = useT();
  const [pending, startTransition] = React.useTransition();
  const [sent, setSent] = React.useState(false);
  const schema = React.useMemo(
    () => z.object({ email: z.string().email(t("validation.email")) }),
    [t],
  );
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "" } });

  function submit(values: Values) {
    startTransition(async () => {
      const result = await signUpAction({ email: values.email, locale: "es" });
      if (!result.ok) {
        // `disabled` no se enseña como error de formulario: la página no
        // debería existir si la bandera está apagada, así que llegar aquí es
        // una carrera y se trata como un fallo del sistema, no del usuario.
        toast.error(result.reason === "rate_limited" ? t("signup.tooMany") : t("common.error.backend"));
        return;
      }
      setSent(true);
    });
  }

  if (sent) {
    return (
      <div className="flex min-w-0 flex-col gap-3" role="status" aria-live="polite">
        <h2 className="text-balance text-xl font-semibold">{t("signup.sent.title")}</h2>
        <p className="text-pretty text-muted-foreground">{t("signup.sent.body")}</p>
        <Link href="/login" className="text-sm underline underline-offset-4">
          {t("signup.haveAccount")}
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
                <Input type="email" autoComplete="email" autoFocus {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={pending}>
          {t("signup.submit")}
        </Button>
        <Link href="/login" className="text-sm text-muted-foreground underline underline-offset-4">
          {t("signup.haveAccount")}
        </Link>
      </form>
    </Form>
  );
}
