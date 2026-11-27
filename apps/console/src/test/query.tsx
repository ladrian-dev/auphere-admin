import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";

/**
 * Spec 082: a fresh query cache per test, so one test never sees another's
 * reads. No retries and no garbage-collection timer left running.
 */
export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity, staleTime: 15_000 }, mutations: { retry: false } },
  });
}

export function withQuery(ui: React.ReactNode, client: QueryClient = testQueryClient()): React.ReactElement {
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

/** A `wrapper` for `render(…, { wrapper })`. */
export function queryWrapper(client: QueryClient = testQueryClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}
