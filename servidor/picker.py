# -*- coding: utf-8 -*-
"""picker — lo que el PICKER de la sala le pide al server (29-sep).

El mapa entero, y de dónde sale cada dirección: `documentacion/PICKER_SISTEMA.md`. Acá van las tres
piezas que son SÓLO del server:

  1. las PREFERIDAS (el ícono de la fila y «Lista de canciones preferidas")
       C→S `FF138` agregar · `FF13A` quitar   [u16 n][u16 canción]×n   al «Completado»/cerrar (`0x5BD320`)
       C→S `FF137` vacío al entrar -> S→C `FF137` [u16 n][u16 canción]×n   (`0x5E19F0`)
     ⛔ Hasta hoy el FF138/FF13A caían en «SIN handler» (en prod desde el 08-sep) y el FF137 iba vacío.

  2. «MI RECORD» — el `FF139` (`CmdGetPlayData`, `0x5DC600` -> `0x5B9C50`), 19 B:
       [u16 canción][u8 flag][u16 mejor combo][u16 precisión ENTERA][u32 veces]
       [u32 puesto de popularidad (999 = «-°»)][u32 cuántos puestos subió (+) o bajó (-)]
     Lo pide el cliente cuando el cursor se queda ~1,5 s sobre una canción. Iba todo en 0.
     ⛔ Los DECIMALES no: el número sólo dibuja dígitos (`0x68D1A0` = itoa). Hace falta la DLL.

  4. las MANERAS DE LISTA (`modo_de_ff1c`, `sortear`): Aleatorio / TOP 20 / NUEVOS 20 los sortea el
     SERVER en el START (el cliente manda canción 0); «En orden» lo avanza el cliente (FF1C tipo 6).

  3. la POPULARIDAD — `FF13B` (`CmdTopMusicList`, `0x5DC6E0`): [u16 n]{u16 canción, u16 puesto}
     -> `canción+0x596`, que usan el orden «popular» y el TOP 20. El cliente lo pide al entrar y
     caía en «SIN handler». Sale de las jugadas terminadas de los últimos días (`jugadas_dia`).
"""
import struct
import threading
import time

from .ajustes import (
    OWNED_SONGS_2013,
    PICKER_FF139_FLAG,
    PICKER_POPULAR_CADA,
    PICKER_POPULAR_DIAS,
    PICKER_POPULAR_TOPE,
    PICKER_PREFERIDAS,
    PICKER_RECORD,
    PICKER_RECORD_DECIMALES,
    PICKER_TOP5,
    PICKER_TOP5_N,
)
from .basedatos import (
    db_anotar_record_cancion,
    db_cambiar_preferidas,
    db_jugadas_por_cancion,
    db_preferidas_de,
    db_record_cancion_de,
    db_top_cancion,
)
from .registro import hx, log

SIN_PUESTO = 999                     # el cliente dibuja «-° lugar(» (`0x5BC983`)
PREFERIDAS_TOPE = 2000               # más de las que hay en el catálogo: sólo corta basura


# ── 1 · las preferidas ──────────────────────────────────────────────────────────────────────
def leer_lista(data):
    """`[u16 n][u16 canción]×n` -> lista, o None si el largo no cierra."""
    if len(data) < 2:
        return None
    n = struct.unpack_from("<H", data, 0)[0]
    if n > PREFERIDAS_TOPE or len(data) < 2 + 2 * n:
        return None
    return [struct.unpack_from("<H", data, 2 + 2 * i)[0] for i in range(n)]


def armar_lista(canciones):
    canciones = list(canciones)[:0xFFFF]
    return struct.pack("<H", len(canciones)) + b"".join(struct.pack("<H", c & 0xFFFF) for c in canciones)


def cambiar_preferidas(st, cmd, data):
    """`FF138` (agregar) / `FF13A` (quitar). El cliente no espera respuesta."""
    uid = int(getattr(st, "usn", 0) or 0)
    lista = leer_lista(data)
    if lista is None or not uid:
        log("LOBBY", f"  ⚠ FF{cmd:02X} preferidas: no cierra el largo (usn={uid}): {hx(data)}")
        return
    if not PICKER_PREFERIDAS:
        return
    if cmd == 0x138:
        db_cambiar_preferidas(uid, agregar=lista)
    else:
        db_cambiar_preferidas(uid, quitar=lista)
    log("LOBBY", f"  ★ FF{cmd:02X} preferidas usn={uid}: {'+' if cmd == 0x138 else '-'}{lista}")


def respuesta_ff137(uid):
    """Las preferidas de `uid` que están en el catálogo de hoy (el cliente ignora las que no conoce)."""
    if not (PICKER_PREFERIDAS and uid):
        return bytes(2)
    _hay = set(OWNED_SONGS_2013)
    prefs = [c for c in db_preferidas_de(uid) if not _hay or c in _hay]
    return armar_lista(prefs)


# ── 3 · la popularidad (va antes que el 2 porque el FF139 la usa) ─────────────────────────
_POP = {"hora": 0.0, "puestos": {}, "antes": {}, "top": []}
_POP_LOCK = threading.Lock()


def _dia(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _ranking(cuentas):
    """`{canción: veces}` -> `{canción: puesto}` (1 = la más jugada; empate: la de id menor)."""
    orden = sorted(cuentas.items(), key=lambda kv: (-kv[1], kv[0]))
    return {c: i + 1 for i, (c, v) in enumerate(orden) if v > 0}


def recalcular_popularidad(ahora=None):
    """Una pasada en LOTE: dos consultas agrupadas, no una por pedido."""
    ahora = time.time() if ahora is None else ahora
    d = max(1, int(PICKER_POPULAR_DIAS))
    hoy = db_jugadas_por_cancion(_dia(ahora - (d - 1) * 86400), _dia(ahora))
    ayer = db_jugadas_por_cancion(_dia(ahora - d * 86400), _dia(ahora - 86400))
    puestos, antes = _ranking(hoy), _ranking(ayer)
    with _POP_LOCK:
        _POP.update(hora=ahora, puestos=puestos, antes=antes,
                    top=sorted(puestos, key=puestos.get)[:max(0, int(PICKER_POPULAR_TOPE))])
    return puestos


def _popularidad():
    with _POP_LOCK:
        vieja = time.time() - _POP["hora"] > PICKER_POPULAR_CADA
    if vieja:
        try:
            recalcular_popularidad()
        except Exception as e:                                       # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude recalcular la popularidad de las canciones: {e!r}")
            with _POP_LOCK:
                _POP["hora"] = time.time()                           # no reintentar en cada pedido
    with _POP_LOCK:
        return _POP["puestos"], _POP["antes"], _POP["top"]


def puesto_de(cancion):
    """`(puesto, cambio)`: el puesto de la canción (999 si no entra) y cuántos subió desde ayer."""
    puestos, antes, _ = _popularidad()
    p = puestos.get(int(cancion))
    if p is None or p > PICKER_POPULAR_TOPE:
        return SIN_PUESTO, 0
    a = antes.get(int(cancion))
    return p, (a - p) if a else 0


def respuesta_ff13b():
    puestos, _, top = _popularidad()
    return (struct.pack("<H", len(top))
            + b"".join(struct.pack("<HH", c & 0xFFFF, min(puestos[c], 0xFFFF)) for c in top))


def top(n):
    """Las `n` canciones más jugadas (para el TOP 20 ALEATORIO)."""
    return list(_popularidad()[2][:n])


# ── 2 · «Mi record» ─────────────────────────────────────────────────────────────────────────
def playdata(uid, cancion):
    """Los 19 B del `FF139` para `uid` en esa canción. La canción va PRIMERO: es la llave del
    candado del cliente (si no coincide con la del cursor, lo ignora).

    ★ + 2 B de milésimas al final (`PICKER_RECORD_DECIMALES`) si hay récord y la precisión es < 100:
      el exe parcheado las lee a la mitad alta del pd y dibuja «94.354» (`herramientas/record_decimales.py`)."""
    r = (db_record_cancion_de(uid, cancion) if (PICKER_RECORD and uid and cancion) else None) or {}
    flag = 1 if (PICKER_FF139_FLAG == "allcombo" and r.get("allcombo")) else 0
    puesto, cambio = puesto_de(cancion) if (PICKER_RECORD and cancion) else (0, 0)
    return (struct.pack("<H", cancion & 0xFFFF) + bytes([flag])
            + struct.pack("<HH", min(r.get("mejor_combo", 0), 0xFFFF), min(r.get("mejor_pd", 0) // 1000, 100))
            + struct.pack("<I", min(r.get("veces", 0), 999999))
            + struct.pack("<Ii", puesto, cambio)
            + _milesimas(r))


def _milesimas(r):
    """Los 2 B del final del FF139: las milésimas del récord, o nada (= el exe dibuja el entero)."""
    pd = int(r.get("mejor_pd") or 0)
    if not (PICKER_RECORD_DECIMALES and pd and pd < 100000):
        return b""
    return struct.pack("<H", pd % 1000)


# ── 2-bis · ★ TOP 5 RANK (09-oct) ──────────────────────────────────────────────────────────────
#   La cola NUESTRA del FF139, detrás de las milésimas. La lee la d3d9 (`top5.c`, en el cave de las milésimas):
#     b"T5" · u16 canción · u16 largo · [largo B]:
#       u8 n · n × FILA · u16 mi puesto (0 = nunca la terminó) · [FILA mía, sólo si el puesto no es 0]
#     FILA = u8 L · apodo (L B, cp1252) · u16 combo · u32 precisión ×1000 · u32 fecha (epoch) · u8 all combo
#            · u32 tiempo de llegada (pasos = 1/60 s; 0 = no se sabe: los récords de antes del 09-oct)
#   ⚠ El ORDEN es un contrato con top5.c (`t5_leer_fila`): si cambia acá, cambia allá.
TOP5_MAGIA = b"T5"
TOP5_APODO_TOPE = 20


def _fila_top5(f):
    nick = (f.get("nick") or "").encode("cp1252", "replace")[:TOP5_APODO_TOPE]
    return (bytes([len(nick)]) + nick
            + struct.pack("<HIIBI", min(f["combo"], 0xFFFF), min(f["pd"], 100000), max(0, f["fecha"]) & 0xFFFFFFFF,
                          1 if f.get("allcombo") else 0, max(0, f.get("frame") or 0) & 0xFFFFFFFF))


def cola_top5(uid, cancion):
    """Los bytes que van DETRÁS del FF139 (ya con sus milésimas): el ranking de la canción."""
    filas, mio = db_top_cancion(cancion, PICKER_TOP5_N, uid) if cancion else ([], None)
    cuerpo = bytes([len(filas)]) + b"".join(_fila_top5(f) for f in filas)
    cuerpo += struct.pack("<H", min(mio[0], 0xFFFF) if mio else 0) + (_fila_top5(mio[1]) if mio else b"")
    return TOP5_MAGIA + struct.pack("<HH", cancion & 0xFFFF, len(cuerpo)) + cuerpo


def playdata_con_top5(uid, cancion):
    """El FF139 entero: los 19 B · las milésimas SIEMPRE (0xFFFF = sin decimales, el exe dibuja el entero) ·
    la cola del TOP 5 RANK. Con `PICKER_TOP5` apagado, el FF139 de siempre."""
    pd = playdata(uid, cancion)
    if not PICKER_TOP5:
        return pd
    if len(pd) == 19:
        pd += b"\xff\xff"
    return pd + cola_top5(uid, cancion)


def contar_carrera(uid, cancion, fila, combo_total):
    """Suma la carrera al récord de (uid, canción). Sólo las TERMINADAS (el que abandonó no cuenta)."""
    if not (PICKER_RECORD and uid and cancion) or fila.get("fallo"):
        return
    combo = int(fila.get("combo") or 0)
    pd = max(0, min(int(fila.get("pd") or 0), 100))
    mil = max(0, min(int(fila.get("milesimas") or 0), 999)) if pd < 100 else 0
    allc = bool(combo_total) and combo >= int(combo_total)
    frame = int(fila.get("frame") or 0)              # ★ TOP 5 RANK: el tiempo de llegada (FF28 C→S @0)
    db_anotar_record_cancion(uid, cancion, combo, pd * 1000 + mil, allc, frame if 0 < frame < 0xFFFFFFFF else 0)
    log("LOBBY", f"  🎵 récord de la canción {cancion} usn={uid}: combo {combo} · {pd}.{mil:03d}%"
                 + (" · ALL COMBO" if allc else ""))


# ── 4 · las maneras de lista ────────────────────────────────────────────────────────────────
#   El tipo del `FF1C` C→S que manda el ANFITRIÓN al elegir el modo (`SetMode` `0x5BEAC0`, medido en el
#   log de prod del 23-sep). Los demás tipos (1/2 una casilla, 3/4 todas, 7..14 y 0x24..0x37 por banda)
#   son CASILLAS, no cambian el modo.
MODOS_FF1C = {0: "una", 6: "orden", 5: "aleatorio", 0x1F: "top20", 0x20: "nuevos20"}
MODOS_AL_AZAR = ("aleatorio", "top20", "nuevos20")


def modo_de_ff1c(tipo):
    return MODOS_FF1C.get(int(tipo))


#   El `FF1C` S→C que pone el cartel de cada modo al azar (`0x5CDD40`, tabla de saltos `0x5CDFF8`):
#     5 -> SetMusic(0) + SetMode(1) · 0x1F -> SetMode(2) · 0x20 -> SetMode(3)   (sin eco: `enviar` = 0)
#   ⚠ Al INVITADO `SetMode` le clava la pestaña en 4 (la canción): a él sólo le sirve el 5 (canción 0 =
#     «Aleatoria»). ⛔ `documentacion/PICKER_Y_PISTA.md` §12 tenía esta tabla corrida en uno (0x1E/0x1F).
FF1C_DEL_MODO = {"aleatorio": 5, "top20": 0x1F, "nuevos20": 0x20}


def ff1c_cartel(modo, es_anfitrion):
    """Los 5 B del `FF1C` que le repone a uno el cartel de un modo al azar, o None si no es al azar."""
    if modo not in FF1C_DEL_MODO:
        return None
    tipo = FF1C_DEL_MODO[modo] if es_anfitrion else 5
    return bytes([tipo, 0, 0, {5: 2, 0x1F: 3, 0x20: 4}[tipo], 0])


def candidatas(modo, banda=None):
    """De dónde sale la canción de cada modo al azar. Sólo canciones del catálogo de hoy."""
    from . import notas                                              # noqa: PLC0415
    hay = list(OWNED_SONGS_2013)
    if modo == "top20":
        _set = set(hay)
        return [c for c in top(20) if not _set or c in _set]
    if modo == "nuevos20":
        return sorted(hay)[-20:]                   # las de id más alto = las últimas importadas
    if modo == "aleatorio":
        # ⚠ Las TILDADAS del anfitrión todavía no se llevan (paso 5 del plan). El cliente las arma por la
        #   banda de la sala (`0x5BDC80`), así que el default nativo es exactamente «las de su banda».
        return [c for c in hay if banda is None or notas.banda_de(c) == banda]
    return []


def sortear(modo, banda=None, rng=None):
    """La canción de un modo al azar, o None (el llamador se queda con la de la sala)."""
    import random                                                    # noqa: PLC0415
    rng = rng or random
    pool = candidatas(modo, banda)
    if modo == "top20" and len(pool) < 20:
        # ⛔ 29-sep, anonimo03: *"siempre se marca la misma canción"*. Con el conteo recién empezado el top
        #   tenía UNA canción (la única terminada) y el sorteo no tenía de dónde elegir. Mientras no haya
        #   20 con jugadas, se completa con canciones de la banda de la sala, como Aleatorio.
        _resto = [c for c in candidatas("aleatorio", banda) if c not in pool]
        pool = pool + rng.sample(_resto, min(20 - len(pool), len(_resto)))
    return rng.choice(pool) if pool else None
