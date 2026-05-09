/**
 * Better Auth handler — exposes ``/api/auth/*`` for sign-in, sign-out,
 * session retrieval, etc. Better Auth's ``toNextJsHandler`` maps the
 * internal router onto Next.js App Router conventions.
 */

import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";

export const { POST, GET } = toNextJsHandler(auth);
