"use client";

import { RouteError } from "@/components/error-boundary";

export default function ClientsError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="clients.error" />;
}
