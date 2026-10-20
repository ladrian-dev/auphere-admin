import * as Crypto from "expo-crypto";

import { base64url, toBase64url } from "@/lib/base64url";

/**
 * PKCE S256 (RFC 7636) for the sign-in window (spec 031, R1, D2): a 43-char
 * verifier from 32 random bytes and its SHA-256 challenge, both base64url
 * without padding — the console accepts nothing else (`app-redirect.ts`).
 */
export type Pkce = { verifier: string; challenge: string; state: string };

export async function createPkce(): Promise<Pkce> {
  const verifier = base64url(Crypto.getRandomBytes(32));
  const digest = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier, {
    encoding: Crypto.CryptoEncoding.BASE64,
  });
  return { verifier, challenge: toBase64url(digest), state: base64url(Crypto.getRandomBytes(16)) };
}
