"use client";

import { RouteError } from "@/components/error-boundary";

export default function ToolsError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="common.error.title" />;
}
