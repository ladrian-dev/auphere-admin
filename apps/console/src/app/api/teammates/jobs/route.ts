import { withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

/** La semilla de oficios y los modelos que el partner puede elegir. */
export async function GET(): Promise<Response> {
  return withPermission("teammates:use", (b) => b.teammateJobs());
}
