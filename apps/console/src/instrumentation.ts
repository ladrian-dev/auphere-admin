import type { Instrumentation } from "next";

import { logRequestError } from "@/lib/request-error-log";

/**
 * Spec 056 (10.2): every error a request hits on the server leaves one JSON line,
 * `console.request_error`, with the digest the error page carries, the route,
 * its kind and the cause's code — never the message, headers or cookies
 * (`lib/request-error-log.ts`). If the cause of the Reservas failure shows up
 * here, it is fixed in the same branch.
 */
export function register(): void {}

export const onRequestError: Instrumentation.onRequestError = async (error, _request, context) => {
  logRequestError(error, context);
};
