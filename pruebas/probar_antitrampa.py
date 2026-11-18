#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probar_antitrampa — las reglas de `servidor/antitrampa.py` y que el cartel no pague lo retenido.

    python pruebas/probar_antitrampa.py

Sin el juego ni la red: la base, el log y el archivo de marcas van a una carpeta temporal.
★ Con sus reveses: cada regla se prueba con un reporte que la rompe Y con uno limpio que no.
"""
import json
import os
import shutil
import struct
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="r2b_antitrampa_")
os.environ.update(R2_BASE=os.path.join(TMP, "datos.db"), R2_CHARS_DB=os.path.join(TMP, "chars_db.json"),
                  R2_CUENTAS=os.path.join(TMP, "cuentas.json"), R2_SESIONES=os.path.join(TMP, "sesiones.json"),
                  R2_LOG=os.path.join(TMP, "servidor.log"), R2_STATUS=os.path.join(TMP, "status.json"),
                  R2_ANTITRAMPA=os.path.join(TMP, "antitrampa.jsonl"), R2_LOG_CONSOLA="0",
                  PYTHONIOENCODING="utf-8")
sys.path.insert(0, RAIZ)

from servidor import antitrampa, notas          # noqa: E402

FALLAS = []
EXE_BUENO = next(iter(antitrampa.ANTITRAMPA_EXE_MD5))


def ok(cond, que):
    print(("  ok  " if cond else "  MAL ") + que)
    if not cond:
        FALLAS.append(que)


def reglas(marcas):
    return sorted(r for r, _d in marcas)


class Conn:
    usn = 4242
    room_id = None
    room_mode = 0
    room_colab = False

    def __init__(self):
        self.enviados = []

    def send_ff55(self, cmd, body, name=""):
        self.enviados.append((cmd, name))


def marcas_guardadas():
    if not os.path.isfile(antitrampa.ANTITRAMPA_ARCHIVO):
        return []
    with open(antitrampa.ANTITRAMPA_ARCHIVO, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def probar_reglas():
    print("reglas puras (marcas_del_cartel):")
    m = antitrampa.marcas_del_cartel
    ok(m(7200, 500, 95, 80, 600, 121.0) == [], "carrera limpia: 120 s de juego en 121 s, combo 500/600")
    ok(reglas(m(7200, 601, 95, 80, 600, 121.0)) == ["combo_imposible"], "combo 601 sobre 600 notas")
    ok(m(7200, 600, 95, 80, 600, 121.0) == [], "revés: combo exacto al total no marca")
    ok(m(7200, 900, 95, 80, None, 121.0) == [], "sin total conocido no se juzga el combo")
    ok(reglas(m(7200, 500, 101, 80, 600, 121.0)) == ["porcentaje_imposible"], "pd 101")
    ok(reglas(m(7200, 500, 95, 200, 600, 121.0)) == ["porcentaje_imposible"], "star 200")
    ok(reglas(m(7200, 500, 95, 80, 600, 96.0)) == ["reloj_rapido"], "120 s de juego en 96 s (125 %)")
    ok(m(7200, 500, 95, 80, 600, 112.0) == [], "revés: 120 s en 112 s cae dentro de la tolerancia")
    ok(reglas(m(7200, 500, 95, 80, 600, 200.0)) == ["reloj_lento"], "120 s de juego en 200 s (60 %)")
    ok(m(7200, 500, 95, 80, 600, 200.0, relevo=True) == [], "relevo: el reloj lento no se juzga")
    ok(m(7200, 900, 95, 80, 600, 50.0, coop=True) == [], "cooperativo: ni combo ni reloj")
    ok(m(0xFFFFFFFF, 500, 95, 80, 600, 10.0) == [], "frame sin meta (relevo cerrado) no juzga el reloj")
    ok(m(7200, 500, 95, 80, 600, None) == [], "sin GO conocido no juzga el reloj")


def probar_juzgar():
    print("juzgar_cartel (acciones, archivo, reintentos):")
    avisos = []
    antitrampa._avisar_gms = avisos.append
    notas.combo_total_de = lambda cancion: 600
    c = Conn()
    antitrampa.al_ff59(c, f"USN:{c.usn} TIME:x SERVER:y\nR2AT v=1 exe={EXE_BUENO} previo=0")
    ok(marcas_guardadas() == [] and avisos == [], "un «hola» con el exe de la receta no marca nada")
    antitrampa.marcar_salida(c, ahora=1000.0)
    ok(antitrampa.juzgar_cartel(c, 7200, 601, 95, 80, 77, ahora=1121.0) is True, "combo imposible -> retener")
    ok(len(marcas_guardadas()) == 1 and marcas_guardadas()[0]["regla"] == "combo_imposible",
       "la marca queda en el archivo")
    ok(len(avisos) == 1 and "premio retenido" in avisos[0], "los GM reciben el aviso")
    ok(antitrampa.juzgar_cartel(c, 7200, 601, 95, 80, 77, ahora=1130.0) is True and len(marcas_guardadas()) == 1,
       "el reintento del mismo FF28 no vuelve a marcar y sigue retenido")
    c2 = Conn()
    antitrampa.marcar_salida(c2, ahora=1000.0)
    ok(antitrampa.juzgar_cartel(c2, 7200, 500, 95, 80, 77, ahora=1200.0) is False, "reloj lento -> sólo avisar")
    ok(marcas_guardadas()[-1]["regla"] == "reloj_lento", "…pero queda anotado")
    c3 = Conn()
    antitrampa.marcar_salida(c3, ahora=1000.0)
    ok(antitrampa.juzgar_cartel(c3, 7200, 500, 95, 80, 77, ahora=1121.0) is False, "revés: carrera limpia")
    ok(antitrampa.juzgar_cartel(c3, 7300, 500, 95, 80, 77, ahora=5000.0) is False,
       "un FF28 sin GO nuevo no se compara con el GO viejo")


def probar_ff3d():
    print("FF3D(0) repetido:")
    antitrampa._avisar_gms = lambda texto: None
    c = Conn()
    antes = len(marcas_guardadas())
    for _ in range(antitrampa.ANTITRAMPA_FF3D0_MIN - 1):
        antitrampa.al_ff3d(c, b"\x00")
    antitrampa.al_ff3d(c, b"\x01")
    ok(len(marcas_guardadas()) == antes, "revés: un cambio de canal (00 y 01) no marca")
    for _ in range(5):
        antitrampa.al_ff3d(c, b"\x00")
    nuevas = marcas_guardadas()[antes:]
    ok(len(nuevas) == 1 and nuevas[0]["regla"] == "animaciones_tocadas", "una sola marca por sesión")


def probar_cliente():
    print("lo que informa la dll (FF59 «R2AT …»):")
    avisos = []
    antitrampa._avisar_gms = avisos.append
    notas.combo_total_de = lambda cancion: 600

    class Otro(Conn):
        usn = 5151

    c = Otro()

    def nuevas(desde):
        return [m["regla"] for m in marcas_guardadas()[desde:]]

    ok(antitrampa.al_ff59(c, "USN:5151\nc2DImage::LoadImage - rnr_bg/x.tga") is False,
       "revés: un FF59 normal no es del antitrampa")
    n0 = len(marcas_guardadas())
    ok(antitrampa.juzgar_cartel(c, 60, 10, 90, 50, 77) is False, "sin «hola» la carrera se paga…")
    antitrampa.juzgar_cartel(c, 120, 11, 90, 50, 77)
    ok(nuevas(n0) == ["sin_antitrampa"], "…pero se anota UNA vez que no mandó el «hola»")
    n0 = len(marcas_guardadas())
    antitrampa.al_ff59(c, "USN:5151\nR2AT v=1 exe=0123456789abcdef0123456789abcdef previo=2 previo_va=0x00501000")
    ok(nuevas(n0) == ["exe_desconocido", "codigo_previo"], "«hola» con otro exe y el exe ya tocado")
    n0, a0 = len(marcas_guardadas()), len(avisos)
    antitrampa.al_ff59(c, "USN:5151\nR2AT codigo=0x00505447 paginas=1 bytes=E9_11_22_33_44_00_00_00")
    ok(nuevas(n0) == ["codigo_modificado"] and "E9 11 22 33 44" in avisos[a0], "código tocado: el GM ve los bytes")
    ok(antitrampa.juzgar_cartel(c, 180, 12, 90, 50, 77) is False, "«codigo_modificado» sólo avisa: se paga")
    antitrampa.al_ff59(c, "USN:5151\nR2AT modulo=toolbitdll.dll")
    ok(marcas_guardadas()[-1]["regla"] == "modulo_prohibido", "un módulo de trampas queda anotado")
    ok(antitrampa.juzgar_cartel(c, 240, 13, 90, 50, 77) is True, "…y retiene la carrera siguiente aunque esté limpia")
    ok(antitrampa.juzgar_cartel(Conn(), 240, 13, 90, 50, 77) is False, "revés: a otra cuenta no la toca")
    antitrampa.al_ff59(c, f"USN:5151\nR2AT v=1 exe={EXE_BUENO} previo=0")
    ok(antitrampa.juzgar_cartel(c, 300, 14, 90, 50, 77) is False, "un «hola» nuevo (juego reabierto) la libera")


def probar_cartel():
    print("el cartel (h_21_ff28) no paga lo retenido:")
    from servidor import lobby_carrera
    pagos = []
    lobby_carrera.db_add_exp = lambda usn, n: pagos.append(("exp", usn, n)) or 0
    lobby_carrera.db_add_rcoin = lambda usn, n: pagos.append(("rcoin", usn, n)) or 0
    antitrampa._avisar_gms = lambda texto: None
    notas.combo_total_de = lambda cancion: 600

    def correr(combo, frame):
        c = Conn()
        c.room_song = 77
        antitrampa.marcar_salida(c)
        pagos.clear()
        lobby_carrera.h_21_ff28(c, 0x28, struct.pack("<IHBBHH", frame, combo, 95, 80, 10, 0) + b"0" * 32)
        return c

    c = correr(combo=601, frame=60)
    ok(pagos == [], "combo imposible: ni exp ni Rcoin")
    ok(any(cmd == 0x28 for cmd, _n in c.enviados), "…y el cartel igual sale (el cliente no queda colgado)")
    correr(combo=500, frame=60)
    ok(any(k == "exp" for k, _u, _n in pagos) and any(k == "rcoin" for k, _u, _n in pagos),
       "revés: un reporte limpio cobra")

    def ff59(texto):
        cuerpo = f"USN:{Conn.usn} TIME:x SERVER:y\n{texto}".encode("cp1252")
        lobby_carrera.h_24_ff59(Conn(), 0x59, struct.pack("<H", len(cuerpo)) + cuerpo)

    ff59("R2AT modulo=r2mods.dll")
    correr(combo=500, frame=61)
    ok(pagos == [], "con R2Mods informado por el FF59, la carrera limpia tampoco cobra")
    ff59(f"R2AT v=1 exe={EXE_BUENO} previo=0")
    correr(combo=500, frame=62)
    ok(any(k == "exp" for k, _u, _n in pagos), "revés: tras reabrir el juego limpio, vuelve a cobrar")


def main():
    try:
        probar_reglas()
        probar_juzgar()
        probar_ff3d()
        probar_cliente()
        probar_cartel()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    if FALLAS:
        print(f"\n{len(FALLAS)} prueba(s) MAL")
        return 1
    print("\ntodo bien")
    return 0


if __name__ == "__main__":
    sys.exit(main())
