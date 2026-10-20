import { requirePartnerModule } from "@/lib/principal";

/**
 * Spec 032: this section exists for a partner only if Auphere switched its
 * module on. Without it the partner lands on its first module — no screen
 * that explains what it does not have (§V). Client users pass: their own
 * pages gate them.
 */
export default async function Layout({ children }: { children: React.ReactNode }) {
  await requirePartnerModule("keys");
  return <>{children}</>;
}
