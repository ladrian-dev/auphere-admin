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

import { takeEmailForForgot } from "./handoff";

type Values = { email: string };

/** Spec 066 (R4.4): pedir otro enlace espera esto, con la cuenta atrás a la vista. */
export const RESEND_AFTER_S = 30;

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
  // Spec 066 (R4.4): la dirección a la que se pidió, tal como se escribió. No
  // es una dirección confirmada por nadie: la respuesta es la misma exista o no.
  const [sentTo, setSentTo] = React.useState<string | null>(null);
  const [left, setLeft] = React.useState(0);
  // El botón de «Reenviar» solo dice «Mandando…» cuando lo que se manda es el reenvío.
  const [resending, setResending] = React.useState(false);
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

  // Spec 066 (R4.3): el correo que ya se escribió en Entrar.
  React.useEffect(() => {
    const email = takeEmailForForgot();
    if (email) form.setValue("email", email);
  }, [form]);

  // La cuenta atrás de «Reenviar» (R4.4).
  React.useEffect(() => {
    if (sentTo === null || left <= 0) return;
    const id = window.setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(id);
  }, [sentTo, left]);

  function request(email: string, again: boolean) {
    setResending(again);
    startTransition(async () => {
      const result = await requestPasswordResetAction({ email });
      if (!result.ok) {
        setFailed(true);
        toast.error(t("common.error.backend"));
        return;
      }
      setFailed(false);
      setSentTo(email);
      setLeft(RESEND_AFTER_S);
      // R4.5: lo mismo exista o no la cuenta. Dice lo que se hizo, no lo que pasó.
      if (again) toast.success(t("forgot.resent"));
    });
  }

  function submit(values: Values) {
    request(values.email.trim(), false);
  }

  if (sentTo !== null) {
    // §V — la ausencia se diseña. Mientras el enlace no llega, la pantalla no
    // finge que ya está: dice qué mirar, en cuánto tiempo, y qué hacer si no
    // llega. Un «listo» a secas deja a la persona mirando una bandeja vacía
    // sin saber si esperar o volver a intentarlo.
    return (
      <div className="flex min-w-0 flex-col gap-3">
        {/* Solo esto se anuncia: la cuenta atrás del botón cambia cada segundo
            y no puede ir dentro de una región viva. */}
        <div role="status" aria-live="polite" className="flex min-w-0 flex-col gap-3">
        <h2 className="text-balance text-xl font-semibold">{t("forgot.sent.title")}</h2>
        <p className="text-pretty text-muted-foreground" data-testid="forgot-sent-body">
          {t("forgot.sent.bodyTo", { email: sentTo })}{" "}
          <button
            type="button"
            className="font-medium text-foreground underline underline-offset-4"
            aria-label={t("forgot.sent.changeLabel")}
            onClick={() => {
              form.setValue("email", sentTo);
              setSentTo(null);
              setLeft(0);
            }}
          >
            {t("forgot.sent.change")}
          </button>
        </p>
        </div>
        <p className="text-pretty text-sm text-muted-foreground">{t("forgot.sent.spam")}</p>
        {failed ? (
          <p role="alert" className="text-pretty text-sm text-destructive">
            {t("common.error.backend")}
          </p>
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="lg"
          disabled={(pending && resending) || left > 0}
          onClick={() => request(sentTo, true)}
        >
          {pending && resending ? t("forgot.submitting") : left > 0 ? t("forgot.resendIn", { s: left }) : t("forgot.resend")}
        </Button>
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
