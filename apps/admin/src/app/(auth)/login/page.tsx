import { redirect } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import { Wordmark } from "@/components/brand/wordmark";
import { getSession } from "@/lib/session";

import { LoginForm } from "./login-form";

export const metadata = { title: "Iniciar sesión · Nexus" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string }>;
}) {
  const session = await getSession();
  if (session) redirect("/tenants");
  const { from } = await searchParams;

  return (
    <main className="min-h-screen grid place-items-center bg-[color:var(--color-bg)] px-6">
      <div className="w-full max-w-md flex flex-col gap-10">
        <header className="flex flex-col gap-4">
          <Wordmark variant="compact" />
          <div className="flex flex-col gap-2">
            <Eyebrow>Operador interno</Eyebrow>
            <h1
              className="text-3xl font-semibold leading-tight"
              style={{ letterSpacing: "var(--tracking-tight)" }}
            >
              Inicia sesión.
            </h1>
            <p className="text-muted-foreground text-base max-w-prose">
              Acceso restringido al equipo de Auphere. Si tu cuenta no funciona, contacta a Lee.
            </p>
          </div>
        </header>

        <LoginForm redirectTo={from && from.startsWith("/") ? from : "/tenants"} />

        <footer className="flex items-center justify-between text-xs font-mono text-muted-foreground uppercase"
          style={{ letterSpacing: "var(--tracking-eyebrow)" }}
        >
          <span>Nexus · Auphere</span>
          <span aria-hidden="true">v0.1</span>
        </footer>
      </div>
    </main>
  );
}
