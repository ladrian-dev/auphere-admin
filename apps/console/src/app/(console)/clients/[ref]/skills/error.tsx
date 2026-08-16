"use client";

import { RouteError } from "@/components/error-boundary";

export default function SkillsError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} titleKey="common.error.title" />;
}
