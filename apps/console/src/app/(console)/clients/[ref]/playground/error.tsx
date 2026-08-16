"use client";

import { RouteError } from "@/components/error-boundary";

export default function PlaygroundError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="playground.error" />;
}
