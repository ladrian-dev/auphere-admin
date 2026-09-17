"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { track } from "@/lib/analytics";
import { clearSession } from "@/lib/storage";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    track("error_shown", { step: "global" });
  }, []);
  return (
    <main className="mx-auto max-w-xl px-4 py-16">
      <Callout tone="warning" title="Algo ha fallado">
        Ha ocurrido un error inesperado. Puedes reintentar; si persiste, reinicia el diagnóstico.
      </Callout>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <Button variant="accent" onClick={reset}>
          Reintentar
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            clearSession();
            window.location.assign("/");
          }}
        >
          Reiniciar el diagnóstico
        </Button>
      </div>
    </main>
  );
}
