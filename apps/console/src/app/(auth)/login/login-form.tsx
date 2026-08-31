"use client";

import { zodResolver } from "@hookform/resolvers/zod";
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

type Values = { email: string; password: string };

export function LoginForm({ redirectTo }: { redirectTo: string }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [submitting, setSubmitting] = React.useState(false);
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
              <FormControl>
                <Input type="password" autoComplete="current-password" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" size="lg" disabled={busy}>
          {t("login.submit")}
        </Button>
        <p className="text-xs text-muted-foreground text-pretty">{t("login.forgot")}</p>
      </form>
    </Form>
  );
}
