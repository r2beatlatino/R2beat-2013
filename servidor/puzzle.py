# -*- coding: utf-8 -*-
"""puzzle — LAS MISIONES DE ROMPECABEZAS: la tragamonedas de «Modo Misión» (15-oct-2026).

El mapa entero (paquetes, el registro de 88 B, los estados, el comparador del cliente): `documentacion/MISIONES_PUZZLE.md`.
anonimo03, 15-oct: *«las carreras de entrenamiento no cuentan»* · *«una misión completa se reinicia con el reset del día:
volver a hacer las misiones»* · el premio (`PUZZLE_*_POR` en ajustes), al verlo andar: *«el de prueba me gusta»*.

EL CICLO (todo del lobby; ⛔ nada se manda en carrera — el `FFB2` de avance llega DESPUÉS del `FF28`)
    FFAF  C→S «mis misiones» (login, canal, vencida)        S→C [n][n×88 B][aceptadas hoy][rearmadas hoy][0][0][0]
    FFAC  C→S [u32 0][u8 0][u8 círculo=0] «armame una»       S→C [res] + [88 B]   (el de círculo sigue en lobby_menu)
    FFB0  C→S [u32 id][u8 estado] los rodillos '0'…'3'        (no se contesta)
    FFB1  C→S [u32 id] «Recibiendo misión» = aceptar          S→C [0][88 B] · [1] = mudo
    FFAE  C→S [u32 id] «Reconstruyendo» = rearmar             S→C [0] (el cliente pide solo el FFAC) · [4] máx 3 por día
    FFB2  C→S [u32 id] AVANCE (lo manda el cliente al ver el FF28) o COBRO («Recompensas», hechas = meta)
          avance → S→C [id][hechas] (⛔ VERIFICADO contra la última carrera que vio el server; [id][0] = mudo)
          cobro  → S→C FFB3 [id][ítem][Rcoin][EXP] (el cartel; el cliente lo suma en pantalla) + FFB5 [id][0] (la saca)
    FFB5  C→S [u32 id] «Misión Abandonar»                     S→C [id][0] · [id][3] «no corresponde»

LO QUE PONE EL SERVER (el XML del cliente no trae ni premio ni meta ni canción):
    · qué misión: del XML, por el NIVEL del jugador (`Min_Level`…`Max_Level`), sin repetir una que ya tenga viva.
      ⏳ Fuera por ahora las 2 de GESTO (`Action`): falta verificar la palabra (MISIONES_PUZZLE.md §5.5).
    · la canción: el XML dice canal + E/N/H. El canal es una BANDA del picker (`CANAL_A_BANDA`) y E/N/H, el tercio de
      las canciones de esa banda ordenadas por nivel. Sólo canciones que servimos (`OWNED_SONGS_2013`).
    · la meta: al azar entre 1 y el 4.º dígito del id (la dificultad del criterio, §2.2) — el 3er rodillo.
    · el premio: escalón (dígitos 2-3 del id) × meta × `PUZZLE_RCOIN_POR` / `PUZZLE_EXP_POR` (anonimo03: «me gusta»).
    · el vencimiento: la MEDIANOCHE DE PERÚ (el reset de la Misión de hoy). Cobrada o no, ahí se termina.
"""
import random
import re
import struct
import threading
import time

from . import almacen
from .registro import log

TABLA = "puzzlemission_lt.xml"
# el «Channel» del XML (1…9) → la BANDA del picker (`notas.NOMBRE_BANDA`), por el texto de cada una y sus niveles
CANAL_A_BANDA = {8: 8, 1: 1, 5: 2, 2: 3, 6: 4, 3: 5, 4: 6, 9: 7}
MAX_ACEPTADAS_DIA, MAX_REARMADAS_DIA, MAX_LISTA = 5, 3, 30          # los de los carteles del propio cliente
EN_ARMADO, ACEPTADA = "0123", "NS"
# FFAC: 0 ok · 1 «Misión superpuesta» · 2 «máx 30» · 5 «falla al obtener la ID» · 6 «máx 5 por día»
AC_OK, AC_SUPERPUESTA, AC_MAX30, AC_SIN_ID, AC_MAX5 = 0, 1, 2, 5, 6
AE_OK, AE_MAX3, AE_FALLA = 0, 4, 7
B5_OK, B5_NO_HAY = 0, 3
CARRERA_VALE_S = 900                # el FFB2 de avance tiene que llegar hasta 15 min después de la carrera

TABLAS = """
CREATE TABLE IF NOT EXISTS puzzle_misiones (
    id_fila INTEGER PRIMARY KEY AUTOINCREMENT, usn INTEGER NOT NULL, dia TEXT NOT NULL, mision INTEGER NOT NULL,
    parametro TEXT NOT NULL DEFAULT '', meta INTEGER NOT NULL, hechas INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL, item INTEGER NOT NULL DEFAULT 0, rcoin INTEGER NOT NULL DEFAULT 0, exp INTEGER NOT NULL DEFAULT 0,
    creada REAL NOT NULL, aceptada REAL, vence REAL NOT NULL, ultima_carrera INTEGER NOT NULL DEFAULT 0,
    fin TEXT);
CREATE INDEX IF NOT EXISTS puzzle_misiones_vivas ON puzzle_misiones (usn, fin);
CREATE TABLE IF NOT EXISTS puzzle_dia (
    usn INTEGER NOT NULL, dia TEXT NOT NULL, aceptadas INTEGER NOT NULL DEFAULT 0, rearmadas INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (usn, dia));
"""
_tablas_ok = set()
_xml = None
_lock = threading.Lock()
ULTIMA = {}                         # usn → la última carrera que vio el server (la que verifica el FFB2)


def _con():
    """⚠ Llamar con `almacen._lock` tomado."""
    c = almacen.conectar()
    if id(c) not in _tablas_ok:
        c.executescript(TABLAS)
        _tablas_ok.add(id(c))
    return c


# ── el XML del cliente (copiado en servidor/tablas-cliente/, latin-1 aunque la cabecera diga euc-kr) ─────────────────

def misiones():
    """{MissionID: {atributos del XML}} — las personales que sabemos verificar."""
    global _xml
    if _xml is None:
        import os
        from .ajustes import _DIR_SERVIDOR
        with open(os.path.join(_DIR_SERVIDOR, "tablas-cliente", TABLA), encoding="latin-1") as f:
            t = f.read()
        out = {}
        for m in re.finditer(r"<Mission\s([^>]*)>", t):
            a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            if "Action" in a:                    # ⏳ las de gesto: falta verificar la palabra
                continue
            out[int(a["MissionID"])] = a
        _xml = out
    return _xml


def veces_max(mision):
    """El 4.º dígito del id = cuántas veces como mucho (MISIONES_PUZZLE.md §2.2)."""
    s = str(int(mision))
    return max(1, int(s[3])) if len(s) >= 4 and s[3].isdigit() else 1


def escalon(mision):
    """Los dígitos 2-3 del id (01…18): crecen con el canal y la dificultad."""
    s = str(int(mision))
    return max(1, int(s[1:3])) if len(s) >= 3 and s[1:3].isdigit() else 1


def premio_de(mision, meta):
    from .ajustes import PUZZLE_EXP_POR, PUZZLE_RCOIN_POR
    e = escalon(mision) * int(meta)
    return {"item": 0, "rcoin": e * PUZZLE_RCOIN_POR, "exp": e * PUZZLE_EXP_POR}


def canciones_para(canal, dificultad):
    """Las canciones de la banda del canal, en el tercio E (fáciles) / N / H (difíciles) por nivel."""
    from . import notas
    from .ajustes import OWNED_SONGS_2013
    banda = CANAL_A_BANDA.get(int(canal))
    pool = sorted((int(notas.nivel_de(c, 0) or 0), c) for c in OWNED_SONGS_2013 if notas.banda_de(c) == banda)
    if not pool:
        return []
    n = len(pool)
    i = {"E": 0, "N": 1, "H": 2}.get(dificultad, 1)
    parte = pool[i * n // 3:(i + 1) * n // 3] or pool
    return [c for _, c in parte]


def parametro_de(a, rng=random):
    """El `+06` del registro: la canción, la pista o vacío. None si no hay con qué armarla."""
    if "Music_Select" in a:
        pool = canciones_para(a.get("Channel", 0), a["Music_Select"])
        return str(rng.choice(pool)) if pool else None
    if "Stage_Select" in a:
        from .ajustes import OWNED_STAGES_2013
        pool = [p for p in OWNED_STAGES_2013 if p]
        return str(rng.choice(pool)) if pool else None
    return ""


# ── el día (el mismo de la Misión de hoy: medianoche de Perú) ────────────────────────────────────────────────────────

def dia():
    from .mision_hoy import dia as _dia
    return _dia()


def fin_del_dia():
    from .mision_hoy import comienzo_del_dia
    return comienzo_del_dia() + 86400


def _fecha(t):
    """«YYYYMMDDhhmm» en la hora del server (la misma del `FF97`): el cliente le suma su desfase."""
    return time.strftime("%Y%m%d%H%M", time.localtime(t)).encode("ascii")


def armar_88(f):
    """El registro de 88 B (`0x43BB40`). `f` = una fila de `puzzle_misiones`."""
    b = bytearray(88)
    struct.pack_into("<IBB", b, 0, int(f["mision"]), min(int(f["hechas"]), 255), int(f["meta"]))
    p = str(f["parametro"] or "").encode("latin-1", "replace")[:35]
    b[0x06:0x06 + len(p)] = p
    b[0x2A:0x2A + 12] = _fecha(f["aceptada"] or f["creada"])
    b[0x3A:0x3A + 12] = _fecha(f["vence"])
    b[0x4A] = ord(f["estado"][:1] or "0")
    struct.pack_into("<III", b, 0x4C, int(f["item"]), int(f["rcoin"]), int(f["exp"]))
    return bytes(b)


# ── la base ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def _vencer(c, usn, ahora):
    c.execute("UPDATE puzzle_misiones SET fin='vencida' WHERE usn=? AND fin IS NULL AND (vence<=? OR dia<>?)",
              (int(usn), ahora, dia()))


def vivas(usn):
    """Las misiones vivas (en armado o aceptadas) de hoy, viejas primero. Vence lo vencido antes de contestar."""
    with almacen._lock:
        c = _con()
        _vencer(c, usn, time.time())
        c.commit()
        filas = c.execute("SELECT * FROM puzzle_misiones WHERE usn=? AND fin IS NULL ORDER BY id_fila", (int(usn),)).fetchall()
    return [dict(r) for r in filas]


def contadores(usn):
    with almacen._lock:
        r = _con().execute("SELECT aceptadas, rearmadas FROM puzzle_dia WHERE usn=? AND dia=?", (int(usn), dia())).fetchone()
    return (int(r[0]), int(r[1])) if r else (0, 0)


def _sumar_dia(c, usn, campo):
    c.execute(f"INSERT INTO puzzle_dia (usn, dia, {campo}) VALUES (?, ?, 1) "
              f"ON CONFLICT (usn, dia) DO UPDATE SET {campo}={campo}+1", (int(usn), dia()))


def _fila(usn, mision):
    for f in vivas(usn):
        if f["mision"] == int(mision):
            return f
    return None


def _cambiar(id_fila, **campos):
    with almacen._lock:
        c = _con()
        c.execute("UPDATE puzzle_misiones SET " + ", ".join(f"{k}=?" for k in campos) + " WHERE id_fila=?",
                  (*campos.values(), int(id_fila)))
        c.commit()


def _nivel(usn):
    from .basedatos import db_get_char
    from .progresion import nivel_de_exp
    return nivel_de_exp(int((db_get_char(usn) or {}).get("exp", 0) or 0))


def sortear(usn, rng=random):
    """Una misión nueva para `usn` (su nivel, sin repetir una viva) con su parámetro, meta y premio, o None."""
    nivel = _nivel(usn)
    tiene = {f["mision"] for f in vivas(usn)}
    with almacen._lock:                         # ★ lo que REARMÓ hoy no vuelve a salir (visto en el juego: rearmó y le
        tiro = {r[0] for r in _con().execute(    #   tocó la misma) — salvo que no quede otra cosa
            "SELECT mision FROM puzzle_misiones WHERE usn=? AND dia=? AND fin='rearmada'", (int(usn), dia()))}
    ids = [i for i, a in misiones().items()
           if i not in tiene and int(a.get("Min_Level", 0) or 0) <= nivel <= int(a.get("Max_Level", 99) or 99)]
    rng.shuffle(ids)
    ids.sort(key=lambda i: i in tiro)           # estable: primero las que no rearmó, en orden al azar
    for i in ids:
        p = parametro_de(misiones()[i], rng)
        if p is None:
            continue
        meta = rng.randint(1, veces_max(i))
        return {"mision": i, "parametro": p, "meta": meta, **premio_de(i, meta)}
    return None


# ── los paquetes ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _id_de(data):
    return struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else 0


def _activo():
    from .ajustes import PUZZLE_ACTIVO
    return PUZZLE_ACTIVO


def h_ffaf(st, cmd, data):
    """`FFAF` «mis misiones»: la lista de hoy y los dos contadores. La de círculo, vacía."""
    usn = int(getattr(st, "usn", 0) or 0)
    filas = vivas(usn) if (_activo() and usn) else []
    ac, re_ = contadores(usn) if usn else (0, 0)
    cuerpo = (bytes([len(filas) & 0xFF]) + b"".join(armar_88(f) for f in filas)
              + bytes([min(ac, 255), min(re_, 255)]) + b"\x00\x00\x00")
    st.send_ff55(0xAF, cuerpo, name=f"FFAF misiones puzzle: {len(filas)} (aceptadas hoy {ac}, rearmadas {re_})")


def h_ffac(st, cmd, data):
    """`FFAC` personal «armame una misión» (clic en el 1er rodillo + Sí)."""
    usn = int(getattr(st, "usn", 0) or 0)
    with _lock:
        res, fila = _armar(usn)
    if res != AC_OK:
        st.send_ff55(0xAC, bytes([res]), name=f"FFAC misión puzzle -> {res}")
        return
    st.send_ff55(0xAC, bytes([AC_OK]) + armar_88(fila),
                 name=f"FFAC misión puzzle {fila['mision']} ({fila['parametro'] or '-'}, {fila['meta']} vez/veces)")
    log("LOBBY", f"  🧩 PUZZLE usn={usn}: armó {fila['mision']} param={fila['parametro']!r} meta={fila['meta']} "
                 f"premio {fila['rcoin']} Rcoin + {fila['exp']} EXP")


def _armar(usn):
    if not _activo() or not usn:
        return AC_SIN_ID, None
    vv = vivas(usn)
    if any(f["estado"] in EN_ARMADO for f in vv):
        return AC_SUPERPUESTA, None
    if len(vv) >= MAX_LISTA:
        return AC_MAX30, None
    if contadores(usn)[0] >= MAX_ACEPTADAS_DIA:
        return AC_MAX5, None
    m = sortear(usn)
    if not m:
        return AC_SIN_ID, None
    ahora = time.time()
    with almacen._lock:
        c = _con()
        cur = c.execute("INSERT INTO puzzle_misiones (usn, dia, mision, parametro, meta, estado, item, rcoin, exp, creada, vence) "
                        "VALUES (?, ?, ?, ?, ?, '0', ?, ?, ?, ?, ?)",
                        (usn, dia(), m["mision"], m["parametro"], m["meta"], m["item"], m["rcoin"], m["exp"], ahora, fin_del_dia()))
        c.commit()
        f = dict(c.execute("SELECT * FROM puzzle_misiones WHERE id_fila=?", (cur.lastrowid,)).fetchone())
    return AC_OK, f


def h_ffb0(st, cmd, data):
    """`FFB0 [u32 id][u8 estado]` — el rodillo que frenó. No se contesta: se guarda, para restaurar al volver."""
    f = _fila(getattr(st, "usn", 0), _id_de(data))
    if f and len(data) >= 5 and chr(data[4]) in EN_ARMADO and f["estado"] in EN_ARMADO:
        _cambiar(f["id_fila"], estado=chr(data[4]))


def h_ffb1(st, cmd, data):
    """`FFB1 [u32 id]` «Recibiendo misión» = aceptarla (sólo con los tres rodillos frenados)."""
    usn = int(getattr(st, "usn", 0) or 0)
    with _lock:
        f = _fila(usn, _id_de(data))
        if not f or f["estado"] != "3" or contadores(usn)[0] >= MAX_ACEPTADAS_DIA:
            st.send_ff55(0xB1, bytes([1]), name=f"FFB1 aceptar misión puzzle {_id_de(data)} -> NO (mudo)")
            return
        ahora = time.time()
        _cambiar(f["id_fila"], estado="N", aceptada=ahora, vence=fin_del_dia())
        with almacen._lock:
            c = _con()
            _sumar_dia(c, usn, "aceptadas")
            c.commit()
        f.update(estado="N", aceptada=ahora, vence=fin_del_dia())
    st.send_ff55(0xB1, bytes([0]) + armar_88(f), name=f"FFB1 misión puzzle {f['mision']} ACEPTADA")
    log("LOBBY", f"  🧩 PUZZLE usn={usn}: aceptó {f['mision']} (vence a la medianoche de Perú)")


def h_ffae(st, cmd, data):
    """`FFAE [u32 id]` «Recibiendo misión otra vez (Reconstruyendo)»: tira la que está en armado (máx 3 por día)."""
    usn = int(getattr(st, "usn", 0) or 0)
    with _lock:
        f = _fila(usn, _id_de(data))
        if contadores(usn)[1] >= MAX_REARMADAS_DIA:
            res = AE_MAX3
        elif not f or f["estado"] not in EN_ARMADO:
            res = AE_FALLA
        else:
            _cambiar(f["id_fila"], fin="rearmada")
            with almacen._lock:
                c = _con()
                _sumar_dia(c, usn, "rearmadas")
                c.commit()
            res = AE_OK
    st.send_ff55(0xAE, bytes([res]), name=f"FFAE rearmar misión puzzle {_id_de(data)} -> {res}")


def h_ffb5(st, cmd, data):
    """`FFB5 [u32 id]` «Misión Abandonar»."""
    mid = _id_de(data)
    f = _fila(getattr(st, "usn", 0), mid)
    if f:
        _cambiar(f["id_fila"], fin="abandonada")
    st.send_ff55(0xB5, struct.pack("<IB", mid, B5_OK if f else B5_NO_HAY),
                 name=f"FFB5 abandonar misión puzzle {mid} -> {'ok' if f else 'no corresponde'}")


def h_ffb2(st, cmd, data):
    """`FFB2 [u32 id]`: AVANCE (hechas < meta, verificado contra la última carrera) o COBRO (hechas = meta)."""
    usn = int(getattr(st, "usn", 0) or 0)
    mid = _id_de(data)
    with _lock:
        f = _fila(usn, mid)
        if f and f["estado"] in ACEPTADA and f["hechas"] >= f["meta"]:
            _cambiar(f["id_fila"], fin="cobrada")
            cobro = f
        else:
            cobro = None
            hechas = 0
            car = ULTIMA.get(usn)
            if (f and f["estado"] in ACEPTADA and car and time.time() - car["t"] <= CARRERA_VALE_S
                    and car["n"] != f["ultima_carrera"] and cumple(misiones().get(mid) or {}, f["parametro"], car)):
                hechas = f["hechas"] + 1
                _cambiar(f["id_fila"], hechas=hechas, ultima_carrera=car["n"])
    if cobro:
        _cobrar(st, usn, cobro)
        return
    st.send_ff55(0xB2, struct.pack("<IB", mid, hechas),
                 name=f"FFB2 avance misión puzzle {mid} -> {hechas or 'NO (mudo: sin carrera que la cumpla)'}")
    if hechas:
        log("LOBBY", f"  🧩 PUZZLE usn={usn}: {mid} {hechas}/{f['meta']}")


def _cobrar(st, usn, f):
    """El premio de verdad («dibujar no es acreditar») + el cartel `FFB3` + sacarla de la lista + la 5001."""
    from .basedatos import db_add_exp, db_add_rcoin
    if f["rcoin"]:
        db_add_rcoin(usn, f["rcoin"])
    if f["exp"]:
        db_add_exp(usn, f["exp"])
    if f["item"]:
        from .regalo import dar_item
        dar_item(usn, f["item"], 0, 1, "puzzle", f"misión puzzle {f['mision']}")
    st.send_ff55(0xB3, struct.pack("<IIII", f["mision"], f["item"], f["rcoin"], f["exp"]),
                 name=f"FFB3 premio misión puzzle {f['mision']}: {f['rcoin']} Rcoin + {f['exp']} EXP")
    st.send_ff55(0xB5, struct.pack("<IB", f["mision"], B5_OK), name=f"FFB5 saca la misión puzzle cobrada {f['mision']}")
    log("LOBBY", f"  🧩 PUZZLE usn={usn}: COBRÓ {f['mision']} -> {f['rcoin']} Rcoin + {f['exp']} EXP")
    try:                                         # la 5001 «Rompecabezas» de la Misión de hoy
        from . import mision_hoy
        mision_hoy.sumar(usn, 5001, poner=1, motivo="cobró una misión puzzle")
    except Exception as e:                       # noqa: BLE001
        log("LOBBY", f"  ⚠ misión de hoy (5001): {e!r}")


# ── la carrera: lo que el server vio, para no creerle al cliente ─────────────────────────────────────────────────────

def fin_de_carrera(usn, carrera):
    """Donde se cobra la carrera MULTI (una vez por jugador). ⛔ El entrenamiento no pasa por acá: no cuenta.
    `carrera` = {cancion, pista, velocidad, coop 'S'/'T'/'R', jugadores, puesto, gano_equipo, pd, star, combo,
    combo_total, fallo}."""
    if usn:
        ULTIMA[int(usn)] = {**carrera, "t": time.time(), "n": time.time_ns() // 1000}


def cumple(a, parametro, car):
    """El MISMO criterio que el cliente (`0x440D00`, MISIONES_PUZZLE.md §2.1) contra la carrera que vio el server."""
    if not a or car.get("fallo"):
        return False
    if "GameMode" in a and (a["GameMode"] == "S") != bool(car.get("velocidad")):
        return False
    if "CooperationMode" in a and a["CooperationMode"] != car.get("coop"):
        return False
    if "Player_NUM" in a and int(car.get("jugadores") or 0) < int(a["Player_NUM"]):
        return False
    if "Rank" in a and int(car.get("puesto") or 0) != int(a["Rank"]):
        return False
    if "Win_Team" in a and not car.get("gano_equipo"):
        return False
    if "AllCombo" in a and not (car.get("combo_total") and int(car.get("combo") or 0) >= int(car["combo_total"])):
        return False
    if "Accuracy" in a and int(car.get("pd") or 0) < int(a["Accuracy"]):
        return False
    if "Star_Accuracy" in a and int(car.get("star") or 0) < int(a["Star_Accuracy"]):
        return False
    if "Music_Select" in a and str(car.get("cancion")) != str(parametro):
        return False
    if "Stage_Select" in a and str(car.get("pista")) != str(parametro):
        return False
    return True
