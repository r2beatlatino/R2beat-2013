#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""compilar — arma nuestra `d3d9.dll` desde `herramientas/dll_d3d9/fuente/`.

    python herramientas/dll_d3d9/compilar.py              # compila y dice si da IGUAL a exe/d3d9.dll

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
PUBLICADA = os.path.join(RAIZ, "exe", "d3d9.dll")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass
    zig = os.environ.get("ZIG") or shutil.which("zig")
    if not zig:
        print("⛔ no encuentro Zig 0.16.0 (ponelo en el PATH o en la variable ZIG)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        for f in os.listdir(FUENTE):
            shutil.copy(os.path.join(FUENTE, f), tmp)
        r = subprocess.run([zig, "cc", "-target", "x86-windows-gnu", "-shared", "-O2", "-s", "-o", "d3d9.dll",
                            "d3d9_proxy.c", "d3d9.def", "-lkernel32", "-luser32", "-lgdi32"],
                           cwd=tmp, capture_output=True, text=True)
        dll = os.path.join(tmp, "d3d9.dll")
        if r.returncode or not os.path.isfile(dll):
            print("⛔ no compiló:\n" + (r.stderr or r.stdout)[-3000:])
            return 1
        datos = open(dll, "rb").read()
    salida = os.path.join(RAIZ, "datos", "d3d9.dll")
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    open(salida, "wb").write(datos)
    md5 = hashlib.md5(datos).hexdigest()
    print("★ %s\n  %s B · md5 %s" % (salida, format(len(datos), ","), md5))
    if os.path.isfile(PUBLICADA):
        igual = md5 == hashlib.md5(open(PUBLICADA, "rb").read()).hexdigest()
        print("  exe/d3d9.dll: %s" % ("IGUAL ✅" if igual else "DISTINTA (¿cambió el fuente? copiala a exe/)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
