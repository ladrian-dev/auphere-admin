"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";

import { makeQueryClient } from "@/lib/query";

/** One query cache per tab (spec 082), around both console frames. */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(makeQueryClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
