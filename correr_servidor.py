#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
  ARRANQUE DEL SERVIDOR DE R2BEAT 2013
=============================================================================

      python correr_servidor.py

  No hay nada que instalar: alcanza con Python 3.10 o más nuevo.

  Antes, una sola vez: `herramientas/extraer_datos.py` (las tablas del juego) y
  las notas de las canciones (servidor/notes/LEEME.md). Ver EMPEZAR.md.

  Lo que se crea solo, en datos/ (y nunca se sube a ningún lado):
      datos.db        las cuentas, personajes e inventario. ⛔ Tiene las
                      contraseñas (hasheadas) de tu gente: hacele copias,
                      no lo compartas.
      sesiones.json   las sesiones abiertas
      servidor.log    el log (el de la corrida anterior queda al lado)
      status.json     quién está online, cada 3 segundos

  Puertos: login 48004, y un lobby por canal (48005, 48015, 48025, …).

  Si algo falla al arrancar, el error queda impreso en la ventana y no se
  cierra sola, para que se pueda leer.
=============================================================================
"""
import importlib
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "datos")


def preparar_entorno():
    os.makedirs(DATOS, exist_ok=True)
    # Todo el estado vivo va a datos/. Una variable de entorno puesta a mano gana siempre.
    for var, nombre in (("R2_BASE", "datos.db"), ("R2_CHARS_DB", "chars_db.json"),
                        ("R2_CUENTAS", "cuentas.json"), ("R2_SESIONES", "sesiones.json"),
                        ("R2_LOG", "servidor.log"), ("R2_STATUS", "status.json")):
        os.environ.setdefault(var, os.path.join(DATOS, nombre))
    # El server lee la tabla de niveles del R2Beat.exe de TU juego (no la trae: es de Softnyx).
    try:
        with open(os.path.join(DATOS, "juego.json"), encoding="utf-8") as f:
            exe = json.load(f).get("exe")
        if exe:
            os.environ.setdefault("R2_EXE", exe)
    except (OSError, ValueError):
        pass
    faltan = [r for r in ("servidor/shop_lt.txt", "servidor/tablas-cliente/music_lt.txt")
              if not os.path.isfile(os.path.join(AQUI, *r.split("/")))]
    if faltan:
        sys.exit("⛔ faltan las tablas del juego (" + ", ".join(faltan) + ").\n"
                 "   Corré primero:  python herramientas/extraer_datos.py \"C:\\ruta\\al\\juego\"\n"
                 "   Ver EMPEZAR.md, paso 1.")
    if not os.path.isfile(os.path.join(AQUI, "servidor", "notes_map_2013.json")):
        print("⚠ todavía no hay notas de canciones: el servidor arranca, pero las salas no van a tener\n"
              "  canciones para correr. Ver EMPEZAR.md, paso 3.")


def main():
    os.chdir(AQUI)
    sys.path.insert(0, AQUI)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    preparar_entorno()
    # ⚠ Se IMPORTA y se llama a `main()`; nunca `python servidor/lobby.py`: correrlo como script deja
    #   DOS copias del módulo con globals distintos (ver el docstring de `servidor.lobby.main`).
    importlib.import_module("servidor.lobby").main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("cortado a mano. Chau.")
    except SystemExit:
        raise
    except Exception:
        import traceback
        print("\n" + "=" * 70)
        print("  EL SERVIDOR NO PUDO ARRANCAR. El error está abajo.")
        print("=" * 70)
        traceback.print_exc()
        print("=" * 70)
        print("\nSi no entendés el error, copialo entero y pedí ayuda con eso.")
        try:
            input("\nApretá ENTER para cerrar esta ventana...")
        except Exception:
            pass
        sys.exit(1)
