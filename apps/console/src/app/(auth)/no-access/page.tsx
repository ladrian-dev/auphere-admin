import { redirect } from "next/navigation";

import { Button, EmptyState } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { resolvePrincipal } from "@/lib/principal";

import { SignOutButton } from "./sign-out-button";

export const metadata = { title: "Sin acceso" };

export default async function NoAccessPage() {
  const res = await resolvePrincipal();
  if (res.kind === "ok") redirect("/");
  if (res.kind === "anonymous") redirect("/login");
  const { t } = await getT();
  const disabled = res.kind === "disabled";
  return (
    <EmptyState
      title={t("noAccess.title")}
      description={
        <>
          {disabled ? t("noAccess.disabled") : t("noAccess.body")}
          <br />
          <span className="font-mono text-xs">{res.email}</span>
        </>
      }
      action={
        <div className="flex gap-2">
          <SignOutButton />
          <Button variant="outline" nativeButton={false} render={<a href="/login" />}>
            {t("login.submit")}
          </Button>
        </div>
      }
    />
  );
}
