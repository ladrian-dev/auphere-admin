/**
 * Bootstrap the first ``owner`` of a partner for the pilot (CP-33):
 *
 *   NEXUS_SEED_PARTNER_SLUG=facelad \
 *   NEXUS_SEED_OWNER_EMAIL=maria@facelad.com \
 *   NEXUS_SEED_OWNER_PASSWORD='…12+ chars…' \
 *   NEXUS_SEED_OWNER_NAME='María' \
 *   pnpm seed:owner
 *
 * Idempotent: creates the Better Auth user through the same code path the
 * login validates against, then inserts the membership row (Alembic
 * table ``public.partner_memberships``) if the user has none. Everyone
 * else joins by invitation from the console.
 */
import "dotenv/config";

import { eq } from "drizzle-orm";

import { auth } from "../src/lib/auth";
import { db, sql } from "../src/db/client";
import { user } from "../src/db/schema";

async function main() {
  const slug = process.env.NEXUS_SEED_PARTNER_SLUG;
  const email = process.env.NEXUS_SEED_OWNER_EMAIL?.toLowerCase();
  const password = process.env.NEXUS_SEED_OWNER_PASSWORD;
  const name = process.env.NEXUS_SEED_OWNER_NAME ?? "Owner";
  if (!slug || !email || !password) {
    console.error("set NEXUS_SEED_PARTNER_SLUG, NEXUS_SEED_OWNER_EMAIL, NEXUS_SEED_OWNER_PASSWORD");
    process.exit(1);
  }
  if (password.length < 12) {
    console.error("password must be at least 12 characters");
    process.exit(1);
  }
  const partner = (await sql<{ id: string; console_enabled: boolean }[]>`SELECT id::text, console_enabled FROM public.partners WHERE slug = ${slug}`)[0];
  if (!partner) {
    console.error(`partner ${slug} not found`);
    process.exit(1);
  }

  let [existing] = await db.select({ id: user.id }).from(user).where(eq(user.email, email)).limit(1);
  if (!existing) {
    const created = await auth.api.signUpEmail({ body: { email, password, name } });
    if (!created || !("user" in created)) {
      console.error("sign-up failed", created);
      process.exit(1);
    }
    existing = { id: created.user.id };
    console.log(`✓ created user ${email} (${existing.id})`);
  } else {
    console.log(`✓ user exists ${email} (${existing.id})`);
  }

  const [membership] = await sql<{ id: string; partner_id: string; role: string }[]>`
    SELECT id::text, partner_id::text, role FROM public.partner_memberships WHERE user_id = ${existing.id} LIMIT 1`;
  if (membership) {
    console.log(`✓ membership exists (${membership.role} of ${membership.partner_id})`);
  } else {
    await sql`
      INSERT INTO public.partner_memberships (partner_id, user_id, email, display_name, role, status, accepted_at)
      VALUES (${partner.id}::uuid, ${existing.id}, ${email}, ${name}, 'owner', 'active', now())`;
    console.log(`✓ ${email} is now owner of ${slug}`);
  }
  if (!partner.console_enabled) {
    console.log(`! partner ${slug} has console_enabled=false — enable it from the backoffice (or SQL) to let them in`);
  }
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .then(() => process.exit(0));
