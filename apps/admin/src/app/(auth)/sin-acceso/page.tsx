import { redirect } from "next/navigation";

import { BrandLockup, Eyebrow } from "@nexus/ui";
import { getOperator } from "@/lib/session";

import { SignOutButton } from "./sign-out-button";

export const metadata = { title: "Sin acceso" };

/**
 * Spec 078, requisito 2.2: adonde ``requireOperator()`` lleva a una cuenta
 * deshabilitada. Usa ``getOperator()`` y no ``requireOperator()``, que la
 * traería de vuelta aquí.
 */
export default async function NoAccessPage() {
  const operator = await getOperator();
  if (!operator) redirect("/login");
  if (operator.access === "ok") redirect("/tenants");

  return (
    <main className="min-h-screen grid place-items-center bg-background px-6">
      <div className="w-full max-w-md flex flex-col gap-10">
        <header className="flex flex-col gap-4">
          <BrandLockup />
          <div className="flex flex-col gap-2">
            <Eyebrow>Operador interno</Eyebrow>
            <h1 className="text-3xl font-semibold leading-tight tracking-tight text-balance">
              Tu cuenta ya no puede operar.
            </h1>
            <p className="text-muted-foreground text-base max-w-prose text-pretty">
              La sesión de {operator.email} sigue abierta, pero la cuenta está deshabilitada y el
              panel no hará nada en su nombre. Si crees que es un error, contacta a Lee.
            </p>
          </div>
        </header>

        <SignOutButton />
      </div>
    </main>
  );
}
