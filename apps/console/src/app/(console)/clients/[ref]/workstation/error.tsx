"use client";

import { RouteError } from "@/components/error-boundary";

export default function WorkstationError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="workstation.error.title" />;
}
