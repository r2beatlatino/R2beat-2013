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
import time

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
    ok(antitrampa.juzgar_cartel(c, 300, 14, 90, 50, 77) is False,
       "★ 19-nov sin bloqueo por tiempo: reabrir el juego limpio vuelve a cobrar")
    antitrampa._BLOQUEADOS[5151] = time.monotonic() + 600                  # con ANTITRAMPA_BLOQUEO_S puesto, como antes
    ok(antitrampa.juzgar_cartel(c, 360, 15, 90, 50, 77) is True, "con bloqueo por tiempo, aunque reabra, no cobra")
    antitrampa._BLOQUEADOS[5151] = 0
    ok(antitrampa.juzgar_cartel(c, 420, 16, 90, 50, 77) is False, "pasado el bloqueo, y con el juego limpio, cobra")


class Socket:
    def __init__(self):
        self.cerrado = False

    def shutdown(self, como):
        self.cerrado = True


def jugador(usn):
    c = Conn()
    c.usn = usn
    c.conn = Socket()
    antitrampa.al_ff59(c, f"R2AT v=1 exe={EXE_BUENO} previo=0")
    return c


def correr_carreras(c, n, cancion=lambda i: 77 + i, combo=lambda i: 300 + i, pd=lambda i: 90,
                    reaccion=lambda i: 3.0 + (i * 7919 % 13), antes=lambda i: None, t0=10_000.0):
    """n carreras con su «listo» antes de cada una (salvo la primera). Devuelve lo que dijo juzgar_cartel."""
    t, retenidas = t0, []
    for i in range(n):
        antes(i)
        if i:
            t += reaccion(i)
            antitrampa.al_listo(c, ahora=t)
        t += 120
        retenidas.append(antitrampa.juzgar_cartel(c, 7000 + i, combo(i), pd(i), 50, cancion(i), ahora=t))
    return retenidas


def reglas_de(usn):
    return [m["regla"] for m in marcas_guardadas() if m["usn"] == usn]


def probar_farmeo():
    print("señales de farmeo:")
    avisos, cerrados = [], []
    antitrampa._avisar_gms = avisos.append
    notas.combo_total_de = lambda cancion: 2000
    niveles = {}
    notas.nivel_de = lambda cancion, por_defecto=None: niveles.get(cancion, por_defecto)

    c = jugador(6001)
    correr_carreras(c, 12, reaccion=lambda i: 2.0 + (0.05 if i % 2 else -0.05))
    ok("listo_automatico" in reglas_de(6001), "«listo» siempre a los 2,0 s ± 0,05 = listo automático")
    c = jugador(6002)
    correr_carreras(c, 12)
    ok("listo_automatico" not in reglas_de(6002), "revés: una persona tarda distinto cada vez")

    c = jugador(6003)
    correr_carreras(c, antitrampa.ANTITRAMPA_SIN_HABLAR)
    ok("carreras_sin_hablar" in reglas_de(6003), f"{antitrampa.ANTITRAMPA_SIN_HABLAR} carreras sin chat")
    c = jugador(6004)
    correr_carreras(c, antitrampa.ANTITRAMPA_SIN_HABLAR, antes=lambda i: i % 10 == 5 and antitrampa.al_hablar(c))
    ok("carreras_sin_hablar" not in reglas_de(6004), "revés: escribe en el chat de vez en cuando")

    c = jugador(6005)
    correr_carreras(c, antitrampa.ANTITRAMPA_MISMA_CANCION, cancion=lambda i: 500)
    ok("misma_cancion" in reglas_de(6005), "la misma canción muchas veces seguidas")

    c = jugador(6006)
    correr_carreras(c, 8, antes=lambda i: antitrampa.al_campana(c))
    ok("campanas_automaticas" in reglas_de(6006), "campana en cada ronda")
    c = jugador(6007)
    correr_carreras(c, 8, antes=lambda i: i % 3 == 0 and antitrampa.al_campana(c))
    ok("campanas_automaticas" not in reglas_de(6007), "revés: campana de vez en cuando")

    c = jugador(6008)
    correr_carreras(c, 5, combo=lambda i: 450)
    ok("combo_repetido" in reglas_de(6008), "combo 450 exacto en canciones distintas (fallar al llegar a N)")
    c = jugador(6009)
    correr_carreras(c, 5, combo=lambda i: 450, cancion=lambda i: 900)
    ok("combo_repetido" not in reglas_de(6009), "revés: el mismo combo repitiendo LA MISMA canción es normal")

    niveles.update({1000 + i: 2 + i for i in range(12)})
    c = jugador(6010)
    correr_carreras(c, 10, cancion=lambda i: 1000 + i, pd=lambda i: 97)
    ok("precision_constante" in reglas_de(6010), "97 % igual del nivel 2 al 11 = automático calibrado")
    c = jugador(6011)
    correr_carreras(c, 10, cancion=lambda i: 1000 + i, pd=lambda i: 99 - 2 * i)
    ok("precision_constante" not in reglas_de(6011), "revés: una persona baja en las difíciles")

    for i in range(antitrampa.ANTITRAMPA_EXPULSIONES):
        antitrampa.al_expulsar_espectador(c, ahora=50_000.0 + i)
    ok("expulsa_espectadores" in reglas_de(6011), "espectadores echados en serie (sólo se registra)")

    c = jugador(6014)
    antitrampa.al_ff59(c, "R2AT teclas=300 inyectadas=280")
    antitrampa.al_ff59(c, "R2AT hilo=0x00D90000")
    ok(reglas_de(6014)[-2:] == ["teclas_inyectadas", "hilo_ajeno"] and not antitrampa.fue_expulsado(c),
       "teclas inyectadas y un hilo ajeno avisan, sin expulsar")

    print("expulsión por farmeo (dos señales):")
    from servidor import salas

    class TimerYa:
        def __init__(self, s, f, args):
            self.f, self.args, self.daemon = f, args, True

        def start(self):
            cerrados.append(self.args[1])
            self.f(*self.args)

    antitrampa.threading.Timer = TimerYa
    c = jugador(6012)
    otro = jugador(6099)
    salas.CONEXIONES.update({6012: c, 6099: otro})
    try:
        retenidas = correr_carreras(c, 15, cancion=lambda i: 500, reaccion=lambda i: 2.0)
    finally:
        salas.CONEXIONES.pop(6012, None)
        salas.CONEXIONES.pop(6099, None)
    r = reglas_de(6012)
    ok("farmeo" in r and r.index("farmeo") > r.index("listo_automatico"), "listo automático + otra señal = farmeo")
    ok(any(retenidas) and retenidas[-1] is True, "la carrera del farmeo no cobra")
    ok(c.conn.cerrado and c.cerrado, "se le cierra la conexión")
    ok(any("detectado por usar trampas" in n for _cmd, n in otro.enviados), "los demás ven el anuncio público")
    ok(any("expulsado" in n for _cmd, n in c.enviados), "él ve por qué lo expulsaron")
    ok(antitrampa.fue_expulsado(c), "y queda anotado como expulsado")
    ok(not antitrampa.fue_expulsado(jugador(6013)), "revés: otra cuenta no queda expulsada")
    ok(antitrampa.juzgar_cartel(c, 99_999, 10, 90, 50, 77) is True, "si vuelve a reportar estando bloqueado, no cobra")

    c = jugador(6015)
    correr_carreras(c, 9, reaccion=lambda i: 2.0)
    antitrampa.al_ff59(c, "R2AT teclas=500 inyectadas=480")
    ok(reglas_de(6015)[-1] == "farmeo" and antitrampa.fue_expulsado(c),
       "listo automático + teclas inyectadas = farmeo y expulsión")
    c = jugador(6016)
    antitrampa.al_ff59(c, "R2AT proceso=cheatengine-i386.exe")
    ok(reglas_de(6016)[-1] == "proceso_prohibido" and antitrampa.fue_expulsado(c), "Cheat Engine abierto = expulsión")

    print("el gancho del juego automático (Ñ2Hock, R2Beat.exe+0x1080B5):")
    c = jugador(6017)
    antitrampa.al_ff59(c, "R2AT gancho=automatico va=0x005080B5 bytes=E9_46_81_B2_31_90_90_6A")
    ok(reglas_de(6017)[-1] == "juego_automatico" and antitrampa.fue_expulsado(c), "«gancho=automatico» = expulsión")
    c = jugador(6018)
    antitrampa.al_ff59(c, "R2AT codigo=0x005080B5 paginas=4 bytes=E9_46_81_B2_31_90_90_6A")
    ok(reglas_de(6018)[-1] == "juego_automatico" and antitrampa.fue_expulsado(c),
       "una dll vieja que lo manda como «codigo=0x005080B5» también expulsa")
    c = jugador(6019)
    antitrampa.al_ff59(c, "R2AT codigo=0x00494E76 paginas=17 bytes=E9_85_B1_BC_03_00_6A_1D")
    ok(reglas_de(6019)[-1] == "codigo_modificado" and not antitrampa.fue_expulsado(c),
       "revés: los otros parches de Ñ2Hock (far, teclado…) sólo avisan")
    c = jugador(6023)
    antitrampa.al_ff59(c, "R2AT modulo=toolbitpracticeengine_0123456789ab.dll")
    ok(reglas_de(6023)[-1] == "modulo_permitido" and not antitrampa.fue_expulsado(c),
       "revés: el motor de práctica de Ñ2Hock (ToolBitPracticeEngine) no expulsa")
    antitrampa.al_ff59(c, "R2AT modulo=toolbitdll.dll")
    ok(reglas_de(6023)[-1] == "modulo_prohibido", "…pero el ToolBit de trampas sí")
    c = jugador(6020)
    antitrampa.al_ff59(c, "R2AT gancho=sala va=0x005AEDD4 bytes=E9_27_12_78_03_90_6A_07")
    ok(reglas_de(6020)[-1] == "sala_automatica" and antitrampa.fue_expulsado(c),
       "Auto Listo / Anfitrión al azar / Misma canción («gancho=sala») = expulsión")
    c = jugador(6021)
    antitrampa.al_ff59(c, "R2AT codigo=0x005AEDD4 paginas=1 bytes=E9_27_12_6F_03_90_6A_07")
    ok(reglas_de(6021)[-1] == "sala_automatica" and antitrampa.fue_expulsado(c),
       "la dll vieja lo manda como «codigo=0x005AEDD4» (medido 19-nov) y también expulsa")
    c = jugador(6022)
    antitrampa.al_ff59(c, "R2AT gancho=relevo va=0x00505340 bytes=E9_00_00_00_00_90_90_90")
    ok(reglas_de(6022)[-1] == "relevo_automatico" and antitrampa.fue_expulsado(c), "pisar el gancho del relevo = expulsión")

    print("la escalera (por cuenta): 1.ª fuera · 2.ª advertencia · 3.ª baneo permanente:")
    from servidor import almacen, basedatos
    usn, motivo = basedatos.cuenta_crear("tramposo", "A" * 64)
    ok(usn is not None, f"creo la cuenta de prueba ({motivo or 'ok'})")
    ok(not antitrampa.esta_bloqueado(jugador(usn)), "revés: sin faltas, nada")
    textos = []
    for vez in range(1, 4):
        c = jugador(usn)
        salas.CONEXIONES[usn] = c
        try:
            antitrampa.al_ff59(c, "R2AT gancho=automatico va=0x005080B5 bytes=E9_46_81_B2_31_90_90_6A")
        finally:
            salas.CONEXIONES.pop(usn, None)
        textos.append(" ".join(n for _cmd, n in c.enviados))
        ok(c.conn.cerrado, f"{vez}.ª: lo saca del juego")
        ok(not antitrampa.esta_bloqueado(c), f"{vez}.ª: sin bloqueo de 10 min")
        ph = almacen.conectar().execute("SELECT pass_hash FROM users WHERE username='tramposo'").fetchone()["pass_hash"]
        ok(ph.startswith("BANNED:") == (vez == 3), f"{vez}.ª: {'BANEADA' if vez == 3 else 'la cuenta sigue activa'}")
    ok("expulsado" in textos[0] and "ADVERTENCIA" not in textos[0] and "BANEADA" not in textos[0],
       "1.ª: sólo «fuiste expulsado»")
    ok("ADVERTENCIA" in textos[1] and "baneada para siempre" in textos[1], "2.ª: con la advertencia")
    ok("BANEADA PERMANENTEMENTE" in textos[2], "3.ª: le dice que quedó baneada")
    ok(almacen.conectar().execute("SELECT faltas FROM antitrampa_faltas WHERE username='tramposo'").fetchone()[0] == 3,
       "las faltas quedan en la base (sobreviven a reiniciar el server)")
    ok(almacen.conectar().execute("SELECT COUNT(*) FROM antitrampa_faltas WHERE username<>'tramposo'").fetchone()[0]
       == 0, "revés: los jugadores sin cuenta en la base no suman faltas a nadie")
    usn2, _m = basedatos.cuenta_crear("doble", "B" * 64)
    c = jugador(usn2)
    antitrampa.al_ff59(c, "R2AT gancho=automatico va=0x005080B5 bytes=E9_46_81_C0_00_90_90_6A")
    antitrampa.al_ff59(c, "R2AT gancho=sala va=0x005AEDD4 bytes=E9_27_12_B4_00_90_6A_07")
    ok(almacen.conectar().execute("SELECT faltas FROM antitrampa_faltas WHERE username='doble'").fetchone()[0] == 1,
       "dos funciones prendidas en la MISMA sesión (medido 19-nov) = UNA sola falta")
    c = jugador(usn2)                                                       # reabre el juego: otra sesión
    antitrampa.al_ff59(c, "R2AT gancho=sala va=0x005AEDD4 bytes=E9_27_12_B4_00_90_6A_07")
    ok(almacen.conectar().execute("SELECT faltas FROM antitrampa_faltas WHERE username='doble'").fetchone()[0] == 2,
       "al reabrir el juego y volver a hacerlo, sí suma la segunda")


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
    antitrampa._BLOQUEADOS[Conn.usn] = 0
    correr(combo=500, frame=62)
    ok(any(k == "exp" for k, _u, _n in pagos), "revés: pasado el bloqueo y con el juego limpio, vuelve a cobrar")


def probar_catalogo():
    print("el catálogo del panel (servidor/antitrampa_catalogo.json) sigue al código:")
    with open(os.path.join(RAIZ, "servidor", "antitrampa_catalogo.json"), encoding="utf-8") as f:
        cat = json.load(f)
    ids = {r["id"]: r for r in cat["reglas"]}
    ok(set(ids) == set(antitrampa.ANTITRAMPA_REGLAS),
       f"las mismas reglas (sobran {sorted(set(ids) - set(antitrampa.ANTITRAMPA_REGLAS))}, "
       f"faltan {sorted(set(antitrampa.ANTITRAMPA_REGLAS) - set(ids))})")
    ok(all(ids[r]["accion"] == a for r, a in antitrampa.ANTITRAMPA_REGLAS.items() if r in ids),
       "con la misma acción por defecto")
    ok({int(g["va"], 16): g["id"] for g in cat["ganchos"]} == antitrampa.ANTITRAMPA_GANCHOS, "y los mismos ganchos")
    ok(len(cat["escalera"]) == antitrampa.ANTITRAMPA_BANEO_EN, "y la escalera llega al baneo")


def probar_coordinador():
    print("con pases y Coordinador (el server avisa; el Coordinador cuenta y banea):")
    import urllib.error
    from servidor import almacen, basedatos, pase, salas

    class TimerYa:
        def __init__(self, s, f, args):
            self.f, self.args, self.daemon = f, args, True

        def start(self):
            self.f(*self.args)

    class FakeResp:
        def __init__(self, status, data):
            self.status = status
            self._raw = json.dumps(data, ensure_ascii=False).encode("utf-8")

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    antitrampa._avisar_gms = lambda texto: None
    antitrampa.threading.Timer = TimerYa
    urlopen_orig = pase.urllib.request.urlopen
    claves_env = ("R2_LOGIN", "R2_CUENTAS_URL", "R2_CUENTAS_FICHA_INTERNA", "R2_PASE_JUEGO")
    env_prev = {k: os.environ.get(k) for k in claves_env}
    pedidos = []
    modo_http = {"caido": False, "faltas": {}}

    def fake_urlopen(req, timeout=None):
        cuerpo = json.loads((req.data or b"{}").decode("utf-8"))
        cabs = {k.lower(): v for k, v in req.header_items()}
        pedidos.append({"url": req.full_url, "metodo": req.get_method(), "cabs": cabs,
                        "cuerpo": cuerpo, "timeout": timeout})
        if modo_http["caido"]:
            raise urllib.error.URLError("coordinador caído")
        clave = (cuerpo["enenos_id"], cuerpo["juego"])
        n = modo_http["faltas"].get(clave, 0) + 1
        modo_http["faltas"][clave] = n
        esc = "baneo" if n >= 3 else ("advertencia" if n == 2 else "expulsado")
        return FakeResp(200, {"ok": True, "faltas": n, "escalon": esc, "baneada": n >= 3})

    try:
        pase.urllib.request.urlopen = fake_urlopen
        # Creamos una cuenta vieja sin enenos_id antes de activar R2_LOGIN=pase
        os.environ.pop("R2_LOGIN", None)
        usn_vieja, _ = basedatos.cuenta_crear("vieja_sin_eid", "C" * 64)
        usn_sin_pase, _ = basedatos.cuenta_crear("uid_10001368", "D" * 64)

        os.environ.update(
            R2_LOGIN="pase",
            R2_CUENTAS_URL="http://coordinador.prueba",
            R2_CUENTAS_FICHA_INTERNA="ficha-prueba-at",
            R2_PASE_JUEGO="r2beat2013-prueba",
        )
        usn_pase, nombre_pase = almacen.asegurar_cuenta_uid(10001366)
        basedatos.db_save_uno(usn_pase, {"char_id": 130900, "nick": "PaseNick", "gender": 0, "parts": []})
        ok(usn_pase is not None and nombre_pase == "uid_10001366", "creo cuenta de pase (uid_10001366)")

        textos, anuncios_pub = [], []
        for vez in range(1, 4):
            c = jugador(usn_pase)
            otro = jugador(6199)
            salas.CONEXIONES.update({usn_pase: c, 6199: otro})
            try:
                antitrampa.al_ff59(c, "R2AT gancho=automatico va=0x005080B5 bytes=E9_46_81_B2_31_90_90_6A")
            finally:
                salas.CONEXIONES.pop(usn_pase, None)
                salas.CONEXIONES.pop(6199, None)
            textos.append(" ".join(n for _cmd, n in c.enviados))
            anuncios_pub.append(" ".join(n for _cmd, n in otro.enviados))
            ok(c.conn.cerrado, f"con pase ({vez}.ª): sigue echando de la partida")
            ph = almacen.conectar().execute("SELECT pass_hash FROM users WHERE username=?",
                                            (nombre_pase,)).fetchone()["pass_hash"]
            ok(not str(ph or "").startswith("BANNED:"),
               f"con pase ({vez}.ª): NO escribe BANNED: en users.pass_hash local")
            f_loc = almacen.conectar().execute("SELECT faltas FROM antitrampa_faltas WHERE username=?",
                                               (nombre_pase,)).fetchone()
            ok(f_loc is None, f"con pase ({vez}.ª): NO suma en antitrampa_faltas local")

        ok(len(pedidos) == 3 and all(p["metodo"] == "POST" and p["url"].endswith("/interno/antitrampa")
                                     and p["cabs"].get("x-r2") == "1"
                                     and p["cabs"].get("x-ficha-interna") == "ficha-prueba-at"
                                     and p["timeout"] == 3.0
                                     and p["cuerpo"]["enenos_id"] == 10001366
                                     and p["cuerpo"]["juego"] == "r2beat2013-prueba"
                                     and p["cuerpo"]["regla"] == "juego_automatico"
                                     and p["cuerpo"]["nick"] == "PaseNick"
                                     and p["cuerpo"]["detalle"]
                                     for p in pedidos),
           "mandó 3 POST internos con ficha, timeout 3 s, enenos_id, juego, regla, detalle y nick")
        ok("expulsado" in textos[0] and "ADVERTENCIA" not in textos[0] and "BANEADA" not in textos[0],
           "con pase (1.ª): aviso de expulsión")
        ok("ADVERTENCIA" in textos[1] and "baneada para siempre" in textos[1],
           "con pase (2.ª): aviso de advertencia")
        ok("BANEADA PERMANENTEMENTE" in textos[2] and "baneado permanentemente" in anuncios_pub[2],
           "con pase (3.ª): respuesta «baneada» del Coordinador arma el aviso y anuncio de baneo")

        # Coordinador caído: sólo expulsar, nunca banear localmente ni sumar en base local
        modo_http["caido"] = True
        usn_caido, nombre_caido = almacen.asegurar_cuenta_uid(10001367)
        textos_c = []
        for vez in range(1, 4):
            c = jugador(usn_caido)
            salas.CONEXIONES[usn_caido] = c
            try:
                antitrampa.al_ff59(c, "R2AT gancho=automatico va=0x005080B5 bytes=E9_46_81_B2_31_90_90_6A")
            finally:
                salas.CONEXIONES.pop(usn_caido, None)
            textos_c.append(" ".join(n for _cmd, n in c.enviados))
            ph = almacen.conectar().execute("SELECT pass_hash FROM users WHERE username=?",
                                            (nombre_caido,)).fetchone()["pass_hash"]
            ok(c.conn.cerrado and not str(ph or "").startswith("BANNED:"),
               f"Coordinador caído ({vez}.ª): expulsa pero NUNCA escribe BANNED: localmente")
        ok(all("expulsado" in t and "ADVERTENCIA" not in t and "BANEADA" not in t for t in textos_c),
           "Coordinador caído: trata cada falta como 1.ª (sólo expulsar)")
        ok(almacen.conectar().execute("SELECT 1 FROM antitrampa_faltas WHERE username=?",
                                      (nombre_caido,)).fetchone() is None,
           "Coordinador caído: tampoco suma en antitrampa_faltas local")

        # Revés 1: cuenta vieja sin uid_ ni enenos_id en modo pase -> mantiene baneo local
        modo_http["caido"] = False
        n_ped_antes = len(pedidos)
        for _ in range(3):
            c = jugador(usn_vieja)
            antitrampa.al_ff59(c, "R2AT gancho=automatico va=0x005080B5 bytes=E9_46_81_B2_31_90_90_6A")
        ph_v = almacen.conectar().execute("SELECT pass_hash FROM users WHERE username='vieja_sin_eid'").fetchone()["pass_hash"]
        ok(len(pedidos) == n_ped_antes and ph_v.startswith("BANNED:"),
           "revés: cuenta vieja sin uid_/enenos_id sigue con el baneo local (sin avisar al Coordinador)")

        # Revés 2: sin pases (R2_LOGIN vacío) -> baneo local de siempre (BANNED:), sin HTTP
        os.environ["R2_LOGIN"] = ""
        n_ped_antes = len(pedidos)
        for _ in range(3):
            c = jugador(usn_sin_pase)
            antitrampa.al_ff59(c, "R2AT gancho=automatico va=0x005080B5 bytes=E9_46_81_B2_31_90_90_6A")
        ph_l = almacen.conectar().execute("SELECT pass_hash FROM users WHERE username='uid_10001368'").fetchone()["pass_hash"]
        f_l = almacen.conectar().execute("SELECT faltas FROM antitrampa_faltas WHERE username='uid_10001368'").fetchone()
        ok(len(pedidos) == n_ped_antes and ph_l.startswith("BANNED:") and f_l and int(f_l["faltas"]) == 3,
           "revés: sin pases (R2_LOGIN vacío) mantiene el baneo local (BANNED:) y no manda HTTP")
    finally:
        pase.urllib.request.urlopen = urlopen_orig
        for k, v in env_prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main():
    try:
        probar_catalogo()
        probar_reglas()
        probar_juzgar()
        probar_ff3d()
        probar_cliente()
        probar_farmeo()
        probar_coordinador()
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
