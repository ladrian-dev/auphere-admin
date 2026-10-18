import { redirect } from "next/navigation";

/** Spec 031 (R4.8): this tab now lives inside «settings». Old links keep working. */
export default async function Moved({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/partners/${id}/settings`);
}
