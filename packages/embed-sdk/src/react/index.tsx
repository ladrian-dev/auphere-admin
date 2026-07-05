/**
 * React bindings for `@auphere/embed` (optional peer dependency).
 *
 * ```tsx
 * import { AuphereBroadcastButton } from "@auphere/embed/react";
 *
 * <AuphereBroadcastButton auphere={auphere} recipients={recipients}>
 *   Campañas WhatsApp
 * </AuphereBroadcastButton>
 * ```
 */

import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from "react";

import type { Auphere, BroadcastRecipient, ConnectionStatus, OpenBroadcastOptions } from "../types";

/** Live connection status for gating your own UI. */
export function useAuphereStatus(auphere: Auphere): ConnectionStatus {
  const [status, setStatus] = useState<ConnectionStatus>(() => auphere.getStatus());
  useEffect(() => {
    setStatus(auphere.getStatus());
    const unsubscribe = auphere.onStatusChange(setStatus);
    if (auphere.getStatus() === "unknown") {
      void auphere.refreshStatus().catch(() => {
        /* stays "unknown" — button stays hidden */
      });
    }
    return unsubscribe;
  }, [auphere]);
  return status;
}

export interface AuphereBroadcastButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> {
  auphere: Auphere;
  /** The audience, from YOUR data (CRM, table selection…). */
  recipients: BroadcastRecipient[];
  onDone?: OpenBroadcastOptions["onDone"];
  onExit?: OpenBroadcastOptions["onExit"];
  children?: ReactNode;
}

/**
 * Renders its children as a button ONLY while the client's WhatsApp is
 * connected — the gating decision of ADR-028. Style it like any button
 * (className/style pass through).
 */
export function AuphereBroadcastButton({
  auphere,
  recipients,
  onDone,
  onExit,
  children,
  ...buttonProps
}: AuphereBroadcastButtonProps) {
  const status = useAuphereStatus(auphere);
  const [opening, setOpening] = useState(false);

  if (status !== "connected") return null;

  return (
    <button
      type="button"
      {...buttonProps}
      disabled={opening || buttonProps.disabled}
      onClick={() => {
        setOpening(true);
        void auphere
          .openBroadcast({ recipients, onDone, onExit })
          .finally(() => setOpening(false));
      }}
    >
      {children ?? "Campañas WhatsApp"}
    </button>
  );
}

export type { Auphere, BroadcastRecipient, ConnectionStatus };
