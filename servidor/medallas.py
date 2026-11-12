# -*- coding: utf-8 -*-
"""medallas — el récord del jugador (ganadas, perdidas, 97%, allcombos…) y las 24 medallas.

El mapa entero, con las direcciones del exe, está en `documentacion/MEDALLAS_Y_RECORD.md`. En corto:

  · El cliente trae las medallas en `medal_lt.txt` (copia en `tablas-cliente/`) y **decide solo**
    cuáles tenés: compara el contador de la escalera (`MedalID // 100`) con el `Value`.
  · Los contadores le llegan en el `FF77` (el perfil), en un bloque de 7 `u32`:
        [medalla puesta][escalera 1][escalera 2] … [escalera 6]
  · Ponerse una: el cliente manda `FFD2 [u32 id]`; contestamos `FFD2 [u8 resultado][u32 id]`.
  · Ganar una: `FFD1 [u8 n][n × u32 id]` = el cartel «¡Medalla adquirida!» con el botón de ponérsela.
  · La puesta viaja además en el `MyRecord @65`.

Acá vive la cuenta; los paquetes salen de los handlers (`lobby_menu`, `lobby_carrera`).
"""
import os
import re
import struct

from .ajustes import (
    _DIR_SERVIDOR,
    RECORD_COLUMNAS_FF77,
    RECORD_ESCALERAS,
    RECORD_MIN_JUGADORES,
    RECORD_PD_MIN,
    RECORD_Y_MEDALLAS,
)
from .basedatos import db_record_de, db_sumar_record
from .registro import log

MEDAL_LT = os.path.join(_DIR_SERVIDOR, "tablas-cliente", "medal_lt.txt")

_TABLA = None


def tabla(ruta=None):
    """`{MedalID: {"nombre", "valor", "condicion"}}` leído del `medal_lt.txt` del cliente.

    ⚠ El archivo dice `encoding="euc-kr"` y es mentira: el texto está en Latin-1 (se tradujo encima
      del coreano sin cambiar la cabecera). Sólo se usa para el log; los números no dependen de eso.
    """
    global _TABLA
    if _TABLA is not None and ruta is None:
        return _TABLA
    with open(ruta or MEDAL_LT, "rb") as f:
        texto = f.read().decode("latin-1")
    out = {}
    for m in re.finditer(r"<Medal\s([^>]*)>", texto):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        try:
            out[int(a["MedalID"])] = {"nombre": a.get("MedalName", "").strip(),
                                      "valor": int(a.get("Value", "0")),
                                      "condicion": a.get("Condition", "M"),
                                      # ★ sólo las difíciles (x03) traen imagen de anuncio
                                      "aviso": "NoticeImage" in a}
        except (KeyError, ValueError):
            continue
    if ruta is None:
        _TABLA = out
    return out


def contador_de(rec, medalla):
    """El contador que el cliente compara con esa medalla (su escalera), o `None`."""
    campo = RECORD_ESCALERAS.get(int(medalla) // 100)
    return int(rec.get(campo, 0) or 0) if campo else None


def la_tiene(rec, medalla, t=None):
    """Lo mismo que decide el cliente: `M` = contador ≥ valor · `E` = igual · `L` = menor o igual."""
    m = (t or tabla()).get(int(medalla))
    c = contador_de(rec, medalla)
    if not m or c is None:
        return False
    if m["condicion"] == "E":
        return c == m["valor"]
    if m["condicion"] == "L":
        return c <= m["valor"]
    return c >= m["valor"]


def ganadas_por(rec, t=None):
    """Las medallas que ese récord ya tiene, en orden."""
    t = t or tabla()
    return [mid for mid in sorted(t) if la_tiene(rec, mid, t)]


def bloque_ff77(rec):
    """Los 7 `u32` del `FF77`: `[medalla puesta][escalera 1..6]`."""
    vals = [int(rec.get("medalla", 0) or 0)]
    vals += [int(rec.get(RECORD_ESCALERAS.get(i, ""), 0) or 0) for i in range(1, 7)]
    return b"".join(struct.pack("<I", v & 0xFFFFFFFF) for v in vals)


def columnas_ff77(rec):
    """`{9: n, 13: n, 17: n}` — los tres números del récord del perfil. Ver `RECORD_COLUMNAS_FF77`."""
    return {off: int(rec.get(campo, 0) or 0) for off, campo in RECORD_COLUMNAS_FF77.items()}


# ── LA SONDA DEL PERFIL (`.record sonda`) ───────────────────────────────────────────────────────
#   Números distintos y reconocibles en cada campo, para saber en pantalla qué dibuja cada uno.
#   ⚠ Los de las escaleras cruzan a propósito algunos escalones y otros no: así la pestaña muestra
#     las dos caras («Medalla adquirida» y «Record: X / Y»).
SONDA_COLUMNAS = {9: 11, 17: 22, 13: 33}
SONDA_RECORD = {"medalla": 300, "exp_max": 2500, "rcoin_max": 7000, "ganadas": 250,
                "perdidas": 123, "pd97": 60, "allcombo": 99}
SONDA_RANKING = 7
#   `.record cabeza N`: el valor de la bandera `cola[28]` del FF0C para los que tienen medalla (None =
#   no tocarla). ⚠ Un dict que se MUTA, no un nombre que se reasigna (`servidor/MAPA.md`, regla 1).
CABEZA = {"bandera": None}


def resultado(fila, puesto, ctx):
    """`"ganada"`, `"perdida"` o `None` (no cuenta). `ctx` = el de las Profecías + `"gano_equipo"`.

    · cooperativo: gana si atraparon al gorila (`perdio` falso), siempre cuenta;
    · equipos / relevo / jefe: el resultado del EQUIPO, siempre cuenta;
    · individual: el puesto 1 gana — sólo si corrieron al menos `RECORD_MIN_JUGADORES`.
    """
    if ctx.get("coop"):
        return "perdida" if fila.get("perdio") else "ganada"
    if ctx.get("equipo"):
        g = ctx.get("gano_equipo")
        if g is None:
            return None
        return "ganada" if g else "perdida"
    if int(ctx.get("jugadores") or 0) < RECORD_MIN_JUGADORES:
        return None
    return "ganada" if (puesto == 1 and not fila.get("fallo")) else "perdida"


def cuentas_de_carrera(fila, puesto, ctx, exp_total, rcoin_total, combo_total):
    """Lo que suma UNA carrera: `(sumas, maximos)`. Pura, para poder probarla."""
    sumas, maximos = {}, {}
    res = resultado(fila, puesto, ctx)
    if res:
        sumas["ganadas" if res == "ganada" else "perdidas"] = 1
    if not fila.get("fallo"):
        if int(fila.get("pd") or 0) >= RECORD_PD_MIN:
            sumas["pd97"] = 1
        if combo_total and int(fila.get("combo") or 0) >= int(combo_total):
            sumas["allcombo"] = 1
    maximos["exp_max"] = max(0, int(exp_total or 0))
    maximos["rcoin_max"] = max(0, int(rcoin_total or 0))
    return sumas, maximos


def contar_carrera(usn, fila, puesto, ctx, exp_total, rcoin_total, combo_total):
    """Suma la carrera al récord de `usn` y devuelve las medallas NUEVAS (para el `FFD1`)."""
    if not RECORD_Y_MEDALLAS or not usn:
        return []
    sumas, maximos = cuentas_de_carrera(fila, puesto, ctx, exp_total, rcoin_total, combo_total)
    viejo, nuevo = db_sumar_record(int(usn), sumas=sumas, maximos=maximos)
    t = tabla()
    nuevas = [m for m in ganadas_por(nuevo, t) if not la_tiene(viejo, m, t)]
    log("LOBBY", f"  🏅 RÉCORD usn={usn}: +{sumas or '{}'} máx {maximos} -> "
                 f"G{nuevo['ganadas']} P{nuevo['perdidas']} 97%:{nuevo['pd97']} AC:{nuevo['allcombo']} "
                 f"EXPmáx {nuevo['exp_max']} RCmáx {nuevo['rcoin_max']}"
                 + (f"  ★ MEDALLA(S) NUEVA(S): {[(m, t[m]['nombre']) for m in nuevas]}" if nuevas else ""))
    return nuevas


def medalla_puesta(usn):
    """La medalla puesta de ese usn (0 = ninguna). ⚠ Si la base falla va 0: es un adorno y no puede
    tumbar la lista de la sala ni el MyRecord."""
    try:
        return int(db_record_de(int(usn)).get("medalla", 0) or 0) if (usn and RECORD_Y_MEDALLAS) else 0
    except Exception as e:                                        # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude leer la medalla de usn={usn}: {e!r}")
        return 0


def poner_medalla(usn, medalla):
    """El `FFD2` del jugador. Devuelve el resultado para el cliente: 0 = puesta · 1 = no la tiene.
    `0` como id = sacársela."""
    medalla = int(medalla)
    rec = db_record_de(int(usn))
    if medalla and not la_tiene(rec, medalla):
        log("LOBBY", f"  🏅 FFD2: usn={usn} pidió la medalla {medalla} y NO la tiene (récord {rec})")
        return 1
    db_sumar_record(int(usn), poner={"medalla": medalla})
    log("LOBBY", f"  🏅 FFD2: usn={usn} se puso la medalla {medalla} "
                 f"({tabla().get(medalla, {}).get('nombre', 'ninguna')})")
    return 0


def armar_ffd1(ids):
    """`FFD1` = el cartel «¡Medalla adquirida!»: `[u8 n][n × u32 id]` (handler `0x5E1430`)."""
    ids = [int(i) for i in ids][:0xFF]
    return bytes([len(ids)]) + b"".join(struct.pack("<I", i) for i in ids)


def se_anuncia(medalla, t=None):
    """¿Esta medalla se anuncia a TODO el server? Ver `MEDALLA_AVISO_GLOBAL`."""
    from .ajustes import MEDALLA_AVISO_GLOBAL
    if MEDALLA_AVISO_GLOBAL == "todas":
        return True
    if MEDALLA_AVISO_GLOBAL == "dificiles":
        return bool((t or tabla()).get(int(medalla), {}).get("aviso"))
    return False


def armar_ff40_36(medalla, apodo):
    """`FF40` subtipo **0x36** = la línea del chat «%s usuario <%s> medallas adquirida» (system.csv
    699) en TODOS los que la reciben. `[0x36][u32 id][u8 len][apodo]` (caso `0x5F1DB2` del `FF40`:
    lee el id, el largo —si es menor a 0x40— y el apodo, y llama a `0x467AB0`, que busca el nombre
    de la medalla y arma la línea)."""
    n = str(apodo or "").encode("cp1252", "replace")[:0x3F]
    return bytes([0x36]) + struct.pack("<I", int(medalla) & 0xFFFFFFFF) + bytes([len(n)]) + n


def armar_ffd2(resultado_, medalla):
    """`FFD2` = la respuesta a «ponerme ésta»: `[u8 resultado][u32 id]` (handler `0x5E1540`)."""
    return bytes([resultado_ & 0xFF]) + struct.pack("<I", int(medalla) & 0xFFFFFFFF)
