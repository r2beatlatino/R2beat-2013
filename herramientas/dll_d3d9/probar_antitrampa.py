#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probar_antitrampa — `fuente/antitrampa.c` sin el juego, en Windows.

    python herramientas/dll_d3d9/probar_antitrampa.py

Arma `prueba/antitrampa_prueba.c` (un programa x86 que incluye el mismo antitrampa.c y se vigila a sí mismo) con
Zig 0.16.0 (`ZIG` o el PATH) o, si no está, con `i686-w64-mingw32-clang`, y lo corre dos veces: limpio (el exe en
memoria tiene que ser igual al del disco) y con las trampas de mentira (un trainer que escribe por fuera, memoria
ejecutable ajena y un módulo «toolbit_prueba.dll», que es una copia de version.dll del sistema).
⚠ Sólo Windows: las pruebas de GitHub no lo corren (corren en Linux, sin compilador de C).
"""
import os
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
PRUEBA = os.path.join(AQUI, "prueba", "antitrampa_prueba.c")


def compilador():
    zig = os.environ.get("ZIG") or shutil.which("zig")
    if zig:
        return [zig, "cc", "-target", "x86-windows-gnu", "-Wl,--no-dynamicbase"]
    clang = shutil.which("i686-w64-mingw32-clang")
    return [clang, "-Wl,--disable-dynamicbase"] if clang else None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass
    if os.name != "nt":
        print("⛔ esta prueba es sólo de Windows")
        return 1
    cc = compilador()
    if not cc:
        print("⛔ no encuentro Zig 0.16.0 ni i686-w64-mingw32-clang")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "antitrampa_prueba.exe")
        r = subprocess.run(cc + ["-O2", "-o", exe, PRUEBA, "-luser32"],     # sin ASLR: así se compara con el disco
                           capture_output=True, text=True)
        if r.returncode:
            print("⛔ no compiló:\n" + (r.stderr or r.stdout)[-3000:])
            return 1
        modulo = os.path.join(tmp, "toolbit_prueba.dll")
        shutil.copy(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64", "version.dll"), modulo)
        fallas = 0
        for args in (["limpio"], [modulo]):
            print(f"── {'limpio' if args == ['limpio'] else 'con trampas de mentira'}", flush=True)
            fallas += subprocess.run([exe] + args).returncode != 0
    print("\n→ TODO BIEN" if not fallas else "\n⛔ ALGO DIO MAL")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
