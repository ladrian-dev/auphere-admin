import { redirect } from "next/navigation";
import { requirePageOperator } from "@/lib/session";

/** Spec 031 (R4.8): this tab now lives inside «settings». Old links keep working. */
export default async function Moved({ params }: { params: Promise<{ id: string }> }) {
  await requirePageOperator("read");
  const { id } = await params;
  redirect(`/partners/${id}/settings`);
}
