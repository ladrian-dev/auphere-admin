"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
} from "@nexus/ui";

import { useT } from "@/i18n/client";
import { finishPasswordResetAction } from "@/lib/auth-actions";

type Values = { password: string };

/**
 * Tres estados, y los tres son verdad (§V):
 *
 * - **el formulario**, con el aviso de lo que va a pasar ANTES de que pase;
 * - **el enlace muerto**, que no dice de quién era ni si existió;
 * - **hecho**, que lleva a la entrada y no finge una sesión que no hay.
 *
 * **El aviso va arriba y antes de pulsar** (R3.6). Restablecer cierra todas las
 * sesiones y da de baja las máquinas; decirlo después convierte una decisión
 * correcta en una sorpresa, y quien recupera su contraseña porque sospecha que
 * alguien entró necesita saber justamente que eso es lo que está comprando.
 *
 * **No se abre sesión al terminar** (D-5): acabamos de cerrarlas todas. Que
 * entre ella con su contraseña nueva es la prueba de que el circuito funciona.
 */
export function ResetForm({ token }: { token: string }) {
  const t = useT();
  const [pending, startTransition] = React.useTransition();
  const [outcome, setOutcome] = React.useState<"form" | "done" | "dead">("form");
  const schema = React.useMemo(
    () => z.object({ password: z.string().min(12, t("validation.password12")) }),
    [t],
  );
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { password: "" } });

  function submit(values: Values) {
    startTransition(async () => {
      const result = await finishPasswordResetAction({ token, password: values.password });
      if (result.ok) {
        setOutcome("done");
        return;
      }
      if (result.reason === "dead_link") {
        setOutcome("dead");
        return;
      }
      // `invalid` es la política de contraseña, que el esquema ya enseña en el
      // campo; llegar aquí significa que el servidor fue más estricto.
      const message = result.reason === "invalid" ? t("validation.password12") : t("common.error.backend");
      toast.error(message);
      form.setError("password", { message });
    });
  }

  if (outcome === "dead") {
    return (
      <div className="flex min-w-0 flex-col gap-3" role="status" aria-live="polite">
        <h2 className="text-balance text-xl font-semibold">{t("reset.deadLink")}</h2>
        <p className="text-pretty text-muted-foreground">{t("reset.deadLink.body")}</p>
        <Link href="/forgot" className="text-sm underline underline-offset-4">
          {t("reset.askAnother")}
        </Link>
      </div>
    );
  }

  if (outcome === "done") {
    return (
      <div className="flex min-w-0 flex-col gap-3" role="status" aria-live="polite">
        <h2 className="text-balance text-xl font-semibold">{t("reset.done.title")}</h2>
        <p className="text-pretty text-muted-foreground">{t("reset.done.body")}</p>
        <Link href="/login" className="text-sm underline underline-offset-4">
          {t("forgot.backToLogin")}
        </Link>
      </div>
    );
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(submit)} noValidate className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
        <Alert>
          <AlertTitle>{t("reset.warning.title")}</AlertTitle>
          <AlertDescription>{t("reset.warning.body")}</AlertDescription>
        </Alert>
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem className="min-w-0">
              <FormLabel>{t("reset.password")}</FormLabel>
              <FormControl>
                <Input type="password" autoComplete="new-password" autoFocus {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" size="lg" disabled={pending}>
          {pending ? t("reset.submitting") : t("reset.submit")}
        </Button>
      </form>
    </Form>
  );
}
