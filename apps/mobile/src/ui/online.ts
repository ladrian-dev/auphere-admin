import { onlineManager } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

/** Whether the phone has network, as React Query sees it (R14.2). */
export function useOnline(): boolean {
  return useSyncExternalStore(
    (cb) => onlineManager.subscribe(cb),
    () => onlineManager.isOnline(),
  );
}
