import { withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

/** Lo que los teammates de esta persona esperan de ella (spec 003, R5.1). */
export async function GET(): Promise<Response> {
  return withPermission("teammates:use", (b) => b.teammateInbox());
}
