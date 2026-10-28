"use client";

import { RouteError } from "@/components/error-boundary";

export default function AgentesError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="lite.agents.error.load" />;
}
