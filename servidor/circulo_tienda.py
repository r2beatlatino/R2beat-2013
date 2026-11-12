# -*- coding: utf-8 -*-
"""circulo_tienda — la TIENDA del círculo, su INVENTARIO y la MARCA (25-sep).

Mapa leído del exe: `documentacion/CIRCULO_EXE_TIENDA.md` (resumen en `CIRCULOS_HALLAZGOS.md`).

  · Se paga con el DINERO del círculo (`circulo_economia.dinero`), TODO: los 965 ítems de
    `circleshop.bin` tienen el byte de Cash en 0. El cliente chequea el saldo antes de mandar
    (circle.csv #90) y NO resta nada: confía en el «dinero que queda» de la respuesta.
  · El itemcode del pedido lleva el PERIODO en el dígito de los miles (`0x50E050`): 1 = 7 días,
    2 = 30, 8 = 1 año, 6 = «Uno» (logos y fondos, permanentes). El Index es el código con ese
    dígito en 0 (`0x50E200`): 2508072 -> 2500072 a 1 año; 6520 -> 520.
  · Comprar NO mete el ítem en el inventario del cliente (el registro del FFD9 se ignora si sale
    bien): hay que mandar detrás un `FFDA` (upsert por clave). El inventario es del CÍRCULO.
  · Decoración (ShopIndex 20xx): sólo el LÍDER (`0x62EBA0`, circle.csv #34). Logos y fondos
    (3001/3002): cualquiera. Nivel mínimo `Clevel` -> resultado 0x0A.
  · La MARCA (`FFDF`): un logo + un fondo del inventario, que se GASTAN (#13/#62). El id de cada
    uno es el cuadro del sprite, de una tabla clavada en el exe (`0x619730`).

  · El ARREGLO (`FFD8`): el líder coloca y guarda; se guarda tal cual lo manda el cliente.

⏳ Sin hacer: que los que están en la sala vean el arreglo EN VIVO, el boleto de expansión (`FFDB`), el tope
`Stack` (#67), el «muro y piso deben expirar antes» (#55) y el vencimiento (hoy se guarda y se
muestra, pero nadie borra lo vencido).
"""
import os
import re
import struct
import time

from .ajustes import _DIR_SERVIDOR, CIRCULO_RANGO_LIDER, CIRCULOS
from .basedatos import (
    _exp_to_wire,
    db_acomodar_items_circulo,
    db_circulo_de,
    db_comprar_item_circulo,
    db_economia_circulo,
    db_items_circulo,
    db_miembros_circulo,
    db_poner_marca_circulo,
)
from .registro import log

CIRCLESHOP = os.path.join(_DIR_SERVIDOR, "tablas-cliente", "circleshop.xml")

# el dígito de los miles del itemcode -> (columna del xml, días; 0 = permanente). `0x4DE308`.
PERIODOS = {1: ("P7", 7), 2: ("P30", 30), 8: ("P365", 365), 6: ("PN", 0)}
SHOP_LOGO, SHOP_FONDO = 3001, 3002

# resultados del FFD9 (el 2º byte de la respuesta; `0x5DA654`)
OK, NO_EXISTE, ERROR, SIN_DINERO, NIVEL = 0, 1, 4, 5, 0x0A

_catalogo = None


def catalogo():
    """`{Index: {"shop", "nombre", "clevel", "P7", "P30", "P365", "PN"}}` de `circleshop.xml`."""
    global _catalogo
    if _catalogo is None:
        t = open(CIRCLESHOP, "rb").read().decode("cp1252", "replace")
        cat = {}
        for m in re.finditer(r"<Circle\s([^>]*)>", t):
            at = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            try:
                idx = int(at["Index"])
            except (KeyError, ValueError):
                continue
            d = {"shop": int(at.get("ShopIndex", 0) or 0), "nombre": at.get("Name", ""),
                 "clevel": int(at.get("Clevel", 0) or 0), "show": at.get("Show", "") == "1"}
            for col, _ in PERIODOS.values():
                if at.get(col, "").strip().isdigit():
                    d[col] = int(at[col])
            cat[idx] = d
        _catalogo = cat
    return _catalogo


def partir_codigo(codigo):
    """itemcode del pedido -> `(Index, dígito del periodo)`."""
    dig = (int(codigo) // 1000) % 10
    return int(codigo) - dig * 1000, dig


SHOP_MUEBLES = 2004


def elegir_regalos(n, azar=None):
    """`n` muebles de regalo para la subida de nivel: al azar entre los muebles (ShopIndex 2004)
    que la tienda muestra y se venden por 30 días."""
    import random
    r = azar or random
    pool = sorted(i for i, d in catalogo().items() if d["shop"] == SHOP_MUEBLES and d["show"] and "P30" in d)
    return [r.choice(pool) for _ in range(int(n))] if pool else []


def codigo_con_periodo(item, dig):
    """El itemcode como lo manda el cliente: el Index con el dígito del periodo en los miles."""
    return int(item) + int(dig) * 1000


def es_de_marca(item):
    return (catalogo().get(int(item)) or {}).get("shop") in (SHOP_LOGO, SHOP_FONDO)


# ── la marca: Index -> id del cuadro del sprite (tabla clavada en `0x619730`) ──────────────────────
def id_logo(index):
    i = int(index)
    return i - 320 if 321 <= i <= 400 else {519: 81, 520: 82}.get(i, 0)


def id_fondo(index):
    i = int(index)
    return i - 400 if 401 <= i <= 450 else (i - 470 if 521 <= i <= 526 else 0)


# ── el registro de 60 B (FFD7 / FFDA / FFD9) ─────────────────────────────────────────────────────
def armar_registro(it):
    """+00 clave · +04 Index · +08 ? · +0C estado ('X' guardado) · +0D ? · +10/+14/+18 x,y,z ·
    +1C vencimiento empacado (el mismo formato que el inventario del jugador) · +20 char[16] ·
    +30 ? · +34 enganche · +38 clave del padre."""
    return (struct.pack("<IIIBB2x", int(it["clave"]), int(it["item"]), 0, int(it.get("estado", 88)) & 0xFF, 0)
            + struct.pack("<IIII", int(it.get("x", 0)) & 0xFFFFFFFF, int(it.get("y", 0)) & 0xFFFFFFFF,
                          int(it.get("z", 0)) & 0xFFFFFFFF, _exp_to_wire(int(it.get("vence", 0) or 0)))
            + bytes(16) + struct.pack("<IB3xI", 0, int(it.get("enganche", 0)) & 0xFF,
                                      int(it.get("padre", 0)) & 0xFFFFFFFF))


def leer_registro(r):
    """Lo que nos importa de un registro de 60 B que manda el cliente (el `FFD8`). x/y/z y el padre
    se guardan CRUDOS: al colocar un piso el cliente mandó x = 0xF000003C y padre = 2100000000
    (25-sep) — no sabemos qué son, pero son SUYOS y se los devolvemos igual."""
    clave, item, _8, estado, _d = struct.unpack_from("<IIIBB", r, 0)
    x, y, z = struct.unpack_from("<III", r, 0x10)
    enganche, padre = r[0x34], struct.unpack_from("<I", r, 0x38)[0]
    return {"clave": clave, "item": item, "estado": estado, "x": x, "y": y, "z": z,
            "enganche": enganche, "padre": padre}


def acomodar(usn, data):
    """`FFD8 [u8 n] + n x 60 B` = GUARDAR EL ARREGLO de la sala (`0x5E3940`, sólo los que cambiaron).
    Respuesta (`0x5E1950`): `[u8 n] + n x 60 B` — el cliente sólo mira que n != 0 (con 0 saca #28
    «Hubo un fallo en el arreglo»), descarta los registros y descuenta un pedido pendiente; al
    llegar a 0 manda un `FFD8 [0]` («listo», `0x5DB450`).
    ⛔⛔ El «listo» NO se contesta con FFD8 — MEDIDO con Frida el 25-sep: cada FFD8 que llega
      descuenta el contador de guardados (`[red+0x21B80]`) y contestar el «listo» lo dejó en -1.
    ★★ Se contesta con **`FFDE`** (`armar_ffde`): el botón «Completar/Guardar» se deshabilita al
      mandar y espera un FFDE — sin él quedaba «no accionable» (`documentacion/CIRCULO_EXE_EDICION.md`).
      Para el «listo» esta función devuelve `(None, cid, modo del FFDE)`.
    Sólo el LÍDER arregla la sala (#35). -> `(respuesta, cid, filas guardadas)` o, para el
    «listo», `(None, cid, modo del FFDE)`."""
    from .circulos import rango_de
    n = data[0] if data else 0
    k = db_circulo_de(usn) if CIRCULOS else None
    if n == 0:
        # el «listo»: NO con FFD8, sino con FFDE (modo 1 si guarda el líder; 2 = sigue editando)
        es_lider = bool(k) and rango_de(k, usn, k["rango"]) == CIRCULO_RANGO_LIDER
        return None, (k or {}).get("id"), (FFDE_LIDER_CAMBIO if es_lider else FFDE_SEGUIR)
    regs = [leer_registro(data[1 + 60 * i:1 + 60 * (i + 1)]) for i in range(n) if len(data) >= 1 + 60 * (i + 1)]
    if not k or rango_de(k, usn, k["rango"]) != CIRCULO_RANGO_LIDER or not regs:
        return bytes([0]), (k or {}).get("id"), []
    filas = db_acomodar_items_circulo(k["id"], regs)
    log("LOBBY", f"  ⭕ ARREGLO de la sala del círculo #{k['id']}: {len(filas)}/{len(regs)} ítem(s) guardado(s) "
                 + ", ".join(f"{f['clave']}:{f['item']} est={f['estado']:#x}" for f in filas))
    return armar_ffda(filas), k["id"], filas


def armar_ffd7(items, ancho_extra=0):
    """`FFD7` = el inventario ENTERO (el cliente borra el suyo y carga éste): `[res][u32 ancho extra
    de la sala: 0/18/36][u16 n] + n x 60 B`."""
    return bytes([0]) + struct.pack("<IH", int(ancho_extra), len(items)) + b"".join(armar_registro(i) for i in items)


def armar_ffda(items):
    """`FFDA` = altas/cambios del inventario, por clave (`0x5E1870`): `[u8 n] + n x 60 B`."""
    return bytes([len(items)]) + b"".join(armar_registro(i) for i in items)


def armar_ffd9(nueva, resultado, dinero, registro=None):
    """`[u8 esNueva][u8 resultado][u32 dinero que queda][60 B]` — ⚠ en ESE orden (el doc viejo los
    tenía al revés): el switch del resultado es sobre el 2º byte (`0x5DA654`)."""
    return (bytes([1 if nueva else 0, resultado & 0xFF]) + struct.pack("<I", max(0, int(dinero)) & 0xFFFFFFFF)
            + (registro if registro is not None else bytes(60)))


FFDE_EXPANDIDA, FFDE_LIDER_CAMBIO, FFDE_SEGUIR = 0, 1, 2


def armar_ffde(modo, gente=()):
    """`FFDE` S→C (`0x5E5DB0`, «CmdRespawn» en el 2019; el cliente NUNCA lo manda) =
    `[u8 modo][u8 n] + n x ([u8 slot][f32 x][f32 z])` — cada entrada pone al avatar de ese slot en
    (x, 5.0, z). ★★ ES LO QUE CIERRA EL «COMPLETAR/GUARDAR» CON CAMBIOS: el botón (`0x589BF0`) se
    deshabilita (`0x589D51`) y espera un FFDE (`0x589D66`: `0x62CCC0(0xDE, 0x475420)`), y lo único
    que lo vuelve a habilitar es esa llegada (`0x475420` -> `0x685A00`). Cualquier modo lo habilita.
        modo 0  la sala se EXPANDIÓ (#87 al líder / #88 a los demás)
        modo 1  #35 «Líder cambia la Sala de Círculo», REARMA la sala del inventario y sale del
                modo edición (`0x589E90`) — va a TODOS los que están en la sala
        otro    sólo mueve avatares (2 = «seguí editando»)
    ⚠ Sólo a los que están en la SALA DEL CÍRCULO: Mi Sala usa el mismo objeto de escena."""
    out = bytes([modo & 0xFF, len(gente) & 0xFF])
    for slot, x, z in gente:
        out += bytes([slot & 0xFF]) + struct.pack("<ff", float(x), float(z))
    return out


def ffd7_de(usn):
    k = db_circulo_de(usn) if CIRCULOS else None
    return armar_ffd7(db_items_circulo(k["id"])) if k else None


def _conectados(cid):
    from .salas import CONEXIONES
    out = []
    for m in db_miembros_circulo(cid):
        c = CONEXIONES.get(m["uid"])
        if c is not None and not getattr(c, "cerrado", False):
            out.append(c)
    return out


def comprar(usn, codigo, clave=0):
    """-> `(paquete FFD9, fila nueva o None, cid)`. Cobra al círculo y guarda, o nada."""
    from .circulos import _ahora, rango_de
    usn = int(usn)
    k = db_circulo_de(usn) if CIRCULOS else None
    item, dig = partir_codigo(codigo)
    ficha = catalogo().get(item)
    col, dias = PERIODOS.get(dig, (None, 0))
    if not k:
        return armar_ffd9(not clave, ERROR, 0), None, None
    eco = db_economia_circulo(k["id"])
    if ficha is None or col not in ficha:
        return armar_ffd9(not clave, NO_EXISTE, eco["dinero"]), None, k["id"]
    if eco["nivel"] < ficha["clevel"]:
        reg = armar_registro({"clave": 0, "item": item})           # el cliente lee el Clevel de +4
        return armar_ffd9(not clave, NIVEL, eco["dinero"], reg), None, k["id"]
    if not es_de_marca(item) and rango_de(k, usn, k["rango"]) != CIRCULO_RANGO_LIDER:
        return armar_ffd9(not clave, ERROR, eco["dinero"]), None, k["id"]   # #34: sólo el líder
    dinero, fila = db_comprar_item_circulo(k["id"], item, ficha[col], dias, usn, int(time.time()), _ahora(), clave)
    if fila is None:
        return armar_ffd9(not clave, SIN_DINERO if dinero < ficha[col] else NO_EXISTE, dinero), None, k["id"]
    log("LOBBY", f"  ⭕ TIENDA DEL CÍRCULO #{k['id']}: usn={usn} {'extiende' if clave else 'compra'} "
                 f"{item} {ficha['nombre']!r} ({col}) por {ficha[col]} -> clave {fila['clave']}, quedan {dinero}")
    return armar_ffd9(not clave, OK, dinero, armar_registro(fila)), fila, k["id"]


def marca(usn, marca_pedida, item_logo, item_fondo):
    """`FFDF [u32 marca][u32 Index logo][u32 Index fondo]` -> `(respuesta, cid o None)`.
    Respuesta `[u8 res][u16 id logo][u16 id fondo]` (alto primero); res 1..7 = #72 «falló»."""
    from .circulos import _es_operador
    k = db_circulo_de(usn) if CIRCULOS else None
    il, ifo = id_logo(item_logo), id_fondo(item_fondo)
    malo = struct.pack("<BHH", 1, 0, 0)
    if not k or not il or not ifo or int(marca_pedida) != ((il << 16) | ifo) or not _es_operador(k, usn):
        return malo, None
    if db_poner_marca_circulo(k["id"], (il << 16) | ifo, item_logo, item_fondo) is None:
        return malo, None                                          # no tiene el logo o el fondo
    log("LOBBY", f"  ⭕ MARCA del círculo #{k['id']}: logo {item_logo} (id {il}) + fondo {item_fondo} (id {ifo})")
    return struct.pack("<BHH", 0, il, ifo), k["id"]


def avisar_inventario(cid, filas, salvo=0):
    """El `FFDA` con lo nuevo, a TODOS los del círculo conectados (el inventario es de todos)."""
    p = armar_ffda(filas)
    cs = [c for c in _conectados(cid) if int(getattr(c, "usn", 0) or 0) != int(salvo)]
    for c in cs:
        c.send_ff55(0xDA, p, name=f"FFDA inventario del círculo: {len(filas)} ítem(s) nuevo(s)")
    return len(cs)


def avisar_inventario_entero(cid):
    """El `FFD7` entero a todos (tras gastar ítems: el `FFDA` sólo agrega, no borra)."""
    p = armar_ffd7(db_items_circulo(cid))
    cs = _conectados(cid)
    for c in cs:
        c.send_ff55(0xD7, p, name=f"FFD7 inventario del círculo ({(len(p) - 7) // 60} ítems)")
    return len(cs)
