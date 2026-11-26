#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probar_maquina — la PC de cada cuenta, el «HWID» (`servidor/maquina.py`).

    python pruebas/probar_maquina.py

Sin el juego ni la red: `FF02` armados a mano, conexiones de mentira y la base en una carpeta temporal.
★ Con sus reveses: la misma cuenta re-logueando no suma, otra PC no suma, sin MAC no se aplica nada, perdonar
  deshace el baneo de PC, y la MAC no queda escrita ni en la base ni en el log.
"""
import os
import shutil
import struct
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="r2b_maquina_")
os.environ.pop("R2_SAL_MAQUINA", None)
os.environ.update(R2_BASE=os.path.join(TMP, "datos.db"), R2_LOG=os.path.join(TMP, "servidor.log"),
                  R2_LOG_CONSOLA="0", PYTHONIOENCODING="utf-8")
sys.path.insert(0, RAIZ)

from servidor import almacen, cifrado, maquina, multicuenta, salas   # noqa: E402

FALLAS = []


def ok(cond, que):
    print(("  ok  " if cond else "  MAL ") + que)
    if not cond:
        FALLAS.append(que)


# MACs inventadas, «administradas localmente» (02-…): no son de ninguna placa real.
PC1, PC2 = "02-00-00-AA-BB-01", "02-00-00-AA-BB-02"


def ff02(mac, cuenta="ana", ip="192.168.1.5", usn=1, challenge=0x88D95945):
    """Un `FF02` de la lobby con el layout medido (ver `cifrado.leer_challenge_ff02`)."""
    campo = lambda b: bytes([len(b)]) + b
    return (struct.pack("<I", usn) + bytes(5) + campo(ip.encode()) + campo(b"") + campo(b"")
            + campo(cuenta.encode()) + struct.pack("<I", challenge) + campo(mac.encode()))


def probar_leer_mac():
    print("leer la MAC del FF02:")
    p = ff02(PC1)
    ok(maquina.leer_mac_ff02(p) == "020000AABB01", "la MAC sale normalizada (12 hex, sin guiones)")
    ok(cifrado.leer_challenge_ff02(p) is not None, "el mismo paquete le sirve a leer_challenge_ff02 (mismo layout)")
    ok(maquina.leer_mac_ff02(ff02("02:00:00:aa:bb:01")) == "020000AABB01", "con dos puntos y minúsculas, igual")
    ok(maquina.leer_mac_ff02(ff02("")) is None, "MAC vacía -> None")
    ok(maquina.leer_mac_ff02(ff02("00-00-00-00-00-00")) is None, "MAC en ceros -> None")
    ok(maquina.leer_mac_ff02(ff02("hola que tal")) is None, "basura -> None")
    ok(maquina.leer_mac_ff02(p + b"\x00") is None, "si sobra un byte (no cierra justo) -> None")
    ok(maquina.leer_mac_ff02(p[:20]) is None and maquina.leer_mac_ff02(b"") is None, "cortado o vacío -> None")
    ok(b"AA-BB" not in maquina.sin_mac(p) and maquina.sin_mac(p) == p[:-18], "sin_mac (para el log) corta la MAC")


def probar_huella():
    print("la huella (HMAC con la clave del server):")
    a, b = maquina.huella("020000AABB01", b"k1"), maquina.huella("020000AABB01", b"k2")
    ok(a == maquina.huella("020000AABB01", b"k1") and len(a) == 32, "misma MAC y clave -> misma huella")
    ok(a != b, "otra clave -> otra huella (sin la clave no se puede buscar una MAC)")
    ok(maquina.huella(None) is None, "sin MAC no hay huella")
    k = maquina.clave()
    ruta = os.path.splitext(almacen.BASE)[0] + ".maquina.key"
    ok(os.path.isfile(ruta) and len(k) == 64, "sin R2_SAL_MAQUINA crea la clave al lado de la base")
    maquina._clave = None
    ok(maquina.clave() == k, "y al volver a arrancar usa la misma (las huellas guardadas siguen coincidiendo)")


class St:
    def __init__(self, usn, maq=None, cerrado=False, reemplazada=False):
        self.usn, self.maquina, self.cerrado, self.reemplazada = usn, maq, cerrado, reemplazada
        self.addr = ("192.168.1.%d" % usn, 50000 + usn)


CUENTA = {1: "ana", 2: "ana", 3: "beto", 4: "caro", 5: "dani"}   # ana tiene DOS personajes (usn 1 y 2)


def cuenta_de(usn):
    return CUENTA.get(usn, f"usn:{usn}")


def probar_tope():
    print("el tope de cuentas a la vez por PC (tope 2), puro:")
    H, J = "h" * 32, "j" * 32
    cx = lambda *s: {x.usn: x for x in s}
    sup = lambda h, cuenta, c: maquina.supera_tope(h, cuenta, c, cuenta_de, tope=2)
    ok(not sup(H, "beto", cx(St(1, H))), "una conectada: la segunda cuenta entra")
    ok(sup(H, "caro", cx(St(1, H), St(3, H))), "dos conectadas: la tercera NO entra")
    ok(not sup(H, "ana", cx(St(1, H), St(3, H))), "revés: la misma cuenta re-logueando entra")
    ok(not sup(J, "caro", cx(St(1, H), St(3, H))), "revés: desde otra PC entra")
    ok(sup(H, "caro", cx(St(1, H), St(2, H), St(3, H))), "dos personajes de una cuenta cuentan como UNA (y frena)")
    ok(not sup(H, "caro", cx(St(1, H), St(3, H, cerrado=True))), "las cerradas no cuentan")
    ok(not sup(None, "caro", cx(St(1, None), St(3, None))), "sin huella (sin MAC) no hay tope")
    ok(not maquina.supera_tope(H, "caro", cx(St(1, H), St(3, H)), cuenta_de, tope=0), "tope 0 = sin tope")


def entrar(usn, mac):
    st = St(usn)
    no = maquina.rechazar_al_entrar(st, usn, ff02(mac, usn=usn))
    if not no:
        salas.CONEXIONES[usn] = st
    return not no, st


def probar_de_punta_a_punta():
    print("de punta a punta (base temporal):")
    multicuenta.cuenta_de = cuenta_de                       # las cuentas de mentira de arriba
    c = almacen.conectar()
    for nombre in ("ana", "beto", "caro", "dani"):
        c.execute("INSERT INTO users (username, pass_hash) VALUES (?, 'x')", (nombre,))
    c.commit()
    salas.CONEXIONES.clear()
    ok(entrar(1, PC1)[0] and entrar(3, PC1)[0], "ana y beto entran desde la misma PC")
    ok(not entrar(4, PC1)[0], "caro, tercera cuenta a la vez en esa PC, NO entra")
    ok(entrar(4, PC2)[0], "caro desde otra PC entra")
    ok(entrar(2, PC1)[0], "ana con su otro personaje (misma cuenta) entra")
    adentro, st = entrar(5, "")
    ok(adentro and st.maquina is None, "dani sin MAC entra y no se le anota PC")
    h1 = maquina.huella("020000AABB01")
    ok(sorted(c for c, *_ in almacen.maquinas_cuentas_de(h1)) == ["ana", "beto"], "quedó anotado quién usó la PC 1")

    salas.CONEXIONES.clear()
    almacen.banear_cuenta("ana")
    ok(almacen.maquina_baneada(h1) is not None, "banear a ana banea su PC")
    ok(not entrar(5, PC1)[0], "dani (cuenta limpia) desde esa PC NO entra")
    ok(entrar(5, PC2)[0], "dani desde otra PC entra")
    ok(almacen.maquinas_perdonar_de("ana") == 1 and almacen.maquina_baneada(h1) is None, "perdonar a ana saca el baneo de PC")
    salas.CONEXIONES.clear()
    ok(entrar(5, PC1)[0], "y dani ya entra desde esa PC")

    almacen.uid_por_nick = lambda nick: {"Ana": 1}.get(nick)
    almacen.cuenta_de_uid = lambda uid: (cuenta_de(uid), 1)
    r = " ".join(maquina.comando_gm(["Ana"], "prueba"))
    ok("beto" in r and "dani" in r and "caro" not in r, "`.maquina Ana` muestra las otras cuentas de su PC")
    almacen.banear_cuenta("ana")
    ok("1 PC" in " ".join(maquina.comando_gm(["perdonar", "Ana"], "prueba")), "`.maquina perdonar Ana` lo deshace")
    ok("no encuentro" in " ".join(maquina.comando_gm(["Nadie"], "prueba")), "apodo que no existe")

    print("privacidad:")
    base = b""
    for ruta in (almacen.BASE, almacen.BASE + "-wal"):
        if os.path.isfile(ruta):
            with open(ruta, "rb") as f:
                base += f.read()
    with open(os.environ["R2_LOG"], "rb") as f:
        registro = f.read()
    crudas = [m.encode() for m in (PC1, PC2, "020000AABB01", "020000AABB02")]
    ok(not any(m in base for m in crudas), "la MAC no está en la base, sólo la huella")
    ok(not any(m in registro for m in crudas), "ni en el log")


def main():
    try:
        probar_leer_mac()
        probar_huella()
        probar_tope()
        probar_de_punta_a_punta()
    finally:
        almacen._local.con.close() if getattr(almacen._local, "con", None) else None
        shutil.rmtree(TMP, ignore_errors=True)
    print()
    if FALLAS:
        print(f"→ {len(FALLAS)} FALLA(S)")
        sys.exit(1)
    print("→ TODO BIEN")


if __name__ == "__main__":
    main()
