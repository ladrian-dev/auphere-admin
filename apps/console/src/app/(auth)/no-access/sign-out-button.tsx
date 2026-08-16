"use client";

import { useRouter } from "next/navigation";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { signOutAction } from "@/lib/auth-actions";

export function SignOutButton() {
  const t = useT();
  const router = useRouter();
  return (
    <Button
      variant="ghost"
      onClick={async () => {
        await signOutAction();
        router.replace("/login");
        router.refresh();
      }}
    >
      {t("shell.signOut")}
    </Button>
  );
}
