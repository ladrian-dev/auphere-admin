import { withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const state = new URL(request.url).searchParams.get("state") ?? undefined;
  return withPermission("teammates:use", (b) => b.teammateTasks(state));
}
