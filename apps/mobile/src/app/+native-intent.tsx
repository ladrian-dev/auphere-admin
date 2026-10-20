/**
 * Links the system hands the app (spec 031, R8.6): a notice's
 * `auphere-customers://inbox/<id>` or `://usage`, and the sign-in callback,
 * which `expo-web-browser` already consumed — it only needs to land somewhere
 * harmless. Never throws: an unknown link goes home.
 */
export function redirectSystemPath({ path }: { path: string; initial: boolean }): string {
  try {
    const url = new URL(path, "auphere-customers://app");
    const parts = (url.protocol === "auphere-customers:" ? [url.hostname, ...url.pathname.split("/")] : url.pathname.split("/")).filter(
      Boolean,
    );
    if (parts[0] === "auth") return "/sign-in";
    if (parts[0] === "inbox" && parts[1]) return `/conversacion/${encodeURIComponent(parts[1])}`;
    if (parts[0] === "inbox") return "/bandeja";
    if (parts[0] === "usage") return "/consumo";
    return path.startsWith("/") ? path : "/";
  } catch {
    return "/";
  }
}
