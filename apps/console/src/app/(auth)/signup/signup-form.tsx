"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button, Form, FormControl, FormField, FormItem, FormLabel, FormMessage, Input } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import { signUpAction } from "@/lib/auth-actions";

type Values = { email: string };

/** Spec 067 (R3.4): reenviar espera esto, con la cuenta atrás a la vista. */
export const SIGNUP_RESEND_AFTER_S = 30;

/**
 * **El éxito es siempre el mismo, exista el correo o no** (Requisito 1.2).
 *
 * Esta pantalla no puede ser más amable con quien ya tiene cuenta, porque
 * serlo reabriría desde el navegador el oráculo que la API cierra: bastaría
 * comparar dos respuestas para saber qué direcciones están registradas. La
 * diferencia la ve quien abre el buzón, que es el dueño de la dirección.
 */
export function SignupForm({ google = null }: { google?: React.ReactNode }) {
  const t = useT();
  // El idioma del correo es el de quien lo va a leer, no un literal: la
  // página se veía en inglés y el asunto llegaba en español.
  const locale = useLocale();
  const [pending, startTransition] = React.useTransition();
  // Spec 067 (R3): la dirección tal como se escribió. No la confirma nadie: la
  // respuesta es la misma pueda registrarse o no (R1.2).
  const [sentTo, setSentTo] = React.useState<string | null>(null);
  const [left, setLeft] = React.useState(0);
  const [resending, setResending] = React.useState(false);
  const schema = React.useMemo(
    () => z.object({ email: z.string().email(t("validation.email")) }),
    [t],
  );
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "" } });

  React.useEffect(() => {
    if (sentTo === null || left <= 0) return;
    const id = window.setTimeout(() => setLeft((n) => n - 1), 1000);
    return () => window.clearTimeout(id);
  }, [sentTo, left]);

  function request(email: string, again: boolean) {
    setResending(again);
    startTransition(async () => {
      const result = await signUpAction({ email, locale });
      if (!result.ok) {
        // `disabled` no se enseña como error de formulario: la página no
        // debería existir si la bandera está apagada, así que llegar aquí es
        // una carrera y se trata como un fallo del sistema, no del usuario.
        toast.error(result.reason === "rate_limited" ? t("signup.tooMany") : t("common.error.backend"));
        return;
      }
      setSentTo(email);
      setLeft(SIGNUP_RESEND_AFTER_S);
      if (again) toast.success(t("signup.resent"));
    });
  }

  function submit(values: Values) {
    request(values.email.trim(), false);
  }

  if (sentTo !== null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        {/* Solo esto se anuncia: la cuenta atrás cambia cada segundo (R3.5). */}
        <div role="status" aria-live="polite" className="flex min-w-0 flex-col gap-3">
          <span className="grid size-11 place-items-center rounded-xl bg-primary/10 text-primary" aria-hidden="true">
            <MailCheck className="size-5" />
          </span>
          <h2 className="text-balance text-xl font-semibold">{t("signup.sent.title")}</h2>
          <p className="text-pretty text-muted-foreground" data-testid="signup-sent-body">
            {t("signup.sent.bodyTo", { email: sentTo })}
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <Button
            type="button"
            variant="outline"
            size="lg"
            disabled={(pending && resending) || left > 0}
            onClick={() => request(sentTo, true)}
          >
            {pending && resending
              ? t("forgot.submitting")
              : left > 0
                ? t("forgot.resendIn", { s: left })
                : t("forgot.resend")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              form.setValue("email", sentTo);
              setSentTo(null);
              setLeft(0);
            }}
          >
            {t("signup.sent.other")}
          </Button>
        </div>
        <p className="text-pretty text-sm text-muted-foreground">{t("forgot.sent.spam")}</p>
        <Link href="/login" className="text-sm underline underline-offset-4">
          {t("forgot.backToLogin")}
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {google}
      <Form {...form}>
        <form onSubmit={form.handleSubmit(submit)} noValidate className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem className="min-w-0">
                <FormLabel>{t("signup.workEmail")}</FormLabel>
                <FormControl>
                  <Input
                    type="email"
                    autoComplete="email"
                    inputMode="email"
                    autoFocus
                    placeholder={t("signup.workEmail.example")}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" size="lg" disabled={pending}>
            {pending ? t("forgot.submitting") : t("signup.submit")}
          </Button>
          {/* R2.4 */}
          <p className="text-sm text-muted-foreground">
            {t("signup.haveAccount")}{" "}
            <Link href="/login" className="font-medium text-foreground underline underline-offset-4">
              {t("signup.signIn")}
            </Link>
          </p>
        </form>
      </Form>
    </div>
  );
}
