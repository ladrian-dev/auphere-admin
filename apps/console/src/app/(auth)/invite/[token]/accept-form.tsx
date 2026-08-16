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

import { acceptInvitationAction } from "./actions";

type Values = { name: string; password: string };

/**
 * The e-mail is fixed by the invitation and shown read-only: it is not an
 * input, and it is not sent — the API reads it from the invitation row.
 */
export function AcceptForm({ token, email }: { token: string; email: string }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const schema = React.useMemo(
    () =>
      z.object({
        name: z.string().min(1, t("validation.required")).max(120, t("validation.tooLong")),
        password: z.string().min(12, t("validation.password12")),
      }),
    [t],
  );
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: "", password: "" } });

  function submit(values: Values) {
    startTransition(async () => {
      const result = await acceptInvitationAction({ token, name: values.name, password: values.password });
      if (!result.ok) {
        const msg =
          result.reason === "account_exists"
            ? t("invite.accountExists")
            : result.reason === "already_member"
              ? t("invite.alreadyMember")
              : result.reason === "not_found"
                ? t("invite.invalid")
                : result.reason === "rate_limited"
                  ? t("login.tooMany")
                  : result.message ?? t("common.error.backend");
        toast.error(msg);
        return;
      }
      router.replace("/");
      router.refresh();
    });
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(submit)} noValidate className="flex flex-col gap-4" aria-busy={pending}>
        <div className="grid gap-2">
          <Label htmlFor="invite-email">{t("login.email")}</Label>
          <Input id="invite-email" value={email} readOnly disabled />
        </div>
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("invite.name")}</FormLabel>
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
            <FormItem>
              <FormLabel>{t("invite.password")}</FormLabel>
              <FormControl>
                <Input type="password" autoComplete="new-password" {...field} />
              </FormControl>
              <FormDescription>{t("invite.signInHint")}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" size="lg" disabled={pending}>
          {t("invite.submit")}
        </Button>
      </form>
    </Form>
  );
}
