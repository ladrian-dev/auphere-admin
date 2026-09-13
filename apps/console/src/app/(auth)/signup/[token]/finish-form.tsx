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
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  Label,
} from "@nexus/ui";

import { useT } from "@/i18n/client";
import { completeSignupAction } from "@/lib/auth-actions";

type Values = { company: string; name: string; password: string };

/**
 * El correo va fijo y en solo lectura: **no es un campo y no se manda**. La
 * API lo lee de la solicitud, que es lo único que sabe a quién se verificó.
 */
export function FinishForm({ token, email }: { token: string; email: string }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
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
        <div className="grid min-w-0 gap-2">
          <Label htmlFor="signup-email">{t("login.email")}</Label>
          <Input id="signup-email" value={email} readOnly disabled />
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
              <FormControl>
                <Input type="password" autoComplete="new-password" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={pending}>
          {t("signup.finish.submit")}
        </Button>
      </form>
    </Form>
  );
}
