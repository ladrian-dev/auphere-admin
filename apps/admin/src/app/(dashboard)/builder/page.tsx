import { redirect } from "next/navigation";

/** Spec 047: Constructor opens on its first view. */
export default function BuilderPage() {
  redirect("/builder/sector-tests");
}
