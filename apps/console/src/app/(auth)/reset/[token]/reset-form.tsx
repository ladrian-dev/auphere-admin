"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Check, Circle, Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { useForm, useWatch } from "react-hook-form";
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

type Values = { password: string; confirm: string };

/** La política del servidor (spec 011). Las reglas de la pantalla no prometen otra. */
export const MIN_PASSWORD = 12;

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
  const [show, setShow] = React.useState(false);
  const schema = React.useMemo(
    () =>
      z
        .object({
          password: z.string().min(MIN_PASSWORD, t("validation.password12")),
          confirm: z.string(),
        })
        .refine((v) => v.password === v.confirm, { path: ["confirm"], message: t("reset.mismatch") }),
    [t],
  );
  // `shouldFocusError` (por defecto) lleva el foco al primer campo que falla (R5.3).
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { password: "", confirm: "" } });
  const password = useWatch({ control: form.control, name: "password" });
  const confirm = useWatch({ control: form.control, name: "confirm" });
  // Spec 066 (R5.2): las reglas se marcan mientras se escribe, antes de fallar.
  const rules = [
    { key: "length", ok: password.length >= MIN_PASSWORD, label: t("reset.rule.length") },
    { key: "match", ok: confirm.length > 0 && password === confirm, label: t("reset.rule.match") },
  ];

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
              <div className="relative">
                <FormControl>
                  <Input
                    type={show ? "text" : "password"}
                    autoComplete="new-password"
                    autoFocus
                    className="pr-11"
                    {...field}
                  />
                </FormControl>
                {/* R5.1: un solo botón para los dos campos. */}
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring"
                  aria-label={show ? t("auth.passwords.hide") : t("auth.passwords.show")}
                  aria-pressed={show}
                  onClick={() => setShow((v) => !v)}
                >
                  {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                </button>
              </div>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="confirm"
          render={({ field }) => (
            <FormItem className="min-w-0">
              <FormLabel>{t("reset.confirm")}</FormLabel>
              <FormControl>
                <Input type={show ? "text" : "password"} autoComplete="new-password" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        {/* Icono y texto, nunca solo color; se anuncia sin interrumpir (R5.2). */}
        <ul className="flex flex-col gap-2 text-sm" aria-live="polite" data-testid="reset-rules">
          {rules.map((r) => (
            <li
              key={r.key}
              data-ok={r.ok ? "" : undefined}
              className={r.ok ? "flex items-center gap-2 text-foreground" : "flex items-center gap-2 text-muted-foreground"}
            >
              {r.ok ? (
                <Check className="size-4 shrink-0 text-primary" aria-hidden />
              ) : (
                <Circle className="size-4 shrink-0" aria-hidden />
              )}
              <span>
                {r.label}
                <span className="sr-only">: {r.ok ? t("reset.rule.met") : t("reset.rule.unmet")}</span>
              </span>
            </li>
          ))}
        </ul>
        <Button type="submit" size="lg" disabled={pending}>
          {pending ? t("reset.submitting") : t("reset.submit")}
        </Button>
      </form>
    </Form>
  );
}
