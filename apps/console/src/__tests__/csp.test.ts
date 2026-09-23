/**
 * The CSP the proxy emits lets the Facebook SDK do its three things (bug
 * meta-no-devuelve-el-codigo): load its script, call the Graph API, and mount
 * the hidden ``staticxx.facebook.com`` frame through which ``FB.login`` hands
 * the Embedded Signup code back. Without the third one the popup completes
 * and the console still says «Meta no devolvió el código».
 */
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { proxy } from "../proxy";

function csp(): Record<string, string> {
  const res = proxy(new NextRequest("https://console.example/clients"));
  const header = res.headers.get("content-security-policy") ?? "";
  return Object.fromEntries(
    header
      .split(";")
      .map((d) => d.trim())
      .filter(Boolean)
      .map((d) => [d.split(" ")[0]!, d]),
  );
}

describe("console CSP · Meta Embedded Signup", () => {
  it("allows the SDK script, the Graph API and the login + xd_arbiter frames", () => {
    const directives = csp();
    expect(directives["script-src"]).toContain("https://connect.facebook.net");
    expect(directives["connect-src"]).toContain("https://graph.facebook.com");
    expect(directives["frame-src"]).toContain("https://www.facebook.com");
    expect(directives["frame-src"]).toContain("https://staticxx.facebook.com");
    expect(directives["frame-ancestors"]).toBe("frame-ancestors 'none'");
  });
});
