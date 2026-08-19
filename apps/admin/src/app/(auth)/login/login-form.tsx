"use client";

import { useRouter } from "next/navigation";
import { useActionState, useEffect, useState } from "react";
import { useFormStatus } from "react-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { loginAction, type LoginState } from "./actions";

const INITIAL: LoginState = { error: null };

function SubmitButton() {
  // ``useFormStatus`` tiene que leerse DENTRO del <form>, por eso es un
  // componente aparte y no una variable del padre.
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="default" disabled={pending} className="w-full cursor-pointer">
      {pending ? "Iniciando sesión…" : "Entrar"}
    </Button>
  );
}

export function LoginForm({ redirectTo }: { redirectTo: string }) {
  const router = useRouter();
  const [state, formAction] = useActionState(loginAction, INITIAL);
  // El correo es CONTROLADO y la contraseña no, a propósito. Una acción de
  // servidor hace ``form.reset()`` al terminar, que vacía los campos no
  // controlados: dejar el correo así obligaría a reescribirlo en cada
  // intento fallido, justo lo que prohíbe la regla 6 del CLAUDE.md del
  // panel. La contraseña sí debe vaciarse — es un secreto y volver a
  // teclearla es lo que se espera tras un fallo.
  const [email, setEmail] = useState("");

  // La acción no redirige ella misma: si lo hiciera, ``useActionState`` no
  // podría devolver el error del intento fallido. El cliente navega cuando
  // la acción vuelve sin error, y refresca para que el layout vea la cookie.
  useEffect(() => {
    if (state === INITIAL) return;
    if (state.error === null) {
      router.replace(redirectTo);
      router.refresh();
    }
  }, [state, redirectTo, router]);

  return (
    <form action={formAction} className="flex flex-col gap-5" noValidate>
      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          inputMode="email"
          placeholder="contacto@auphere.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="password">Contraseña</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••••"
          required
        />
      </div>

      {state.error ? (
        <p role="alert" aria-live="polite" className="text-sm text-[color:var(--color-danger)]">
          {state.error}
        </p>
      ) : null}

      <SubmitButton />
    </form>
  );
}
