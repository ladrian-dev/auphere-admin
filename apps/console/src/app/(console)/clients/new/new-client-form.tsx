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
} from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { Quota } from "@/lib/backend";

import { createClientAction } from "../actions";

type Values = { name: string; external_client_ref: string; timezone: string };

function slugify(s: string) {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

export function NewClientForm({ quota }: { quota: Quota }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [refTouched, setRefTouched] = React.useState(false);
  const schema = React.useMemo(
    () =>
      z.object({
        name: z.string().min(1, t("validation.required")).max(255, t("validation.tooLong")),
        external_client_ref: z
          .string()
          .min(1, t("validation.required"))
          .max(255, t("validation.tooLong"))
          .regex(/^[A-Za-z0-9._:-]+$/, t("validation.refFormat")),
        timezone: z.string().min(1, t("validation.required")).max(64, t("validation.tooLong")),
      }),
    [t],
  );
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      external_client_ref: "",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    },
  });
  const full = quota.remaining_clients === 0;

  function submit(values: Values) {
    startTransition(async () => {
      const res = await createClientAction(values);
      if (!res.ok) {
        toast.error(res.message);
        if (res.status === 409) form.setError("external_client_ref", { message: res.message });
        return;
      }
      toast.success(t("clients.create.done"));
      router.push(`/clients/${encodeURIComponent(res.data.external_client_ref)}`);
      router.refresh();
    });
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(submit)} noValidate className="flex max-w-lg flex-col gap-4" aria-busy={pending}>
        {full ? (
          <p role="alert" className="rounded-md border border-status-warning/40 bg-status-warning/10 px-4 py-3 text-sm">
            {t("clients.quota.full")}
          </p>
        ) : null}
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("common.name")}</FormLabel>
              <FormControl>
                <Input
                  autoComplete="organization"
                  {...field}
                  onChange={(e) => {
                    field.onChange(e);
                    if (!refTouched) form.setValue("external_client_ref", slugify(e.target.value));
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="external_client_ref"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("clients.ref")}</FormLabel>
              <FormControl>
                <Input
                  className="font-mono"
                  autoComplete="off"
                  spellCheck={false}
                  {...field}
                  onChange={(e) => {
                    setRefTouched(true);
                    field.onChange(e);
                  }}
                />
              </FormControl>
              <FormDescription>{t("clients.create.refHint")}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="timezone"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("clients.timezone")}</FormLabel>
              <FormControl>
                <Input className="font-mono" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={() => router.back()}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={pending || full}>
            {t("clients.create.submit")}
          </Button>
        </div>
      </form>
    </Form>
  );
}
