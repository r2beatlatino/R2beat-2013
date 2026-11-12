# -*- coding: utf-8 -*-
"""circulos — el círculo (el clan) del jugador: crear, pedir entrar, aceptar, echar, el mando.

El mapa, con las direcciones del exe y la web original, está en `documentacion/CIRCULOS_HALLAZGOS.md`.
En corto:

  · En el original, **crear / unirse / echar / pasar el mando se hacía en la WEB de Softnyx**
    (`r2beat.softnyx.com/Circle/*.aspx`): el cliente no tiene ni una pantalla ni un paquete para eso.
    Acá lo reemplaza el comando `.circulo …` del chat (la web propia viene después, sobre esto mismo).
  · Lo que el cliente SÍ ve sale de dos lados:
      - el `FF40 0x21` (GuildInfo): el nombre prende la pestaña «Círculo» de la Mensajería
        (`[mensajería+0xA32] = largo > 0`, `0x5F17D7`) y trae la lista de miembros, el aviso y
        «soy líder»;
      - `char["guild"]` (el MyRecord @44 y el str2 del `FF0C`), que `almacen.filas_a_char` llena
        desde `circulo_miembros`.
  · Las reglas (nivel para crear/unirse, topes, largo del nombre) son las de la web original y
    viven en `ajustes.py` (`CIRCULO_*`).

Acá viven las reglas; la base es `almacen.py`; el comando es `chat.py` (`.circulo`).
"""
import re
import struct
import threading
import time

from .ajustes import (
    CIRCULO_AVISO_MAX,
    CIRCULO_CHAT_COLOR,
    CIRCULO_COSTO_NIVEL,
    CIRCULO_DINERO_POR_100_RCOIN,
    CIRCULO_EXP_POR_RCOIN,
    CIRCULO_GRACIA_SALIDA,
    CIRCULO_MAX_JEFES,
    CIRCULO_MAX_MIEMBROS,
    CIRCULO_NIVEL_CREAR,
    CIRCULO_NIVEL_UNIRSE,
    CIRCULO_NOMBRE_MAX,
    CIRCULO_RANGO_JEFE,
    CIRCULO_RANGO_LIDER,
    CIRCULO_RANGO_MIEMBRO,
    CIRCULO_REGALO_DIAS,
    CIRCULO_REGALOS_POR_NIVEL,
    CIRCULO_TOPE_MAX,
    CIRCULO_TOPES,
    CIRCULOS,
)
from .basedatos import (
    db_agregar_miembro,
    db_borrar_circulo,
    db_borrar_solicitud,
    db_circulo_de,
    db_circulo_por_id,
    db_circulo_por_nombre,
    db_economia_circulo,
    db_add_rcoin,
    db_crear_circulo,
    db_donaciones_circulo,
    db_donar_a_circulo,
    db_get_char,
    db_get_rcoin,
    db_miembros_circulo,
    db_pedir_circulo,
    db_poner_aviso_circulo,
    db_poner_lider_circulo,
    db_poner_rango_circulo,
    db_puesto_circulo,
    db_quitar_miembro,
    db_solicitud_de,
    db_subir_nivel_circulo,
    db_solicitudes_circulo,
)
from .progresion import nivel_de_exp
from .registro import log

# Letras, números y unos pocos signos (los círculos de la web: «R2&Online», «llQQR2ll», «ZeRo»).
# Sin espacios: el comando corta por espacios.
_NOMBRE_OK = re.compile(r"^[A-Za-z0-9_\-.*&]+$")


def _ahora():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _txt(s, tope=0xFF):
    return str(s or "").encode("cp1252", "replace")[:tope]


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  LO QUE VE EL CLIENTE
# ══════════════════════════════════════════════════════════════════════════════════════════════
def armar_ff40_21(nombre="", miembros=(), x16=0, aviso="", bandera=0):
    """`FF40` subtipo **0x21** = GuildInfo, «éste es tu círculo» (handler `0x5F176E`).

        [0x21][u8 resultado=0]
        [u8 len][nombre]                  largo 0 -> sin círculo (la pestaña queda gris)
        por miembro: [u32 id][u8 a][u8 b][u32 c][u8 len][apodo]
        [u32 0xFFFFFFFF]                  fin de la lista
        [u16 ?][u8 len][aviso][u8 lider]  -> 0x457850(u16) · 0x460ab0(aviso) · mensajería+0xA3E

    `miembros` = [(id, a, b, c, apodo)]. El último byte es «soy líder» (`+0xA3E`, lo lee
    `0x5FDD10`). ⚠ `a`, `b`, `c` y el `u16`: sin medir — ver `miembros_para_ff40`.
    """
    n = _txt(nombre)
    out = bytes([0x21, 0, len(n)]) + n
    for mid, a, b, c, apodo in miembros:
        ap = _txt(apodo)
        out += struct.pack("<IBBI", int(mid) & 0xFFFFFFFF, a & 0xFF, b & 0xFF, int(c) & 0xFFFFFFFF)
        out += bytes([len(ap)]) + ap
    av = _txt(aviso)
    out += struct.pack("<IH", 0xFFFFFFFF, x16 & 0xFFFF) + bytes([len(av)]) + av + bytes([bandera & 0xFF])
    return out


def rango_de(circulo, miembro_uid, rango_guardado):
    """El byte de rango del cliente: 0x5A líder (lo dice `lider_uid`) · 0x50 jefe · 0x0A miembro."""
    if int(miembro_uid) == int(circulo["lider_uid"]):
        return CIRCULO_RANGO_LIDER
    return CIRCULO_RANGO_JEFE if int(rango_guardado) == CIRCULO_RANGO_JEFE else CIRCULO_RANGO_MIEMBRO


def _ordenados(circulo, miembros):
    """Líder, después los jefes, después los miembros (cada grupo por antigüedad)."""
    orden = {CIRCULO_RANGO_LIDER: 0, CIRCULO_RANGO_JEFE: 1, CIRCULO_RANGO_MIEMBRO: 2}
    return sorted(miembros, key=lambda m: orden[rango_de(circulo, m["uid"], m["rango"])])


def miembros_para_ff40(circulo, miembros, para, fuera=0):
    """Los renglones del GuildInfo que le toca a `para`: **sólo los CONECTADOS, y sin él**.
    Mismo molde que el amigo del `FF40 0x03` (`[u32 uid][u8 a][u8 b][u32 exp][u8 len][apodo]`).

    ★★★ LA LISTA ES DE CONECTADOS (24-sep, medido en el cliente vivo con `leer_lista.py`):
      el cliente mete a TODO renglón que llega como «conectado» (`0x4629A0` -> ctor `0x45FD50`
      con estado 1, fijo), sin mirar `a` ni `b`: jugador3 desconectada, con a=0, seguía verde. Los
      desconectados NO se listan: son sólo un número, `total - conectados`. Y el alta/baja en vivo
      tiene sus propios subtipos, `0x22`/`0x23` (ver `armar_ff40_22`).
    ★★ SIN el que lo recibe: el cliente se cuenta solo (`0x461180`: conectados = renglones + 1).
    ⚠ [NM] `a` y `b` (-> renglón +0x24/+0x25): van 1 y el rango; no cambian nada visible."""
    from .salas import CONEXIONES
    return [(m["uid"], 1, rango_de(circulo, m["uid"], m["rango"]), m["exp"], m["nick"])
            for m in _ordenados(circulo, miembros)
            if m["uid"] != int(para) and m["uid"] != int(fuera) and m["uid"] in CONEXIONES]


def guildinfo_de(usn, fuera=0):
    """El `FF40 0x21` que le toca a `usn`: su círculo, o «sin círculo».

    ★★ El `u16` de la cola es el TOTAL de miembros, contándose a uno mismo (24-sep): va a
      `mensajería+0xAD2` (`0x457850`, ⚠ guarda sólo el byte bajo — 50 entra de sobra) y de ahí
      sale «desconectados = total - conectados». En 0 daba «desconectados (65533)» (= 0 - 3).
    ⚠ El NOMBRE que dibuja la pestaña NO sale de acá: es `[0x9314E0]+0x1B5`, que sólo escribe el
      MyRecord @44 (`0x5ECDD5` -> `0x484850`). Por eso `refrescar` re-manda también el MyRecord."""
    k = db_circulo_de(usn) if CIRCULOS else None
    if not k:
        return armar_ff40_21()
    ms = db_miembros_circulo(k["id"])
    return armar_ff40_21(k["nombre"], miembros_para_ff40(k, ms, usn, fuera), x16=len(ms), aviso=k["aviso"],
                         bandera=1 if int(usn) == k["lider_uid"] else 0)


def enviar_guildinfo(st, motivo="", fuera=0):
    usn = int(getattr(st, "usn", 0) or 0)
    p = guildinfo_de(usn, fuera)
    st.send_ff55(0x40, p, name=f"FF40/0x21 GuildInfo usn={usn}{motivo} ({len(p)} B)")


def refrescar(uids, motivo="", nombre=()):
    """Le vuelve a mandar el GuildInfo a los que estén conectados. Devuelve a cuántos.

    `nombre` = los uid a los que les CAMBIÓ el círculo (entró, salió, lo echaron, se creó o se
    cerró): a ésos además se les re-manda el MyRecord, el único que escribe el nombre que dibuja
    la pestaña (ver `guildinfo_de`). Es el refresco de siempre (`con_personaje=False`, el de las
    compras)."""
    from .myrecord import enviar_myrecord
    from .salas import CONEXIONES
    nombre = set(int(x) for x in nombre)
    n = 0
    for u in set(int(x) for x in uids) | nombre:
        c = CONEXIONES.get(u)
        if c is None or getattr(c, "cerrado", False):
            continue
        try:
            if u in nombre:
                enviar_myrecord(c, f"MyRecord refresh (cambió el círculo{motivo})", con_personaje=False)
            enviar_guildinfo(c, motivo)
            n += 1
        except Exception as e:                                   # noqa: BLE001
            log("LOBBY", f"  ⚠ círculo: no pude refrescar a uid={u}: {e!r}")
    return n


def armar_ff40_22(uid, apodo, a, b, exp):
    """`FF40` 0x22 = «**%s ha iniciado la sesión.**» (system.csv 486) + lo suma a la lista.
    `[u32 uid][u8 len][apodo][u8 a][u8 b][u32 exp]` (caso `0x5F1A33` -> `0x4629A0`)."""
    ap = _txt(apodo)
    return (bytes([0x22]) + struct.pack("<I", int(uid) & 0xFFFFFFFF) + bytes([len(ap)]) + ap
            + bytes([a & 0xFF, b & 0xFF]) + struct.pack("<I", int(exp) & 0xFFFFFFFF))


def armar_ff40_23(uid, apodo):
    """`FF40` 0x23 = «**%s cerró sesión.**» (system.csv 487) + lo saca de la lista.
    `[u32 uid][u8 len][apodo]` (caso `0x5F1B52` -> `0x462C60(uid)`)."""
    ap = _txt(apodo)
    return bytes([0x23]) + struct.pack("<I", int(uid) & 0xFFFFFFFF) + bytes([len(ap)]) + ap


def armar_ff40_24(apodo, texto, color=2, extra=0):
    """`FF40` 0x24 = una línea del CHAT DEL CÍRCULO (la pestaña «Círculo» del chat).
    `[u8 len][apodo][u8 len][texto][u8 color][u8 ?]` (caso `0x5F1C5A` -> `0x494C30`). `color` indexa
    la tabla `0x886290`: 0 gris · 1 amarillo · 2 verde · 3 azul · 4 celeste · 5 gris · 6 rosa · 7 lila."""
    ap, tx = _txt(apodo), _txt(texto)
    return bytes([0x24, len(ap)]) + ap + bytes([len(tx)]) + tx + bytes([color & 0xFF, extra & 0xFF])


def armar_ff40_25(aviso):
    """`FF40` 0x25 = el AVISO del círculo nuevo (el del parlante). `[u8 len][aviso]` (`0x5F1D02` -> `0x460AB0`)."""
    av = _txt(aviso)
    return bytes([0x25, len(av)]) + av


# ★ La baja se avisa con unos segundos de GRACIA: un cambio de canal cierra la conexión y abre otra
#   al segundo, y sin esto cada cambio de canal le tiraría a todo el círculo «X cerró sesión» +
#   «X ha iniciado la sesión». Si vuelve antes de que venza, no se avisa ni la baja ni el alta.
_BAJAS = {}                    # usn -> threading.Timer
_bajas_lock = threading.Lock()


def _companeros_conectados(k, usn):
    from .salas import CONEXIONES
    for m in db_miembros_circulo(k["id"]):
        c = CONEXIONES.get(m["uid"])
        if m["uid"] != int(usn) and c is not None and not getattr(c, "cerrado", False):
            yield m, c


def presencia(usn, entro):
    """Alta o baja de `usn` en la lista de sus compañeros conectados, con los subtipos nativos
    `0x22`/`0x23` (que además escriben «ha iniciado la sesión» / «cerró sesión» en el chat).
    ⚠ Al irse, `lobby.py` lo llama ANTES de sacarlo de `CONEXIONES`: la baja real sale del timer."""
    if not CIRCULOS:
        return 0
    usn = int(usn)
    if entro:
        with _bajas_lock:
            t = _BAJAS.pop(usn, None)
        if t is not None:
            t.cancel()
            log("LOBBY", f"  ⭕ círculo: uid={usn} volvió antes de la gracia (cambio de canal): sin aviso")
            return 0
        return _alta(usn)
    t = threading.Timer(CIRCULO_GRACIA_SALIDA, _baja, args=(usn,))
    t.daemon = True
    with _bajas_lock:
        viejo = _BAJAS.pop(usn, None)
        _BAJAS[usn] = t
    if viejo is not None:
        viejo.cancel()
    t.start()
    return 0


def _alta(usn):
    k = db_circulo_de(usn)
    if not k:
        return 0
    ch = db_get_char(usn) or {}
    p = armar_ff40_22(usn, ch.get("nick", ""), 1, rango_de(k, usn, k["rango"]), ch.get("exp", 0))
    n = 0
    for m, c in _companeros_conectados(k, usn):
        try:
            c.send_ff55(0x40, p, name=f"FF40/0x22 círculo: {ch.get('nick', '')!r} ha iniciado la sesión")
            n += 1
        except Exception as e:                                   # noqa: BLE001
            log("LOBBY", f"  ⚠ círculo: alta a uid={m['uid']}: {e!r}")
    if n:
        log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r}: uid={usn} entró -> avisado a {n}")
    return n


def _baja(usn):
    from .salas import CONEXIONES
    with _bajas_lock:
        _BAJAS.pop(usn, None)
    if usn in CONEXIONES:                       # volvió (otra conexión) sin pasar por `presencia`
        return 0
    k = db_circulo_de(usn)
    if not k:
        return 0
    p = armar_ff40_23(usn, _nick(usn))
    n = 0
    for m, c in _companeros_conectados(k, usn):
        try:
            c.send_ff55(0x40, p, name=f"FF40/0x23 círculo: {_nick(usn)!r} cerró sesión")
            n += 1
        except Exception as e:                                   # noqa: BLE001
            log("LOBBY", f"  ⚠ círculo: baja a uid={m['uid']}: {e!r}")
    if n:
        log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r}: uid={usn} se fue -> avisado a {n}")
    return n


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  LO QUE MANDA EL CLIENTE — `FF40` 0x22 (chat del círculo) y 0x23 (el aviso, desde el parlante)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def chat(st, texto_bytes):
    """C2S `FF40 22 [u8 len][texto]`: lo que se escribe en la pestaña «Círculo» del chat.
    Va a los del círculo conectados MENOS al que escribe: ése ya la tiene. ★ Medido (24-sep): el
    emisor (`0x497EC0` -> `0x5D45F0`) la agrega él mismo a su chat (`0x494C30`, con SU color, blanco)
    apenas la manda; devolvérsela la duplicaba (blanca + verde)."""
    usn = int(getattr(st, "usn", 0) or 0)
    k = db_circulo_de(usn) if CIRCULOS else None
    if not k:
        log("LOBBY", f"  ⭕ círculo: uid={usn} escribió en el chat del círculo sin tener círculo")
        return 0
    from .salas import CONEXIONES
    p = armar_ff40_24(_nick(usn), texto_bytes.decode("cp1252", "replace"), CIRCULO_CHAT_COLOR)
    n = 0
    for m in db_miembros_circulo(k["id"]):
        c = CONEXIONES.get(m["uid"])
        if c is None or c is st or getattr(c, "cerrado", False):
            continue
        try:
            c.send_ff55(0x40, p, name=f"FF40/0x24 chat del círculo de {_nick(usn)!r}")
            n += 1
        except Exception as e:                                   # noqa: BLE001
            log("LOBBY", f"  ⚠ círculo: chat a uid={m['uid']}: {e!r}")
    log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r} chat de uid={usn}: {texto_bytes!r} -> {n}")
    return n


def aviso_desde_cliente(st, texto_bytes):
    """C2S `FF40 23 [u8 len][aviso]`: el líder edita el aviso con el botón del parlante."""
    usn = int(getattr(st, "usn", 0) or 0)
    return poner_aviso(usn, texto_bytes.decode("cp1252", "replace"))


def avisar(uids, texto):
    """Una línea de «SERVER» en el chat de los que estén conectados (la misma forma que las
    respuestas de los comandos, `lobby_menu.h_07_ff08`). ⚠ En ASCII: ver `chat.a_ascii`."""
    from .chat import a_ascii
    from .salas import CONEXIONES
    rb, sysnick = _txt(a_ascii(texto)), b"SERVER"
    for u in set(int(x) for x in uids):
        c = CONEXIONES.get(u)
        if c is None or getattr(c, "cerrado", False):
            continue
        try:
            c.send_ff55(0x08, bytes([len(sysnick)]) + sysnick + bytes([len(rb)]) + rb + bytes([2, 0]),
                        name=f"FF08 aviso de círculo {texto!r}")
        except Exception as e:                                   # noqa: BLE001
            log("LOBBY", f"  ⚠ círculo: no pude avisarle a uid={u}: {e!r}")


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  LAS REGLAS — cada una devuelve las líneas para el que escribió el comando
# ══════════════════════════════════════════════════════════════════════════════════════════════
def mismo_circulo(a, b):
    """¿`a` y `b` están en el mismo círculo? (la «i» del renglón pide la ficha como a un amigo)"""
    if not CIRCULOS:
        return False
    ka, kb = db_circulo_de(a), db_circulo_de(b)
    return bool(ka and kb and ka["id"] == kb["id"])


def _nivel(usn):
    return nivel_de_exp(int((db_get_char(usn) or {}).get("exp", 0) or 0))


def _nick(usn):
    return (db_get_char(usn) or {}).get("nick", "") or f"#{usn}"


def _es_operador(k, usn):
    """Líder o Jefe: los que aceptan, rechazan, echan y ponen el aviso (web: «Operador del Círculo»)."""
    return rango_de(k, usn, k["rango"]) in (CIRCULO_RANGO_LIDER, CIRCULO_RANGO_JEFE)


def _operadores(k):
    return [m["uid"] for m in db_miembros_circulo(k["id"])
            if rango_de(k, m["uid"], m["rango"]) in (CIRCULO_RANGO_LIDER, CIRCULO_RANGO_JEFE)]


def _buscar(lista, apodo):
    """El renglón de `lista` con ese apodo (sin mayúsculas). ⚠ El apodo NO es único en el server
    (`almacen.uids_por_nick`), pero acá se busca sólo dentro del círculo o de sus solicitudes.
    Devuelve `(renglón, error)`."""
    hay = [x for x in lista if (x["nick"] or "").lower() == str(apodo).lower()]
    if not hay:
        return None, f"no encontré a {apodo!r}"
    if len(hay) > 1:
        return None, f"hay {len(hay)} que se llaman {apodo!r}: avisale a un GM"
    return hay[0], None


def crear(usn, nombre, saltear_nivel=False):
    nombre = str(nombre or "").strip()
    if db_circulo_de(usn):
        return ["ya estás en un círculo: para crear otro primero tenés que salir (.circulo salir)"]
    if not saltear_nivel and _nivel(usn) < CIRCULO_NIVEL_CREAR:
        return [f"para crear un círculo hace falta nivel {CIRCULO_NIVEL_CREAR} (tenés {_nivel(usn)})"]
    if not (2 <= len(nombre) <= CIRCULO_NOMBRE_MAX) or not _NOMBRE_OK.match(nombre):
        return [f"el nombre va de 2 a {CIRCULO_NOMBRE_MAX} caracteres: letras, números y _ - . * &"
                " (sin espacios)"]
    cid = db_crear_circulo(usn, nombre, _ahora())
    if not cid:
        return [f"ya existe un círculo que se llama {nombre!r}"]
    log("LOBBY", f"  ⭕ CÍRCULO CREADO: {nombre!r} (id={cid}) líder uid={usn}")
    refrescar([usn], " (creó el círculo)", nombre=[usn])
    return [f"¡creaste el círculo {nombre}! sos el líder",
            "⚠ el nombre NO se puede cambiar · los demás entran con .circulo unirme " + nombre]


def pedir(usn, nombre, saltear_nivel=False):
    if db_circulo_de(usn):
        return ["ya estás en un círculo (.circulo salir para dejarlo)"]
    if not saltear_nivel and _nivel(usn) < CIRCULO_NIVEL_UNIRSE:
        return [f"para entrar a un círculo hace falta nivel {CIRCULO_NIVEL_UNIRSE} (tenés {_nivel(usn)})"]
    k = db_circulo_por_nombre(nombre)
    if not k:
        return [f"no existe el círculo {nombre!r}"]
    if len(db_miembros_circulo(k["id"])) >= CIRCULO_MAX_MIEMBROS:
        return [f"{k['nombre']} está lleno ({CIRCULO_MAX_MIEMBROS} miembros)"]
    db_pedir_circulo(usn, k["id"], _ahora())
    log("LOBBY", f"  ⭕ CÍRCULO: uid={usn} pidió entrar a {k['nombre']!r}")
    avisar(_operadores(k), f"{_nick(usn)} pidió entrar al círculo -> .circulo aceptar {_nick(usn)}")
    return [f"pedido mandado a {k['nombre']}: te avisamos cuando el líder o un jefe lo acepte"]


def cancelar(usn):
    cid = db_solicitud_de(usn)
    if not cid:
        return ["no tenés ningún pedido pendiente"]
    db_borrar_solicitud(usn)
    return ["pedido cancelado"]


def solicitudes(usn):
    k = db_circulo_de(usn)
    if not k or not _es_operador(k, usn):
        return ["sólo el líder o un jefe ven los pedidos"]
    ss = db_solicitudes_circulo(k["id"])
    if not ss:
        return ["no hay pedidos pendientes"]
    return [f"{len(ss)} pedido(s): " + ", ".join(f"{s['nick']} (nv {nivel_de_exp(s['exp'])})" for s in ss),
            ".circulo aceptar <apodo> · .circulo rechazar <apodo>"]


def aceptar(usn, apodo):
    k = db_circulo_de(usn)
    if not k or not _es_operador(k, usn):
        return ["sólo el líder o un jefe aceptan pedidos"]
    s, err = _buscar(db_solicitudes_circulo(k["id"]), apodo)
    if err:
        return [err + " entre los pedidos (.circulo solicitudes)"]
    if not db_agregar_miembro(s["uid"], k["id"], _ahora(), CIRCULO_MAX_MIEMBROS):
        db_borrar_solicitud(s["uid"])
        return [f"no pude sumar a {s['nick']}: ya está en otro círculo o el tuyo está lleno"]
    log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r}: uid={usn} aceptó a uid={s['uid']}")
    avisar([s["uid"]], f"¡te aceptaron en el círculo {k['nombre']}!")
    refrescar([m["uid"] for m in db_miembros_circulo(k["id"])], f" ({s['nick']} entró)", nombre=[s["uid"]])
    return [f"{s['nick']} ya es miembro de {k['nombre']}"]


def rechazar(usn, apodo):
    k = db_circulo_de(usn)
    if not k or not _es_operador(k, usn):
        return ["sólo el líder o un jefe rechazan pedidos"]
    s, err = _buscar(db_solicitudes_circulo(k["id"]), apodo)
    if err:
        return [err + " entre los pedidos"]
    db_borrar_solicitud(s["uid"])
    avisar([s["uid"]], f"el círculo {k['nombre']} no aceptó tu pedido")
    return [f"pedido de {s['nick']} rechazado"]


def echar(usn, apodo):
    k = db_circulo_de(usn)
    if not k or not _es_operador(k, usn):
        return ["sólo el líder o un jefe pueden echar"]
    ms = db_miembros_circulo(k["id"])
    m, err = _buscar(ms, apodo)
    if err:
        return [err + " en el círculo"]
    if m["uid"] == usn:
        return ["para irte usá .circulo salir"]
    rm = rango_de(k, m["uid"], m["rango"])
    if rm == CIRCULO_RANGO_LIDER:
        return ["al líder no se lo puede echar"]
    if rm == CIRCULO_RANGO_JEFE and usn != k["lider_uid"]:
        return ["a un jefe sólo lo puede echar el líder"]
    db_quitar_miembro(m["uid"])
    log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r}: uid={usn} echó a uid={m['uid']}")
    avisar([m["uid"]], f"te sacaron del círculo {k['nombre']}")
    refrescar([x["uid"] for x in ms], f" ({m['nick']} fue echado)", nombre=[m["uid"]])
    return [f"{m['nick']} ya no está en {k['nombre']}"]


def poner_jefe(usn, apodo, si=True):
    k = db_circulo_de(usn)
    if not k or usn != k["lider_uid"]:
        return ["sólo el líder nombra o saca jefes"]
    ms = db_miembros_circulo(k["id"])
    m, err = _buscar(ms, apodo)
    if err:
        return [err + " en el círculo"]
    rm = rango_de(k, m["uid"], m["rango"])
    if rm == CIRCULO_RANGO_LIDER:
        return ["el líder ya manda"]
    if si:
        if rm == CIRCULO_RANGO_JEFE:
            return [f"{m['nick']} ya es jefe"]
        jefes = sum(1 for x in ms if rango_de(k, x["uid"], x["rango"]) != CIRCULO_RANGO_MIEMBRO)
        if jefes >= CIRCULO_MAX_JEFES:
            return [f"ya hay {CIRCULO_MAX_JEFES} jefes contando al líder: sacá uno primero"]
    elif rm != CIRCULO_RANGO_JEFE:
        return [f"{m['nick']} no es jefe"]
    db_poner_rango_circulo(m["uid"], CIRCULO_RANGO_JEFE if si else CIRCULO_RANGO_MIEMBRO)
    log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r}: uid={m['uid']} {'es JEFE' if si else 'ya no es jefe'}")
    avisar([m["uid"]], f"{'ahora sos jefe' if si else 'ya no sos jefe'} del círculo {k['nombre']}")
    refrescar([x["uid"] for x in ms])
    return [f"{m['nick']} {'ahora es jefe' if si else 'volvió a ser miembro'}"]


def pasar_mando(usn, apodo):
    k = db_circulo_de(usn)
    if not k or usn != k["lider_uid"]:
        return ["sólo el líder puede pasar el mando"]
    ms = db_miembros_circulo(k["id"])
    m, err = _buscar(ms, apodo)
    if err:
        return [err + " en el círculo"]
    if m["uid"] == usn:
        return ["ya sos el líder"]
    db_poner_lider_circulo(k["id"], m["uid"])
    log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r}: el mando pasa de uid={usn} a uid={m['uid']}")
    avisar([x["uid"] for x in ms if x["uid"] != usn], f"{m['nick']} es el nuevo líder de {k['nombre']}")
    refrescar([x["uid"] for x in ms])
    return [f"{m['nick']} es el nuevo líder; vos quedás de miembro"]


def sucesor(k, miembros, sin):
    """A quién pasa el mando si el líder se va (regla de la web): un jefe; si no hay, el de más
    nivel; a igual nivel, el que entró primero. `None` si no queda nadie."""
    resto = [m for m in miembros if m["uid"] != sin]
    if not resto:
        return None
    jefes = [m for m in resto if rango_de(k, m["uid"], m["rango"]) == CIRCULO_RANGO_JEFE]
    grupo = jefes or resto
    # `miembros` viene por antigüedad: `max` se queda con el primero de los empatados
    return max(grupo, key=lambda m: nivel_de_exp(m["exp"]))


def salir(usn):
    k = db_circulo_de(usn)
    if not k:
        return ["no estás en ningún círculo"]
    ms = db_miembros_circulo(k["id"])
    if usn == k["lider_uid"]:
        s = sucesor(k, ms, usn)
        if s is None:
            db_borrar_circulo(k["id"])
            log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r} CERRADO: se fue el líder y no quedaba nadie")
            refrescar([usn], " (se cerró)", nombre=[usn])
            return [f"saliste y {k['nombre']} se cerró (no quedaba nadie)"]
        db_poner_lider_circulo(k["id"], s["uid"])
        avisar([s["uid"]], f"el líder dejó {k['nombre']}: ahora el líder sos vos")
    db_quitar_miembro(usn)
    log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r}: uid={usn} salió")
    refrescar([x["uid"] for x in ms], f" ({_nick(usn)} salió)", nombre=[usn])
    return [f"saliste de {k['nombre']}"]


def cerrar(usn, confirmacion):
    k = db_circulo_de(usn)
    if not k or usn != k["lider_uid"]:
        return ["sólo el líder puede cerrar el círculo"]
    if str(confirmacion or "") != k["nombre"]:
        return [f"⚠ esto BORRA el círculo para todos. Para confirmar: .circulo cerrar {k['nombre']}"]
    uids = db_borrar_circulo(k["id"])
    log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r} CERRADO por el líder uid={usn} ({len(uids)} miembros)")
    avisar([u for u in uids if u != usn], f"el líder cerró el círculo {k['nombre']}")
    refrescar(uids, " (se cerró)", nombre=uids)
    return [f"{k['nombre']} quedó cerrado"]


def poner_aviso(usn, texto):
    k = db_circulo_de(usn)
    if not k or not _es_operador(k, usn):
        return ["sólo el líder o un jefe ponen el aviso"]
    texto = str(texto or "").strip()[:CIRCULO_AVISO_MAX]
    db_poner_aviso_circulo(k["id"], texto)
    from .salas import CONEXIONES
    for m in db_miembros_circulo(k["id"]):                 # el subtipo nativo del aviso (0x25)
        c = CONEXIONES.get(m["uid"])
        if c is not None and not getattr(c, "cerrado", False):
            c.send_ff55(0x40, armar_ff40_25(texto), name=f"FF40/0x25 aviso del círculo {texto!r}")
    log("LOBBY", f"  ⭕ CÍRCULO {k['nombre']!r}: uid={usn} puso el aviso {texto!r}")
    return [f"aviso puesto: {texto!r}" if texto else "aviso borrado"]


def ver(usn):
    k = db_circulo_de(usn)
    if not k:
        cid = db_solicitud_de(usn)
        pend = db_circulo_por_id(cid) if cid else None
        return ["no estás en ningún círculo" + (f" (pediste entrar a {pend['nombre']})" if pend else ""),
                ".circulo crear <nombre> · .circulo unirme <nombre> · .circulo ayuda"]
    ms = db_miembros_circulo(k["id"])
    cargo = {CIRCULO_RANGO_LIDER: "líder", CIRCULO_RANGO_JEFE: "jefe"}.get(
        rango_de(k, usn, k["rango"]), "miembro")
    out = [f"círculo {k['nombre']} · sos {cargo} · {len(ms)}/{CIRCULO_MAX_MIEMBROS} miembros"
           f" · líder {_nick(k['lider_uid'])}"]
    if k["aviso"]:
        out.append(f"aviso: {k['aviso']}")
    if _es_operador(k, usn):
        n = len(db_solicitudes_circulo(k["id"]))
        if n:
            out.append(f"{n} pedido(s) para entrar: .circulo solicitudes")
    return out


def lista_miembros(usn):
    k = db_circulo_de(usn)
    if not k:
        return ["no estás en ningún círculo"]
    ms = _ordenados(k, db_miembros_circulo(k["id"]))
    marca = {CIRCULO_RANGO_LIDER: "★", CIRCULO_RANGO_JEFE: "☆"}
    return [f"{len(ms)} miembros: " + ", ".join(
        marca.get(rango_de(k, m["uid"], m["rango"]), "") + m["nick"] for m in ms)[:240]]


AYUDA = [
    ".circulo  (ver el tuyo) · .circulo crear <nombre> · .circulo unirme <nombre> · .circulo cancelar",
    ".circulo miembros · .circulo salir · .circulo aviso <texto>",
    "líder/jefe: .circulo solicitudes · aceptar <apodo> · rechazar <apodo> · echar <apodo>",
    "líder: .circulo jefe <apodo> · quitarjefe <apodo> · lider <apodo> · cerrar <nombre>",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ★★ LA ECONOMÍA (24-sep) — FFD4 (datos del círculo), FFD7 (inventario), FFE3 (lista completa)
#     Mapa en `CIRCULOS_HALLAZGOS.md` §0 («La economía»). El cliente pide FFD7 + FFD4 al entrar a
#     cada canal (`0x4A4081`/`0x4A408C`), sólo si tiene círculo.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def tope_de(nivel):
    """El TOPE de EXP que le mandamos al cliente para que dibuje `nivel` (ver `CIRCULO_TOPES`)."""
    n = max(1, min(10, int(nivel)))
    return CIRCULO_TOPE_MAX if n >= 10 else CIRCULO_TOPES[n - 1]


def nivel_del_tope(tope):
    """Lo que hace el cliente (`0x5FDB80`), para la prueba: el primer nivel cuyo tope alcanza."""
    if tope == CIRCULO_TOPE_MAX:
        return 10
    for n in range(1, 10):
        if tope <= CIRCULO_TOPES[n - 1]:
            return n
    return 10


def fecha_empacada(texto):
    """La fecha de creación como la lee el cliente en A+10: año bits 0-11, mes 12-15, día 16-20
    (`0x4093F0` cuenta los días hasta hoy). `"2026-09-25 ..."` -> `0x001997EA`. Vacía o rota -> 0."""
    try:
        a, m, d = (int(x) for x in str(texto)[:10].split("-"))
        return (a & 0xFFF) | ((m & 0xF) << 12) | ((d & 0x1F) << 16)
    except Exception:                                            # noqa: BLE001
        return 0


def armar_ffd4(eco, fecha=0, ranking=(), aporte=0, puesto=0, punto=0):
    """`FFD4` = los DATOS del círculo (handler `0x5DA130` -> `0x600410`, el `cCircleInfoView`, y la
    ventana «Dinero de Círculo» `cDialogCircleMoney`). Mapa del 25-sep (`documentacion/CIRCULO_EXE_PANEL.md`):

        [u8 resultado]        ⛔ != 0 saca el cartel de error del círculo (circle.csv 0x1A)
        [28 B] bloque A:  +00 u32 EXP actual        (-> vista+0x3C = cfg+0x6F8)
                          +04 u32 TOPE de EXP       (-> vista+0x154; de acá sale el NIVEL y el bono)
                          +08 u32 dinero de círculo («Dinero de mi Círculo»)
                          +0C u16 logo, +0E u16 fondo = la MARCA
                          +10 u32 FECHA DE CREACIÓN empacada (`fecha_empacada`)
                          +14 (no lo lee nadie)   +18 (lo pisa Z)
        [216 B] bloque B: 5 x 40 B = el RANKING DE DONACIÓN (`0x5FE270`; puesto 0 = fila vacía):
                              [u16 puesto][2][u32 uid][char 24 apodo][u32 Rcoin donado][s32 cambio]
                          +C8 u16 (lo pisa Y) · +CC s32 cambio del puesto · +D0 u16 ranking semanal
                          +D2 u16 ranking total · +D4 s32 su cambio
        [u32 X] «Nivel de Contribución»: X y X/EXP (%, tope 100) -> lo donado por EL QUE LO RECIBE
        [u32 Y] su u16 = el PUESTO del círculo («Puesto %d»; 0 = «-»)
        [u32 Z] «Punto Círculo»
    «Cambio» va en 0: en el csv español los tres textos son «0» (en el KR eran ▲▼-).
    La EXP que dona el cliente se calcula igual del otro lado (`0x5E3B70`): ganada =
    min(donado, TOPE - EXP), y 0 en el nivel 10."""
    a = struct.pack("<IIIHHIII", int(eco["exp"]) & 0xFFFFFFFF, tope_de(eco["nivel"]),
                    int(eco["dinero"]) & 0xFFFFFFFF, (int(eco["marca"]) >> 16) & 0xFFFF,
                    int(eco["marca"]) & 0xFFFF, int(fecha) & 0xFFFFFFFF, 0, 0)
    b = b""
    for i, (uid, apodo, donado) in enumerate(list(ranking)[:5]):
        ap = _txt(apodo, 23)
        b += struct.pack("<HHI", i + 1, 0, int(uid) & 0xFFFFFFFF) + ap + bytes(24 - len(ap))
        b += struct.pack("<Ii", int(donado) & 0xFFFFFFFF, 0)
    b += bytes(0xC8 - len(b))
    b += struct.pack("<HHiHHi", 0, 0, 0, 0, int(puesto) & 0xFFFF, 0) + bytes(0xD8 - 0xC8 - 16)
    return bytes([0]) + a + b + struct.pack("<III", int(aporte) & 0xFFFFFFFF, int(puesto) & 0xFFFF,
                                            int(punto) & 0xFFFFFFFF)


def armar_ffe3(pagina, ultima, renglones):
    """`FFE3` = la LISTA COMPLETA de miembros, por páginas (`CmdGuildMemberList`, handler `0x5F48F0`).

        [u8 res][u16 PÁGINA][u16 ÚLTIMA página][u8 n] + n x 36 B:
            [u32 uid][char 24 apodo][u8 rango][3 B][u32 Rcoin donados]     (`0x5EB000`)
    -> vista+0x3A4 / +0x3A6. ⛔ Son PÁGINAS, no posiciones (medido el 25-sep: los botones piden
    0, 1, 2, 3 — `0x600DBB dec ax` y ±5 en `0x600D96` para saltar de a 5 páginas), y el 2º es la
    ÚLTIMA página, 0-based: `0x5FDBB0` deja pasar mientras `pedida <= [+0x3A6]`. Mandando «desde
    el miembro n» y «total de miembros», con 3 miembros salían 4 páginas, cada una con uno menos.
    La columna del `u32` dice «Rcoin donados» (captura de anonimo03, 25-sep). De a `CIRCULO_PAGINA` (9)."""
    out = bytes([0]) + struct.pack("<HH", int(pagina) & 0xFFFF, int(ultima) & 0xFFFF) + bytes([len(renglones)])
    for uid, apodo, rango, x in renglones:
        ap = _txt(apodo, 23)
        out += struct.pack("<I", int(uid) & 0xFFFFFFFF) + ap + bytes(24 - len(ap))
        out += bytes([rango & 0xFF, 0, 0, 0]) + struct.pack("<I", int(x) & 0xFFFFFFFF)
    return out


CIRCULO_PAGINA = 9     # ★ el panel tiene 9 renglones (captura de anonimo03, 25-sep); el lector no pone tope


def _ffd4_comun(k):
    """Lo del `FFD4` que es igual para todos los del círculo: economía, fecha, ranking, puesto."""
    ms = db_miembros_circulo(k["id"])
    donado = db_donaciones_circulo(k["id"])
    top = sorted(((m["uid"], m["nick"], donado.get(int(m["uid"]), 0)) for m in ms
                  if donado.get(int(m["uid"]), 0) > 0), key=lambda x: -x[2])[:5]
    return (db_economia_circulo(k["id"]), fecha_empacada(k.get("creado_at", "")), top,
            db_puesto_circulo(k["id"]), donado, ms)


def aporte_en_exp(rcoin):
    """«Nivel de Contribución» = X y X/EXP del círculo: lo donado pasado a EXP (con el multiplicador;
    si no, con 150 EXP por Rcoin el porcentaje saldría 150 veces más chico)."""
    return int(rcoin) * CIRCULO_EXP_POR_RCOIN


def ffd4_de(usn):
    k = db_circulo_de(usn) if CIRCULOS else None
    if not k:
        return None
    eco, fecha, top, puesto, donado, _ms = _ffd4_comun(k)
    return armar_ffd4(eco, fecha, top, aporte_en_exp(donado.get(int(usn), 0)), puesto)


def ffe3_de(usn, pagina):
    k = db_circulo_de(usn) if CIRCULOS else None
    if not k:
        return None
    ms = _ordenados(k, db_miembros_circulo(k["id"]))
    donado = db_donaciones_circulo(k["id"])
    ultima = max(0, (len(ms) - 1) // CIRCULO_PAGINA)
    pagina = max(0, min(int(pagina), ultima))
    pag = ms[pagina * CIRCULO_PAGINA:(pagina + 1) * CIRCULO_PAGINA]
    return armar_ffe3(pagina, ultima, [(m["uid"], m["nick"], rango_de(k, m["uid"], m["rango"]),
                                        donado.get(int(m["uid"]), 0)) for m in pag])


# ── DONAR (FFD6) ─────────────────────────────────────────────────────────────────────────────────
#   C→S `[u32 monto]` (el cliente ya lo trunca a múltiplos de 100 y frena < 100 y > su saldo:
#   circle.csv #54 / #5). S→C `[u8 res][u32 Rcoin que le QUEDA]` (handler `0x5E3B70`): con 0 el
#   cliente calcula él mismo lo ganado (saldo viejo − el nuevo) y saca el recibo #33; por eso el
#   saldo tiene que ser EXACTO. Errores: 2 = #56 «Rcoin ganados anormalmente», 3 = «error DB»
#   (system 148), cualquier otro = #32 «Tu donación ha fallado».
DONAR_OK, DONAR_FALLO, DONAR_ANORMAL, DONAR_ERROR_DB = 0, 1, 2, 3
CIRCULO_DONACION_MINIMA = 100


def armar_ffd6(resultado, saldo):
    return bytes([resultado & 0xFF]) + struct.pack("<I", max(0, int(saldo)) & 0xFFFFFFFF)


def donar(usn, monto):
    """-> `(resultado, saldo, cid, exp_ganada, dinero_ganado)`. Cobra y acredita, o nada."""
    usn, monto = int(usn), int(monto)
    saldo = db_get_rcoin(usn)
    k = db_circulo_de(usn) if CIRCULOS else None
    monto = (monto // 100) * 100                         # lo mismo que hace el cliente (`0x5F84D0`)
    if not k or monto < CIRCULO_DONACION_MINIMA or monto > saldo:
        return DONAR_FALLO, saldo, (k or {}).get("id"), 0, 0
    nuevo = db_add_rcoin(usn, -monto)                   # ya se vio que alcanza: no puede quedar < 0
    try:
        exp, dinero = db_donar_a_circulo(usn, k["id"], monto, tope_de, _ahora(),
                                         exp_bruta=monto * CIRCULO_EXP_POR_RCOIN,
                                         dinero=monto * CIRCULO_DINERO_POR_100_RCOIN // 100)
    except Exception as e:                                       # noqa: BLE001
        log("LOBBY", f"  ⛔ donación de usn={usn} ({monto}) no se pudo acreditar: {e!r} -> se devuelve")
        return DONAR_ERROR_DB, db_add_rcoin(usn, monto), k["id"], 0, 0
    log("LOBBY", f"  ⭕ DONACIÓN usn={usn} -> círculo #{k['id']} {k['nombre']!r}: {monto} Rcoin "
                 f"= +{exp} EXP, +{dinero} dinero (le quedan {nuevo})")
    # ★ el recibo del CLIENTE sale a 1:1 y /100 (lo calcula él, `0x5E3B70`): los números de verdad, aparte
    nota = ""
    if exp < monto * CIRCULO_EXP_POR_RCOIN:
        nota = (" (nivel maximo: la EXP ya no sube)" if db_economia_circulo(k["id"])["nivel"] >= 10
                else " (la EXP llego al tope: falta subir de nivel)")
    # ★ 29-sep: con la tasa ORIGINAL (1 y 1) el recibo del cliente ya dice la verdad: la línea sobra.
    if (CIRCULO_EXP_POR_RCOIN, CIRCULO_DINERO_POR_100_RCOIN) != (1, 1):
        avisar([usn], f"Donaste {monto} Rcoin al circulo: +{exp} EXP y +{dinero} de dinero de circulo{nota}")
    return DONAR_OK, nuevo, k["id"], exp, dinero


def donado_por(cid):
    """`{uid: Rcoin donados}` del círculo (la columna «Rcoin donados» y el ranking)."""
    return db_donaciones_circulo(cid)


# ── SUBIR DE NIVEL (FFE1) ────────────────────────────────────────────────────────────────────────
#   C→S vacío (el botón sale sólo con la EXP justo en el tope: `0x5FDBD0`). S→C (`0x5DAD30`):
#   `[u8 res][u32 dinero que queda][u32 TOPE nuevo][u8 n] + n x u32 itemcode` (los regalos, que
#   el cliente muestra con `0x42D9F0`). res 0 -> `cfg+0x780` = dinero y `cfg+0x810` = tope; res != 0
#   -> circle.csv #38 «Subida de nivel de tu círculo ha fallado». El costo que cobra es el MISMO que
#   el cliente muestra antes (su tabla `0x887230` = `CIRCULO_COSTO_NIVEL`).
def costo_de(nivel):
    return CIRCULO_COSTO_NIVEL[max(1, min(9, int(nivel))) - 1]


def armar_ffe1(resultado, dinero, tope, regalos=()):
    return (bytes([resultado & 0xFF]) + struct.pack("<II", max(0, int(dinero)) & 0xFFFFFFFF, int(tope) & 0xFFFFFFFF)
            + bytes([len(regalos) & 0xFF]) + b"".join(struct.pack("<I", int(c) & 0xFFFFFFFF) for c in regalos))


def armar_ff40_3a(nivel, circulo):
    """`FF40 0x3A` = el cartel «¡Felicitaciones! Círculo <X> llegó al nivel N» (caso `0x5EE68B`):
    `[0x3A][u8 nivel][u16 0][u16 nivel][u8 len][círculo][u8 len][círculo]`. Leído del exe el
    25-sep: llama `0x4325E0(u8, str1, u16 b, u16 c)` — las dos muestras viejas (15 y 24-sep) que
    parecían contradecirse ponían el nivel una en el u8 y otra en el u16 c: va en LOS DOS. El 2º
    nombre es a QUÉ círculo: el cliente lo compara con el suyo (`cfg+0xBDC`, `0x5EE737`) y a sus
    miembros les abre el panel grande («Pasar de nivel Recompensas»)."""
    n = _txt(circulo, 0xFF)
    return (bytes([0x3A, int(nivel) & 0xFF]) + struct.pack("<HH", 0, int(nivel) & 0xFFFF)
            + bytes([len(n)]) + n + bytes([len(n)]) + n)


def subir_nivel(usn, azar=None):
    """-> `(paquete FFE1, cid o None, nuevo nivel o None, filas de regalo)`. Sólo el LÍDER."""
    from .circulo_tienda import PERIODOS, codigo_con_periodo, elegir_regalos
    usn = int(usn)
    k = db_circulo_de(usn) if CIRCULOS else None
    if not k:
        return armar_ffe1(1, 0, 0), None, None, []
    eco = db_economia_circulo(k["id"])
    falla = armar_ffe1(1, eco["dinero"], tope_de(eco["nivel"]))
    if rango_de(k, usn, k["rango"]) != CIRCULO_RANGO_LIDER:
        log("LOBBY", f"  ⭕ SUBIR DE NIVEL: usn={usn} no es el líder de #{k['id']} -> no")
        return falla, k["id"], None, []
    regalos = elegir_regalos(CIRCULO_REGALOS_POR_NIVEL.get(min(10, eco["nivel"] + 1), 0), azar)
    nivel, dinero, filas = db_subir_nivel_circulo(k["id"], costo_de, tope_de, regalos,
                                                  int(time.time()) + CIRCULO_REGALO_DIAS * 86400, _ahora())
    if nivel is None:
        log("LOBBY", f"  ⭕ SUBIR DE NIVEL #{k['id']}: no — {dinero}")
        return falla, k["id"], None, []
    dig30 = next(d for d, (col, _) in PERIODOS.items() if col == "P30")
    log("LOBBY", f"  ⭕ ¡CÍRCULO #{k['id']} {k['nombre']!r} SUBIÓ AL NIVEL {nivel}! quedan {dinero} de dinero; "
                 f"regalos {[f['item'] for f in filas]}")
    return (armar_ffe1(0, dinero, tope_de(nivel), [codigo_con_periodo(f["item"], dig30) for f in filas]),
            k["id"], nivel, filas)


def reenviar_ffd4(cid):
    """Le re-manda el `FFD4` a los del círculo conectados (tras donar, subir de nivel, `.circulo eco`)."""
    from .salas import CONEXIONES
    k = db_circulo_por_id(cid)
    if not k:
        return 0
    eco, fecha, top, puesto, donado, ms = _ffd4_comun(k)    # ★ una vez; sólo el aporte es de cada uno
    n = 0
    for m in ms:
        c = CONEXIONES.get(m["uid"])
        if c is not None and not getattr(c, "cerrado", False):
            p = armar_ffd4(eco, fecha, top, aporte_en_exp(donado.get(int(m["uid"]), 0)), puesto)
            c.send_ff55(0xD4, p, name=f"FFD4 datos del círculo (refresco, {len(p)} B)")
            n += 1
    return n
