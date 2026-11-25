import { redirect } from "next/navigation";
import { requirePageOperator } from "@/lib/session";

/** Spec 047: Constructor opens on its first view. */
export default async function BuilderPage() {
  await requirePageOperator("read");
  redirect("/builder/sector-tests");
}
