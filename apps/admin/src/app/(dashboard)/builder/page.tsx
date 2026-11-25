import { redirect } from "next/navigation";
import { requireOperator } from "@/lib/session";

/** Spec 047: Constructor opens on its first view. */
export default async function BuilderPage() {
  await requireOperator();
  redirect("/builder/sector-tests");
}
