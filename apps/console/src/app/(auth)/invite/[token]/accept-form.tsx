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

export function AcceptForm({ token, email, alreadySignedInAs }: { token: string; email: string; alreadySignedInAs: string | null }) {
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
  const signedInMatches = alreadySignedInAs?.toLowerCase() === email.toLowerCase();

  function submit(values?: Values) {
    startTransition(async () => {
      const result = await acceptInvitationAction({ token, name: values?.name, password: values?.password });
      if (!result.ok) {
        const msg =
          result.reason === "email_mismatch"
            ? t("invite.emailMismatch")
            : result.reason === "already_member"
              ? t("invite.alreadyMember")
              : result.reason === "not_found"
                ? t("invite.invalid")
                : result.message ?? t("common.error.backend");
        toast.error(msg);
        return;
      }
      router.replace("/");
      router.refresh();
    });
  }

  if (signedInMatches) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm">
          <span className="font-mono">{email}</span>
        </p>
        <Button size="lg" onClick={() => submit()} disabled={pending}>
          {t("invite.submit")}
        </Button>
      </div>
    );
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit((v) => submit(v))} noValidate className="flex flex-col gap-4" aria-busy={pending}>
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
