#!/usr/bin/env bash
#
# Lo que la tubería ejecuta, ejecutable en local.
#
# Existe por una razón con fecha. El 2026-09-11 la spec 003 añadió un cron al
# worker sin declararlo en el contrato de nombres de ``bootstrap.py``; en local
# se habían corrido 3103 pruebas de la API y **ninguna** del worker, y el
# despliegue a staging abortó. La evaluación de empaquetado lo escribió así:
#
#   «El arreglo no es "acordarse": es un comando que corra lo mismo que la
#    tubería, y que la tubería use ese mismo comando para que no puedan
#    divergir.»
#
# El 2026-09-13 volvió a pasar, con la spec 005 y otro cron. Dos veces es un
# patrón, así que aquí está el comando.
#
#   ./scripts/verify.sh          todo
#   ./scripts/verify.sh lint     solo ruff + mypy
#   ./scripts/verify.sh py       solo las suites de Python
#   ./scripts/verify.sh js       solo consola + panel + @nexus/ui
#
# No sustituye a la tubería —ella además construye imágenes y valida
# Terraform—, pero cubre todo lo que se rompe escribiendo código.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/apps/api"
PKGS=(api worker channels mcp)

FAILED=()
step() {
  local name="$1"; shift
  printf '\n\033[1m▸ %s\033[0m\n' "$name"
  if "$@"; then
    printf '\033[32m  ok\033[0m\n'
  else
    printf '\033[31m  FALLÓ\033[0m\n'
    FAILED+=("$name")
  fi
}

run_lint() {
  for pkg in "${PKGS[@]}"; do
    step "ruff check · $pkg" uv run --directory "$API" \
      ruff check "$ROOT/apps/$pkg/src" "$ROOT/apps/$pkg/tests"
    step "ruff format · $pkg" uv run --directory "$API" \
      ruff format --check "$ROOT/apps/$pkg/src" "$ROOT/apps/$pkg/tests"
  done
  # mypy --strict sobre los cuatro paquetes. El worker es el que más se olvida
  # y es justo el que rompió la tubería dos veces.
  step "mypy · api"      uv run --directory "$API" mypy --strict "$API/src/nexus_api"
  step "mypy · worker"   uv run --directory "$API" mypy --strict "$ROOT/apps/worker/src/nexus_worker"
  step "mypy · channels" uv run --directory "$API" mypy --strict "$ROOT/apps/channels/src/nexus_channels"
  step "mypy · mcp"      uv run --directory "$API" mypy --strict "$ROOT/apps/mcp/src/nexus_mcp"
}

run_py() {
  # La API entera: unit + isolation + integration. Necesita Docker arriba.
  step "pytest · api"      uv run --directory "$API" pytest "$API/tests" -q
  step "pytest · worker"   uv run --directory "$API" pytest "$ROOT/apps/worker/tests" -q
  step "pytest · channels" uv run --directory "$API" pytest "$ROOT/apps/channels/tests" -q
  step "pytest · mcp"      uv run --directory "$API" pytest "$ROOT/apps/mcp/tests" -q
}

run_js() {
  # El orden y el alcance salen de ``.github/workflows/ci.yml``. Lo que más se
  # olvida en local es lo de abajo del todo: el paquete compartido, la
  # aplicación de escritorio y el ``next build`` — que falla por cosas que
  # ``tsc`` no ve, como un import de servidor en un componente de cliente.
  step "@nexus/ui · typecheck" pnpm --dir "$ROOT/packages/ui" typecheck
  step "@nexus/ui · lint"      pnpm --dir "$ROOT/packages/ui" lint
  step "@nexus/ui · test"      pnpm --dir "$ROOT/packages/ui" test

  step "consola · sin token de admin" pnpm --dir "$ROOT/apps/console" check:no-admin-token
  step "consola · typecheck" pnpm --dir "$ROOT/apps/console" exec tsc --noEmit -p tsconfig.json
  step "consola · lint"      pnpm --dir "$ROOT/apps/console" exec eslint src/
  step "consola · vitest"    pnpm --dir "$ROOT/apps/console" exec vitest run

  step "companion-ui · typecheck" pnpm --filter @nexus/companion-ui typecheck
  step "companion-ui · test"      pnpm --filter @nexus/companion-ui test

  step "desktop · typecheck" pnpm --filter @nexus/desktop typecheck
  step "desktop · test"      pnpm --filter @nexus/desktop test

  step "panel · typecheck"   pnpm --dir "$ROOT/apps/admin" exec tsc --noEmit -p tsconfig.json
  step "panel · lint"        pnpm --dir "$ROOT/apps/admin" exec eslint .
  step "panel · vitest"      pnpm --dir "$ROOT/apps/admin" exec vitest run

  step "consola · next build" pnpm --dir "$ROOT/apps/console" build
}

case "${1:-all}" in
  lint) run_lint ;;
  py)   run_py ;;
  js)   run_js ;;
  all)  run_lint; run_py; run_js ;;
  *)    echo "uso: $0 [all|lint|py|js]" >&2; exit 2 ;;
esac

printf '\n'
if [ ${#FAILED[@]} -eq 0 ]; then
  printf '\033[32mTodo verde.\033[0m La tubería debería pasar.\n'
  exit 0
fi
printf '\033[31mFallaron %d:\033[0m\n' "${#FAILED[@]}"
printf '  · %s\n' "${FAILED[@]}"
exit 1
