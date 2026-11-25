"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { Button } from "@nexus/ui";

import { logoutAction } from "../login/actions";

/** Cierra la sesión y vuelve al login, como «Cerrar sesión» del menú. */
export function SignOutButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return (
    <Button
      type="button"
      disabled={pending}
      onClick={() =>
        startTransition(async () => {
          await logoutAction();
          router.replace("/login");
          router.refresh();
        })
      }
    >
      {pending ? "Cerrando sesión…" : "Cerrar sesión"}
    </Button>
  );
}
