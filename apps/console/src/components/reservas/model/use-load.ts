import { useEffect, useRef, useState } from "react";

import type { ActionResult } from "@/lib/actions";

export type Loaded<T> = { kind: "idle" } | { kind: "loading" } | { kind: "error" } | { kind: "ok"; data: T };

/**
 * A read through a Server Action, keyed by what it asks for (spec 043): a
 * new key is «loading» until its answer arrives, an answer for an old key is
 * dropped, and `null` asks nothing («idle»). No state is set synchronously in
 * an effect: «loading» is derived, not stored.
 *
 * `keepOk`: while a new key loads, keep showing the last good answer (a quiet
 * refresh after a change, without flashing a skeleton).
 */
export function useActionLoad<T>(
  key: string | null,
  load: () => Promise<ActionResult<T>>,
  opts: { delayMs?: number; keepOk?: boolean } = {},
): Loaded<T> {
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });
  const [result, setResult] = useState<{ key: string; value: Loaded<T> } | null>(null);
  const delayMs = opts.delayMs ?? 0;
  useEffect(() => {
    if (key === null) return;
    let live = true;
    const timer = window.setTimeout(() => {
      loadRef
        .current()
        .then((res) => {
          if (live) setResult({ key, value: res.ok ? { kind: "ok", data: res.data } : { kind: "error" } });
        })
        .catch(() => {
          if (live) setResult({ key, value: { kind: "error" } });
        });
    }, delayMs);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [key, delayMs]);
  if (key === null) return { kind: "idle" };
  if (result?.key === key) return result.value;
  if (opts.keepOk && result?.value.kind === "ok") return result.value;
  return { kind: "loading" };
}
