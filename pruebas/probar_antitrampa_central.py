#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probar_antitrampa_central — el REGISTRO CENTRAL, la telemetría de la dll, las acciones y el TABLERO (26-nov-2026).

    python pruebas/probar_antitrampa_central.py

Sin el juego: la base, el log y el jsonl van a una carpeta temporal. El tablero se levanta DE VERDAD (HTTP en un puerto
libre de 127.0.0.1) y se le habla como lo haría el navegador. Cada cosa con su revés.
"""
import http.cookiejar
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="r2b_at_central_")
os.environ.update(R2_BASE=os.path.join(TMP, "datos.db"), R2_CHARS_DB=os.path.join(TMP, "chars_db.json"),
                  R2_CUENTAS=os.path.join(TMP, "cuentas.json"), R2_SESIONES=os.path.join(TMP, "sesiones.json"),
                  R2_LOG=os.path.join(TMP, "servidor.log"), R2_STATUS=os.path.join(TMP, "status.json"),
                  R2_ANTITRAMPA=os.path.join(TMP, "antitrampa.jsonl"), R2_LOG_CONSOLA="0",
                  R2_TABLERO_ADMINS="ana:clave-de-prueba-larga,corta:123", PYTHONIOENCODING="utf-8")
sys.path.insert(0, RAIZ)

from servidor import almacen, antitrampa, antitrampa_eventos as eventos, basedatos, notas, salas   # noqa: E402

notas.duracion_minima_de = lambda cancion: None
EXE_BUENO = next(iter(antitrampa.ANTITRAMPA_EXE_MD5))
FALLAS = []


def ok(cond, que):
    print(("  ok  " if cond else "  MAL ") + que)
    if not cond:
        FALLAS.append(que)


class Socket:
    def __init__(self):
        self.cerrado = False

    def shutdown(self, _como):
        self.cerrado = True


class Conn:
    room_id = None
    room_mode = 0
    room_colab = False

    def __init__(self, usn):
        self.usn = usn
        self.conn = Socket()
        self.enviados = []
        self.addr = ("127.0.0.1", 5000)

    def send_ff55(self, cmd, body, name=""):
        self.enviados.append((cmd, name))


def cuenta(nombre):
    usn, _m = basedatos.cuenta_crear(nombre, nombre[0].upper() * 64)
    return usn


def evs(**f):
    eventos.esperar()
    return almacen.ev_listar(f, 500)


def hola(c, extra=""):
    antitrampa.al_ff59(c, f"USN:{c.usn}\nR2AT v=1 exe={EXE_BUENO} previo=0 dll=abc123 lat=60{extra}")


# ═══ 1 · el parser de los R2AT ═══════════════════════════════════════════════════════════════════════════════════
def probar_parser():
    print("los renglones R2AT (antes: sólo el primero de cada FF59, y los valores se cortaban en el espacio):")
    r = antitrampa.leer_r2at("USN:5\nR2AT proceso=Cheat Engine.exe firma=Candy s=4 t=99\nR2AT hilo=0x1234 s=5")
    ok(len(r) == 2, "dos renglones en un FF59 = dos renglones")
    ok(r[0][0].get("proceso") == "Cheat Engine.exe" and r[0][0].get("firma") == "Candy",
       "un valor con espacio llega entero («Cheat Engine.exe»)")
    ok(r[1][0] == {"hilo": "0x1234", "s": "5"}, "y el segundo, con su secuencia")
    ok(antitrampa.leer_r2at("USN:5\nnada que ver") == [], "revés: un FF59 sin R2AT no es del antitrampa")


# ═══ 2 · el registro central ══════════════════════════════════════════════════════════════════════════════════════
def probar_registro():
    print("el registro central (antitrampa_eventos):")
    usn = cuenta("registro")
    c = Conn(usn)
    c.room_id, c.game_magic = 7, 0xABCDEF01
    hola(c)
    antitrampa.al_ff59(c, "R2AT modulo=speedhack.dll s=2")
    e = evs(cuenta="registro", regla="modulo_prohibido")
    ok(len(e) == 1, "la detección queda como UN evento en la base")
    e = e[0]
    campos = ("evento", "usn", "cuenta", "nick", "sesion", "partida", "cuando", "categoria", "regla", "modulo",
              "descripcion", "evidencia", "riesgo", "confianza", "reincidencias", "version_cliente",
              "version_antitrampa", "estado")
    ok(all(k in e for k in campos), "con todos los campos pedidos")
    ok(len(e["evento"]) == 32 and e["usn"] == usn and e["cuenta"] == "registro", "id único, usn y cuenta")
    ok(e["categoria"] == "dll_no_autorizada" and e["riesgo"] == "alto" and e["origen"] == "cliente",
       "categoría, riesgo y origen (lo declara la dll)")
    ok(e["partida"] == "7:abcdef01" and e["sesion"], "la sesión del juego y la partida (sala:corrida)")
    ok("exe " in (e["version_cliente"] or "") and "dll abc123" in (e["version_antitrampa"] or ""),
       "las versiones del cliente y del antitrampa")
    ok("speedhack.dll" in e["evidencia"] and e["estado"] == "nuevo", "la evidencia (el renglón) y el estado nuevo")
    antitrampa.al_ff59(c, "R2AT modulo=speedhack.dll s=3")
    antitrampa.al_ff59(c, "R2AT modulo=speedhack.dll s=4")
    e = evs(cuenta="registro", regla="modulo_prohibido")
    ok(len(e) == 1 and e[0]["repeticiones"] == 3, "la misma detección persistente NO duplica: suma repeticiones (3)")
    antitrampa.al_ff59(c, "R2AT modulo=otrohack.dll s=5")
    ok(len(evs(cuenta="registro", regla="modulo_prohibido")) == 2, "revés: OTRO módulo sí es otro evento")
    hola(c)                                                          # el juego reabierto: sesión nueva
    antitrampa.al_ff59(c, "R2AT modulo=speedhack.dll s=2")
    e = evs(cuenta="registro", regla="modulo_prohibido")
    ok(len(e) == 3 and e[0]["reincidencias"] == 2, "en otra sesión es un evento nuevo, con sus reincidencias (2)")
    lineas = [json.loads(x) for x in open(antitrampa.ANTITRAMPA_ARCHIVO, encoding="utf-8")]
    ok(any(x.get("evento") == e[0]["evento"] for x in lineas), "y el jsonl de siempre lleva el mismo id")


# ═══ 3 · la telemetría ════════════════════════════════════════════════════════════════════════════════════════════
def probar_telemetria():
    print("la telemetría de la dll (tope, secuencia, latido, reloj):")
    usn = cuenta("telemetria")
    c = Conn(usn)
    hola(c, " s=1")
    antes = len(evs(cuenta="telemetria"))
    for i in range(antitrampa.ANTITRAMPA_R2AT_POR_MINUTO + 15):
        antitrampa.al_ff59(c, f"R2AT memoria=0x{0x10000000 + i:08X} regiones=1 s={i + 2}")
    e = evs(cuenta="telemetria")
    ok(len([x for x in e if x["regla"] == "telemetria_inundada"]) == 1, "una inundación de renglones: UNA marca")
    est = antitrampa.estado_de(usn)
    ok(est["descartados"] >= 15, f"y los de más se descartan ({est['descartados']})")
    ok(len(e) - antes <= antitrampa.ANTITRAMPA_R2AT_POR_MINUTO + 2, "revés: no entran miles de eventos")

    usn2 = cuenta("secuencia")
    c2 = Conn(usn2)
    hola(c2, " s=1")
    antitrampa.al_ff59(c2, "R2AT hilo=0x00AA0000 s=2")
    antitrampa.al_ff59(c2, "R2AT hilo=0x00BB0000 s=2")           # repetido / fabricado
    e = evs(cuenta="secuencia")
    ok(any(x["regla"] == "telemetria_repetida" for x in e), "una secuencia ya vista: telemetria_repetida")
    ok(not any("00BB0000" in x["descripcion"] for x in e), "y el renglón repetido no se cree")
    antitrampa.al_ff59(c2, "R2AT hilo=0x00CC0000 s=9")
    ok(antitrampa.estado_de(usn2)["perdidos"] == 6, "un salto de secuencia cuenta los renglones perdidos (6)")

    usn3 = cuenta("latido")
    c3 = Conn(usn3)
    hola(c3)
    t0 = time.monotonic()
    ok(antitrampa.revisar_latidos({usn3: c3}, ahora=t0 + 60) == 0, "revés: con latido reciente no marca nada")
    ok(antitrampa.revisar_latidos({usn3: c3}, ahora=t0 + antitrampa.ANTITRAMPA_LATIDO_TOPE_S + 5) == 1,
       "sin latido más que el tope, con el juego conectado: telemetria_interrumpida")
    ok(antitrampa.revisar_latidos({usn3: c3}, ahora=t0 + antitrampa.ANTITRAMPA_LATIDO_TOPE_S + 60) == 0,
       "una sola vez (no se repite mientras siga callada)")
    ok(antitrampa.estado_de(usn3)["estado"] == "activo", "revés: con el latido reciente, el tablero la ve activa")
    with antitrampa._cuentas_lock:                                   # el reloj de verdad: su último latido, atrás
        antitrampa._CUENTAS[usn3]["ult_latido"] -= antitrampa.ANTITRAMPA_LATIDO_TOPE_S + 10
    ok(antitrampa.estado_de(usn3)["estado"] == "callado", "sin latido, el tablero la ve «callado»")
    usn4 = cuenta("viejo")
    c4 = Conn(usn4)
    antitrampa.al_ff59(c4, f"R2AT v=1 exe={EXE_BUENO} previo=0")    # una dll vieja: sin lat=
    ok(antitrampa.revisar_latidos({usn4: c4}, ahora=time.monotonic() + 3600) == 0,
       "revés: una dll vieja (sin «lat=») no se marca por no latir")

    # el reloj de la PC entre latidos (t= al mandar): a 1,5x
    usn5 = cuenta("reloj")
    c5 = Conn(usn5)
    hola(c5)
    base = 1000.0
    for i in range(4):
        antitrampa._al_latido(c5, {"latido": str(i + 1), "t": str(int(500_000 + i * 90_000))}, ahora=base + i * 60)
    ok(any(x["regla"] == "reloj_cliente" for x in evs(cuenta="reloj")), "el reloj de la PC al 150 % = reloj_cliente")
    usn6 = cuenta("relojbien")
    c6 = Conn(usn6)
    hola(c6)
    for i in range(5):
        antitrampa._al_latido(c6, {"latido": str(i + 1), "t": str(int(500_000 + i * 60_400))}, ahora=base + i * 60)
    ok(not any(x["regla"] == "reloj_cliente" for x in evs(cuenta="relojbien")),
       "revés: con el reloj al 100,7 % (la red) no se marca")


# ═══ 4 · la correlación, el farmeo y el hola falso ════════════════════════════════════════════════════════════════
def probar_reglas_nuevas():
    print("Cheat Engine solo no prueba nada; la correlación sí; el farmeo pide una señal fuerte; el hola no lava:")
    antitrampa.ANTITRAMPA_SILENCIOSO = True
    usn = cuenta("herramienta")
    c = Conn(usn)
    hola(c)
    antitrampa.al_ff59(c, "R2AT proceso=Cheat Engine.exe s=2")
    e = evs(cuenta="herramienta")
    ok([x["regla"] for x in e] == ["proceso_prohibido"] and e[0]["accion"] == "avisar",
       "Cheat Engine abierto: un evento de riesgo bajo que sólo AVISA")
    ok(antitrampa.juzgar_cartel(c, 7200, 300, 90, 50, 77) is False, "y sus carreras cobran (no se le retiene nada)")
    antitrampa.al_ff59(c, "R2AT manija=cheatengine-x86_64.exe acceso=0x1FFFFF s=3")
    antitrampa.al_ff59(c, "R2AT codigo=0x00412000 paginas=1 bytes=90_90_90_90_90_90_90_90 s=4")
    e = evs(cuenta="herramienta")
    cor = [x for x in e if x["regla"] == "manipulacion_correlacionada"]
    ok(len(cor) == 1 and cor[0]["riesgo"] == "critico", "herramienta + código tocado = manipulación correlacionada")
    eventos.esperar()
    ok(cor and almacen.ev_listar({"evento": cor[0]["evento"]}, 1)[0]["pendiente"], "y queda atada a su pendiente")

    # el hola fabricado ya no lava la retención
    ok(antitrampa.juzgar_cartel(c, 7300, 301, 90, 50, 78) is True, "con la detección pendiente, no cobra")
    hola(c)
    ok(antitrampa.juzgar_cartel(c, 7400, 302, 90, 50, 79) is True,
       "y un «hola» nuevo (fabricado o el juego reabierto) NO le devuelve el cobro mientras espere la tanda")
    pend = [f for f in almacen.antitrampa_pendientes(0) if f.get("cuenta") == "herramienta"]
    hola(c)
    antitrampa.al_ff59(c, "R2AT codigo=0x00413000 paginas=1 bytes=90_90_90_90_90_90_90_90 s=2")
    antitrampa.al_ff59(c, "R2AT proceso=Cheat Engine.exe s=3")
    pend2 = [f for f in almacen.antitrampa_pendientes(0) if f.get("cuenta") == "herramienta"]
    ok(len(pend2) == len(pend), "y repetir hola + detección no multiplica los pendientes de la tanda")

    # el farmeo: callado + teclado en pantalla no es un bot
    usn2 = cuenta("callado")
    c2 = Conn(usn2)
    hola(c2)
    antitrampa._senal(c2, "carreras_sin_hablar", "40 carreras sin chat")
    antitrampa._senal(c2, "teclas_inyectadas", "teclado en pantalla")
    ok(not any(x["regla"] == "farmeo" for x in evs(cuenta="callado")), "dos señales DÉBILES no son farmeo")
    antitrampa._senal(c2, "listo_automatico", "listo siempre a los 2.00 s")
    ok(any(x["regla"] == "farmeo" for x in evs(cuenta="callado")), "con una señal fuerte (listo automático), sí")
    antitrampa.ANTITRAMPA_SILENCIOSO = False


# ═══ 5 · la tanda ══════════════════════════════════════════════════════════════════════════════════════════════════
def probar_tanda():
    print("la tanda (la regla más grave; si la falta no se suma, queda pendiente):")
    antitrampa.ANTITRAMPA_SILENCIOSO = True
    usn = cuenta("tanda")
    c = Conn(usn)
    hola(c)
    antitrampa.al_ff59(c, "R2AT gancho=automatico va=0x005080B5 bytes=E9 s=2")
    antitrampa.al_ff59(c, "R2AT modulo=r2tr.dll s=3")
    real = antitrampa._escalon
    antitrampa._escalon = lambda u, regla, detalle="", nick="": (antitrampa._ESCALON_FALLO.__setitem__(u, True) or
                                                                 (1, None, False))
    try:
        lineas = antitrampa.sancionar_tanda("prueba", ya=True)
    finally:
        antitrampa._escalon = real
    pend = [f for f in almacen.antitrampa_pendientes(0) if f.get("cuenta") == "tanda"]
    ok(len(pend) == 2 and any("NO se pudo sumar" in x for x in lineas),
       "si la falta no se pudo sumar (Coordinador caído), las detecciones siguen pendientes")
    usadas = {}
    antitrampa._escalon = lambda u, regla, detalle="", nick="": (usadas.__setitem__(u, regla) or (1, "tanda", False))
    try:
        antitrampa.sancionar_tanda("prueba", ya=True)
    finally:
        antitrampa._escalon = real
    ok(usadas.get(usn) == "juego_automatico",
       f"la tanda sanciona con la regla MÁS GRAVE ({usadas.get(usn)}), no la 1.ª alfabética (modulo_prohibido)")
    e = evs(cuenta="tanda")
    ok(all(x["estado"] == "sancionado" for x in e if x["pendiente"]), "y sus eventos quedan «sancionado»")
    acc = almacen.at_acciones(50, cuenta="tanda")
    ok(any(a["accion"] == "tanda" for a in acc), "la tanda queda en el registro de acciones")
    antitrampa.ANTITRAMPA_SILENCIOSO = False


# ═══ 6 · las acciones de los administradores ═════════════════════════════════════════════════════════════════════
def probar_acciones():
    print("las acciones de los administradores:")
    from servidor import lobby
    antitrampa.ANTITRAMPA_SILENCIOSO = True
    usn = cuenta("acusado")
    c = Conn(usn)
    salas.CONEXIONES[usn] = c
    try:
        hola(c)
        antitrampa.al_ff59(c, "R2AT gancho=automatico va=0x005080B5 bytes=E9 s=2")
        e = evs(cuenta="acusado", regla="juego_automatico")[0]
        ok(eventos.revisar("ana", e["evento"], "confirmado", "visto en el video")[0], "confirmar un evento")
        ok(evs(evento=e["evento"])[0]["estado"] == "confirmado" and evs(evento=e["evento"])[0]["revisado_por"] == "ana",
           "queda confirmado, con quién lo revisó")
        okd, msj = eventos.descartar("ana", evento=e["evento"], nota="era el motor de práctica")
        ok(okd and "perdonado" in msj, "falso positivo: se descarta")
        ok(not [f for f in almacen.antitrampa_pendientes(0) if f.get("cuenta") == "acusado"],
           "y su pendiente de la tanda queda perdonado (no suma falta)")
        ok(eventos.advertir("ana", "acusado")[0] and any(True for _ in c.enviados), "advertir: le llega un aviso")
        okh, hasta = eventos.suspender("ana", "acusado", 2, "pruebas")
        ok(okh and c.conn.cerrado, f"suspender 2 h: {hasta}, y se lo saca")
        ok(lobby.cuenta_suspendida(usn), "y el login lo rechaza mientras dure")
        ok(eventos.levantar("ana", "acusado")[0] and not lobby.cuenta_suspendida(usn), "levantar la suspensión")
        ok(eventos.banear("ana", "acusado", "reincidente")[0] and almacen.cuenta_estado("acusado")["baneada"],
           "banear a mano (BANNED:, el de siempre)")
        ok(eventos.desbanear("ana", "acusado")[0] and not almacen.cuenta_estado("acusado")["baneada"], "y desbanear")
        ok(not eventos.suspender("ana", "noexiste", 2)[0], "revés: no se suspende una cuenta que no existe")
        acc = [a["accion"] for a in almacen.at_acciones(50, cuenta="acusado")]
        ok({"confirmado", "descartar", "advertir", "suspender", "levantar_suspension", "banear", "desbanear"} <= set(acc),
           "cada acción queda en el registro, con el admin")
        ok(all(a["admin"] == "ana" for a in almacen.at_acciones(50, cuenta="acusado")), "(todas de «ana»)")
        avisos = " ".join(n for _c, n in c.enviados)
        ok("automatico" not in avisos and "gancho" not in avisos, "al jugador nunca le llega un detalle técnico")
    finally:
        salas.CONEXIONES.pop(usn, None)
        antitrampa.ANTITRAMPA_SILENCIOSO = False
    ok(lobby.login_previo_ok.__doc__ and not lobby.login_previo_ok(987654, "127.0.0.1"),
       "el lobby: un usn sin login del juego no entra")
    lobby._login_anotar(987654, "127.0.0.1")
    ok(lobby.login_previo_ok(987654, "127.0.0.1"), "con su FF01 válido desde esa IP, sí")
    ok(not lobby.login_previo_ok(987654, "10.0.0.9"), "revés: desde OTRA IP, no")


# ═══ 7 · el tablero, por HTTP ══════════════════════════════════════════════════════════════════════════════════════
def probar_tablero():
    print("el tablero (HTTP de verdad en 127.0.0.1):")
    from servidor import tablero_antitrampa as tab
    ok(set(tab.admins()) == {"ana"}, "una clave de menos de 12 caracteres no vale como admin")
    srv = tab.arrancar(puerto=0, host="127.0.0.1")
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def pedir(ruta, cuerpo=None, csrf=None):
        req = urllib.request.Request(url + ruta, data=None if cuerpo is None else json.dumps(cuerpo).encode(),
                                     headers={"Content-Type": "application/json", **({"X-CSRF": csrf} if csrf else {})})
        try:
            with op.open(req, timeout=10) as r:
                return r.status, r.read().decode("utf-8"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), e.headers

    try:
        st, html, hd = pedir("/")
        ok(st == 200 and "Tablero antitrampa" in html and "nonce-" in (hd.get("Content-Security-Policy") or ""),
           "la página sale con CSP y nonce")
        ok("{{NONCE}}" not in html and "innerHTML" not in html, "sin innerHTML: todo dato se pinta como texto")
        ok(pedir("/api/resumen")[0] == 401, "revés: sin sesión, la API no contesta (401)")
        ok(pedir("/api/login", {"usuario": "ana", "clave": "mala"})[0] == 403, "revés: la clave mala no entra")
        st, txt, hd = pedir("/api/login", {"usuario": "ana", "clave": "clave-de-prueba-larga"})
        ok(st == 200 and "HttpOnly" in (hd.get("Set-Cookie") or "") and "SameSite=Strict" in (hd.get("Set-Cookie") or ""),
           "la clave buena entra (cookie HttpOnly, SameSite=Strict)")
        csrf = json.loads(txt)["csrf"]
        eventos.esperar()
        st, txt, _ = pedir("/api/resumen")
        d = json.loads(txt)
        ok(st == 200 and {"conectados", "hoy", "total", "alertas", "registro", "categorias"} <= set(d),
           "el resumen: conectados, estadísticas, alertas, estado del registro")
        ok(d["total"]["total"] > 0 and d["alertas"], "con las detecciones de las pruebas de arriba y alertas críticas")
        st, txt, _ = pedir("/api/eventos?categoria=dll_no_autorizada&limite=50")
        lista = json.loads(txt)
        ok(lista and all(x["categoria"] == "dll_no_autorizada" for x in lista), "filtrar por categoría")
        st, txt, _ = pedir("/api/eventos?jugador=registro&riesgo_min=alto")
        lista = json.loads(txt)
        ok(lista and all(x["cuenta"] == "registro" and x["riesgo"] in ("alto", "critico") for x in lista),
           "filtrar por jugador y riesgo mínimo")
        ultimo = max(x["id"] for x in json.loads(pedir("/api/eventos?limite=5")[1]))
        st, txt, _ = pedir(f"/api/eventos?despues_de={ultimo}")
        ok(json.loads(txt) == [], "el tiempo real: «despues_de» el último no trae nada…")
        c = Conn(cuenta("envivo"))
        hola(c)
        antitrampa.al_ff59(c, "R2AT depurador=1 s=2")
        eventos.esperar()
        nuevos = json.loads(pedir(f"/api/eventos?despues_de={ultimo}")[1])
        ok(any(x["regla"] == "depurador" for x in nuevos), "…y trae la detección nueva en cuanto se guarda")
        st, txt, _ = pedir("/api/jugador?cuenta=registro")
        j = json.loads(txt)
        ok(st == 200 and j["resumen"]["cuenta"] == "registro" and j["eventos"], "el historial de una cuenta")
        ok("pass_hash" not in txt and "pass_hash" not in json.dumps(d), "revés: nunca sale el pass_hash")
        # ★ 28-nov · «ESTÁ USANDO»: cada evento dice qué usa, y la ficha y los conectados lo juntan
        print("  · «Está usando» (28-nov):")
        f = Conn(cuenta("farmero"))
        hola(f)
        antitrampa.al_ff59(f, "R2AT gancho=pd0 va=0x005003D0 bytes=E9_00_00_00_00_90_90_90 s=2")
        antitrampa.al_ff59(f, "R2AT proceso=cheatengine-i386.exe s=3")
        antitrampa.al_ff59(f, "R2AT codigo=0x0054F31A paginas=1 bytes=90_90_90_90_90_90_8B_46 s=4")
        antitrampa.al_ff59(f, "R2AT memoria=0x12E70000 regiones=5 s=5")
        antitrampa.anotar(f, "farmeo", "listo automático + misma canción", {})
        eventos.esperar()
        filas = json.loads(pedir("/api/eventos?jugador=farmero&limite=50")[1])
        por = {x["regla"]: x for x in filas}
        ok(por["juego_automatico"]["usa"] == "Automático PD0 silencioso (R2AutoRouteLab2013)"
           and por["juego_automatico"]["usa_tipo"] == "trampa", "el automático dice cuál y de qué programa (trampa)")
        ok(por["proceso_prohibido"]["usa"] == "Programa abierto: cheatengine-i386.exe", "Cheat Engine abierto, por nombre")
        ok(por["n2hock_permitido"]["usa"].startswith("Ñ2Hock: Sin piedra") and por["n2hock_permitido"]["usa_tipo"] == "permitido",
           "Sin piedra de Ñ2Hock: permitido (verde)")
        ok(por["farmeo"]["usa"] == "Auto farmeo" and por["farmeo"]["usa_tipo"] == "trampa", "el farmeo: «Auto farmeo»")
        ok(por["memoria_ajena"]["usa"] == "", "revés: la memoria ajena (la tiene todo juego) no se muestra como «usa»")
        j = json.loads(pedir("/api/jugador?cuenta=farmero")[1])
        textos = [x["texto"] for x in j["usando"]]
        tipos = [x["tipo"] for x in j["usando"]]
        ok("Auto farmeo" in textos and "Automático PD0 silencioso (R2AutoRouteLab2013)" in textos
           and tipos == sorted(tipos, key=["trampa", "sospecha", "permitido", "info"].index),
           "la ficha: «Está usando» con lo más grave primero")
        e_auto = por["juego_automatico"]["evento"]
        pedir("/api/accion", {"accion": "descartar", "evento": e_auto, "nota": "prueba"}, csrf)
        j = json.loads(pedir("/api/jugador?cuenta=farmero")[1])
        ok("Automático PD0 silencioso (R2AutoRouteLab2013)" not in [x["texto"] for x in j["usando"]],
           "revés: lo marcado como falso positivo sale de «Está usando»")
        e = antitrampa.estado_de(f.usn)
        ok({"texto": "Auto farmeo", "tipo": "trampa"} in e["usa"], "«Conectados»: lo que usa en esta sesión")
        ok("Está usando" in pedir("/")[1], "la página tiene la columna «Está usando»")
        ev_db = [x for x in evs(cuenta="farmero") if x["regla"] == "farmeo"][0]
        ok(json.loads(ev_db["evidencia"]).get("usa") == "Auto farmeo",
           "el evento guarda «usa» en la base (para el panel del administrador)")
        ok(pedir("/api/accion", {"accion": "advertir", "cuenta": "registro"})[0] == 403,
           "revés: una acción sin el token CSRF no se hace")
        st, txt, _ = pedir("/api/accion", {"accion": "suspender", "cuenta": "registro", "horas": 1, "motivo": "x"}, csrf)
        ok(st == 200 and json.loads(txt)["ok"] and almacen.suspendida_hasta("registro"), "suspender desde el tablero")
        acc = json.loads(pedir("/api/acciones")[1])
        ok(any(a["accion"] == "suspender" and a["admin"] == "ana" for a in acc), "y queda en el registro de acciones")
        st, txt, _ = pedir("/api/estadisticas")
        s = json.loads(txt)
        ok(st == 200 and s["categoria"] and s["riesgo"] and s["dia"], "las estadísticas por categoría, riesgo y día")
        ok(json.loads(pedir("/api/catalogo")[1])["reglas"]["proceso_prohibido"]["accion"] == "avisar",
           "el catálogo: Cheat Engine abierto sólo avisa")
        for _ in range(9):
            pedir("/api/login", {"usuario": "ana", "clave": "otra-mala-mala"})
        ok(pedir("/api/login", {"usuario": "ana", "clave": "clave-de-prueba-larga"})[0] == 403,
           "revés: tras muchos intentos fallidos desde la misma IP, ni la buena entra (un rato)")
    finally:
        srv.shutdown()


def main():
    try:
        probar_parser()
        probar_registro()
        probar_telemetria()
        probar_reglas_nuevas()
        probar_tanda()
        probar_acciones()
        probar_tablero()
    finally:
        eventos.esperar()
        shutil.rmtree(TMP, ignore_errors=True)
    if FALLAS:
        print(f"\n{len(FALLAS)} prueba(s) MAL")
        return 1
    print("\ntodo bien")
    return 0


if __name__ == "__main__":
    sys.exit(main())
