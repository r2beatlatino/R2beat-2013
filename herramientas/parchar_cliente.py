#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
=============================================================================
  PREPARAR EL CLIENTE DE R2BEAT 2013
=============================================================================

  Le aplica al R2Beat.exe la misma receta de parches con la que se juega contra
  este servidor (`receta_exe.py`: 40 cambios chicos, cada uno con su porqué), y
  le pone la dirección de TU servidor.

      python herramientas/parchar_cliente.py  "C:\ruta\al\juego"  192.168.1.50

  Antes de tocar nada deja una copia intacta al lado (R2Beat.exe.original), así
  siempre podés volver:

      python herramientas/parchar_cliente.py  "C:\ruta\al\juego"  --ver
      python herramientas/parchar_cliente.py  "C:\ruta\al\juego"  --restaurar

  ⛔ ES TODO O NADA. La receta está hecha sobre UN binario: el R2Beat.exe del
    instalador del 23-05-2013 (md5 b8f2517f…). Si tu exe es otro, no se escribe
    NADA y se avisa. Un cliente a medio parchear es peor que uno sin tocar.

  ★ Entre los 40 están los dos que más se notan:
    · el COLOR DE 32 BITS (el juego pedía 16, que Windows moderno emula lentísimo):
      sin él hace falta el modo de compatibilidad de XP, que mete lag y esconde Vulkan;
    · el arreglo de las placas de video viejas, que se caían entrando al lobby.

  ⚠ La IP horneada casi no importa: `jugar.py` le pasa la de tu servidor al abrir
    el juego. Se parchea igual para que el exe no apunte a los servidores muertos
    de Softnyx.
=============================================================================
"""
import hashlib
import ipaddress
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import receta_exe  # noqa: E402

EXES = ("R2Beat.exe", "R2BeatMultiTest.exe")      # el mismo binario con dos nombres: van los dos
IP_OFF, IP_LARGO = 0x484D08, 15                   # 15 letras + el 0 final caben en el hueco


def md5(b):
    return hashlib.md5(b).hexdigest()


def receta_con_ip(ip):
    """La receta, con la IP del usuario en vez de la de la máquina del proyecto."""
    nueva = ip.encode("ascii")
    out = []
    for off, antes, despues, desc in receta_exe.PARCHES:
        if off == IP_OFF:
            if len(nueva) > len(antes):          # 15 letras: pisa también uno de los dos 0 de relleno
                antes = antes + b"\x00"
            despues = nueva.ljust(len(antes), b"\x00")
        out.append((off, antes, despues, desc))
    return out


def armar(original, ip):
    datos = bytearray(original)
    for off, antes, despues, desc in receta_con_ip(ip):
        real = bytes(datos[off:off + len(antes)])
        if real != antes:
            return None, f"el parche de 0x{off:06X} no coincide ({desc.splitlines()[0][:60]})"
        datos[off:off + len(antes)] = despues
    return bytes(datos), None


def comprobar_receta(original):
    """Con la IP del proyecto la receta tiene que dar EXACTO el exe que se juega allá."""
    ip_proyecto = next(d for o, _a, d, _x in receta_exe.PARCHES if o == IP_OFF).decode()
    datos, err = armar(original, ip_proyecto)
    return err or (None if md5(datos) == receta_exe.MD5_ESPERADO else
                   "la receta no reproduce el exe esperado (¿se tocó receta_exe.py?)")


def estado(juego):
    for n in EXES:
        p = os.path.join(juego, n)
        if not os.path.isfile(p):
            continue
        h = md5(open(p, "rb").read())
        if h == receta_exe.MD5_PRISTINO:
            print(f"  {n}: SIN parchear (el original del instalador)")
        else:
            orig = p + ".original"
            if os.path.isfile(orig) and md5(open(orig, "rb").read()) == receta_exe.MD5_PRISTINO:
                datos = open(p, "rb").read()
                ip = datos[IP_OFF:IP_OFF + IP_LARGO].split(b"\x00")[0].decode("ascii", "replace")
                print(f"  {n}: PARCHEADO, apunta a {ip}  (el original está en {n}.original)")
            else:
                print(f"  {n}: md5 {h} — no lo conozco (¿otra versión del cliente?)")


def restaurar(juego):
    hechos = 0
    for n in EXES:
        p = os.path.join(juego, n)
        if os.path.isfile(p + ".original"):
            shutil.copy2(p + ".original", p)
            print(f"  [ok] {n} vuelto al original")
            hechos += 1
    if not hechos:
        print("  no había nada para restaurar")


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    juego, arg = os.path.abspath(sys.argv[1]), sys.argv[2]
    if not os.path.isfile(os.path.join(juego, "R2Beat.exe")):
        sys.exit(f"⛔ no hay R2Beat.exe en {juego}")
    if arg == "--ver":
        return estado(juego)
    if arg == "--restaurar":
        return restaurar(juego)

    try:
        ip = str(ipaddress.IPv4Address(arg))
    except ValueError:
        sys.exit(f"⛔ {arg!r} no es una IP (algo como 192.168.1.50)")
    if ip.startswith("127."):
        sys.exit("⛔ no uses 127.0.0.1: el cliente le pasa esa dirección a otras partes del juego y se\n"
                 "   pierde. Usá la IP de tu red (ipconfig -> «Dirección IPv4»).")

    # 1) Todo se arma EN MEMORIA y se comprueba antes de escribir un solo byte.
    listos = []
    for n in EXES:
        p = os.path.join(juego, n)
        if not os.path.isfile(p):
            continue
        fuente = p + ".original" if os.path.isfile(p + ".original") else p
        original = open(fuente, "rb").read()
        if md5(original) != receta_exe.MD5_PRISTINO:
            sys.exit(f"⛔ {os.path.basename(fuente)} no es el exe que esta receta conoce.\n"
                     f"   md5 {md5(original)}\n   debía ser {receta_exe.MD5_PRISTINO}\n"
                     "   Bajá el instalador del 23-05-2013 (ver EMPEZAR.md). No toqué nada.")
        err = comprobar_receta(original)
        if err:
            sys.exit(f"⛔ {err}. No toqué nada.")
        datos, err = armar(original, ip)
        if err:
            sys.exit(f"⛔ {err}. No toqué nada.")
        listos.append((p, fuente == p, original, datos))

    # 2) Recién ahora se escribe: primero la copia intacta, después el parcheado.
    for p, sin_copia, original, datos in listos:
        if sin_copia:
            with open(p + ".original", "wb") as f:
                f.write(original)
        try:
            with open(p, "wb") as f:
                f.write(datos)
        except PermissionError:
            sys.exit(f"⛔ no pude escribir {p}: el juego está abierto. Cerralo y volvé a correr esto.")
        if md5(open(p, "rb").read()) != md5(datos):
            sys.exit(f"⛔ escribí {p} pero al releerlo no da lo mismo. No uses ese cliente.")
        print(f"  [ok] {os.path.basename(p)}: {len(receta_exe.PARCHES)} parches, apunta a {ip}")
    print("\nListo. Siguiente paso: python correr_servidor.py  (ver EMPEZAR.md)")


if __name__ == "__main__":
    main()
