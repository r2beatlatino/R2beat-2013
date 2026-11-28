# -*- coding: utf-8 -*-
"""lucky_star — la LUCKY STAR del 2013: se gana corriendo y se abre con una llave de la tienda.

★ 27-nov (Eñeños: «el FF mapa del 2013 no completó aún las lucky star que se ganan en gameplay y se compran sus llaves
  en la tienda»). Leído del desensamblado del 2013 (`_trabajo/lucky_star/NOTAS.md`, ⏳ falta medirlo en vivo):

  1. LA PONE EL CLIENTE. `0x565C20` le marca `0xF2` a una nota-estrella en ~30 % de las carreras, si el jugador tiene
     menos de 10 Lucky Star (ítem 298). El server no manda nada para eso.
  2. AGARRARLA no manda nada: al final, el `FF28` C→S trae el **byte 56** = 1 (`[rep+0x1A]`, `0x501310`).
  3. EL SERVER LA DA con el `FFC6 [u8 res]` (RX `0x5DE480`): 0 = el cliente se suma él solo un 298 y abre el popup
     «ganaste una Lucky Star» (0x67) · 1 = «ya tenés las 10» (texto 877) · 2 = «error al ganarla» (882).
     ⚠ NO mandar además un `FFCE`: el cliente ya se la sumó y la contaría dos veces. Sí el `FF69` con el TOTAL
     (el armario dibuja la cantidad desde ahí, ver «el cliente no dibuja del inventario»).
  4. ABRIRLA: en el armario, clic en la estrella o en una llave → elige la llave → «¿seguro?» → la animación → el
     `FFC7` C→S `[u32 la llave]` (299/300/301/776/777, dentro del `FF55`). El cliente ESPERA la respuesta: siempre se
     contesta.
  5. LA RESPUESTA `FFC7` S→C (RX `0x5DE690`): `[u8 res][u32 A la llave][u32 B el premio]` + `[u32 C vence]` sólo si
     res=0. Con 0 el cliente se resta la llave y la estrella y muestra el popup 0x50 con B; 1 = «no tenés la Lucky
     Star» (880) · 2 = «no tenés la llave» (879) · 3/4 = «error (code %d)» (881).
     ⚠ El 2013 NO mete el premio en su inventario (el 4.º arg del popup va en 0): lo da el server, en vivo.

  LOS PREMIOS los decide el server, por llave (oro / plata / bronce, según el ItemEffect 917/918/919 de la llave), en
  la tabla `lucky_star_premios` de `datos.db` — un SORTEO por `chance`, como la misión de hoy. ★ Por ahora sólo Rcoin
  (Eñeños: «pon sólo rcoin como premio por ahora, pero luego lo cambiaremos desde el coordinador»).
  ⏳ Lo que sigue (su idea): una llave da EXP, otra Rcoin y la otra ROPA al azar con su chance («de las más
     detalladas: las del set collab o las Show 0»). La tabla ya tiene `tipo`; hoy `poner_premios` sólo acepta «rcoin».
"""
import random
import struct
import threading
import time

from . import almacen
from .registro import log

ESTRELLA = 298
TOPE_ESTRELLAS = 10                    # el cliente tampoco la pone en la pista con 10 (`0x4875C0(298) < 10`)
# las llaves, en el orden en que las CLAVÓ el exe (`0x47E440`), con su tier (el ItemEffect: 917 oro · 918 plata · 919 bronce)
LLAVES = {776: "oro", 777: "plata", 299: "oro", 300: "plata", 301: "bronce"}
TIERS = ("oro", "plata", "bronce")
# ⚠ Un cliente tocado puede mandar byte 56 = 1 en TODAS las carreras. El tope de 10 sin abrir ya lo frena (y abrir
#   cuesta una llave), pero además: como mucho tantas estrellas por día por personaje.
TOPE_POR_DIA = 30
BYTE_FF28 = 56

RES_OK, RES_SIN_ESTRELLA, RES_SIN_LLAVE, RES_ERROR = 0, 1, 2, 3
GANO_OK, GANO_TIENE_10, GANO_ERROR = 0, 1, 2

# ★ Los premios POR DEFECTO: se siembran UNA vez, cuando la tabla nace (si después se vacía un tier, queda vacío).
#   Montos con su cajita de Rcoin (`cupon.iconos_rcoin`: 100/150/200/500/1.000/1.500/20.000), así el popup 0x50
#   muestra el ícono y el número. ⚠ Las llaves cuestan 3.600 en la tienda: ajustar desde el panel.
PREMIOS_POR_DEFECTO = {"oro": 1500, "plata": 1000, "bronce": 500}

TABLAS = """
CREATE TABLE IF NOT EXISTS lucky_star_premios (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tier TEXT NOT NULL, tipo TEXT NOT NULL DEFAULT 'rcoin',
    valor INTEGER NOT NULL DEFAULT 0, item INTEGER NOT NULL DEFAULT 0, dias INTEGER NOT NULL DEFAULT 0,
    chance INTEGER NOT NULL DEFAULT 1, activo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS lucky_star_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL, cuando REAL NOT NULL, que TEXT NOT NULL,
    llave INTEGER NOT NULL DEFAULT 0, premio TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS lucky_star_log_uid ON lucky_star_log (uid, que, cuando);
"""
_tablas_ok = set()
_abrir_lock = threading.Lock()


def _con():
    """La conexión del hilo a `datos.db`, con las tablas. ⚠ Llamar con `almacen._lock` tomado."""
    c = almacen.conectar()
    if id(c) not in _tablas_ok:
        nueva = not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lucky_star_premios'").fetchone()
        c.executescript(TABLAS)
        if nueva:
            c.executemany("INSERT INTO lucky_star_premios (tier, tipo, valor, chance) VALUES (?, 'rcoin', ?, 1)",
                          list(PREMIOS_POR_DEFECTO.items()))
            c.commit()
            log("MAIN", f"lucky star: premios por defecto {PREMIOS_POR_DEFECTO} (Rcoin por llave)")
        _tablas_ok.add(id(c))
    return c


def _anotar(uid, que, llave=0, premio=""):
    with almacen._lock:
        c = _con()
        c.execute("INSERT INTO lucky_star_log (uid, cuando, que, llave, premio) VALUES (?, ?, ?, ?, ?)",
                  (int(uid), time.time(), que, int(llave), str(premio)[:200]))
        c.commit()


def ganadas_hoy(uid, ahora=None):
    ahora = time.time() if ahora is None else ahora
    with almacen._lock:
        r = _con().execute("SELECT COUNT(*) FROM lucky_star_log WHERE uid=? AND que='gano' AND cuando>=?",
                           (int(uid), ahora - 86400)).fetchone()
    return int(r[0] or 0)


# ── el inventario ──────────────────────────────────────────────────────────────────────────────────

def cuantas(uid, item):
    """Cuántas unidades tiene de `item`. Una entrada SIN `cant` (comprada antes de que las llaves fueran por cargas)
    cuenta como 1."""
    from .basedatos import db_get_char
    n = 0
    for e in (db_get_char(int(uid)) or {}).get("inventory", []) or []:
        eid = int(e["id"]) if isinstance(e, dict) else int(e)
        if eid == int(item):
            n += max(1, int(e.get("cant", 0) or 0)) if isinstance(e, dict) else 1
    return n


def _ff69(st, item):
    """El TOTAL que tiene de `item` (el armario dibuja la cantidad desde el FF69). Si llegó a 0 no se manda: un count
    0 el cliente lo lee como 1 (`MYRECORD_MANDA_CARGAS`); ahí el cliente ya se lo restó él solo."""
    from .basedatos import db_get_rcoin
    n = cuantas(st.usn, item)
    if n > 0:
        st.send_ff55(0x69, bytes([1]) + struct.pack("<IHI", int(item), n & 0xFFFF, db_get_rcoin(int(st.usn)) & 0xFFFFFFFF),
                     name=f"FF69 lucky star: {n} del {item}")


# ── ganarla (FF28 byte 56 → FFC6) ─────────────────────────────────────────────────────────────────

def al_fin_de_carrera(st, data):
    """El `FF28` C→S: si trae la estrella agarrada, se la acredita YA en la base (si se cae antes de volver a la sala,
    no la pierde) y el `FFC6` queda para cuando vuelva del cartel (`al_volver`)."""
    if len(data) <= BYTE_FF28 or data[BYTE_FF28] != 1:
        return None
    uid = int(getattr(st, "usn", 0) or 0)
    if not uid or getattr(st, "slot_espectador", None) is not None or not getattr(st, "en_carrera", False):
        log("LOBBY", f"  ⚠ LUCKY STAR: byte 56 = 1 de usn={uid} fuera de una carrera propia -> no se da")
        return None
    from .basedatos import db_add_inventory
    if cuantas(uid, ESTRELLA) >= TOPE_ESTRELLAS:
        res = GANO_TIENE_10
    elif ganadas_hoy(uid) >= TOPE_POR_DIA:
        res = GANO_ERROR
        log("LOBBY", f"  ⛔ LUCKY STAR: usn={uid} ya ganó {TOPE_POR_DIA} en 24 h -> no se da (¿cliente tocado?)")
    else:
        db_add_inventory(uid, ESTRELLA, 0, cant=1)
        _anotar(uid, "gano")
        res = GANO_OK
    st.lucky_pendiente = res
    log("LOBBY", f"  ★ LUCKY STAR: usn={uid} la agarró -> res {res} (tiene {cuantas(uid, ESTRELLA)}); el FFC6 al volver")
    return res


def al_volver(st):
    """Al volver del cartel (el `FF13` que apaga `en_carrera`): el `FFC6` pendiente."""
    res = getattr(st, "lucky_pendiente", None)
    if res is None:
        return
    st.lucky_pendiente = None
    st.send_ff55(0xC6, bytes([res & 0xFF]), name=f"FFC6 lucky star (res {res})")
    if res == GANO_OK:
        _ff69(st, ESTRELLA)


# ── abrirla (FFC7) ────────────────────────────────────────────────────────────────────────────────

def premios(tier=None, todos=False):
    with almacen._lock:
        q = "SELECT * FROM lucky_star_premios" + (" WHERE tier=?" if tier else "") + " ORDER BY tier, id"
        filas = _con().execute(q, (tier,) if tier else ()).fetchall()
    out = [dict(r) for r in filas]
    return out if todos else [f for f in out if f["activo"]]


def sortear(tier, rnd=random):
    filas = [f for f in premios(tier) if int(f["chance"]) > 0]
    if not filas:
        return None
    x = rnd.uniform(0, sum(int(f["chance"]) for f in filas))
    for f in filas:
        x -= int(f["chance"])
        if x <= 0:
            return f
    return filas[-1]


def poner_premios(tier, filas):
    """Reemplaza los premios de un tier (para el panel / el Coordinador). ⏳ Por ahora sólo Rcoin."""
    if tier not in TIERS:
        raise ValueError(f"tier «{tier}»: tiene que ser uno de {', '.join(TIERS)}")
    limpias = []
    for f in filas or []:
        tipo = str(f.get("tipo") or "rcoin")
        if tipo != "rcoin":
            raise ValueError(f"premio «{tipo}»: por ahora la Lucky Star sólo da Rcoin")
        valor, chance = int(f.get("valor") or 0), int(f.get("chance", 1) or 0)
        if not 1 <= valor <= 1_000_000 or not 0 <= chance <= 1_000_000:
            raise ValueError(f"Rcoin {valor} / chance {chance}: fuera de rango")
        limpias.append((tier, tipo, valor, chance, 1 if f.get("activo", True) else 0))
    if len(limpias) > 40:
        raise ValueError("Como mucho 40 premios por llave.")
    with almacen._lock:
        c = _con()
        c.execute("DELETE FROM lucky_star_premios WHERE tier=?", (tier,))
        c.executemany("INSERT INTO lucky_star_premios (tier, tipo, valor, chance, activo) VALUES (?, ?, ?, ?, ?)", limpias)
        c.commit()
    return premios(tier, todos=True)


def armar_ffc7(res, llave, premio=0, vence_wire=0):
    p = struct.pack("<BII", res & 0xFF, int(llave) & 0xFFFFFFFF, int(premio) & 0xFFFFFFFF)
    return p + struct.pack("<I", int(vence_wire) & 0xFFFFFFFF) if res == RES_OK else p


def leer_ffc7(data):
    return struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else None


def abrir(st, data):
    """C→S `FFC7 [u32 llave]`. Contesta SIEMPRE el `FFC7` (el cliente queda esperándolo)."""
    from .basedatos import _exp_to_wire, db_add_rcoin, db_del_inventory
    from .cupon import iconos_rcoin
    uid = int(getattr(st, "usn", 0) or 0)
    llave = leer_ffc7(data)
    with _abrir_lock:                                    # (dos FFC7 seguidos no gastan la misma estrella dos veces)
        if llave is None or llave not in LLAVES or not uid or cuantas(uid, llave) < 1:
            res, premio = RES_SIN_LLAVE, None
        elif cuantas(uid, ESTRELLA) < 1:
            res, premio = RES_SIN_ESTRELLA, None
        else:
            premio = sortear(LLAVES[llave])
            res = RES_OK if premio else RES_ERROR
            if res == RES_OK:
                monto = int(premio["valor"])
                try:                                     # ★ ANTES de gastar nada: si esto falla, no se pierde la llave
                    icono = iconos_rcoin().get(monto, 0)
                except Exception as e:                   # noqa: BLE001  (sin tienda: el popup sale sin ícono)
                    log("LOBBY", f"  ⚠ LUCKY STAR: sin el ícono de {monto} Rcoin: {e!r}")
                    icono = 0
                if not (db_del_inventory(uid, llave) and db_del_inventory(uid, ESTRELLA)):
                    res, premio = RES_ERROR, None        # (no debería: se acaba de contar)
        if res != RES_OK:
            st.send_ff55(0xC7, armar_ffc7(res, llave or 0), name=f"FFC7 lucky star: no (res {res}, llave {llave})")
            log("LOBBY", f"  ⚠ LUCKY STAR: usn={uid} abrir con la llave {llave} -> res {res}")
            return res
        saldo = int(db_add_rcoin(uid, monto))
        _anotar(uid, "abrio", llave, f"rcoin {monto}")
    st.send_ff55(0xC7, armar_ffc7(RES_OK, llave, icono, _exp_to_wire(0)),
                 name=f"FFC7 lucky star: llave {llave} ({LLAVES[llave]}) -> {monto} Rcoin (ícono {icono})")
    st.send_ff55(0xAB, struct.pack("<I", saldo & 0xFFFFFFFF), name=f"FFAB saldo {saldo} (+{monto} lucky star)")
    for it in (llave, ESTRELLA):
        _ff69(st, it)
    log("LOBBY", f"  ★ LUCKY STAR: usn={uid} abrió con la llave {llave} ({LLAVES[llave]}) -> {monto} Rcoin, saldo {saldo}")
    return res


def h_ffc7(st, cmd, data):
    """La ruta del `despacho` (FFC7)."""
    return abrir(st, data)
