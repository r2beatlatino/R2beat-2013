#!/usr/bin/env bash
# despliegue/actualizar.sh — pone un entorno en lo último de SU rama y lo reinicia, sólo si cambió algo.
#
#   bash /opt/r2b2013/prod/despliegue/actualizar.sh prod      # master  → r2b-prod   (A MANO, lo corre el dueño)
#   bash /opt/r2b2013/prueba/despliegue/actualizar.sh prueba  # develop → r2b-prueba (cron, cada 5 min)
#   … --forzar                                                # rearma aunque no haya cambios
#
# ★ Si la prueba del login falla, la imagen NO se arma (el Dockerfile la corre) y el contenedor que
#   andaba SIGUE andando: un PR roto en develop no tira el server de prueba.
# ⚠ Reiniciar el contenedor corta a los que están jugando en ESE entorno. Prod se actualiza a mano.
set -euo pipefail

ENTORNO="${1:?uso: actualizar.sh prod|prueba [--forzar]}"
BASE=/opt/r2b2013
case "$ENTORNO" in
    prod) RAMA=master ;;
    prueba) RAMA=develop ;;
    *) echo "⛔ entorno: prod o prueba"; exit 1 ;;
esac
DIR="$BASE/$ENTORNO"
ENV="$BASE/$ENTORNO.env"
cd "$DIR"

git fetch --quiet origin "$RAMA"
ANTES="$(git rev-parse --short HEAD)"
AHORA="$(git rev-parse --short "origin/$RAMA")"
CORRIENDO="$(docker ps --filter "name=^r2b-$ENTORNO$" --format '{{.Names}}')"
if [ "${2:-}" != "--forzar" ]; then
    [ "$ANTES" = "$AHORA" ] && [ -n "$CORRIENDO" ] && exit 0                     # nada nuevo
    [ "$AHORA" = "$(cat "$BASE/$ENTORNO.fallido" 2>/dev/null)" ] && exit 0      # ya falló: no reintentar
fi

echo "$(date '+%F %T') $ENTORNO ($RAMA): $ANTES → $AHORA"
git reset --hard --quiet "origin/$RAMA"
if ! docker compose -p "r2b-$ENTORNO" --env-file "$ENV" -f despliegue/docker-compose.yml up -d --build --quiet-pull; then
    echo "$(date '+%F %T') ⛔ $ENTORNO: no se pudo armar ($AHORA). Sigue el anterior."
    echo "$AHORA" > "$BASE/$ENTORNO.fallido"
    git reset --hard --quiet "$ANTES"
    exit 1
fi
rm -f "$BASE/$ENTORNO.fallido"
echo "$(date '+%F %T') ✅ $ENTORNO en $AHORA"
