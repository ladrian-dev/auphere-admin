"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import {
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
import { signInAction } from "@/lib/auth-actions";

import { rememberEmailForForgot } from "../forgot/handoff";

type Values = { email: string; password: string };

export function LoginForm({ redirectTo }: { redirectTo: string }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [submitting, setSubmitting] = React.useState(false);
  const [show, setShow] = React.useState(false);
  const passwordRef = React.useRef<HTMLInputElement | null>(null);
  const schema = React.useMemo(
    () =>
      z.object({
        email: z.string().email(t("validation.email")),
        password: z.string().min(1, t("login.passwordRequired")),
      }),
    [t],
  );
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  async function onSubmit(values: Values) {
    setSubmitting(true);
    const result = await signInAction({ email: values.email, password: values.password });
    setSubmitting(false);
    if (!result.ok) {
      // Never clear the form on error. "invalid" covers wrong password,
      // unknown e-mail and locked account — the API does not distinguish
      // them and neither does this copy.
      const message = result.reason === "rate_limited" ? t("login.tooMany") : t("login.invalid");
      toast.error(message);
      form.setError("password", { message });
      return;
    }
    startTransition(() => {
      router.replace(redirectTo);
      router.refresh();
    });
  }

  const busy = pending || submitting;
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4" aria-busy={busy}>
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("login.email")}</FormLabel>
              <FormControl>
                <Input type="email" autoComplete="email" inputMode="email" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("login.password")}</FormLabel>
              {/* Spec 066 (R4.1): mostrar/ocultar sin perder el foco ni el
                  cursor. El botón va fuera de `FormControl` para que el
                  `aria-describedby` del error siga en el campo. */}
              <div className="relative">
                <FormControl>
                  <Input
                    type={show ? "text" : "password"}
                    autoComplete="current-password"
                    className="pr-11"
                    {...field}
                    ref={(el) => {
                      field.ref(el);
                      passwordRef.current = el;
                    }}
                  />
                </FormControl>
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring"
                  aria-label={show ? t("auth.password.hide") : t("auth.password.show")}
                  aria-pressed={show}
                  onClick={() => {
                    setShow((v) => !v);
                    const el = passwordRef.current;
                    if (el) {
                      requestAnimationFrame(() => {
                        el.focus();
                        el.setSelectionRange(el.value.length, el.value.length);
                      });
                    }
                  }}
                >
                  {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                </button>
              </div>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" size="lg" disabled={busy}>
          {t("login.submit")}
        </Button>
        {/* Spec 011: la salida existe. Era una frase sin destino a dos
            centímetros del botón de Google, y luego una que decía honestamente
            que no había forma de restablecer; ahora la hay y es un enlace. */}
        {/* Spec 066 (R4.3): el correo ya escrito pasa a Recuperar la cuenta
            por `sessionStorage`, nunca por la URL. */}
        <Link
          href="/forgot"
          onClick={() => rememberEmailForForgot(form.getValues("email"))}
          className="text-sm text-muted-foreground underline underline-offset-4"
        >
          {t("login.forgot")}
        </Link>
      </form>
    </Form>
  );
}
