"use client";

import { RouteError } from "@/components/error-boundary";

/**
 * Spec 056 (10.1): the error boundary for what fails ABOVE every route group —
 * a console layout that could not load, for instance. Without it Next drew its
 * own page, in English and with its technical sentence. It renders inside the
 * root layout (the language is already resolved there) and outside the console
 * frame, so it never shows the error's message.
 */
export default function AppError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-lg flex-col justify-center px-4 py-12">
      <RouteError {...props} />
    </main>
  );
}
