"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Copy, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  cn,
} from "@nexus/ui";

import { inviteAction } from "@/app/(console)/team/actions";
import { inviteConflictMessage } from "@/components/team/invite-conflict";
import { useT } from "@/i18n/client";
import { roleKey } from "@/i18n/messages";
import type { InvitationCreated } from "@/lib/backend";

const ROLES = ["owner", "admin", "builder", "analyst", "billing"] as const;
type Values = { email: string; role: (typeof ROLES)[number] };

export function InviteButton({ origin }: { origin: string }) {
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [created, setCreated] = React.useState<InvitationCreated | null>(null);
  const [pending, startTransition] = React.useTransition();
  const schema = React.useMemo(() => z.object({ email: z.string().email(t("validation.email")), role: z.enum(ROLES) }), [t]);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", role: "builder" } });

  function submit(values: Values) {
    startTransition(async () => {
      const res = await inviteAction(values);
      if (!res.ok) {
        const message = inviteConflictMessage(res.status, res.message, t("team.invite.alreadyMember"));
        form.setError("email", { message });
        toast.error(message);
        return;
      }
      setCreated(res.data);
      toast.success(t("team.invite.sent"));
      router.refresh();
    });
  }

  const link = created ? `${origin}${created.accept_path}` : "";
  return (
    <>
      <Button
        onClick={() => {
          setCreated(null);
          form.reset();
          setOpen(true);
        }}
      >
        <UserPlus aria-hidden="true" />
        {t("team.invite")}
      </Button>
      <Dialog open={open} onOpenChange={(o) => setOpen(o)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("team.invite.title")}</DialogTitle>
            <DialogDescription>{t("team.invite.body")}</DialogDescription>
          </DialogHeader>
          {created ? (
            <div className="flex flex-col gap-3">
              <p className="text-sm">{created.email_sent ? t("team.invite.emailSent", { email: created.email }) : t("team.invite.emailNotSent")}</p>
              <p className="text-sm text-muted-foreground">{t("team.invite.link")}</p>
              <div className="flex gap-2">
                <Input readOnly value={link} className="font-mono text-xs" aria-label={t("team.invite.link")} />
                <Button
                  variant="outline"
                  size="icon"
                  aria-label={t("common.copy")}
                  onClick={async () => {
                    await navigator.clipboard.writeText(link);
                    toast.success(t("common.copied"));
                  }}
                >
                  <Copy />
                </Button>
              </div>
              <DialogFooter>
                <Button onClick={() => setOpen(false)}>{t("common.close")}</Button>
              </DialogFooter>
            </div>
          ) : (
            <Form {...form}>
              <form onSubmit={form.handleSubmit(submit)} noValidate className="flex flex-col gap-4" aria-busy={pending}>
                <FormField
                  control={form.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("common.email")}</FormLabel>
                      <FormControl>
                        <Input type="email" autoComplete="off" placeholder={t("proto.team.email.placeholder")} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                {/* Spec 047 (prototipo): el rol en opciones con su descripción, no en un desplegable. */}
                <FormField
                  control={form.control}
                  name="role"
                  render={({ field }) => (
                    <fieldset className="grid gap-2">
                      <legend className="mb-2 text-sm font-medium">{t("common.role")}</legend>
                      {ROLES.map((r) => (
                        <label
                          key={r}
                          className={cn(
                            "flex cursor-pointer items-start gap-3 rounded-md border border-input p-3 text-sm",
                            field.value === r && "border-primary ring-1 ring-primary",
                          )}
                        >
                          <input
                            type="radio"
                            name={field.name}
                            value={r}
                            checked={field.value === r}
                            onChange={() => field.onChange(r)}
                            onBlur={field.onBlur}
                            className="mt-1 size-4 shrink-0 accent-primary"
                          />
                          <span className="flex min-w-0 flex-col">
                            <span className="font-medium">{t(roleKey(r))}</span>
                            <span className="text-pretty text-muted-foreground">{t(`role.${r}.desc` as "role.owner.desc")}</span>
                          </span>
                        </label>
                      ))}
                    </fieldset>
                  )}
                />
                <DialogFooter>
                  <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                    {t("common.cancel")}
                  </Button>
                  <Button type="submit" disabled={pending}>
                    {t("team.invite")}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
