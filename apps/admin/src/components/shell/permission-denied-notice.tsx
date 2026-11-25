"use client";

import { Alert, AlertAction, AlertDescription, Button } from "@nexus/ui";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

/** Must match `DENIED_PARAM` in `lib/session.ts` (server-only, so not imported). */
const DENIED_PARAM = "sin-permiso";

/**
 * Spec 079, criterio 2.2: when a Server Action is refused for lack of
 * permission, the guard sends the operator back to the same page with
 * `?sin-permiso=1`. This says so once — the action did nothing — and drops the
 * parameter without reloading, so a refresh or a shared link does not repeat it.
 *
 * It is an error state after an attempt, not an explanation of what the role
 * lacks: the controls themselves are hidden from spec 079's phase 1b on.
 */
export function PermissionDeniedNotice() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const denied = params.get(DENIED_PARAM) === "1";
  const [shown, setShown] = useState(denied);
  // A new refusal on the same page shows the notice again. Adjusted while
  // rendering, not in the effect (react.dev, "you might not need an effect").
  const [lastDenied, setLastDenied] = useState(denied);
  if (denied !== lastDenied) {
    setLastDenied(denied);
    if (denied) setShown(true);
  }

  useEffect(() => {
    if (!denied) return;
    const rest = new URLSearchParams(params.toString());
    rest.delete(DENIED_PARAM);
    const query = rest.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [denied, params, pathname, router]);

  if (!shown) return null;

  return (
    <Alert role="status" aria-live="polite">
      <AlertDescription>Tu rol no permite esa acción; no se hizo nada.</AlertDescription>
      <AlertAction>
        <Button variant="ghost" size="sm" onClick={() => setShown(false)}>
          Cerrar
        </Button>
      </AlertAction>
    </Alert>
  );
}
