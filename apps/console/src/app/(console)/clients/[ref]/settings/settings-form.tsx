"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button, Form, FormControl, FormField, FormItem, FormLabel, FormMessage, Input } from "@nexus/ui";

import { updateClientAction } from "@/app/(console)/clients/actions";
import { useT } from "@/i18n/client";

type Values = { name: string; timezone: string };

export function SettingsForm({ refId, name, timezone }: { refId: string; name: string; timezone: string }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const schema = React.useMemo(
    () =>
      z.object({
        name: z.string().min(1, t("validation.required")).max(255, t("validation.tooLong")),
        timezone: z.string().min(1, t("validation.required")).max(64, t("validation.tooLong")),
      }),
    [t],
  );
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name, timezone } });
  return (
    <Form {...form}>
      <form
        noValidate
        aria-busy={pending}
        className="flex flex-col gap-4"
        onSubmit={form.handleSubmit((values) =>
          startTransition(async () => {
            const res = await updateClientAction({ ref: refId, ...values });
            if (!res.ok) return void toast.error(res.message);
            toast.success(t("clients.settings.saved"));
            router.refresh();
          }),
        )}
      >
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("common.name")}</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
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
        <div>
          <Button type="submit" disabled={pending || !form.formState.isDirty}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </Form>
  );
}
