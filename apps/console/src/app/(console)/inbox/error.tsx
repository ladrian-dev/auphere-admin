"use client";

import { RouteError } from "@/components/error-boundary";

export default function InboxError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} />;
}
