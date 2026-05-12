import { Badge } from "@/components/ui/badge";
import type { ConnectorAuthKind } from "@/lib/backend";

const AUTH_KIND_LABEL: Record<ConnectorAuthKind, string> = {
  oauth_composio: "OAuth",
  browser_credentials: "Credenciales (browser)",
  webhook_manual: "Webhook manual",
  api_key: "API key",
};

export function ConnectorAuthBadge({ kind }: { kind: ConnectorAuthKind }) {
  return (
    <Badge variant="outline" className="text-[10px]">
      {AUTH_KIND_LABEL[kind]}
    </Badge>
  );
}
