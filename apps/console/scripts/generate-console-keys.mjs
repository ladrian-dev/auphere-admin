#!/usr/bin/env node
/**
 * Generate the Ed25519 pair for the console ↔ API tokens (CP-03).
 *
 *   pnpm keys:generate
 *
 * Prints the PRIVATE key (for the console: NEXUS_CONSOLE_JWT_PRIVATE_KEY)
 * and the PUBLIC key (for the API: NEXUS_CONSOLE_JWT_PUBLIC_KEY). Store
 * them in the secret manager; never commit them.
 */
import { generateKeyPairSync } from "node:crypto";

const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const priv = privateKey.export({ type: "pkcs8", format: "pem" });
const pub = publicKey.export({ type: "spki", format: "pem" });

console.log("# apps/console (.env.local)");
console.log(`NEXUS_CONSOLE_JWT_PRIVATE_KEY="${String(priv).trim().replace(/\n/g, "\\n")}"`);
console.log();
console.log("# apps/api (.env)");
console.log(`NEXUS_CONSOLE_JWT_PUBLIC_KEY="${String(pub).trim().replace(/\n/g, "\\n")}"`);
console.log("NEXUS_CONSOLE_ENABLED=true");
