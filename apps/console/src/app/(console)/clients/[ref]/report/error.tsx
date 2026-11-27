"use client";

import { RouteError } from "@/components/error-boundary";

export default function ClientReportError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="report.error" />;
}
