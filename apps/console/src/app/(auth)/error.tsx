"use client";

import { RouteError } from "@/components/error-boundary";

/** Without this, a failure on the access pages fell through to Next's raw
 * error screen — the only group of the console with no boundary. */
export default function AuthError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} />;
}
