import "server-only";

import { SignJWT, importPKCS8, type CryptoKey } from "jose";

import { env } from "./env";

/**
 * Console → API tokens (CP-03). One token per backend call:
 *
 *   {iss, aud, sub: user_id, partner_id, role, jti, iat, exp = iat + 60}
 *
 * EdDSA (Ed25519), private key only here; the API verifies with the public
 * key, re-checks the membership in the DB and refuses a reused ``jti``.
 * Service tokens (``svc: "console"``, no partner) are for the two
 * pre-membership invitation calls.
 */
export const TOKEN_TTL_SECONDS = 60;

let keyPromise: Promise<CryptoKey> | null = null;

function signingKey() {
  keyPromise ??= importPKCS8(env().NEXUS_CONSOLE_JWT_PRIVATE_KEY, "EdDSA");
  return keyPromise;
}

type PrincipalClaims = { userId: string; partnerId: string; role: string };

async function sign(extra: Record<string, unknown>, sub: string): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT(extra)
    .setProtectedHeader({ alg: "EdDSA", typ: "JWT" })
    .setIssuer(env().NEXUS_CONSOLE_JWT_ISSUER)
    .setAudience(env().NEXUS_CONSOLE_JWT_AUDIENCE)
    .setSubject(sub)
    .setJti(crypto.randomUUID().replace(/-/g, ""))
    .setIssuedAt(now)
    .setExpirationTime(now + TOKEN_TTL_SECONDS)
    .sign(await signingKey());
}

export function mintPrincipalToken(claims: PrincipalClaims): Promise<string> {
  return sign({ partner_id: claims.partnerId, role: claims.role }, claims.userId);
}

export function mintServiceToken(): Promise<string> {
  return sign({ svc: "console" }, "console-bff");
}
