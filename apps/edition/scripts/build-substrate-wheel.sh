#!/usr/bin/env bash
# T004 — construye la rueda del sustrato desde el commit fijado.
#
# No existe rueda pública: PyPI da 404 para `kirocrew` y los releases del proyecto
# publican solo bundles de escritorio. Así que la construimos nosotros, y por eso
# esto es cadena de suministro del paquete firmado y no una línea de dependencias.
#
# El clon NUNCA se toca: se exporta el commit con `git archive` a un directorio
# aparte y se construye desde esa copia. Un `pip install -e` sobre el clon dejaría
# artefactos dentro y rompería la comprobación de "0 archivos modificados".
set -euo pipefail

PINNED="${NEXUS_SUBSTRATE_COMMIT:-37933a5}"
CLONE="${NEXUS_SUBSTRATE_CLONE:-$HOME/Workspace/_oss-research/kirocrew}"
OUT="${1:-$(cd "$(dirname "$0")/.." && pwd)/build}"

[ -d "$CLONE/.git" ] || { echo "no hay clon del sustrato en $CLONE (fija NEXUS_SUBSTRATE_CLONE)" >&2; exit 2; }

before="$(git -C "$CLONE" rev-parse HEAD)"
rm -rf "$OUT/src" "$OUT/dist"
mkdir -p "$OUT/src" "$OUT/dist"
git -C "$CLONE" archive "$PINNED" | tar -x -C "$OUT/src"
uv build --wheel --out-dir "$OUT/dist" "$OUT/src" >"$OUT/build.log" 2>&1

# La comprobación que separa componer de forkear.
after="$(git -C "$CLONE" rev-parse HEAD)"
dirty="$(git -C "$CLONE" status --porcelain | wc -l | tr -d ' ')"
[ "$before" = "$after" ] || { echo "el clon cambió de HEAD durante el build" >&2; exit 1; }
[ "$dirty" = "0" ] || { echo "el clon quedó con $dirty ficheros modificados: eso es un fork, no una composición" >&2; exit 1; }

# Apache-2.0 §4.d: el NOTICE viaja con lo distribuido. Es obligación de licencia,
# así que es una puerta del build y no una costumbre.
WHEEL="$(ls "$OUT"/dist/*.whl)"
# El listado se captura UNA vez a propósito: `unzip -l | grep -q` bajo `pipefail`
# marca la tubería como fallida cuando grep acierta y sale antes de tiempo, y la
# puerta denunciaba ruedas correctas.
listing="$(unzip -l "$WHEEL")"
for required in NOTICE LICENSE; do
  case "$listing" in
    *"licenses/$required"*) ;;
    *) echo "la rueda no lleva $required dentro: Apache-2.0 §4.d lo exige" >&2; exit 1 ;;
  esac
done

# T055 — vigilancia de marcas. No hay constante central de marca en el sustrato,
# así que un bump puede reintroducirlas en superficie visible sin que nadie se
# entere. Renombrar es un día; vigilar es siempre.
#
# Se cuenta el catálogo de cadenas EN INGLÉS, que es la fuente de la que derivan
# los demás idiomas. Los identificadores internos (`kiro_crew`) NO se cuentan: no
# son marca y renombrarlos costaría el seguimiento aguas arriba.
# Las cadenas visibles en inglés viven aquí — `enCatalog.ts` es la tabla de
# claves y no contiene el copy. Se comprobó fichero a fichero: las 17 apariciones
# que midió la evaluación están en `en.context.json`.
CATALOG="$OUT/src/website/src/i18n/en.context.json"
BASELINE="${NEXUS_BRAND_BASELINE:-10}"
if [ -f "$CATALOG" ]; then
  # `grep` sale con 1 cuando no encuentra nada, y bajo `pipefail` eso tumbaría el
  # build justo en el caso bueno. Es el mismo tropiezo que la puerta del NOTICE.
  marks=$( { grep -oiE '\bkiro[ -]?crew\b|\bkiro\b' "$CATALOG" || true; } | wc -l | tr -d ' ')
  if [ "$marks" -gt "$BASELINE" ]; then
    echo "el bump reintrodujo marcas en superficie visible: $marks (línea base $BASELINE)" >&2
    echo "revisa el catálogo inglés antes de publicar la rueda" >&2
    exit 1
  fi
  echo "marcas en superficie visible: $marks (línea base $BASELINE)"
fi

echo "rueda: $WHEEL"
echo "NOTICE y LICENSE presentes en la rueda (Apache-2.0 §4.d)"
echo "clon intacto en $PINNED, 0 modificados"
