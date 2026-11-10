"use client";

import { RouteError } from "@/components/error-boundary";

export default function ConnectionError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="common.error.title" />;
}
