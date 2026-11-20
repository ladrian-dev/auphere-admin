"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BadgeCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import {
  Button,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
} from "@nexus/ui";

import { useT } from "@/i18n/client";
import { PasswordRule } from "@/components/auth/password-rule";
import { PasswordToggle } from "@/components/auth/password-toggle";
import { completeSignupAction } from "@/lib/auth-actions";

type Values = { company: string; name: string; password: string };

/**
 * El correo va fijo: **no es un campo y no se manda**. La API lo lee de la
 * solicitud, que es lo único que sabe a quién se verificó. Spec 067 (R4.2): se
 * enseña como texto legible con su icono, no como un campo gris deshabilitado.
 */
export function FinishForm({ token, email }: { token: string; email: string }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [show, setShow] = React.useState(false);
  const schema = React.useMemo(
    () =>
      z.object({
        company: z.string().min(1, t("validation.required")).max(255, t("validation.tooLong")),
        name: z.string().max(255, t("validation.tooLong")),
        password: z.string().min(12, t("validation.password12")),
      }),
    [t],
  );
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { company: "", name: "", password: "" },
  });
  // R4.3: la regla se marca mientras se escribe, antes de fallar.
  const password = useWatch({ control: form.control, name: "password" });

  function submit(values: Values) {
    startTransition(async () => {
      const result = await completeSignupAction({
        token,
        company_name: values.company,
        password: values.password,
        display_name: values.name || undefined,
      });
      if (!result.ok) {
        const msg =
          result.reason === "already_member"
            ? t("signup.alreadyMember")
            : result.reason === "not_found"
              ? t("signup.invalidLink")
              : t("common.error.backend");
        toast.error(msg);
        return;
      }
      router.replace("/");
      router.refresh();
    });
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(submit)} noValidate className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
        <div className="flex min-w-0 items-center gap-3 rounded-lg border bg-muted/40 px-3 py-2">
          <BadgeCheck className="size-5 shrink-0 text-primary" aria-hidden />
          <div className="flex min-w-0 flex-col">
            <span className="text-xs text-muted-foreground">{t("signup.verifiedEmail")}</span>
            <span className="truncate text-sm font-medium" data-testid="signup-email">
              {email}
            </span>
          </div>
        </div>
        <FormField
          control={form.control}
          name="company"
          render={({ field }) => (
            <FormItem className="min-w-0">
              <FormLabel>{t("signup.company")}</FormLabel>
              <FormControl>
                <Input autoFocus autoComplete="organization" {...field} />
              </FormControl>
              <FormDescription>{t("signup.company.help")}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem className="min-w-0">
              <FormLabel>{t("signup.yourName")}</FormLabel>
              <FormControl>
                <Input autoComplete="name" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem className="min-w-0">
              <FormLabel>{t("login.password")}</FormLabel>
              <div className="relative">
                <FormControl>
                  <Input type={show ? "text" : "password"} autoComplete="new-password" className="pr-11" {...field} />
                </FormControl>
                <PasswordToggle
                  shown={show}
                  onToggle={() => setShow((v) => !v)}
                  showLabel={t("auth.password.show")}
                  hideLabel={t("auth.password.hide")}
                />
              </div>
              <FormMessage />
            </FormItem>
          )}
        />
        <ul className="flex flex-col gap-2 text-sm" aria-live="polite" data-testid="signup-rules">
          <PasswordRule
            ok={password.length >= 12}
            label={t("reset.rule.length")}
            met={t("reset.rule.met")}
            unmet={t("reset.rule.unmet")}
          />
        </ul>
        <Button type="submit" size="lg" disabled={pending}>
          {t("signup.finish.submit")}
        </Button>
      </form>
    </Form>
  );
}
