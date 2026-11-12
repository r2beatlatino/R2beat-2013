#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
=============================================================================
  SACAR DEL CLIENTE LAS TABLAS QUE NECESITA EL SERVIDOR
=============================================================================

  POR QUÉ ESTA HERRAMIENTA EXISTE
  -------------------------------
  El servidor necesita saber cosas que están escritas adentro del juego: qué
  ítems hay en la tienda y cuánto salen, qué caras, alas y anillos existen, la
  lista de canciones, las medallas, las mascotas, las misiones del día…

  Esos archivos son de Softnyx, no nuestros, así que NO están en este
  repositorio. Pero ya los tenés: vienen adentro del cliente que instalaste.
  Esta herramienta los saca de ahí y los deja donde el servidor los busca.

  No necesita `r2pak.exe`: lee los .pak con `herramientas/pak.py`.

  CÓMO SE USA
  -----------
      python herramientas/extraer_datos.py  "C:\ruta\al\juego"

  (la carpeta donde está R2Beat.exe y los rnr_*.pak)

  Al terminar vas a tener:

      servidor/shop_lt.txt          el catálogo de la tienda
      servidor/tablas-cliente/*     caras, alas, anillos, medallas, mascotas, …
      datos/juego.json              dónde está tu juego (el server lee de ahí
                                    la tabla de niveles del R2Beat.exe)

  QUÉ NO SACA: las notas de cada canción (servidor/notes/*.bin). El cliente
  2013 no las trae: se las pedía al servidor. Ver servidor/notes/LEEME.md.

  ★ Las tablas se copian TAL CUAL, byte por byte. El servidor las lee con el
    mismo formato que el juego: si las tocás a mano, tocá también el .pak, o
    el juego y el servidor van a pensar cosas distintas.
=============================================================================
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
from pak import Paks  # noqa: E402

SERVIDOR = os.path.join(RAIZ, "servidor")
TABLAS = os.path.join(SERVIDOR, "tablas-cliente")
DATOS = os.path.join(RAIZ, "datos")

# ruta adentro de los .pak -> adónde va
SACAR = {"rnr_script/shop_lt.txt": os.path.join(SERVIDOR, "shop_lt.txt")}
for _n in ("circleshop.xml", "face.txt", "gacha_machine.txt", "hero.txt", "medal_lt.txt",
           "namecard.xml", "pet.xml", "puzzlemission_lt.xml", "ring.txt", "setitem.txt",
           "slotpack.txt", "spec.txt", "todaymission.txt", "wing.txt", "music_lt.txt"):
    SACAR["rnr_script/" + _n] = os.path.join(TABLAS, _n)

# Sin éstas el server no arranca bien; las demás apagan una parte (y el log lo dice).
IMPRESCINDIBLES = {"rnr_script/shop_lt.txt", "rnr_script/music_lt.txt", "rnr_script/face.txt",
                   "rnr_script/wing.txt"}


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    juego = os.path.abspath(sys.argv[1])
    if not os.path.isdir(juego):
        sys.exit(f"⛔ no existe la carpeta {juego}")
    paks = Paks(juego)
    if not paks.ix:
        sys.exit(f"⛔ en {juego} no hay ningún rnr_*.pak que se pueda leer.\n"
                 "   Pasame la carpeta donde está R2Beat.exe (no la del instalador).")
    if paks.rotos:
        print(f"  (no pude leer {len(paks.rotos)} .pak que no hacen falta: {', '.join(paks.rotos[:4])}…)")

    os.makedirs(TABLAS, exist_ok=True)
    os.makedirs(DATOS, exist_ok=True)
    faltan = []
    for ruta, destino in SACAR.items():
        if not paks.tiene(ruta):
            faltan.append(ruta)
            print(f"  [falta] {ruta}")
            continue
        datos = paks.sacar(ruta)
        with open(destino, "wb") as f:
            f.write(datos)
        print(f"  [ok] {ruta} ({paks.de_donde(ruta)}) -> {os.path.relpath(destino, RAIZ)} ({len(datos)} bytes)")

    exe = None
    for nombre in ("R2Beat.exe.original", "R2Beat.exe"):
        if os.path.isfile(os.path.join(juego, nombre)):
            exe = os.path.join(juego, nombre)
            break
    with open(os.path.join(DATOS, "juego.json"), "w", encoding="utf-8") as f:
        json.dump({"juego": juego, "exe": exe}, f, indent=2, ensure_ascii=False)
    print(f"  [ok] datos/juego.json -> {juego}")

    if not exe:
        print("  ⚠ no encontré R2Beat.exe en esa carpeta: sin él el server no sabe la tabla de niveles")
    malas = IMPRESCINDIBLES.intersection(faltan)
    if malas:
        sys.exit(f"\n⛔ faltan tablas imprescindibles: {', '.join(sorted(malas))}\n"
                 "   ¿Es de verdad el cliente 2013? Ver EMPEZAR.md.")
    print("\nListo. Siguiente paso: python herramientas/parchar_cliente.py  (ver EMPEZAR.md)")


if __name__ == "__main__":
    main()
