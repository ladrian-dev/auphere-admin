"use client";

import { RouteError } from "@/components/error-boundary";

export default function ReservasError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="reservas.error.title" />;
}
