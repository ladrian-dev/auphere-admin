import { Redirect } from "expo-router";

import { useMe } from "@/api/hooks";
import { useSession } from "@/auth/session";
import { firstRoute } from "@/lib/modules";
import { MeGateState } from "@/features/me-gate";

/**
 * Where everyone lands, and where a guard sends them when the session changes.
 * Signed in, it is the client's first module in the API's order (R3.2, R3.4).
 */
export default function Index() {
  const { state } = useSession();
  if (state.status === "booting") return null;
  if (state.status === "update-required") return <Redirect href="/update-required" />;
  if (state.status === "signed-out") return <Redirect href="/sign-in" />;
  return <FirstModule />;
}

function FirstModule() {
  const me = useMe();
  const route = me.data ? firstRoute(me.data.nav) : null;
  if (route) return <Redirect href={route} />;
  return <MeGateState query={me} />;
}
