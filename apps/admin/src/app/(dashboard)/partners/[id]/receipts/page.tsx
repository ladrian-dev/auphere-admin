import { redirect } from "next/navigation";
import { requireOperator } from "@/lib/session";

/** Spec 031 (R4.8): this tab now lives inside «money». Old links keep working. */
export default async function Moved({ params }: { params: Promise<{ id: string }> }) {
  await requireOperator();
  const { id } = await params;
  redirect(`/partners/${id}/money`);
}
