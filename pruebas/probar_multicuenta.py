#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probar_multicuenta — el tope de cuentas conectadas A LA VEZ desde la misma IP (`servidor/multicuenta.py`).

    python pruebas/probar_multicuenta.py

Sin el juego ni la red: conexiones de mentira y la base en una carpeta temporal.
★ Con sus reveses: el mismo jugador (re-login, cambio de canal o de personaje) no suma, otra IP no suma,
  las IP sin tope y loopback pasan siempre.
"""
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="r2b_multicuenta_")
os.environ.update(R2_BASE=os.path.join(TMP, "datos.db"), R2_LOG=os.path.join(TMP, "servidor.log"),
                  R2_LOG_CONSOLA="0", PYTHONIOENCODING="utf-8")
sys.path.insert(0, RAIZ)

from servidor import multicuenta, salas          # noqa: E402

FALLAS = []


def ok(cond, que):
    print(("  ok  " if cond else "  MAL ") + que)
    if not cond:
        FALLAS.append(que)


class St:
    def __init__(self, usn, ip, cerrado=False, reemplazada=False):
        self.usn, self.addr, self.cerrado, self.reemplazada = usn, (ip, 50000 + usn), cerrado, reemplazada


CUENTA = {1: "ana", 2: "ana", 3: "beto", 4: "caro", 5: "dani"}   # ana tiene DOS personajes (usn 1 y 2)


def cuenta_de(usn):
    return CUENTA.get(usn, f"usn:{usn}")


def conectadas(*sts):
    return {s.usn: s for s in sts}


# IPs privadas a propósito: el repo no admite IPs públicas (probar_nada_prohibido). Al tope le da igual: sólo
#   exime loopback y las de R2_IPS_SIN_TOPE; en prod el server ve las públicas.
def probar_tope():
    print("el tope de cuentas a la vez por IP (tope 2):")
    X, Y = "192.168.10.1", "192.168.20.2"
    sup = lambda ip, cuenta, cx, **kw: multicuenta.supera_tope(ip, cuenta, cx, cuenta_de, tope=2, libres=frozenset(), **kw)
    ok(not sup(X, "beto", conectadas(St(1, X))), "una conectada: la segunda cuenta entra")
    ok(sup(X, "caro", conectadas(St(1, X), St(3, X))), "dos conectadas: la tercera cuenta NO entra")
    ok(not sup(X, "ana", conectadas(St(1, X), St(3, X))), "revés: la misma cuenta re-logueando (cambio de canal) entra")
    ok(sup(X, "caro", conectadas(St(1, X), St(2, X), St(3, X))) and
       len(multicuenta.cuentas_de_ip(X, conectadas(St(1, X), St(2, X), St(3, X)), cuenta_de)) == 2,
       "dos personajes de la misma cuenta cuentan como UNA cuenta")
    ok(not sup(Y, "caro", conectadas(St(1, X), St(3, X))), "revés: desde otra IP no suma")
    ok(not sup(X, "caro", conectadas(St(1, X), St(3, X, cerrado=True))), "una sesión ya cerrada no cuenta")
    ok(not sup(X, "caro", conectadas(St(1, X), St(3, X, reemplazada=True))), "una sesión reemplazada no cuenta")
    ok(not multicuenta.supera_tope(X, "caro", conectadas(St(1, X), St(3, X)), cuenta_de, tope=2,
                                   libres=frozenset({X})), "una IP sin tope (cyber) no tiene tope")
    ok(not multicuenta.supera_tope("127.0.0.1", "caro", conectadas(St(1, "127.0.0.1"), St(3, "127.0.0.1")),
                                   cuenta_de, tope=2, libres=frozenset()), "loopback (pruebas en la misma PC) no tiene tope")
    ok(not multicuenta.supera_tope("::1", "caro", conectadas(St(1, "::1"), St(3, "::1")),
                                   cuenta_de, tope=2, libres=frozenset()), "loopback IPv6 tampoco")
    ok(not multicuenta.supera_tope(X, "caro", conectadas(St(1, X), St(3, X)), cuenta_de, tope=0,
                                   libres=frozenset()), "tope 0 = sin tope")
    ok(not sup(None, "caro", conectadas(St(1, X), St(3, X))), "sin IP conocida no se frena")


def probar_rechazo():
    print("al entrar al lobby (rechazar_por_tope con el registro de verdad):")
    X = "192.168.30.3"
    original = multicuenta.cuenta_de
    multicuenta.cuenta_de = cuenta_de
    try:
        salas.CONEXIONES.clear()
        salas.CONEXIONES.update(conectadas(St(1, X), St(3, X)))
        ok(multicuenta.rechazar_por_tope(St(4, X), 4), "la tercera cuenta desde la misma IP se rechaza")
        ok(not multicuenta.rechazar_por_tope(St(2, X), 2), "revés: otro personaje de ana entra")
        ok(not multicuenta.rechazar_por_tope(St(5, "192.168.90.9"), 5), "revés: desde otra IP entra")
        with open(os.environ["R2_LOG"], encoding="utf-8") as f:
            ok("MULTICUENTA" in f.read(), "el rechazo queda en el log con la IP y las cuentas")
    finally:
        multicuenta.cuenta_de = original
        salas.CONEXIONES.clear()


def probar_cableado():
    print("el lobby lo usa antes del doble login y no limpia nada al rechazar:")
    with open(os.path.join(RAIZ, "servidor", "lobby.py"), encoding="utf-8") as f:
        fuente = f.read()
    i_tope = fuente.find("multicuenta.rechazar_por_tope(st, _u)")
    i_doble = fuente.find("echar_sesion_anterior(_u, st)")
    ok(0 < i_tope < i_doble, "el tope va ANTES de echar la sesión anterior y de registrar")
    ok("st.reemplazada = True" in fuente[i_tope:i_doble], "al rechazar marca la conexión para que el finally no limpie")


def main():
    try:
        probar_tope()
        probar_rechazo()
        probar_cableado()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    if FALLAS:
        print(f"\n{len(FALLAS)} prueba(s) MAL")
        return 1
    print("\ntodo bien")
    return 0


if __name__ == "__main__":
    sys.exit(main())
