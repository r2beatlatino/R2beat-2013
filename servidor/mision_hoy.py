# -*- coding: utf-8 -*-
"""mision_hoy — la «Misión de hoy» del lobby (`FF117` / `FF118`): 15 misiones por día, 100 puntos, 4 premios.

★ 15-oct, anonimo03: «sigamos con las misiones» · día nuevo a la medianoche de PERÚ · el rompecabezas (5001), investigarlo
  (un agente mapea el puzzle: `documentacion/MISIONES_PUZZLE.md`) · premios PROPIOS, editables desde el panel.
  Mapa del cliente: `documentacion/LOBBY_CUPON_MISION_BOTONES.md` §2 · doc: `documentacion/MISION_DE_HOY.md`.

CÓMO LO ARMÓ EL JUEGO (exe 2013, sin parches)
  · El botón «Misión de hoy» y la ventana salen SIEMPRE. Los datos el cliente NUNCA los pide: los EMPUJA el server.
      S→C `FF117 [u16 n] + n × ([u32 id][u32 valor])`  (handler `0x5D9BE0`)
        n = 0 → resetea todo (día nuevo) · id 0 → los PUNTOS de hoy (el cliente no los suma) · id 10/50/80/100 → ese
        premio «Ya recibido» · id = TMID → el AVANCE de esa misión (la 1002 en SEGUNDOS; el cliente lo topea a la meta).
  · Cobrar: «Obten Premios» → C→S `FF118 [u32 escalón]` (10/50/80/100) → S→C `FF118 [u8 res][u32 escalón]
      [u32 ítem o Rcoin][u32 vence][u16 cantidad][u8 tipo]` (`0x5E15C0`): res 0 + tipo 'M' = Rcoin (lo suma al saldo,
      «Ha recibido %d Rcoin.») · res 0 + otro tipo = ítem (le saca el dígito de los miles, lo mete al inventario con
      `vence` y `cantidad`, «Felicitaciones. Has conseguido %s por el premio.») · res 5/6 = «falta de puntos» · otro =
      «Error Code: %d».

LAS REGLAS (del server)
  · El día va de medianoche a medianoche de Perú (`MISION_HOY_UTC` = −5). Cambia el día → `FF117 n=0` + la lista.
  · Lo que se cuenta, y dónde: 1001 primer ingreso del día (`FF03`) · 1002 tiempo conectado (este reloj, cada 5 min) ·
    1003 entrar a la charla (`charla`) · 2001…2010 fin de carrera (`lobby_carrera`, donde se cobra) · 3001 aceptar un
    amigo (los dos) · 4001 / 4002 un gesto en la charla / en la sala (`FF60`, `FF7B`) · 5001 el rompecabezas (⏳).
  · ⛔ Nunca se le manda nada al que está corriendo, cargando o mirando una carrera: queda pendiente y sale al volver.
  · Los premios los define el ADMIN en el panel (tabla `mision_hoy_premios`): por escalón, un SORTEO por `chance`, con
    ítem (+ días o unidades) o Rcoin, y opcionalmente sólo para hombre o mujer.
"""
import json
import random
import re
import struct
import threading
import time
from datetime import datetime, timedelta, timezone

from . import almacen
from .registro import log

TABLA = "todaymission.txt"
ESCALONES = (10, 50, 80, 100)
ID_PUNTOS = 0
# ★ 15-oct: los SEGUNDOS CONECTADOS DE HOY SIN TOPE, en `mision_hoy_avance` con este tmid (NO es una misión: no da puntos
#   ni viaja en el FF117). La 1002 se topea en su meta (2 h) y el cartel «Hoy tu inicio de sesión continúa por X horas»
#   tiene que seguir contando: va en el FF03 y en el FF49 (`segundos_hoy_de`, `MISION_DE_HOY.md` §8).
TMID_TIEMPO = 1
PUNTOS_MAX = 100
CADA_SEG = 300                    # cada cuánto se suma el tiempo conectado y se empuja el avance de la 1002
PENDIENTES_SEG = 20               # cada cuánto se mira si hay un avance pendiente para mandar
RES_OK, RES_SIN_PUNTOS, RES_ERROR = 0, 5, 1
TIPO_RCOIN, TIPO_ITEM = ord("M"), ord("C")
# ★ Los premios POR DEFECTO (15-oct, anonimo03: «200 de Rcoin escalando hasta 10 mil al completar los 100 puntos, y que
#   siga editable en el panel»). Se siembran UNA vez, cuando la tabla nace: si después alguien vacía un escalón desde
#   el panel, queda vacío (no vuelven solos).
PREMIOS_POR_DEFECTO = {10: 200, 50: 1000, 80: 3000, 100: 10000}

TABLAS = """
CREATE TABLE IF NOT EXISTS mision_hoy_avance (
    uid INTEGER NOT NULL, dia TEXT NOT NULL, tmid INTEGER NOT NULL, valor INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, dia, tmid));
CREATE TABLE IF NOT EXISTS mision_hoy_cobros (
    uid INTEGER NOT NULL, dia TEXT NOT NULL, escalon INTEGER NOT NULL, premio TEXT, cuando REAL NOT NULL,
    PRIMARY KEY (uid, dia, escalon));
CREATE TABLE IF NOT EXISTS mision_hoy_premios (
    id INTEGER PRIMARY KEY AUTOINCREMENT, escalon INTEGER NOT NULL, item INTEGER NOT NULL DEFAULT 0,
    dias INTEGER NOT NULL DEFAULT 0, cant INTEGER NOT NULL DEFAULT 1, rcoin INTEGER NOT NULL DEFAULT 0,
    chance INTEGER NOT NULL DEFAULT 1, sexo TEXT NOT NULL DEFAULT '', activo INTEGER NOT NULL DEFAULT 1);
"""
_tablas_ok = set()
_cobro_lock = threading.Lock()
_misiones = None


def _con():
    """La conexión del hilo a `datos.db`, con las tablas. ⚠ Llamar con `almacen._lock` tomado."""
    c = almacen.conectar()
    if id(c) not in _tablas_ok:
        nueva = not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mision_hoy_premios'").fetchone()
        c.executescript(TABLAS)
        if nueva:
            c.executemany("INSERT INTO mision_hoy_premios (escalon, rcoin, chance) VALUES (?, ?, 1)",
                          sorted(PREMIOS_POR_DEFECTO.items()))
            c.commit()
            log("MAIN", f"misión de hoy: premios por defecto {PREMIOS_POR_DEFECTO} (Rcoin por escalón)")
        _tablas_ok.add(id(c))
    return c


# ── las 15 misiones (la tabla del CLIENTE, copiada en servidor/tablas-cliente/) ─────────────────────

def misiones():
    """{tmid: {goal, puntos, tipo}} de `todaymission.txt`."""
    global _misiones
    if _misiones is None:
        import os
        from .ajustes import _DIR_SERVIDOR
        t = open(os.path.join(_DIR_SERVIDOR, "tablas-cliente", TABLA), "rb").read().decode("cp949", "replace")
        out = {}
        for m in re.finditer(r"<Mission ([^>]*)>", t):
            a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            out[int(a["TMID"])] = {"goal": int(a["Goal"]), "puntos": int(a["Activepoint"]), "tipo": a.get("MType", "")}
        _misiones = out
    return _misiones


def puntos_de(avance):
    """Los puntos de hoy con el avance {tmid: valor}: cada misión da su parte por UNIDAD (Activepoint / Goal, como
    el cliente), topeada a la meta. La 1002 va en segundos y cuenta por HORA (el cliente la divide por 3600)."""
    total = 0
    for tmid, m in misiones().items():
        v = int(avance.get(tmid, 0) or 0)
        goal = m["goal"]
        if tmid == 1002:
            v, goal = v // 3600, max(1, goal // 3600)
        total += min(v, goal) * m["puntos"] // max(1, goal)
    return min(total, PUNTOS_MAX)


# ── el día (medianoche de Perú) ───────────────────────────────────────────────────────────────────

def dia(ahora=None):
    """'AAAA-MM-DD' del día de la misión: medianoche a medianoche en UTC + `MISION_HOY_UTC` (Perú: −5)."""
    from .ajustes import MISION_HOY_UTC
    t = datetime.fromtimestamp(time.time() if ahora is None else ahora, tz=timezone.utc) + timedelta(hours=MISION_HOY_UTC)
    return t.strftime("%Y-%m-%d")


def comienzo_del_dia(ahora=None):
    """El epoch de la medianoche (de Perú) de hoy."""
    from .ajustes import MISION_HOY_UTC
    d = datetime.strptime(dia(ahora), "%Y-%m-%d").replace(tzinfo=timezone.utc) - timedelta(hours=MISION_HOY_UTC)
    return d.timestamp()


# ── el avance ─────────────────────────────────────────────────────────────────────────────────────

def avance(uid, d=None):
    """{tmid: valor} de hoy (o del día `d`)."""
    d = d or dia()
    with almacen._lock:
        filas = _con().execute("SELECT tmid, valor FROM mision_hoy_avance WHERE uid=? AND dia=?", (int(uid), d)).fetchall()
    return {int(r[0]): int(r[1]) for r in filas}


def cobrados(uid, d=None):
    d = d or dia()
    with almacen._lock:
        filas = _con().execute("SELECT escalon FROM mision_hoy_cobros WHERE uid=? AND dia=?", (int(uid), d)).fetchall()
    return {int(r[0]) for r in filas}


def sumar(uid, tmid, n=1, poner=None, motivo=""):
    """Suma `n` a la misión `tmid` de hoy (o la PONE en `poner`), topeada a la meta. Si cambió, el avance queda
    pendiente de mandar. -> el valor nuevo."""
    from .ajustes import MISION_HOY_ACTIVA
    if not MISION_HOY_ACTIVA or not uid:
        return None
    m = misiones().get(int(tmid))
    if not m:
        return None
    d = dia()
    with almacen._lock:
        c = _con()
        r = c.execute("SELECT valor FROM mision_hoy_avance WHERE uid=? AND dia=? AND tmid=?", (int(uid), d, int(tmid))).fetchone()
        antes = int(r[0]) if r else 0
        nuevo = min(m["goal"], int(poner) if poner is not None else antes + int(n))
        if nuevo == antes:
            return antes
        c.execute("INSERT INTO mision_hoy_avance (uid, dia, tmid, valor) VALUES (?, ?, ?, ?) "
                  "ON CONFLICT (uid, dia, tmid) DO UPDATE SET valor=excluded.valor", (int(uid), d, int(tmid), nuevo))
        c.commit()
    if tmid != 1002:
        log("LOBBY", f"  📅 MISIÓN DE HOY usn={uid}: {tmid} {antes} → {nuevo}/{m['goal']}" + (f" ({motivo})" if motivo else ""))
    _marcar(uid)
    return nuevo


# ── las cuentas que vienen de afuera (los lugares que ya existen llaman a éstas) ──────────────────────

def al_entrar(st):
    """El `FF03` (entrar al juego): la 1001, el reloj de la 1002 desde ahora, y la lista entera."""
    uid = int(getattr(st, "usn", 0) or 0)
    if getattr(st, "mh_desde", None) is not None:
        _guardar_tiempo(st)                     # un FF03 repetido en la misma conexión no pierde lo que llevaba
    st.mh_desde = time.time()
    st.mh_dia = None                            # que el primer envío mande el reinicio si cambió el día
    sumar(uid, 1001, poner=1, motivo="primer ingreso del día")
    enviar(st, motivo="al entrar")


def al_conectar(st):
    """El `FF49` pedido (★ el CAMBIO DE CANAL: entrar a la charla, a «Libre»… es una conexión NUEVA que no pasa por
    el `FF03` del cliente). Sin esto esa conexión quedaba sin reloj: ni tiempo conectado ni envíos. El `FF49` también
    llega al entrar a una sala ⇒ sólo arranca si no estaba, y no manda en el acto: lo deja PENDIENTE (la vuelta de
    20 s respeta al que carga o corre)."""
    if getattr(st, "mh_desde", None) is not None:
        return
    st.mh_desde = time.time()
    st.mh_dia = None
    sumar(int(getattr(st, "usn", 0) or 0), 1001, poner=1, motivo="primer ingreso del día")
    st.mh_pendiente = True


def al_salir(st):
    """La conexión se cae o cambia de canal: guarda el tiempo desde el último corte (si no, se perdían hasta 5 min)."""
    if getattr(st, "mh_desde", None) is not None:
        _guardar_tiempo(st)
        st.mh_desde = None


def fin_de_carrera(usn, equipo, velocidad, gano_equipo, puesto):
    """Donde se cobra la carrera (una vez por jugador): 2001/2002/2005/2006 jugar y 2007/2008/2009/2010 ganar."""
    if not usn:
        return
    if equipo:
        sumar(usn, 2001 if velocidad else 2005, motivo="carrera en equipo")
        if gano_equipo:
            sumar(usn, 2007 if velocidad else 2009, motivo="ganó en equipo")
    else:
        sumar(usn, 2002 if velocidad else 2006, motivo="carrera solo")
        if puesto == 1:
            sumar(usn, 2008 if velocidad else 2010, motivo="1.º solo")


# ── el envío (FF117) ──────────────────────────────────────────────────────────────────────────────

def armar_ff117(registros):
    return struct.pack("<H", len(registros)) + b"".join(struct.pack("<II", int(i) & 0xFFFFFFFF, int(v) & 0xFFFFFFFF)
                                                        for i, v in registros)


def _segundos_de_hoy(st, uid, ahora=None):
    """La 1002: lo guardado hoy + lo que lleva esta conexión desde el último corte (o desde la medianoche)."""
    ahora = time.time() if ahora is None else ahora
    desde = max(float(getattr(st, "mh_desde", ahora) or ahora), comienzo_del_dia(ahora))
    av = avance(uid)
    return av.get(TMID_TIEMPO, av.get(1002, 0)) + max(0, int(ahora - desde))   # (sin la fila nueva: lo de la 1002)


def segundos_hoy_de(uid):
    """Los segundos conectados de HOY, sin tope (lo guardado + lo de la conexión viva): el cartel «Hoy tu inicio de
    sesión continúa por X horas» que el cliente lee del `FF03` y del `FF49` (`0x480CA0` lo PONE y le suma 1 min por
    timer). 0 con la misión apagada."""
    from .ajustes import MISION_HOY_ACTIVA
    if not MISION_HOY_ACTIVA or not uid:
        return 0
    from .salas import CONEXIONES
    st = CONEXIONES.get(int(uid))
    return _segundos_de_hoy(st, int(uid)) if st is not None else avance(uid).get(TMID_TIEMPO, avance(uid).get(1002, 0))


def _guardar_tiempo(st, ahora=None):
    """Pasa a la base el tiempo de esta conexión y corre el reloj."""
    ahora = time.time() if ahora is None else ahora
    uid = int(getattr(st, "usn", 0) or 0)
    if not uid or getattr(st, "mh_desde", None) is None:
        return
    seg = _segundos_de_hoy(st, uid, ahora)
    st.mh_desde = ahora
    with almacen._lock:                         # el tiempo SIN tope (el cartel); la 1002 se topea en su meta
        c = _con()
        c.execute("INSERT INTO mision_hoy_avance (uid, dia, tmid, valor) VALUES (?, ?, ?, ?) "
                  "ON CONFLICT (uid, dia, tmid) DO UPDATE SET valor=excluded.valor", (uid, dia(ahora), TMID_TIEMPO, int(seg)))
        c.commit()
    sumar(uid, 1002, poner=seg)


def _se_puede(st):
    """⛔ Nunca al que corre, carga o mira una carrera (un paquete a destiempo tumba a la máquina lenta)."""
    if getattr(st, "cerrado", False) or getattr(st, "en_carrera", False):
        return False
    rid = getattr(st, "room_id", None)
    if rid is not None:
        from .lobby_salas import sala_en_carrera
        if sala_en_carrera(rid):
            return False
    return True


def registros_de(uid):
    """Lo que va en el FF117: los puntos, el avance de cada misión y los premios ya cobrados."""
    av = avance(uid)
    reg = [(ID_PUNTOS, puntos_de(av))]
    ms = misiones()
    reg += [(t, v) for t, v in sorted(av.items()) if v and t in ms]       # ⛔ el TMID_TIEMPO no es una misión
    reg += [(e, 1) for e in sorted(cobrados(uid))]
    return reg


def enviar(st, motivo=""):
    """Empuja el FF117 al que esté en condiciones (si no, queda pendiente). Si cambió el día, antes el reinicio."""
    from .ajustes import MISION_HOY_ACTIVA
    if not MISION_HOY_ACTIVA:
        return False
    uid = int(getattr(st, "usn", 0) or 0)
    if not uid:
        return False
    if not _se_puede(st):
        st.mh_pendiente = True
        return False
    hoy = dia()
    if getattr(st, "mh_dia", None) not in (None, hoy):
        st.send_ff55(0x117, armar_ff117([]), name="FF117 misión de hoy: DÍA NUEVO (reinicio)")
    st.mh_dia = hoy
    reg = registros_de(uid)
    st.send_ff55(0x117, armar_ff117(reg), name=f"FF117 misión de hoy: {reg[0][1]} puntos, {len(reg) - 1} registro(s)"
                 + (f" ({motivo})" if motivo else ""))
    st.mh_pendiente = False
    return True


def _marcar(uid):
    from .salas import CONEXIONES
    st = CONEXIONES.get(int(uid))
    if st is not None:
        st.mh_pendiente = True


def al_volver(st):
    """Al volver de una carrera (el `FF13` que apaga `en_carrera`): lo pendiente sale ahora."""
    if getattr(st, "mh_pendiente", False):
        enviar(st, motivo="al volver de la carrera")


# ── el cobro (FF118) ──────────────────────────────────────────────────────────────────────────────

def armar_ff118(res, escalon, valor=0, vence=0, cant=0, tipo=0):
    return struct.pack("<BIIIHB", res & 0xFF, int(escalon) & 0xFFFFFFFF, int(valor) & 0xFFFFFFFF,
                       int(vence) & 0xFFFFFFFF, int(cant) & 0xFFFF, tipo & 0xFF)


def premios(escalon=None, todos=False):
    """Las filas de premio (del panel), de un escalón o de todos."""
    with almacen._lock:
        q = "SELECT * FROM mision_hoy_premios" + (" WHERE escalon=?" if escalon is not None else "") + " ORDER BY escalon, id"
        filas = _con().execute(q, (int(escalon),) if escalon is not None else ()).fetchall()
    out = [dict(r) for r in filas]
    return out if todos else [f for f in out if f["activo"]]


def sortear(escalon, sexo, rnd=random):
    """Un premio del escalón, por `chance`, entre los de su sexo (o los de los dos). None si no hay ninguno."""
    filas = [f for f in premios(escalon) if f["sexo"] in ("", sexo) and int(f["chance"]) > 0]
    if not filas:
        return None
    x = rnd.uniform(0, sum(int(f["chance"]) for f in filas))
    for f in filas:
        x -= int(f["chance"])
        if x <= 0:
            return f
    return filas[-1]


def guardar_premios(escalon, filas):
    """El panel: deja los premios del `escalon` IGUAL a `filas` [{item|rcoin, dias, cant, chance, sexo, activo}].
    El ítem con la misma regla que los cupones (`cupon.por_unidades` / `duraciones`: la ropa por plazo de la tienda,
    lo que se gasta por unidades). ⛔ ValueError en criollo si algo no cierra. -> las filas guardadas."""
    from . import shop_catalog
    from .cupon import duraciones, por_unidades
    escalon = int(escalon)
    if escalon not in ESCALONES:
        raise ValueError(f"El escalón va 10, 50, 80 ó 100 (no {escalon}).")
    limpias = []
    for f in (filas or [])[:41]:
        rcoin, chance = max(0, int(f.get("rcoin") or 0)), max(0, int(f.get("chance") or 0))
        sexo = str(f.get("sexo") or "").upper()[:1]
        if sexo not in ("", "M", "F"):
            raise ValueError("El sexo va vacío (los dos), M o F.")
        if not chance:
            raise ValueError("Cada premio necesita una chance mayor que 0.")
        item, dias, cant = 0, 0, 1
        if not rcoin:
            iid = shop_catalog.normalize_id(int(f.get("item") or 0)) if str(f.get("item") or "").strip().isdigit() else None
            if iid is None:
                raise ValueError(f"El ítem {f.get('item')!r} no está en el catálogo.")
            item, dias, cant = int(iid), int(f.get("dias") or 0), max(1, min(int(f.get("cant") or 1), 999))
            if por_unidades(iid):
                dias = 0
            else:
                cant = 1
                vale = duraciones(iid)
                if vale and dias not in vale:
                    raise ValueError(f"«{(shop_catalog.get(iid) or {}).get('name', iid)}» se da por "
                                     + " / ".join("permanente" if x == 0 else f"{x} días" for x in vale) + ".")
        limpias.append((escalon, item, dias, cant, rcoin, chance, sexo, 1 if f.get("activo", True) else 0))
    if len(limpias) > 40:
        raise ValueError("Como mucho 40 premios por escalón.")
    with almacen._lock:
        c = _con()
        c.execute("DELETE FROM mision_hoy_premios WHERE escalon=?", (escalon,))
        c.executemany("INSERT INTO mision_hoy_premios (escalon, item, dias, cant, rcoin, chance, sexo, activo) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", limpias)
        c.commit()
    return premios(escalon, todos=True)


def resumen_de_hoy():
    """Para el panel: cuántos jugaron la misión hoy y cuántos cobraron cada escalón."""
    d = dia()
    with almacen._lock:
        c = _con()
        con_avance = c.execute("SELECT COUNT(DISTINCT uid) FROM mision_hoy_avance WHERE dia=?", (d,)).fetchone()[0]
        por = dict(c.execute("SELECT escalon, COUNT(*) FROM mision_hoy_cobros WHERE dia=? GROUP BY escalon", (d,)).fetchall())
    return {"dia": d, "jugadores": int(con_avance), "cobros": {str(e): int(por.get(e, 0)) for e in ESCALONES}}


def _sexo(uid):
    from .basedatos import db_get_char
    from .gacha import genero_visible
    try:
        return "F" if genero_visible(db_get_char(int(uid)) or {}) == 1 else "M"
    except Exception:                                                     # noqa: BLE001
        return "M"


def _entregar(uid, f):
    """Mete el premio en la BASE (el cliente lo mete en su inventario con el FF118: no se manda FFCE ni FF54).
    -> (valor, vence_wire, cant, tipo)."""
    from . import shop_catalog
    from .basedatos import _exp_to_wire, db_add_inventory, db_add_rcoin
    from .catalogo import desempacar_pack, entregar_compra, tiene_cargas
    shop_catalog.get(0)                                          # que el catálogo esté cargado (packs, cargas)
    if f["rcoin"]:
        db_add_rcoin(int(uid), int(f["rcoin"]))
        return int(f["rcoin"]), 0, 1, TIPO_RCOIN
    item, dias, cant = int(f["item"]), int(f["dias"]), max(1, int(f["cant"]))
    vence = int(time.time() + dias * 86400) if dias else 0
    if tiene_cargas(item) and not desempacar_pack(item)[1]:
        db_add_inventory(int(uid), item, vence, cant=cant)
    else:
        for _ in range(min(cant, 50)):
            entregar_compra(int(uid), item, vence)
    return item, _exp_to_wire(vence), cant, TIPO_ITEM


def cobrar(st, data):
    """C→S `FF118 [u32 escalón]`. Contesta SIEMPRE."""
    uid = int(getattr(st, "usn", 0) or 0)
    escalon = struct.unpack_from("<I", bytes(data))[0] if len(bytes(data)) >= 4 else 0

    def contestar(res, *rest, motivo=""):
        st.send_ff55(0x118, armar_ff118(res, escalon, *rest), name=f"FF118 premio de la misión de hoy ({motivo})")
        log("LOBBY", f"  📅 FF118 usn={uid} escalón {escalon} -> res {res} ({motivo})")

    if escalon not in ESCALONES:
        return contestar(RES_ERROR, motivo="escalón que no existe")
    with _cobro_lock:
        puntos = puntos_de(avance(uid))
        if puntos < escalon:
            return contestar(RES_SIN_PUNTOS, motivo=f"tiene {puntos} puntos")
        if escalon in cobrados(uid):
            return contestar(RES_ERROR, motivo="ya lo cobró hoy")
        f = sortear(escalon, _sexo(uid))
        if f is None:
            return contestar(RES_ERROR, motivo="el escalón no tiene premios cargados (panel)")
        try:
            valor, vence, cant, tipo = _entregar(uid, f)
        except Exception as e:                                             # noqa: BLE001
            return contestar(RES_ERROR, motivo=f"la entrega falló: {e!r}")
        with almacen._lock:
            c = _con()
            c.execute("INSERT INTO mision_hoy_cobros (uid, dia, escalon, premio, cuando) VALUES (?, ?, ?, ?, ?)",
                      (uid, dia(), escalon, json.dumps({k: f[k] for k in ("item", "dias", "cant", "rcoin")}), time.time()))
            c.commit()
    contestar(RES_OK, valor, vence, cant, tipo,
              motivo=f"{'Rcoin ' + str(valor) if tipo == TIPO_RCOIN else 'ítem ' + str(valor) + ' ×' + str(cant)}")


# ── el reloj de fondo ─────────────────────────────────────────────────────────────────────────────

def _vuelta(ahora=None, tiempo=False):
    from .salas import CONEXIONES
    for st in list(CONEXIONES.values()):
        try:
            if getattr(st, "mh_desde", None) is None or getattr(st, "cerrado", False):
                continue
            hoy = dia(ahora)
            if tiempo or getattr(st, "mh_dia", hoy) != hoy:
                _guardar_tiempo(st, ahora)
            if getattr(st, "mh_pendiente", False) or getattr(st, "mh_dia", hoy) != hoy:
                enviar(st, motivo="el reloj")
        except Exception as e:                                             # noqa: BLE001
            log("LOBBY", f"  ⚠ misión de hoy, reloj: {e!r}")


def arrancar():
    """El hilo de fondo: cada `PENDIENTES_SEG` manda lo pendiente; cada `CADA_SEG` suma el tiempo conectado (1002)."""
    from .ajustes import MISION_HOY_ACTIVA
    if not MISION_HOY_ACTIVA:
        log("MAIN", "misión de hoy APAGADA (MISION_HOY_ACTIVA=False)")
        return

    def _bucle():
        ultimo = 0.0
        while True:
            time.sleep(PENDIENTES_SEG)
            ahora = time.time()
            tiempo = ahora - ultimo >= CADA_SEG
            if tiempo:
                ultimo = ahora
            _vuelta(ahora, tiempo)

    from .ajustes import MISION_HOY_UTC
    threading.Thread(target=_bucle, daemon=True, name="mision-hoy").start()
    log("MAIN", f"misión de hoy: el día cambia a la medianoche de UTC{MISION_HOY_UTC:+d} · tiempo conectado cada "
                f"{CADA_SEG}s · {len(misiones())} misiones")
