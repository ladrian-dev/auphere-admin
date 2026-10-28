"use client";

import { RouteError } from "@/components/error-boundary";

export default function NegocioError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="lite.business.error.load" />;
}
