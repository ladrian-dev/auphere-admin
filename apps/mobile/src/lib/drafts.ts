import { useCallback, useState } from "react";

/**
 * What the person typed and has not saved yet (spec 047, 50.5): without a
 * connection nothing is saved or queued, and what was typed stays until it
 * returns — also if the screen is left and opened again. In memory only, like
 * everything else of a business's customers on this phone (spec 031, D9): a
 * correction can carry a customer's words, and nothing of that goes to disk.
 * A successful save clears it; signing out ends the process's memory with it.
 */
const store = new Map<string, unknown>();

export function useDraft<T>(key: string): [T | null, (next: T | null) => void] {
  const [value, setValue] = useState<T | null>(() => (store.has(key) ? (store.get(key) as T) : null));
  const set = useCallback(
    (next: T | null) => {
      if (next === null) store.delete(key);
      else store.set(key, next);
      setValue(next);
    },
    [key],
  );
  return [value, set];
}

/** Forget every draft (sign-out). */
export function clearDrafts(): void {
  store.clear();
}

/** For tests: what is kept under a key. */
export function peekDraft(key: string): unknown {
  return store.get(key);
}
