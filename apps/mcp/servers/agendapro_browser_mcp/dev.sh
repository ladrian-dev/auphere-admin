#!/usr/bin/env bash
# Spawn local manual del server para depurar.
#
# Uso:
#   NEXUS_TENANT_ID=<uuid> ./dev.sh
#
# El server espera JSON-RPC por stdin. Para testing manual:
#   echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | NEXUS_TENANT_ID=test ./dev.sh
#
# Para integración con un Browserbase real, exportar:
#   BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID
#
# Para run "vacío" sin tocar Browserbase, las tools fallarán al primer
# ensureAttached — usar fakes en tests.

set -euo pipefail

cd "$(dirname "$0")"

export NEXUS_TENANT_ID="${NEXUS_TENANT_ID:-00000000-0000-0000-0000-000000000000}"
export NEXUS_REDIS_URL="${NEXUS_REDIS_URL:-redis://localhost:6379/0}"
export NEXUS_AGENDAPRO_LOG_LEVEL="${NEXUS_AGENDAPRO_LOG_LEVEL:-debug}"

if [ ! -d node_modules ]; then
  echo "node_modules missing — running pnpm install" >&2
  pnpm install
fi

# tsx hot-reloads TypeScript without a build step.
exec pnpm exec tsx src/server.ts
