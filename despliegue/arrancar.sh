#!/usr/bin/env bash
# despliegue/arrancar.sh — lo que corre ADENTRO del contenedor.
#
# 1. Copia las tablas y las notas del juego (montadas en /r2b/juego, sólo lectura) a servidor/,
#    SIN pisar lo que ya trae la imagen (nuestras tablas .json ganan siempre).
# 2. Arranca el server. Las cuentas, el log y el estado quedan en /r2b/datos (correr_servidor.py).
set -euo pipefail
cd /r2b
JUEGO=/r2b/juego
if [ -d "$JUEGO" ]; then
    [ -f "$JUEGO/shop_lt.txt" ]          && cp -n "$JUEGO/shop_lt.txt" servidor/
    [ -f "$JUEGO/notes_map_2013.json" ]  && cp -n "$JUEGO/notes_map_2013.json" servidor/
    [ -d "$JUEGO/notes" ]                && cp -rn "$JUEGO/notes/." servidor/notes/
    [ -d "$JUEGO/tablas-cliente" ]       && cp -rn "$JUEGO/tablas-cliente/." servidor/tablas-cliente/
fi
mkdir -p /r2b/datos
exec python correr_servidor.py
