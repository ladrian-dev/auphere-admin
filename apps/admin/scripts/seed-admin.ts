/**
 * Bootstrap the first admin user for the operator panel.
 *
 * Run once after Drizzle migrations have provisioned the ``auth.*``
 * tables:
 *
 *     NEXUS_BOOTSTRAP_ADMIN_EMAIL=lee@auphere.com \
 *     NEXUS_BOOTSTRAP_ADMIN_PASSWORD='choose-a-good-one' \
 *     pnpm tsx scripts/seed-admin.ts
 *
 * The script is idempotent: if a user with the same email already
 * exists it just confirms and exits. Phase 2 replaces this with an
 * invitation flow.
 */

import "dotenv/config";

import { auth } from "@/lib/auth";
import { db } from "@/db/client";
import { user } from "@/db/schema";
import { eq } from "drizzle-orm";

async function main() {
  const email = process.env.NEXUS_BOOTSTRAP_ADMIN_EMAIL;
  const password = process.env.NEXUS_BOOTSTRAP_ADMIN_PASSWORD;
  const name = process.env.NEXUS_BOOTSTRAP_ADMIN_NAME ?? "Auphere Admin";

  if (!email || !password) {
    console.error(
      "Set NEXUS_BOOTSTRAP_ADMIN_EMAIL and NEXUS_BOOTSTRAP_ADMIN_PASSWORD",
    );
    process.exit(1);
  }
  if (password.length < 12) {
    console.error("Password must be at least 12 characters.");
    process.exit(1);
  }

  const existing = await db
    .select({ id: user.id })
    .from(user)
    .where(eq(user.email, email))
    .limit(1);

  if (existing[0]) {
    console.log(`✓ admin already exists: ${email} (id=${existing[0].id})`);
    return;
  }

  // Use Better Auth's sign-up endpoint so the password gets hashed
  // through the same code path the login flow validates against.
  const result = await auth.api.signUpEmail({
    body: { email, password, name },
  });

  if (!result || "error" in result) {
    console.error(`failed to create admin:`, result);
    process.exit(1);
  }
  console.log(`✓ created admin: ${email} (id=${result.user.id})`);
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .then(() => process.exit(0));
