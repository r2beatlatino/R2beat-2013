#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""compilar — arma nuestra `d3d9.dll` desde `herramientas/dll_d3d9/fuente/`.

    python herramientas/dll_d3d9/compilar.py              # compila y dice si da IGUAL a exe/d3d9.dll
    python herramientas/dll_d3d9/compilar.py --igual      # lo mismo, y sale con 2 si NO da igual (lo usa GitHub)
    python herramientas/dll_d3d9/compilar.py --prod       # ★ 25-nov la de PROD: sin la isla de temporada
                                                          #   (-DR2_SIN_TEMPORADA) → datos/d3d9_prod.dll

Hace falta **Zig 0.16.0** (https://ziglang.org/download/): en el PATH, o con la variable `ZIG`
apuntando al `zig.exe`. La receta es determinista: el mismo fuente da el mismo archivo, byte a byte.

  · `zig cc -target x86-windows-gnu -shared -O2 -s` y `-lkernel32 -luser32 -lgdi32`;
  · ⛔ la salida SE LLAMA `d3d9.dll`: el enlazador escribe ese nombre ADENTRO (la tabla de
    exportaciones). Por eso se compila en una carpeta aparte y no se renombra después.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
FUENTE = os.path.join(AQUI, "fuente")
PUBLICADA = os.environ.get("DLL_PUBLICADA") or os.path.join(RAIZ, "exe", "d3d9.dll")   # (la variable: el revés de la prueba)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass
    zig = os.environ.get("ZIG") or shutil.which("zig")
    prod = "--prod" in sys.argv
    if not zig:
        print("⛔ no encuentro Zig 0.16.0 (ponelo en el PATH o en la variable ZIG)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        for f in os.listdir(FUENTE):
            shutil.copy(os.path.join(FUENTE, f), tmp)
        marcas = ["-DR2_SIN_TEMPORADA"] if prod else []
        r = subprocess.run([zig, "cc", "-target", "x86-windows-gnu", "-shared", "-O2", "-s", *marcas, "-o", "d3d9.dll",
                            "d3d9_proxy.c", "d3d9.def", "-lkernel32", "-luser32", "-lgdi32"],
                           cwd=tmp, capture_output=True, text=True)
        dll = os.path.join(tmp, "d3d9.dll")
        if r.returncode or not os.path.isfile(dll):
            print("⛔ no compiló:\n" + (r.stderr or r.stdout)[-3000:])
            return 1
        datos = open(dll, "rb").read()
    salida = os.path.join(RAIZ, "datos", "d3d9_prod.dll" if prod else "d3d9.dll")
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    open(salida, "wb").write(datos)
    md5 = hashlib.md5(datos).hexdigest()
    print("★ %s\n  %s B · md5 %s" % (salida, format(len(datos), ","), md5))
    if prod:
        # la de prod no se compara con exe/d3d9.dll (es otra): sólo se arma. GitHub sigue comprobando la de prueba.
        return 0
    if os.path.isfile(PUBLICADA):
        igual = md5 == hashlib.md5(open(PUBLICADA, "rb").read()).hexdigest()
        print("  exe/d3d9.dll: %s" % ("IGUAL ✅" if igual else "DISTINTA (¿cambió el fuente? copiala a exe/)"))
        if not igual and "--igual" in sys.argv:
            # ★ 21-nov: el server de PRUEBA reparte la `exe/d3d9.dll` de develop SÓLO si esta prueba dio verde en
            #   GitHub: así la dll que llega a los jugadores es la que sale del fuente, no un archivo armado aparte.
            return 2
    elif "--igual" in sys.argv:
        print("⛔ no está %s" % PUBLICADA)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
