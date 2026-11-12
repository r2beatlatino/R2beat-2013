# -*- coding: utf-8 -*-
"""lobby_tienda — comprar, equipar, inventario, misiones y premios.

Cada función es UNA rama del `handle_inner` original, movida tal cual.
El orden y las condiciones viven en `despacho.py`.
"""
from . import shop_catalog
from . import preferidos
import struct
import time

from .ajustes import (
    MONEDA_GORILA_ITEM,
    CASH,
    DISCOVER_DURATION,
    COBRAR_COMPRAS,
    HOST_SLOT,
    MASCARA_DE_MISION,
    MISIONES_POR_REPLAY,
    NOMBRE_DE_MISION,
    RCOIN,
    REFRESCAR_ROPA_EN_SALA,
    REFRESCO_ROPA_FF15,
    REFRESCO_ROPA_RESPAWN,
    REFRESH_AFTER_BUY,
    RESPONDER_COMO_EL_REAL,
)
from .registro import (
    hx,
    log,
)
from . import gacha
from .ajustes import OWNED_SONGS_2013, GACHA_PERSONAJE_RAFAGA, REAPARECER_AL_CAMBIAR_PERSONAJE
# ⚠ `aviso_sistema` vive en `lobby_carrera` por dónde nació (el cartel del START), no porque sea
#   de carreras: es "una línea de chat firmada SERVER". No hay ciclo — a `lobby_tienda` sólo lo
#   importa `despacho`.
from .lobby_carrera import aviso_sistema
from .basedatos import (
    _exp_to_wire,
    compute_expiry,
    db_add_exp,
    db_add_inventory,
    db_add_rcoin,
    db_del_inventory,
    db_get_char,
    db_get_mission,
    db_get_rcoin,
    db_load,
    db_marcar_premio,
    db_premio_cobrado,
    db_save,
    db_save_uno,
    db_set_mission,
    inv_ids,
    inv_cant,
)
from .catalogo import (
    entregar_compra,
    tiene_cargas,
    db_equip,
    face_id,
    real_item_id,
    wing_id,
)
from .progresion import (
    nibbles_a_campoE,
)
from .misiones import (
    db_add_mision,
    db_set_grado,
    entregar_premio_mision,
    item_para_el_cartel,
    premio_de,
)
from .myrecord import (
    enviar_ff69_moneda_gorila,
    enviar_myrecord,
    build_myrecord,
)
from .paquetes import (
    build_ff0c_2013_real,
    build_ff49,
    inventario_para_ff49,
    build_ff126,
    build_ff15_2013,
    build_ff81_progreso,
)
from .salas import (
    CONEXIONES,
    _ocupante_de,
    equipo_para_ff0c,
    enviar_equipos,
    ff15_de,
    mesa_de,
)


def h_10_ff111(st, cmd, data):
    # rama original:  cmd == 273
    # ★ Lo manda la MISIÓN DE LICENCIA ("Premio: Licencia"). Sin respuesta el cliente SE TRABA.
    # Handler: lee un **u32** -> `[player+0x664] = ese valor` (★ LA LICENCIA) y después
    #   `0x488FD0(player, word[[0x931624]+2])` = OTORGAR la máscara de la misión en curso.
    # Capturado al hacer "Licencia Estrella": `01 00 00 00 01` -> pide licencia **1 = ESTRELLA**,
    # que es exactamente el valor medido en re/barrido_licencia.py. RESPUESTA = **[licencia:u32]**.
    # ★★ EL 5º BYTE DECIDE (medido comparando las tres capturas):
    #      `01 00 00 00 01` -> misión TERMINADA de verdad  -> otorgar + responder
    #      `01 00 00 00 00` -> el cliente ENTRA a repetirla -> **NO responder**
    #   ⚠ El handler `0x5E3410` DISPARA UN POPUP (`push 0x31`) al procesar la respuesta. Si se
    #     contesta el caso `00`, el cartel de "ya la hiciste" sale **apenas entrás** y **no te deja
    #     repetir la misión**. Mismo patrón que el FF81 del CBT ("inicio de lección -> no responder").
    _fin   = data[4] if len(data) > 4 else 1
    _pide  = struct.unpack("<I", data[0:4])[0] if len(data) >= 4 else 0
    if not _fin:
        log("LOBBY", f"  ★ FF111 raw={hx(data)} pide={_pide} -> ENTRADA a la misión (5º byte=0): "
                     f"NO se responde (si se responde, sale el cartel antes de tiempo)")
        return
    _antes = int((db_get_char(getattr(st, "usn", 0)) or {}).get("licencia", 0) or 0)
    _nueva = _antes | _pide                      # acumulativa: 1=estrella · 2=luna · 4=sol
    # ★★ 2026-09-05 — DOS cosas acá, y la segunda NO es de rendimiento:
    #   1. era `db_load()` = los 4806 personajes para tocar uno.
    #   2. ⛔ escribía la licencia en el personaje **"0"**, no en el que la pidió. `_antes` sí lee
    #      la del jugador (`st.usn`), así que leía de uno y guardaba en otro: la licencia no le
    #      quedaba a nadie. Es el MISMO error que `lobby_carrera.py` ya tenía anotado para las
    #      monedas del gorila ("acreditaba al personaje 0 fijo"); allá se arregló y acá quedó.
    _usn = getattr(st, "usn", 0)
    _chl = db_get_char(_usn)
    if _chl:
        _chl["licencia"] = _nueva; db_save_uno(_usn, _chl)
    st.send_ff55(0x111, struct.pack("<I", _nueva), name=f"FF111 licencia otorgada = {_nueva}")
    log("LOBBY", f"  ★★★ FF111 LICENCIA: raw={hx(data)} pide={_pide} | licencia {_antes} -> {_nueva} "
                 f"({ {0:'ninguna',1:'ESTRELLA',2:'LUNA',4:'SOL'}.get(_nueva, _nueva) }) — guardada en la DB")


def h_11_ffab(st, cmd, data):
    # rama original:  cmd == 171
    # Handler entero: lee un u32 y hace `[player+0x2d8] = valor ^ 0x1FEF` (misma ofuscación que el
    # exp en +0x2d0). Es el "?" que el cliente muestra como premio inferior a S: **lo llena el
    # SERVER**. Capturado al reclamar: `32 7f 00 00` = 32562.
    # ★★ 2026-07-31: DEVOLVER EL ECO ERA EL BUG DEL "Rcoin ?" INVISIBLE. El cliente manda **0**
    #    (no sabe cuánto ganó) y espera que el SERVER le diga el número; devolviéndole su propio 0
    #    el cartel queda en blanco. El monto real está en el script de la misión: el `Succ` coreano
    #    de `rnr_script/mission/1.txt` dice literal `5000 알코인 획득!`. Ver PREMIOS_MISION.
    _v = struct.unpack("<I", data[0:4])[0] if len(data) >= 4 else 0
    _mid   = getattr(st, "ultima_mision", 0)
    _mask  = MASCARA_DE_MISION.get(_mid, 0)
    _prem  = premio_de(_mask)[0]
    # ★ de UNA SOLA VEZ: la misión se puede repetir, el premio no se cobra de nuevo.
    #   (Con rank S el cliente ya no ofrece el set, pero el FFAB lo manda igual.)
    _yacobrado = db_premio_cobrado(getattr(st, "usn", 0), _mid, "rcoin") if _mid else False
    if _prem and not _yacobrado:
        _saldo = db_add_rcoin(getattr(st, "usn", 0), _prem)
        db_marcar_premio(getattr(st, "usn", 0), _mid, "rcoin")
    else:
        _saldo = db_get_rcoin(getattr(st, "usn", 0))
    st.send_ff55(0xAB, struct.pack("<I", _saldo & 0xFFFFFFFF),
                 name=f"FFAB premio {_prem if not _yacobrado else 0} -> saldo {_saldo}")
    log("LOBBY", f"  ★★★ FFAB PREMIO EN MONEDA: el cliente pidió {_v} (su saldo actual) | "
                 f"misión {_mid} (máscara 0x{_mask:04X}) premia {_prem} Rcoin -> saldo nuevo "
                 f"{_saldo} ([player+0x2d8])")
    if _yacobrado:
        log("LOBBY", f"  ★ el premio en Rcoin de la misión {_mid} YA se cobró — no se paga de "
                     f"nuevo (sólo se devuelve el saldo)")
    elif not _prem:
        log("LOBBY", f"  ⚠ no tengo premio en Rcoin para la máscara 0x{_mask:04X}")
    if REFRESH_AFTER_BUY:
        enviar_myrecord(st, "MyRecord refresh (premio de misión)", con_personaje=False)


def h_12_ff125(st, cmd, data):
    # rama original:  cmd == 293
    # ★ HALLADO 2026-07-30 jugando la misión: al terminarla el cliente manda `FF125` (NO el FF81,
    #   que es el tutorial de la escuela). Sin respuesta -> **el premio sale VACÍO y la misión
    #   queda en "reto"**. Capturado: `0a 41 00 00`.
    # ★ WIRE DEL PEDIDO (capturado jugando): **[mision:u8][grado:u8 ASCII][premio:u16]**
    #     `0a 41 00 00` = misión 10, grado 'A' (0x41), premio 0
    #     `0a 53 04 00` = misión 10, grado 'S' (0x53), premio 4  ← el set elegido
    # RESPUESTA = **2 BYTES**: [A:u8][B:u8]. Lo que hace el cliente (disasm 0x5DA100):
    #     esi = 0x48A5E0(player, A)        -> busca la entrada en el vector de licencias/misiones
    #     si B != 0:  0x488FD0(player, esi)  ← ★ la MISMA función del paso 5 del FF81 = OTORGAR
    #     0x48A530(player, esi, B)
    #   ⇒ ambas recorren `[player+0x3c]..+0x40`, que es el vector de 19 structs de 124B que
    #     volcamos (máscara u16 en +0, "otorgada" en +3). Por acá se marca la misión Y la licencia.
    # ★★ 2026-07-31: `0x48A5E0` NO es una traducción con tabla aparte — recorre ese mismo vector
    #    comparando `byte [ebp+0x79]`, o sea **cada struct lleva adentro su id de misión**. Ver
    #    MISIONES_2013: la tabla entera (id, máscara, nivel, nombre) salió del cliente.
    _a = data[0] if len(data) > 0 else 0
    _b = data[1] if len(data) > 1 else 0
    _premio = struct.unpack("<H", data[2:4])[0] if len(data) >= 4 else 0
    _resp = bytes([_a & 0xFF, (_b or 1) & 0xFF])
    _antes = db_get_mission(getattr(st, "usn", 0))
    _desp  = db_set_mission(getattr(st, "usn", 0), _a)          # persistir en la DB, como el CBT
    # ★ y sumar la misión a su grupo, que es lo que la deja "hecha" tras reloguear. El grupo ya no
    #   se asume: sale de la MÁSCARA de la misión, que está en MISIONES_2013 (volcada del cliente).
    _mask   = MASCARA_DE_MISION.get(_a, 0)
    _nombre = NOMBRE_DE_MISION.get(_a, "??? (id desconocido)")
    _nib = db_add_mision(getattr(st, "usn", 0), _a)
    _grado = db_set_grado(getattr(st, "usn", 0), _a, _b or ord("S"))     # ★ persiste el grado, quedándose con el mejor
    st.send_ff55(0x125, _resp, name=f"FF125 misión completada A={_a} B={_b or 1}")
    log("LOBBY", f"  ★★★ FF125 MISIÓN COMPLETADA: raw={hx(data)} -> misión={_a} "
                 f"({_nombre}, máscara 0x{_mask:04X}) "
                 f"grado={chr(_b) if 32 <= _b < 127 else _b!r} premio_elegido={_premio} | "
                 f"resp={hx(_resp)} | mission {_antes} -> {_desp} | nibbles={_nib} "
                 f"-> campo E del login = " +
                 ("0x000 (NIBBLE OFF: la persistencia la hace el replay de FF125)"
                  if MISIONES_POR_REPLAY else f"0x{nibbles_a_campoE(_nib):03X}") +
                 f" | grado guardado={_grado!r}")
    if not _mask:
        log("LOBBY", f"  ⚠ id {_a} NO está en MISIONES_2013 — anotalo, es una misión sin mapear")
    # ★★ ENTREGAR EL PREMIO (2026-07-31). El cliente NO agrega nada solo: sólo reporta qué eligió.
    st.ultima_mision = _a                       # el FFAB llega después y necesita saber cuál fue
    # ⛔⛔ ACÁ HABÍA UN `0` HARDCODEADO EN VEZ DEL usn — 2026-09-05.
    #   `entregar_premio_mision(0, ...)` hacía DOS destrozos silenciosos:
    #     1. `genero = db_get_char(0)["char_id"] & 1` -> no existe el usn 0 -> char_id 0 -> **género
    #        HOMBRE siempre**. Una jugadora recibía el set de varón, que no se puede equipar.
    #     2. `db_add_inventory(0, ...)` empieza con `if not ch: return` ⇒ **el premio se calculaba,
    #        se logueaba "PREMIO ENTREGADO" y se tiraba a la basura**. Y `db_marcar_premio(0,...)`
    #        tampoco anotaba nada, así que ni siquiera quedaba rastro de que se había cobrado.
    #   El síntoma que lo destapó: cuenta nueva de mujer, misión 1, "sólo recibí zapatos de hombre".
    #   Los "zapatos" eran el CARTEL (`item_para_el_cartel` elige el calzado del set); del set no
    #   llegó nada. Y eran de hombre por el punto 1.
    #   ⚠ El Rcoin de la misma misión SÍ funcionaba: viaja por el `FFAB`, que unas líneas más arriba
    #     usa `getattr(st, "usn", 0)` como corresponde. Por eso el bug parecía "a medias".
    #   ⛔ Y NO fue la modularización: el monolito `legacy/server_login2013.py:4485` tiene el mismo
    #     `0`. Nació así. Ver `documentacion/mapeo_misiones.md` §8-7, donde ya había una sospecha
    #     anotada ("no se pudo distinguir 'lo inyectamos a mano' de un bug de entrega").
    _pr = entregar_premio_mision(getattr(st, "usn", 0), _a, _premio)
    log("LOBBY", f"  ★ premio: wire={_premio} género={'mujer' if _pr['genero'] else 'hombre'} "
                 f"-> RECUADRO {_pr['recuadro']} (remapeo del cliente, ver RECUADRO_DESDE_WIRE)")
    if _pr["items"]:
        log("LOBBY", f"  ★ PREMIO ENTREGADO: ítems {_pr['items']} por {_pr['dias']} días "
                     f"(caduca {_pr['caduca']})" +
                     (f" | +{_pr['exp']} EXP -> {_pr['exp_nuevo']}" if _pr["exp"] else ""))
        # ★★ y POBLAR EL CARTEL con el FF126 (sin esto el recuadro sale vacío)
        _cartel = item_para_el_cartel(_pr["items"])
        if _cartel:
            st.send_ff55(0x126, build_ff126([_cartel], caduca=_pr["caduca"]),
                         name=f"FF126 cartel de premio: ítem {_cartel}")
            log("LOBBY", f"  ★★ FF126 -> el cartel muestra {_cartel} "
                         f"({shop_catalog.CATALOG.get(_cartel, {}).get('name', '?')})"
                         + (" [calzado del set]" if len(_pr["items"]) > 1 else ""))
        enviar_myrecord(st, "MyRecord refresh (premio de misión)", con_personaje=False)
    elif _pr.get("repetida"):
        log("LOBBY", f"  ★ misión REPETIDA: el premio en ítems ya se cobró, no se entrega otra vez")
    elif _premio:
        log("LOBBY", f"  ⚠ wire={_premio} -> recuadro {_pr['recuadro']}: sin ítems en "
                     f"SETS_PREMIO_MISION para ese recuadro/género")


def h_13_ff81(st, cmd, data):
    # rama original:  cmd == 129
    # ★ PLAN (idea del usuario, calcada del CBT): en vez de adivinar offsets, **hacer las misiones
    #   una por una** y mirar QUÉ reporta el cliente. Acá sólo se LOGUEA crudo y se persiste en la
    #   DB (`char["mission"]`, monótono), igual que el `chars.mission` del CBT.
    # RESPUESTA S->C (14B, layout confirmado en el disasm y = al CBT):
    #   [A:u8][selector:u8][f3:u32][f4:u32][f5:u32]
    #   selector 0 + f3!=0  ->  el cliente hace `[player+0x335] = A`  (0x5E31A0)
    #   ⚠ A ∈ {6,7,8} entra por OTRA rama (0x5E31D4). A == 5 llama además 0x488FD0.
    # ★ Y `[player+0x335]` es lo que otorga las licencias con máscara {6,7,8} (bucle 0x489103).
    _fase   = data[0] if len(data) > 0 else 0
    _paso   = data[1] if len(data) > 1 else 0
    _extra  = data[2] if len(data) > 2 else None
    _antes  = db_get_mission(getattr(st, "usn", 0))
    _desp   = _antes
    if _fase == 1 and _paso >= 1:                     # 1 = paso TERMINADO -> persistir
        _desp = db_set_mission(getattr(st, "usn", 0), _paso)
        st.send_ff55(0x81, build_ff81_progreso(_paso),
                     name=f"FF81 avance: paso {_paso} (selector 0, f3=1 -> [player+0x335]={_paso})")
        _sc = f" -> S->C avance paso={_paso}"
    else:
        _sc = " (inicio de paso -> NO se responde, igual que el CBT)"
    log("LOBBY", f"  ★★★ FF81 MISIÓN: raw={hx(data)} len={len(data)} | fase={_fase} paso={_paso} "
                 f"extra={_extra} | mission {_antes} -> {_desp}{_sc}")


def h_16_ffaf(st, cmd, data):
    # rama original:  cmd == 175
    # ★★ FFAF (handler cliente 0x5D71C0) — DOS listas de registros de 88 bytes (0x58) que van al
    #   objeto [0x9316DC]. Formato MEDIDO:
    #       [u8 n1]{ [88B] × n1 }[u8 a][u8 b]      a -> [obj+0x30], b -> [obj+0x34]
    #       [u8 n2]{ [88B] × n2 }[u8 c][u8 d]      c -> [obj+0x38], d -> [obj+0x3c]
    #   ★ 15-oct: son las MISIONES PUZZLE. El despacho ya NO llama acá: va a `puzzle.h_ffaf` (la lista de verdad).
    #   Queda como la respuesta vacía de referencia.
    st.send_ff55(0xAF, b"\x00\x00\x00\x00\x00\x00", name="FFAF dos listas vacías")


def h_34_ffc8(st, cmd, data):
    # rama original:  cmd == 200
    # 4 slots: f0=current(1.08) · u32 dur(frames) · f2=bonus-precision(0=precision real) · f3=target(1.08).
    st.send_ff55(0xC8, struct.pack("<f I f f", 1.08, 380, 0.0, 1.08), name="FFC8 boost (1.08/380/0/1.08)")
    log("LOBBY", "  ★ FFC8 -> boost default (dispara FF57)")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ EL COBRO — hasta el 2026-09-05 la tienda era DECORATIVA
#
# `h_35_ff2a` y `h_36_ff50` contestaban éxito y devolvían el saldo **sin tocar** (`saldo = RCOIN`,
# con un comentario que decía "sin descuento aún"). Se podía comprar el catálogo entero con
# cualquier saldo, y el número que mostraba el cliente era una constante de `ajustes.py`.
#
# ⚠ QUÉ PRECIO SE COBRA — no es "el precio del item", es **el precio DEL PLAZO que eligió**.
#   El plazo viaja en el **dígito de las MILÉSIMAS del id de compra** y el mapeo está MEDIDO en
#   vivo (`shop_catalog.PERIOD_TO_ATTR`, modo `DISCOVER_DURATION`, 2026-07-11):
#       1 -> P7 (7 días) · 2 -> P30 · 9 -> PI (permanente) · 5 -> P (pack) · 6 -> PN (uso único)
#   ⏳ Los códigos **3 y 4** (las duraciones largas, P100/P365) NO están medidos. Si llega uno, se
#     cobra el precio más caro que ofrezca el item y **se loguea con ⚠**: cobrar de menos regala
#     items, y cobrar el más caro es el error que se nota — que es justo el que queremos que se
#     note para poder cerrar el mapeo.
# ═════════════════════════════════════════════════════════════════════════════════════════════
def precio_de_compra(item_id, periodo):
    """Cuánto sale ese item en ese plazo. Devuelve (precio, de_donde_salio)."""
    it = shop_catalog.get(item_id) if item_id else None
    precios = {k: v for k, v in (it or {}).get("durations", {}).items() if 0 < v < 100_000_000}
    if not precios:
        return 0, "el item no tiene ningún precio en el catálogo -> GRATIS"
    attr = shop_catalog.PERIOD_TO_ATTR.get(int(periodo or 0))
    if attr and attr in precios:
        return precios[attr], attr
    if len(precios) == 1:                       # un solo plazo: no hay ambigüedad posible
        k, v = next(iter(precios.items()))
        return v, f"{k} (único plazo del item)"
    k = max(precios, key=precios.get)
    return precios[k], f"⚠ período {periodo} SIN MAPEAR -> cobro el más caro ({k})"


def cobrar(st, item_id, periodo, comando):
    """Descuenta el precio si alcanza. Devuelve (alcanza, precio, saldo_final)."""
    usn = getattr(st, "usn", 0)
    saldo = db_get_rcoin(usn)
    precio, de_donde = precio_de_compra(item_id, periodo)
    if not COBRAR_COMPRAS:
        log("LOBBY", f"  ⚠ {comando}: COBRAR_COMPRAS=False -> sale gratis (precio era {precio})")
        return True, 0, saldo
    if precio > saldo:
        log("LOBBY", f"  ⛔ {comando}: SIN SALDO. item={item_id} plazo={periodo} ({de_donde}) "
                     f"cuesta {precio} y tiene {saldo}")
        return False, precio, saldo
    nuevo = db_add_rcoin(usn, -precio) if precio else saldo
    log("LOBBY", f"  🪙 {comando}: COBRADO {precio} rcoin por el item {item_id} "
                 f"(plazo {periodo} = {de_donde}) · saldo {saldo} -> {nuevo}")
    return True, precio, nuevo


def sacar_escaparate(st, item_id, comando):
    """Si lo comprado era un pack de ESCAPARATE, se lo saca de la vista al cliente.

    ★ El server ya no lo guarda (se abre en `entregar_compra`), pero el CLIENTE, al leer la respuesta
      de compra, lo mete él solo en su inventario, y el MyRecord de después sólo SUMA: quedaba a la
      vista junto al contenido hasta reconectar (anonimo03, 23-sep: *"recibí los 4 ítems, pero también
      fue a parar el ítem de escaparate"*).
    ⇒ El camino nativo para sacar un ítem es el `FF6A` (`CmdDecreaseItemCount`, `0x48FDA0`): baja una
      unidad y, en 0, **borra la fila** del inventario. Es el mismo que ya usan las campanas.
    """
    from .ajustes import TIENDA_ABRE_SETS
    try:
        if TIENDA_ABRE_SETS and shop_catalog.es_set(item_id) and shop_catalog.contenido_de_set(item_id):
            st.send_ff55(0x6A, struct.pack("<I", int(item_id) & 0xFFFFFFFF),
                         name=f"FF6A saca el escaparate {item_id} de la vista ({comando}; se abrió)")
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude sacar el escaparate {item_id} de la vista: {e!r}")


def h_35_ff2a(st, cmd, data):
    # rama original:  cmd == 42
    # req medido 2013: [u8 ?][u32 raw][u8 ?] (6B, ej '00 00 fc 9b 00 00' -> raw@1=10222080 -> item 222080/dur1).
    # raw codifica item+duración (item=raw%10^7, dur=raw//10^7). RESPUESTA guía CBT (handle_buy_dress 0x578F20):
    #   [result:u8][0:u8][item_id:u32][end_time:u32][coin:u32]. result 0=OK, 1=sin saldo, 2=ya lo tiene.
    raw = struct.unpack_from("<I", data, 1)[0] if len(data) >= 5 else 0
    dur = shop_catalog.period_code(raw)             # el dígito de miles ES el código de período/duración
    item_id = shop_catalog.normalize_id(raw)        # ★ valida contra catálogo (Index real)
    fam = shop_catalog.family(item_id) if item_id else "?"
    if item_id is None:                             # no está en catálogo: fallback heurístico + aviso
        item_id = real_item_id(raw)
        log("LOBBY", f"  ⚠ FF2A raw={raw} no está en catálogo; fallback -> {item_id}")
    _ch = db_get_char(getattr(st, "usn", 0)) or {}
    owned = item_id in (inv_ids(_ch) + _ch.get("parts", []))
    # ★★★★★ UN CONSUMIBLE SE PUEDE COMPRAR DE NUEVO — 2026-09-15. anonimo03: *"si compro unidad 1 en
    #   tienda, sólo puedo comprarlo 1 vez; debería poder comprar más y acumular cargas tal cual
    #   hace el de 5"*. El `result = 2` («ya lo tenés») tiene sentido para una PRENDA —comprar dos
    #   veces el mismo pantalón es tirar la plata— pero no para algo que se gasta.
    #   ★ Y acumular ya funcionaba solo: `db_add_inventory` SUMA las cargas cuando el ítem ya
    #     está. Lo único que faltaba era dejarlo pasar por acá. Él mismo lo confirmó con el pack:
    #     *"gasté 1, compré otros 5 y me quedé con 9"* — la suma estaba bien desde antes.
    #   ★★ 2026-09-15 (campanas): la pregunta se mudó a `catalogo.tiene_cargas`, que además de la
    #     familia mira la lista de ÍTEMS sueltos. Las campanas son `coupon_buff` —la familia de
    #     los cupones de EXP, que nadie probó— así que no se puede abrir la familia entera.
    if owned and tiene_cargas(item_id):
        owned = False
        log("LOBBY", f"  ★ item {item_id} es consumible: se deja RE-COMPRAR para sumar cargas")
    # ★ Un pack de ESCAPARATE no es algo que «se tenga»: se abre al comprarlo (ver `TIENDA_ABRE_SETS`).
    #   Si quedó en el inventario de antes (cuando se entregaba crudo), igual se deja re-comprar.
    if owned and shop_catalog.es_set(item_id):
        owned = False
        log("LOBBY", f"  ★ item {item_id} es un SET: se deja re-comprar (se abre al entregarlo)")
    result = 0 if DISCOVER_DURATION else (2 if owned else 0)   # discovery: siempre OK (re-comprable)
    exp = compute_expiry(dur)                       # Fase B: expiry UNIX (0 = permanente/consumible)
    # ★ EL COBRO. `result 1 = sin saldo` ya estaba previsto en el layout (guía del CBT); hasta hoy
    #   no lo usábamos nunca porque nunca mirábamos el saldo.
    saldo = db_get_rcoin(getattr(st, "usn", 0))
    if result == 0 and not DISCOVER_DURATION:
        _alcanza, _precio, saldo = cobrar(st, item_id, dur, "FF2A")
        if not _alcanza:
            result = 1                              # 1 = SIN SALDO -> el cliente muestra su cartel
    resp = (bytes([result, 0]) + struct.pack("<I", item_id & 0xFFFFFFFF)
            + struct.pack("<I", _exp_to_wire(exp))     # end_time real (o centinela permanente)
            + struct.pack("<I", saldo & 0xFFFFFFFF))    # ★ el saldo YA descontado
    st.send_ff55(0x2A, resp, name=f"FF2A BUY item={item_id} fam={fam} dur={dur} result={result}")
    if DISCOVER_DURATION:
        log("LOBBY", f"  ⏱ FASE-B FF2A  item={item_id} ({fam})  raw={raw}  PERIODO(díg miles)={dur}")
    elif result == 0:
        # ★★ ABRE EL PACK si lo es (2026-09-15). Ver `catalogo.entregar_compra`: anonimo03 compró
        #   «5 megáfonos» y le quedó el PACK sin abrir, que el cliente **no deja usar**.
        entregar_compra(getattr(st, "usn", 0), item_id, exp)   # persistir -> aparece en el MyRecord
        sacar_escaparate(st, item_id, "FF2A")
        preferidos.sacar_comprado(st, item_id)               # ★ (132) y sale del carrito (la tira de la tienda)
    log("LOBBY", f"  ★ FF2A BUY req={data.hex()} raw={raw} -> item={item_id} fam={fam} dur={dur} exp={exp} result={result}")
    if REFRESH_AFTER_BUY and not DISCOVER_DURATION and result == 0:
        st.buy_needs_refresh = True                  # extra: si llega un poll, re-refresca
        enviar_myrecord(st, "MyRecord refresh (post-compra FF2A)", con_personaje=False)


def h_36_ff50(st, cmd, data):
    # rama original:  cmd == 80
    # Request medido: [u32 item_raw][u8 currency 'C'(0x43)/'S'(0x53)][u16 opt]  (ej '29 5d 0f 00 43 00 00').
    # Response 22B (mapa de lecturas de 0x5D0080): [u8 result GATE ==1][u32 end_time][u32 ITEM_ID][u32 usn]
    #   [u32 ?][u32 saldo][u8 currency]. result=1 -> exito: 0x50e6e0(item)+0x5c79d0 lo AÑADE al closet+refresh.
    #   usn (campo4) se compara con cfg+0x7c (=0) -> ponerlo 0 para que aplique a MI char. saldo (campo6)
    #   bajo 'C' setea la moneda via 0x485d90 -> mantengo el saldo actual (sin descuento aun).
    if len(data) >= 5:
        item_raw = struct.unpack_from("<I", data, 0)[0]
        currency = data[4]
    else:
        item_raw, currency = 0, 0x43
    # El raw = Index del catálogo con el dígito de MILES (10^3) usado como código de período/duración.
    # normalize_id valida contra el catálogo real (10329545->10320545, 529644->520644).
    duration = shop_catalog.period_code(item_raw)  # dígito de miles = período (P7/P30/P365/PI)
    item_id = shop_catalog.normalize_id(item_raw)  # id real del catálogo (si no, 0x511d80 lo rechaza)
    fam = shop_catalog.family(item_id) if item_id else "?"
    if item_id is None:
        item_id = real_item_id(item_raw)
        log("LOBBY", f"  ⚠ FF50 raw={item_raw} no está en catálogo; fallback -> {item_id}")
    exp = compute_expiry(duration)                  # Fase B: expiry UNIX (0 = permanente/consumible)
    # ★ EL COBRO. Ojo con el `result`: acá **1 = ÉXITO** (es un gate, al revés que el FF2A).
    #   ⚠ Toda la tienda se pasó a rcoin (ver `TIENDA_RCOIN.md`), así que aunque el cliente mande
    #     `currency='C'` se cobra RCOIN igual: no hay otra moneda que cobrar.
    saldo = db_get_rcoin(getattr(st, "usn", 0))
    _ok50 = True
    if not DISCOVER_DURATION:
        _ok50, _precio50, saldo = cobrar(st, item_id, duration, "FF50")
    resp = (bytes([1 if _ok50 else 0])              # [0]  result: 1 = EXITO (gate) · 0 = no
            + struct.pack("<I", _exp_to_wire(exp))  # [1:5]  end_time real (o centinela permanente)
            + struct.pack("<I", item_id)            # [5:9]  ITEM_ID -> lookup + add al inventario
            + struct.pack("<I", 0)                  # [9:13] usn = 0 (== cfg+0x7c -> aplica a mi char)
            + struct.pack("<I", 0)                  # [13:17] ? (0)
            + struct.pack("<I", saldo & 0xFFFFFFFF) # [17:21] ★ el saldo YA descontado
            + bytes([currency & 0xFF]))             # [21] tipo moneda echo ('C'/'S')
    st.send_ff55(0x50, resp, name=f"FF50 BUY item={item_id} fam={fam} dur={duration} "
                                  f"cur={currency:#x} {'EXITO' if _ok50 else 'SIN SALDO'}")
    if DISCOVER_DURATION:
        log("LOBBY", f"  ⏱ FASE-B FF50  item={item_id} ({fam})  raw={item_raw}  PERIODO(díg miles)={duration}")
    elif _ok50:
        # ★★ idem FF2A: si es un pack, se abre. Es el camino por el que compró anonimo03.
        entregar_compra(getattr(st, "usn", 0), item_id, exp)   # persistir en chars_db.json
        sacar_escaparate(st, item_id, "FF50")
        preferidos.sacar_comprado(st, item_id)               # ★ (132) y sale del carrito (la tira de la tienda)
    log("LOBBY", f"  ★ FF50 BUY req={data.hex()} raw={item_raw} -> item={item_id} fam={fam} "
                 f"dur={duration} exp={exp} cur={currency:#x} -> {'EXITO' if _ok50 else 'SIN SALDO'}")
    if REFRESH_AFTER_BUY and not DISCOVER_DURATION and _ok50:
        st.buy_needs_refresh = True                  # extra: si llega un poll, re-refresca
        enviar_myrecord(st, "MyRecord refresh (post-compra FF50)", con_personaje=False)


def refrescar_apariencia_en_sala(st, motivo=""):
    """Repinta al jugador para TODA la sala: `FF0C` + `FF15`. Devuelve a cuántos les llegó.

    ⛔ EL BUG QUE ARREGLA (2026-09-09), reportado por anonimo03: *"no se está actualizando el cambio de
      ropa normal a personaje entre las 2 cuentas que uso en una misma sala"*. Al cambiar de
      personaje sólo se lo decíamos al que se cambió; los demás seguían viendo el cuerpo viejo.

    ★ Es el MISMO camino que ya usa el cambio de ropa (`h_37_ff1a`), y por la misma razón escrita
      allá: *"el cliente arma los avatares una vez al poblar la sala; un `FF0C` repetido le refresca
      el PANEL pero no reconstruye el modelo"* — por eso hace falta el `FF15` detrás.
    ⚠ El `equipo` va sí o sí en el `FF0C`: ese paquete **re-escribe la entrada entera del ocupante**
      y sin él te borra del equipo en el padrón. Es el quinto caso de esa familia (ver la memoria
      `estado-de-la-conexion-vs-la-sala`).
    """
    _rid = getattr(st, "room_id", None)
    # ★★ En la SALA DE CONVERSACIÓN (24-sep): la caché de la estancia + el repintado (`charla.py`).
    if REFRESCAR_ROPA_EN_SALA and _rid is None and getattr(st, "lugar_clave", None) is not None:
        from .charla import refrescar_apariencia
        return refrescar_apariencia(st, motivo)
    if not REFRESCAR_ROPA_EN_SALA or _rid is None:
        return 0
    _dest = [CONEXIONES.get(u) for u in mesa_de(_rid).values()]
    _dest = [c for c in _dest if c is not None and not getattr(c, "cerrado", False)]
    _nick = (db_get_char(getattr(st, "usn", 0)) or {}).get("nick", "")
    _slot = getattr(st, "room_slot", None)
    if _slot is None:
        _slot = HOST_SLOT
    _occ = _ocupante_de(getattr(st, "usn", 0), _slot)
    _occ["equipo"] = equipo_para_ff0c(st, _slot)
    # ★★ Y EL ENLACE DE PAREJA, o este refresco lo BORRA. `_ocupante_de` no lo trae, así que sin
    #   esto el `FF0C` saldría con `0xFF` (soltero) y cambiarse de ropa te rompería el recuadro.
    #   Es el mismo cálculo que hace `armar_ocupantes`: sólo si los dos están en ESTA sala.
    try:
        from .basedatos import db_pareja_de, db_anillo_de_pareja
        _yo15 = int(getattr(st, "usn", 0) or 0)
        _pj15 = db_pareja_de(_yo15) if _yo15 else 0
        if _pj15:
            _slot_pj = next((int(_s) for _s, _u in mesa_de(_rid).items() if int(_u) == _pj15), None)
            if _slot_pj is not None:
                _occ["pareja_slot"] = _slot_pj
                _occ["anillo"] = db_anillo_de_pareja(_yo15)
    except Exception as _e15:                                    # noqa: BLE001
        log("LOBBY", f"  ⚠ refresco: no pude armar el enlace de pareja: {_e15!r}")
    _n = 0
    for _c in (_dest or [st]):
        try:
            # ★★★★★ EL `FF0E` PRIMERO, Y ESTO NO ES OPCIONAL PARA EL DISTINTIVO (2026-09-09).
            #   ⛔ Reportado: al cambiar de personaje dentro de la sala, el ícono de sexo del
            #     cartelito **se queda con el que tenías al entrar**; saliendo y volviendo sale bien.
            #   ★ La causa ya estaba medida y escrita por nosotros: **el `FF0C` CREA si el asiento
            #     está libre, y si el ocupante YA existe se va sin hacer nada** (`cRoom::OnRoomUser`,
            #     `0x59FDF0`; ver `FF0C_INFORME_AGENTE.md`). O sea que nuestro repintado mandaba el
            #     sexo correcto y el cliente lo ignoraba.
            #   ⇒ Hay que SACAR al ocupante y volver a ponerlo. El `FF15` de abajo recarga el
            #     modelo —por eso el cuerpo sí cambiaba— pero no re-crea la entrada, que es donde
            #     vive el distintivo.
            #   ⚠ Si esto produce parpadeo o se pierde el "soy yo", se apaga con
            #     `REAPARECER_AL_CAMBIAR_PERSONAJE` y queda el comportamiento anterior.
            if REAPARECER_AL_CAMBIAR_PERSONAJE and _nick:
                _nb = _nick.encode("cp1252", "replace")[:0xFF]
                _c.send_ff55(0x0E, bytes([len(_nb)]) + _nb,
                             name=f"FF0E sacar a {_nick!r} (para re-crearlo){motivo}")
            _c.send_ff55(0x0C, build_ff0c_2013_real(_occ, 1),
                         name=f"FF0C apariencia nueva de {_nick!r}{motivo}")
            if REFRESCO_ROPA_FF15:
                # ★★ El FF15 sale de `salas.ff15_de`: lleva la pareja, el EQUIPO, el capitán y las
                #   joyas del alma (2026-09-23). Armado a mano se olvidaba del equipo y te sacaba
                #   del padrón, y con la cola cortada te borraba las joyas.
                _c.send_ff55(0x15, ff15_de(_occ, _rid),
                             name=f"FF15 reload de {_nick!r} (slot {_slot})")
            enviar_equipos(_c, _rid)
            _n += 1
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude repintar a usn={getattr(_c,'usn','?')}: {e!r}")
    log("LOBBY", f"  ★★ apariencia repintada en la sala {_rid} -> {_n} jugador(es){motivo}")
    return _n


def h_ff19_equipar_personaje(st, cmd, data):
    """`FF19 [personaje:u32]` — **"quiero ponerme este personaje"**. (`0x19` = 25.)

    ⛔ NO EXISTÍA. anonimo03 ganó un personaje en el gacha, apareció en la pestaña «Personaje»… y al
      clickearlo no pasaba nada. El log mostró el pedido **nueve veces seguidas**:

          21:43:17  inner FF19 len=4 : ee fb 01 00     ← 0x1FBEE = 130030, el que ganó
          21:43:17  inner FF19 SIN handler                (x9, el cliente reintenta)

      ⚠ Y ojo con esas nueve: un pedido sin respuesta que el cliente REPITE es el mismo patrón que
        ya se vio en el `FF1A`. No es sólo "no anda": es una tormenta esperando.

    ★ LA RESPUESTA — 5 bytes, leídos del handler del cliente `0x5CDBC0`:

          @0  u8   RESULTADO — **0 = OK** (`005cdbf2 cmp byte,0 / jne <salir>`)
                   ⚠ Al revés que el `FF50` de la tienda, donde el 1 es el éxito. Cada paquete
                     tiene su convención y suponerla es como se pierden las tardes.
          @1  u32  el personaje

      Con el 0, el cliente hace `0x487F40(id)` sobre el registro de personajes, llama la ranura
      `+0x34` de su vtable y redibuja. Con cualquier otro valor se va en silencio.

    ★★ Y SE PUEDE VOLVER AL PERSONAJE ORIGINAL. Éste pisa el `char_id`, así que ese número deja de
      decir quién era el jugador — y el personaje base **no está en `spec.txt`**, o sea que tampoco
      puede ir en la lista de la pestaña (el cliente lo descartaría con "Spec data error").
      ⛔ Acá se guardaba un campo `char_base` para recordarlo, y **ese campo no existe en la base**:
        se evaporaba al reloguear, en silencio. El default era `130900` = el base MASCULINO, así que
        toda jugadora que se pusiera un personaje y se lo sacara **quedaba hombre**. Le pasó a una
        cuenta de prueba el 2026-09-09.
      ★ El dato bueno estaba guardado desde siempre: la columna **`gender`**. Ver
        `gacha.personaje_base`. No hacía falta una columna nueva.
    """
    _usn = getattr(st, "usn", 0)
    if len(data) < 4:
        log("LOBBY", f"  ⚠ FF19 con {len(data)} byte(s), esperaba 4: {data.hex()}")
        return
    pj = struct.unpack_from("<I", data, 0)[0]
    _ch = db_get_char(_usn) or {}

    def _no(motivo):
        st.send_ff55(0x19, bytes([1]) + struct.pack("<I", pj),
                     name=f"FF19 NO se equipa el personaje {pj} ({motivo})")
        log("LOBBY", f"  ⛔ FF19 personaje {pj} de usn={_usn}: {motivo}")

    # ⛔⛔ ACÁ HABÍA UN INTERRUPTOR HECHO POR EL SERVER, Y ERA UN ERROR MÍO (2026-09-08).
    #   Yo leí *"al activar o desactivar volvía a la ropa normal"* y deduje que el cliente mandaba
    #   el mismo id las dos veces y que la dirección la decidía el server —como en el `FF99` de
    #   mirar⇄competir—. **El emisor del cliente dice otra cosa** (`0x5C7250` = `SendEditChar`):
    #   para PONER manda el id clickeado y para SACAR manda `cAccount::GetDefaultCharID()`
    #   (`0x487E70`: el registro terminado en 900/901, y si no hay, `130900`).
    #   ⇒ El interruptor ya es del cliente. Mi guard rechazaba el id base por "no es del gacha" y
    #     por eso sacar **nunca** funcionó. Acá se OBEDECE el id que llega.
    #   ★ La lección, para la próxima: un paquete parecido a otro no se comporta como el otro. El
    #     `FF99` llega VACÍO —por eso allá decide el server—; éste trae un id adentro.
    # ★★★ EL FRENO. Medido por anonimo03: clics rápidos -> se cae al segundo; clics espaciados ->
    #   aguanta. Es una carrera con la carga del modelo 3D del personaje, no un dato mal armado.
    #   Ver `GACHA_PERSONAJE_ESPERA` en `ajustes.py` — ahí está el porqué entero, y por qué esto es
    #   un FRENO y no el arreglo.
    #   ⚠ Se contesta con resultado ≠ 0 (el cliente se va en silencio, sin cambiar nada) en vez de
    #     callarse: un `FF19` sin respuesta lo hace REINTENTAR, y ya vimos nueve seguidos.
    #   ⛔⛔ EL CLIENTE ENUMERA LA LISTA, NO SÓLO CLICKEA — medido el 2026-09-09, 00:19.
    #     anonimo03: *"se está cambiando de ropa al personaje si solamente hice clic en la pestaña, no
    #     seleccioné ninguno"*. En el log, al abrir el panel llegan TRES `FF19` seguidos:
    #         00:19:37  ef fb 01 00 -> 130031 (Dark)
    #         00:19:38  ee fb 01 00 -> 130030 (Assault)
    #         00:19:38  ed fb 01 00 -> 130029 (Ice)
    #     Uno por personaje, **en el mismo orden en que se ven en pantalla**. Es el cliente
    #     armando el panel, no el jugador eligiendo — y obedeciéndolos todos le queda puesto el
    #     último de la lista.
    #   ★ CÓMO SE DISTINGUEN: un clic real llega SOLO. La enumeración llega en RÁFAGA. Así que si
    #     entra otro `FF19` pegado al anterior, es el panel cargando: se rechaza **y se devuelve el
    #     personaje al que estaba antes de la ráfaga**, que es el que el jugador de verdad tenía.
    #   ⚠ Es una HEURÍSTICA, y se dice: no hay en el paquete ningún byte que distinga "enumerar" de
    #     "elegir" — son 4 bytes con el id y nada más. Si aparece la forma buena, esto se saca.
    #   ★★★★★ EL BUCLE, MEDIDO CON LA PILA REAL (2026-09-09, `Backtracer.ACCURATE`):
    #
    #       ✉ SendEditChar(130031)  ×8 en 1,4 s  (uno cada ~180 ms)
    #         pila: 0x4ce709 <- 0x5c7250 <- 0x4ce709
    #
    #     El MISMO personaje, repetido, y el manejador del clic (`0x4CE6C0`) aparece DOS veces con
    #     el emisor en el medio. ⇒ **nuestra respuesta dispara el siguiente pedido**: el cliente
    #     aplica el eco, la interfaz reacciona y vuelve a mandar.
    #
    #   ★ Y ESTO YA NOS PASÓ, con la ropa. Está escrito en `h_37_ff1a` desde julio:
    #       *"el eco aplica el equip PERO el UI del clóset reacciona a cada eco reenviando FF1A
    #         -> feedback infinito"*
    #     La solución de allá es la de acá: **no ecoar dos veces lo mismo**.
    #
    #   ⇒ Dos frenos, y los dos cortan el bucle por el mismo lado — no volver a decirle que sí:
    #     1. si ya tiene puesto ese personaje, **no se ecoa** (se contesta ≠ 0, que el cliente
    #        ignora en silencio). Es lo que mata el bucle: el 2º pedido ya no cambia nada.
    #     2. y un enfriamiento por personaje, como el del `FF1A`, para el rato en que el estado
    #        todavía no se asentó.
    #   ⚠⚠ Y SE SACA LA HEURÍSTICA DE "RÁFAGA" que tenía acá. Estaba tratando de distinguir un clic
    #     del jugador de un clic del panel — y la medición mostró que **los dos son el mismo clic**:
    #     el bucle pasa por el manejador del clic. No había nada que distinguir.
    _ahora = time.time()
    _mismo = (int(_ch.get("char_id") or 0) == int(pj))
    _ult_pj, _ult_t = getattr(st, "pj_ultimo", (None, 0.0))
    if _mismo:
        _no(f"ya tiene puesto el {pj} -> no se ecoa (es lo que corta el bucle del eco)")
        return
    #   ⛔⛔ EL ENFRIAMIENTO ESTABA ATADO AL ID, Y POR ESO NO SERVÍA (2026-09-09).
    #     El botón del cliente **ya es un interruptor**: compara la ranura contra lo que tenés
    #     puesto y te manda **el otro id** (`0x4CE6DB`: si son distintos manda el clickeado, si son
    #     iguales manda `GetDefaultCharID`). O sea que en el ping-pong **nunca llega dos veces el
    #     mismo id** — llega alternado, `110275 ⇄ 130900`. Un dedup por id no se dispara jamás.
    #   ⇒ El enfriamiento va **por TIEMPO, sin mirar el id**: después de aplicar un cambio, se
    #     ignora cualquier otro durante `RAFAGA` segundos. Corta el ping-pong porque lo que se
    #     repite es el RITMO, no el número.
    #   ⚠ Y sigue siendo una heurística, dicho de frente: el costo es que dos clics de verdad
    #     seguidos y rápidos pierden el segundo. Es el mismo trato que ya aceptamos en el `FF1A`.
    if (_ahora - _ult_t) < GACHA_PERSONAJE_RAFAGA:
        _no(f"otro cambio hace {_ahora - _ult_t:.2f}s (enfriamiento por TIEMPO, no por id: "
            f"el cliente alterna el número, así que atarlo al id no servía)")
        return
    st.pj_ultimo = (int(pj), _ahora)
    _aplicar_personaje(st, pj)


def _aplicar_personaje(st, pj):
    """Aplica el cambio de personaje y avisa a la sala."""
    try:
        _usn = getattr(st, "usn", 0)
        _ch = db_get_char(_usn) or {}
        # ★ LA COMPROBACIÓN DE PROPIEDAD VIVE ACÁ, no en la recepción: el cliente manda el id que
        #   quiera, y el chequeo tiene que estar donde se APLICA el cambio, no donde se recibe.
        _permitidos = {gacha.personaje_base(_ch)} | set(gacha.personajes_de(_ch))
        if int(pj) not in _permitidos:
            st.send_ff55(0x19, bytes([1]) + struct.pack("<I", pj),
                         name=f"FF19 {pj} RECHAZADO (no es suyo)")
            log("LOBBY", f"  ⛔ FF19 {pj} de usn={_usn}: no es un personaje suyo "
                         f"(tiene {sorted(_permitidos)})")
            return
        _antes = int(_ch.get("char_id") or 0)
        _ch["char_id"] = int(pj)
        db_save_uno(_usn, _ch)
        _base = gacha.personaje_base(_ch)
        st.send_ff55(0x19, bytes([0]) + struct.pack("<I", pj),
                     name=f"FF19 personaje {pj} "
                          f"{'QUITADO (vuelve al base)' if pj == _base else 'EQUIPADO'}")
        log("LOBBY", f"  ★★★ PERSONAJE: usn={_usn} char_id {_antes} -> {pj}"
                     f"{' (es el BASE)' if pj == _base else ''}")
        refrescar_apariencia_en_sala(st, f" (personaje -> {pj})")
    except Exception as e:
        log("LOBBY", f"  ⚠ no pude aplicar el personaje {pj}: {e!r}")


def h_ff69_abrir_capsula(st, cmd, data):
    """`FF69 [capsula:u32]` — **"abrí esta cápsula y decime qué salió"**. (`0x69` = 105.)

    ⛔ NO EXISTÍA, y por eso el gacha no andaba. Reportado por anonimo03 el 2026-09-08:
      *"compré una gacha pero la animación de sorteo no ocurrió"*. En el log de esa compra se ve
      todo el hilo en tres segundos:

          19:46:28  FF50 BUY item=577 fam=capsule_gacha … EXITO      ← la compra sí andaba
          19:46:29  inner FF69 len=4 : 41 02 00 00                   ← 0x241 = 577, LA MISMA cápsula
          19:46:29  inner FF69 SIN handler                           ← ★ y acá se cortaba

      La animación no es un adorno que arranque solo: **espera la respuesta del server**. Sin
      contestar, el cliente se queda mirando la máquina para siempre.

    ⛔⛔⛔ Y LA PRIMERA VERSIÓN DE ESTO CONTESTABA EL PAQUETE EQUIVOCADO — 2026-09-08.
      Contestaba un `FF69` de 11 bytes armado con el handler `0x5D0E00`, porque la tabla RX dice
      que ése es el handler del `FF69`. **El server contestaba perfecto y no pasaba nada**: anonimo03
      lo probó con la cápsula 754 (100 % RCoin) y *"sólo me descuenta el rcoin"* — ni siquiera
      subía el saldo del premio, que es lo que partió el diagnóstico al medio.

      Lo que faltaba no era leer mejor ese handler: **era el paquete equivocado**. El 2013 trae
      adentro su propio texto de log, y ese texto tiene la respuesta:

          [CASH][Buy] GACHA result : r:%u cr:%u gachaid:%u, char:%u remain_cash:%u

      **Cinco campos, no cuatro.** Está en `0x5D9320`, que la tabla registra en el slot `0x21608`
      ⇒ `(0x21608 - 0x203E8) / 0x10` = **`0x122`**. El gacha es el **`FF122`**.

      ★ La lección, que ya está en la memoria del proyecto y volvió a cobrar: **saber en qué byte
        viaja un campo no dice qué paquete lo llena.** El `FF69` existe, tiene handler y hasta se
        parece (gate + ítem + saldo) — pero no es éste.

    ★★★ LA RESPUESTA: `FF122`, **19 bytes**, leídos de `0x5D9320` (siete `read` seguidos):

          @0   u8    RESULTADO — **0 = ÉXITO** (`005d93d8 test al,al / jne <error>`)
                     ⚠ Al revés que el `FF50`, donde 1 = éxito. Y coincide con el 2019.
          @1   u8    el `cr` del log. Sin identificar; viaja a la animación (`+0x4F9D`)
          @2   u32   `gachaid` = LA CÁPSULA que se abrió
          @6   u32   `char` = ★ EL PREMIO. Se resuelve con `0x50E200` contra la tabla de ítems y,
                     si `0x46C8B0` dice que es una prenda, entra al clóset con `0x48F5D0`
          @10  u32   sin loguear; viaja a la animación (`+0x4F98`)
          @14  u32   `remain_cash` = EL SALDO QUE QUEDA -> `0x485300`, la misma que usa el `FF50`
          @18  u8    la moneda. El handler la pre-carga en `0x43` = `'C'` **antes** de leerla, así
                     que ése es el valor por defecto y el que mandamos

      ★★ Y ACÁ ARRANCA LA ANIMACIÓN — `0x4D3970(resultado, cr, item, @10)` sobre `[0x9314BC]`:

          004d3978  test bl, bl                  ; si el resultado es 0…
          004d397c  call 0x40B800(0x70)          ;   …dispara el efecto 0x70
          004d3995  mov [esi+0x4f94], item
          004d39b5  mov dword [esi+0x2758], 2    ; ★★★ el estado de la máquina pasa a 2: GIRA

    ★ EL ORDEN DE LAS OPERACIONES, que es lo que evita el bug caro: **primero se cobra la cápsula
      y después se entrega el premio.** Si algo explota en el medio, el jugador pierde la cápsula;
      al revés, la duplicaría. Entre las dos, la que no se puede desarmar es la duplicación.
    """
    _usn = getattr(st, "usn", 0)
    if len(data) < 4:
        log("LOBBY", f"  ⚠ FF69 con {len(data)} byte(s), esperaba 4: {data.hex()}")
        return
    capsula = struct.unpack_from("<I", data, 0)[0]

    def _ff122(resultado, item, saldo, nota):
        """El `FF122` de 19 bytes. `resultado` 0 = éxito; cualquier otro = falló."""
        # ⚠ Los dos campos sin identificar (`cr` @1 y el `u32` @10) van en CERO. No se inventan: se
        #   guardan tal cual en la animación (`+0x4F9D` y `+0x4F98`) y no se comparan con nada, así
        #   que el 0 es el valor neutro. Si algún día se ve para qué sirven, se llenan acá.
        st.send_ff55(0x122, (bytes([resultado & 0xFF, 0])
                             + struct.pack("<I", capsula & 0xFFFFFFFF)
                             + struct.pack("<I", item & 0xFFFFFFFF)
                             + struct.pack("<I", 0)
                             + struct.pack("<I", saldo & 0xFFFFFFFF)
                             + bytes([0x43])),          # 'C' = el default del propio handler
                     name=f"FF122 GACHA {nota}")

    def _no(motivo):
        _ff122(1, 0, db_get_rcoin(_usn), f"cápsula {capsula} NO se abre ({motivo})")
        log("LOBBY", f"  ⛔ FF122 cápsula {capsula} de usn={_usn}: {motivo}")
    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★★ 0 · ¿ES SIQUIERA UN GACHA? — SI NO, ESTO NO ES "ABRÍ": ES "¿CUÁNTOS TENGO?"
    #
    #   ⛔⛔ EL BUG, medido el 2026-09-12: anonimo03 compró la **Esmeralda de la Amistad (1200091)** y
    #     **el cliente se murió en el mismo segundo**. `servidor.log`, 01:13:49, cuatro líneas:
    #         FF2A BUY item=1200091 fam=friendship_gem  result=0     ← la compra, bien
    #         RX  FF69 : db 4f 12 00                                 ← 0x124FDB = 1200091
    #         TX  FF122 "cápsula 1200091 NO se abre"                 ← ⛔ le contestamos GACHA
    #         (el cliente manda `reset`)
    #
    #   ★★★ CONTROL NATURAL, en la MISMA sesión y el MISMO jugador: compró dos **anillos de
    #     pareja** (30216 y 30562) y **no pasó nada** — porque para ésos el cliente ni pregunta.
    #     Tres compras, una sola respuesta de gacha, un solo muerto.
    #
    #   ★★ LA LECTURA CORRECTA: el `FF69` es **`CmdGetItemCount`** ("¿cuántos tengo de este
    #     ítem?"), no "abrí la cápsula" — lo confirma el nombre del cliente 2019 (`reg19b.json`)
    #     y lo confirmamos NOSOTROS, que ya lo mandamos así para las Monedas Gorila
    #     (`myrecord.py:452`). El cliente lo usa para las DOS cosas y distingue por el ítem.
    #   ⇒ Cuando NO es una máquina de gacha, la respuesta correcta es **el número**, no un
    #     resultado de sorteo. Contestar `FF122` ahí le manda a animar una máquina inexistente.
    #
    #   ⚠⚠ Y POR QUÉ ESTO **NO** TOCA EL GACHA: el camino de abajo —la máquina que sí existe,
    #     sortea y entrega— queda intacto. Esto es una puerta NUEVA delante, para el caso que
    #     **hoy ya está roto**. El gacha anda en prod desde el 2026-09-09 y sigue igual.
    #     Lo preguntó anonimo03 antes de dejarme tocar, y la respuesta salió de leer las dos ramas.
    # ══════════════════════════════════════════════════════════════════════════════════════════
    if not gacha.es_maquina(capsula):
        # ⛔⛔ ACÁ SE CONTABAN **ENTRADAS DEL INVENTARIO**, NO CARGAS — 2026-09-15, lo vio anonimo03:
        #   compró 5 megáfonos, el ícono no mostraba la cantidad, y el log decía *"tenés 1"*.
        #   Un consumible con cargas ocupa **UNA sola entrada** con `cant=5`, así que esta cuenta
        #   siempre daba 1 y el cliente dibujaba el ítem sin número.
        #   ★ La cuenta buena ya existía: `inv_cant()` devuelve `{id: cargas}` y se escribió
        #     justo para esto ("consumibles con cargas: impulsores, etc."). Van dos formas de
        #     contar lo mismo en el repo; ésta se queda con la que sabe de cargas.
        _ch69 = db_get_char(_usn) or {}
        _cargas = inv_cant(_ch69).get(capsula, 0)
        _cuantos = _cargas or sum(1 for _i in inv_ids(_ch69) if _i == capsula)
        st.send_ff55(0x69, (bytes([1]) + struct.pack("<I", capsula & 0xFFFFFFFF)
                            + struct.pack("<H", _cuantos & 0xFFFF)
                            + struct.pack("<I", db_get_rcoin(_usn) & 0xFFFFFFFF)),
                     name=f"FF69 CmdGetItemCount: tenés {_cuantos} del item {capsula} "
                          f"(NO es gacha — antes le contestábamos FF122 y lo MATÁBAMOS)")
        log("LOBBY", f"  ★★ FF69 '¿cuántos tengo?' del item {capsula} (usn={_usn}) -> {_cuantos}. "
                     f"No es máquina de gacha: se contesta el CONTEO, no un sorteo")
        return

    # 1 · ¿es una máquina que existe, y sabemos entregar TODOS sus premios?
    _ok, _motivo = gacha.se_puede_abrir(capsula)
    if not _ok:
        _no(_motivo)
        # ⚠ Un resultado ≠ 0 no saca ningún cartel (el handler se va en silencio), así que el aviso
        #   va por chat. Sin esto el jugador ve exactamente lo mismo que veía con el bug.
        aviso_sistema(st, f"Esta cápsula todavía no se puede abrir: {_motivo}.")
        return
    # 2 · ¿LA TIENE? Es lo único que impide abrir cápsulas que nunca se compraron: el cliente
    #     manda el id que quiera, y confiar en que "el botón no está" no es un control.
    if capsula not in set(inv_ids(db_get_char(_usn) or {})):
        _no("no la tiene en el inventario")
        aviso_sistema(st, "No tenés esa cápsula.")
        return
    # ★★★ 2·bis — ¿LE QUEDA ALGO POR GANAR EN ESTA MÁQUINA? Va **ANTES DE COBRAR**, a propósito.
    #   Pedido de anonimo03 el 2026-09-09: *"que no toquen repetidos"*. Si se sacan los repetidos del
    #   bombo, puede quedar vacío — y entonces cobrar la cápsula sería cobrarle por nada.
    #   ⚠ El orden es: comprobar (acá) -> cobrar (3) -> entregar (5). El chequeo se adelanta, pero
    #     la regla de siempre no se toca: **cobrar antes de entregar**, nunca al revés.
    #   ⚠ Un resultado ≠ 0 no saca cartel: el aviso va por chat, si no parece que el botón no anda.
    _pool = gacha.pool_para(capsula, inv_ids(db_get_char(_usn) or {}))
    if not _pool:
        _no("ya tiene TODOS los premios de esta máquina")
        aviso_sistema(st, "Ya tenés todos los personajes de esta cápsula. No te la gasté.")
        return
    # 3 · SE COBRA PRIMERO (ver la nota del orden, arriba)
    if not db_del_inventory(_usn, capsula, 1):
        _no("no se pudo consumir del inventario")
        return
    # 4 · el sorteo, sobre los que TODAVÍA LE SIRVEN (ya calculados arriba, antes de cobrar)
    # ⚠ Acá había un filtro POR SEXO y lo saqué el 2026-09-09: era una invención mía que convertía
    #   máquinas en expendedoras (la 577 tiene un solo premio de mujer, y una jugadora sacaba
    #   siempre el mismo — 29 cápsulas quemadas en prod). El juego elegía el sexo por la MÁQUINA,
    #   avisando en su nombre. Todo el porqué está en `gacha.sortear_para`.
    premio = gacha.sortear(capsula, _pool)
    if premio is None:                       # no debería: el paso 1 ya validó la máquina
        _no("la máquina no tiene premios")
        return
    # 5 · la entrega, según lo que sea el premio
    saldo = db_get_rcoin(_usn)
    _clase, _valor = premio["clase"], int(premio["valor"] or 0)
    _cant = 1
    if _clase in ("MONEY", "SEED"):
        # ★ SEED se paga en RCOIN: decisión de anonimo03 ("toda nuestra tienda vale rcoin"). Está
        #   explicada en `gacha.py`; acá sólo se aplica.
        saldo = db_add_rcoin(_usn, _valor)
        _entrega = f"{_valor} RCoin" + (" (era SEED)" if _clase == "SEED" else "")
    elif _clase == "EXP":
        db_add_exp(_usn, _valor)
        _entrega = f"{_valor} de experiencia"
    else:
        # Un ÍTEM. Va permanente (exp=0): los premios del gacha no traen período en la tabla, y el
        # catálogo de la cápsula tampoco se lo pasa al premio.
        _cant = _valor if _valor > 0 else 1        # los packs traen su cantidad en `Value`
        db_add_inventory(_usn, premio["item"], 0, cant=(_valor if _valor > 0 else 0))
        _entrega = f"el ítem {premio['item']}" + (f" x{_valor}" if _valor > 0 else "")
    # 6 · la respuesta que dispara la animación
    _ff122(0, premio["item"], saldo,
           f"cápsula {capsula} -> {premio['item']} ({premio['nombre']!r}) x{_cant} saldo={saldo}")
    log("LOBBY", f"  ★★★ GACHA: usn={_usn} abrió la cápsula {capsula} y sacó "
                 f"{premio['item']} {premio['nombre']!r} ({_entrega}) "
                 f"[clase={_clase or 'ITEM'} boletos={premio['boletos'] or 'parejo'}] "
                 f"-> saldo={saldo}")
    # 7 · y el refresco del clóset, igual que hace la compra: sin esto la cápsula sigue dibujada
    #     en el inventario y el premio no aparece hasta reabrir la pantalla.
    st.buy_needs_refresh = True
    enviar_myrecord(st, "MyRecord refresh (post-gacha FF69)", con_personaje=False)


def h_37_ff1a(st, cmd, data):
    # rama original:  cmd == 26
    # Request medido: [u8 flag=01(equipar)][u32 item_id]  (ej '01 a8 ef 9b 00'). El cliente lo manda
    #   solo tras comprar (auto-equipar) y REINTENTA si no le respondemos (se veia el spam de FF1A).
    # Response (mapa de lecturas 0x5E2740): [u8 b0=0 (entra al path)][u8 result=1][u32 item_id].
    #   result=1 -> 0x48f040 EQUIPA la prenda al slot del char + broadcast (el "sonidito"). b0!=0 -> otro path.
    flag = data[0] if data else 1
    item_id = struct.unpack_from("<I", data, 1)[0] if len(data) >= 5 else 0
    # ★ DEDUP anti-bucle: el eco aplica el equip (0x48f040) PERO el UI del closet reacciona a cada eco
    #   reenviando FF1A -> feedback infinito (spam FF3D). Echo SOLO 1 vez por item (cooldown 2s).
    # ⚠ 2026-07-31: la clave del dedup incluye el FLAG. Antes era sólo el item_id, así que
    #   ACTIVAR y DESACTIVAR el mismo ítem seguido (< 2s) hacía que el 2º FF1A se descartara sin
    #   respuesta => "se puede activar pero no desactivar" (reportado con el Auto Impulsor).
    #   El bucle que el dedup corta es eco→UI→eco del MISMO flag, así que distinguirlos no lo reabre.
    now = time.time()
    if (item_id, flag) == getattr(st, "last_equip_item", None) and now - getattr(st, "last_equip_time", 0) < 2.0:
        log("LOBBY", f"  ★ FF1A EQUIP item={item_id} -> IGNORADO (dedup, corta el bucle)")
    elif flag == 0 and now - (getattr(st, "quitar_empujado", None) or {}).get(item_id, -99) < 3.0:
        log("LOBBY", f"  ★ FF1A QUITAR item={item_id} -> IGNORADO (rebote del «quitar» que le mandamos tras quitar todo)")
    elif flag == 2:
        # ★ 11-oct: `[02][0]` = «QUITAR TODO» (`0x5E1FB0`: result 2 vacía las 11 partes y redibuja). Lo manda
        #   «Restaurar» (`0x4CA935`) y detrás viene el `FF7F` con el set básico. Antes se contestaba result=1 = poner
        #   el ítem 0: no hacía nada y no se guardaba (anonimo03: «las alas no se desequiparon»).
        st.last_equip_item = (item_id, flag); st.last_equip_time = now
        st.send_ff55(0x1A, bytes([0x00, 0x02]) + struct.pack("<I", item_id & 0xFFFFFFFF), name="FF1A QUITAR TODO result=2")
        from .catalogo import categoria_worn, db_quitar_todo                 # noqa: PLC0415
        _sac = db_quitar_todo(getattr(st, "usn", 0))
        # ★ 4.ª vuelta: las de la categoría 10 que se ven (alas, caras, pieles) no las apaga el result 2: a cada una su
        #   «quitar» (result 0 -> `0x48E830(ítem, 0)` + redibujo). Se anotan para no contestar si el armario rebota.
        _c10 = [x for x in _sac if categoria_worn(x) == 10]
        _emp = getattr(st, "quitar_empujado", None)
        if _emp is None:
            _emp = st.quitar_empujado = {}
        for _x in _c10:
            st.send_ff55(0x1A, bytes([0x00, 0x00]) + struct.pack("<I", _x & 0xFFFFFFFF), name=f"FF1A QUITAR {_x} (cat 10, tras quitar todo)")
            _emp[_x] = now
        log("LOBBY", f"  ★ FF1A QUITAR TODO usn={getattr(st, 'usn', 0)} -> resp [00 02 0], sacó {_sac}"
                     + (f" · cat 10 apagadas una por una: {_c10}" if _c10 else ""))
        if _sac:
            refrescar_ropa(st, "FF1A quitar todo")
    else:
        st.last_equip_item = (item_id, flag); st.last_equip_time = now
        # ★★ 2026-07-31: el 2º byte (`result`) SE ECOA, no va clavado en 1. Antes mandábamos
        #   siempre 1 = "equipado", así que al pedir APAGAR un ítem el cliente lo volvía a
        #   encender (síntoma: el Auto Impulsor se activaba pero no se desactivaba).
        #   Confirmado en el disasm de `0x5E2740`, no adivinado — las ramas por `result` son:
        #     ==2 -> 0x5E27D1 (otro camino)
        #     ==1 -> 0x5E282D:  0x48F040(player, item, **1**)  = EQUIPAR
        #     ==0 -> 0x5E2966:  0x48F040(player, item, **0**)  = QUITAR   ← la que faltaba
        #     (dentro de cada una, `0x50E6E0(item)` da la categoría; 0xA toma un sub-camino)
        resp = bytes([0x00, 0x01 if flag else 0x00]) + struct.pack("<I", item_id & 0xFFFFFFFF)
        st.send_ff55(0x1A, resp,
                     name=f"FF1A {'EQUIP' if flag else 'QUITAR'} item={item_id} result={1 if flag else 0}")
        # ★★ Un GLOBO o un CRAYÓN de chat (25-sep): no es ropa — se guarda aparte y sale en el FF08
        #   (`catalogo.estilo_chat_de`). Antes caían en `db_equip`, que los rechazaba por ser de la
        #   familia «megaphone», y la tilde de Mi Casa no quedaba guardada.
        #   El LÁPIZ DEL APODO sí sigue al repintado de la sala de abajo: su color viaja en el
        #   ocupante (`FF0C cola[13]` / `FF15 #14`) y los demás lo tienen que ver en vivo.
        #   ★ 23-oct: el CRAYÓN DE CÍRCULO igual (el nombre del círculo viaja en el ocupante, con su marca).
        from .catalogo import LAPICES_APODO, LAPICES_CIRCULO, tildar_estilo_chat   # noqa: PLC0415
        _estilo = tildar_estilo_chat(getattr(st, "usn", 0), item_id, bool(flag))
        if _estilo is not None and item_id not in LAPICES_APODO and item_id not in LAPICES_CIRCULO:
            return
        # ★ Fase A: persistir el equip -> queda puesto al re-loguear (slot por familia; soporta N slots)
        if _estilo is None:
            _antes1a = list((db_get_char(getattr(st, "usn", 0)) or {}).get("parts", []))
            db_equip(getattr(st, "usn", 0), item_id, equip=bool(flag))
            # ★ 12-oct (anonimo03: «2 alas»): un ítem de la categoría 10 (alas, auras, caras, pieles) se prende con
            #   `0x48E830(ítem, 1)` y el cliente NO apaga el que tenía de la misma familia: el server lo reemplaza en
            #   la base pero se seguían dibujando los dos (y el set siguiente se guardaba con las dos). Al reemplazado,
            #   su «quitar» (result 0), anotado para no contestar el rebote del armario.
            if flag == 1:
                from .catalogo import categoria_worn                                 # noqa: PLC0415
                _desp1a = set((db_get_char(getattr(st, "usn", 0)) or {}).get("parts", []))
                _reempl = [x for x in _antes1a if x not in _desp1a and x != item_id and categoria_worn(x) == 10]
                _emp1a = getattr(st, "quitar_empujado", None)
                if _emp1a is None:
                    _emp1a = st.quitar_empujado = {}
                for _x in _reempl:
                    st.send_ff55(0x1A, bytes([0x00, 0x00]) + struct.pack("<I", _x & 0xFFFFFFFF),
                                 name=f"FF1A QUITAR {_x} (reemplazado por {item_id})")
                    _emp1a[_x] = now
                if _reempl:
                    log("LOBBY", f"  ★ FF1A {item_id} reemplaza a {_reempl} (cat. 10): se le apagan al cliente")
        fam = shop_catalog.family(item_id)
        log("LOBBY", f"  ★ FF1A {'EQUIP' if flag else 'QUITAR'} item={item_id} fam={fam} "
                     f"flag={flag} -> resp [00 {1 if flag else 0:02x} item] + persistido")
        # ★★★★ 2026-09-01 — LO PUESTO NO SE REFRESCABA EN LA SALA.
        #   Medido en el log de las 19:53: el jugador se cambió la ropa DENTRO de la sala
        #   (FF1A a las 19:53:15/16/17) y **no salió ni un FF0C detrás** ⇒ los avatares de la
        #   sala se quedaban con la ropa del momento en que se armó el userlist. El eco del
        #   FF1A sólo repinta al que se cambió, no a los demás.
        #   Se re-manda el USERLIST a TODA la sala (es lo que redibuja los muñecos).
        # ★★ En la SALA DE CONVERSACIÓN (24-sep): los gestos EQUIPAN su ítem justo antes de decir la
        #   palabra (báculo -> «baculo melodia», anillo -> «/besar»); sin repintar, los demás no lo
        #   tenían y el gesto lo veía sólo el que lo hacía. Mismo FF0C + FF15, sin FF0E.
        # ★ 23-oct · el CRAYÓN DE CÍRCULO: el nombre del círculo sólo lo lee el cliente al CREAR al ocupante (el FF0C a
        #   uno que ya está no lo cambia, y el FF15 no lo trae) ⇒ sacarlo y volver a ponerlo (FF0E + FF0C + FF15), el
        #   repintado del cambio de personaje. Sin esto se veía recién al salir y volver a entrar.
        from .catalogo import LAPICES_CIRCULO as _LC                          # noqa: PLC0415
        if item_id in _LC and getattr(st, "room_id", None) is not None:
            refrescar_apariencia_en_sala(st, f" (crayón de círculo {item_id})")
        else:
            refrescar_ropa(st, f"FF1A item {item_id}")

def refrescar_ropa(st, que):
    """Después de cambiarse la ropa (`FF1A` una prenda, `FF7F` varias): que los DEMÁS lo vean, en la sala
    de juego (FF0C + FF15 + equipos) o en la de conversación. El eco al que se cambió va aparte.
    (Era el final de `h_37_ff1a`; 11-oct pasó a función para el `FF7F`.)"""
    if (REFRESCAR_ROPA_EN_SALA and getattr(st, "room_id", None) is None
            and getattr(st, "lugar_clave", None) is not None):
        from .charla import refrescar_apariencia
        refrescar_apariencia(st, f" ({que})", recrear=False)
    if REFRESCAR_ROPA_EN_SALA and getattr(st, "room_id", None) is not None:
        # ★★★★ 2026-09-01 — RE-MANDAR EL FF0C SOLO NO ALCANZA.
        #   Reportado en pantalla: con el FF0C repetido, cambiarse los ojos o las alas
        #   DENTRO de la sala no actualizaba el muñeco. El cliente arma los avatares una
        #   vez al poblar la sala; un FF0C repetido le refresca el PANEL de usuarios pero
        #   no reconstruye el modelo — y las alas y la cara no viajan como prendas, van
        #   como índices en la cola del FF0C, así que el eco del FF1A tampoco las mueve.
        #   ⇒ hay que SACAR al jugador y volver a ponerlo: `FF0E [len][nick]` (formato
        #     tomado del wire real: 'YETIIIIIIIII', 'Kaimanzote', 'jugador29', 'jugador25')
        #     y detrás el FF0C del ocupante, que lo re-crea ya vestido.
        #   ⚠ NO hay muestra de cómo lo resuelve el REFERENTE: en toda la captura no
        #     entró ni un FF1A, así que esto es una vía DEDUCIDA, no copiada. Si el
        #     re-spawn diera problemas (parpadeo, perder el "soy yo"), apagar
        #     `REFRESCO_ROPA_RESPAWN` y queda sólo el FF0C, que al menos actualiza el panel.
        #
        # ★★★★★ 2026-09-06 — SE BUSCÓ EL PAQUETE "DE VERDAD" Y **NO EXISTE EN ESTE BUILD**.
        #   El usuario preguntó lo correcto: *"no debería haber un repintado, sino que el
        #   paquete que hace el sync de ropa no cambie el color"*. Se fue a buscarlo al 2019
        #   desempacado (el oráculo, que conserva los nombres) y se encontró:
        #
        #     · su tabla de registro de handlers, armada en runtime en `0xCB9A60`+, con la
        #       forma `push <id>; push <fn>; push <nombre>` ⇒ los IDs salen leídos, no
        #       deducidos:
        #           `CNetwork::CmdEditAvatar`     = **0x1A**  (nuestro FF1A)
        #           `CNetwork::CmdEditAvatarMult` = **0x7F**  (registro en `0xCBAD65`+)
        #     · y el 2013 TIENE los dos: `FF1A` en `0x5E1FB0` y `FF7F` en `0x5E22B0`
        #       (pegados uno detrás del otro, como corresponde a dos comandos hermanos).
        #
        #   ⛔ PERO LOS DOS SE APLICAN A **UNO MISMO**, y eso es lo que cierra el caso:
        #       0x5E1FB0 / 0x5E22B0:
        #           eax = [0x9314E0]
        #           esi = entrada nº word[eax+0x8C] del array [eax+0xC8]   ← LA FICHA
        #           ... recién ACÁ empieza a leer bytes del paquete
        #     La ficha sobre la que van a escribir **se elige ANTES de leer un solo byte del
        #     paquete** ⇒ el paquete no tiene forma de decir "esto es de otro jugador".
        #   Y el cuerpo lo confirma: el `FF1A` del 2013 lee **`[estado:1][tipo:1][item:u32]`**
        #     y nada más. El del 2019 lee **dos bytes de más** —un slot y un flag— que en el
        #     2013 NO se leen: la capacidad de apuntarle a otro jugador es un AGREGADO
        #     POSTERIOR. El `FF7F` es el mismo cuento en plural: `[N:1]` y después N ítems de
        #     4 B, todos escritos en `[esi + parte*4 + 4]`, o sea otra vez en la ficha propia.
        #
        #   ⇒ En ESTE build no hay ningún paquete que diga *"el jugador X se cambió"*. El
        #     FF0E+FF0C sigue siendo la única vía, y por eso hace falta el repintado de
        #     equipo de abajo. No es un parche sobre un invento: es lo único que hay.
        #   ⚠⚠ Y OJO CON LA TENTACIÓN DE DIFUNDIR EL `FF7F`: como se aplica a uno mismo,
        #     mandárselo a la sala le pondría **esa ropa a todos los que lo reciban**.
        _dest1a = [CONEXIONES.get(u) for u in mesa_de(st.room_id).values()]
        _dest1a = [c for c in _dest1a if c is not None and not getattr(c, "cerrado", False)]
        _nick1a = (db_get_char(getattr(st, "usn", 0)) or {}).get("nick", "")
        # Sólo se re-manda al que SE CAMBIÓ, no la lista entera: tras el FF0E el
        # cliente lo borró, y re-mandar a todos podría duplicar a los que no se movieron.
        _slot1a = getattr(st, "room_slot", None)
        if _slot1a is None:
            _slot1a = HOST_SLOT
        _occ1a = _ocupante_de(getattr(st, "usn", 0), _slot1a)
        # ★ El `rel12` = el EQUIPO. Sin esto, cambiarse de ropa te BORRABA del equipo en el
        #   padrón del cliente (este FF0C re-escribe la entrada entera del ocupante).
        _occ1a["equipo"] = equipo_para_ff0c(st, _slot1a)
        for _c in (_dest1a or [st]):
            try:
                # 1) FF0C: deja el registro del ocupante con la ropa/alas/ojos nuevos
                _c.send_ff55(0x0C, build_ff0c_2013_real(_occ1a, 1),
                             name=f"FF0C apariencia nueva de {_nick1a!r}")
                # 2) FF15: fuerza el RELOAD del mesh (el FF0C solo no re-renderiza)
                if REFRESCO_ROPA_FF15:
                    # ★★ Ver `salas.ff15_de`: pareja, equipo, capitán y joyas en un solo lugar.
                    _c.send_ff55(0x15, ff15_de(_occ1a, getattr(st, "room_id", None)),
                                 name=f"FF15 reload de {_nick1a!r} (slot {_slot1a})")
                elif REFRESCO_ROPA_RESPAWN and _nick1a:
                    _nb = _nick1a.encode("cp1252", "replace")[:0xFF]
                    _c.send_ff55(0x0E, bytes([len(_nb)]) + _nb,
                                 name=f"FF0E sacar a {_nick1a!r} (respawn, vía deducida)")
                # 3) ★★★★★ Y EL EQUIPO OTRA VEZ, AL PADRÓN. 2026-09-06.
                #   Reportado en pantalla: *"en modo equipo, al cambiarse de ropa el slot del
                #   jugador cambia de color como si estuviera en modo solo"*.
                #   El equipo vive en DOS lados del cliente y acá llenábamos UNO:
                #     · el `rel12` del `FF0C` (arriba, `equipo_para_ff0c`) — el asiento;
                #     · `sRoomUser+0x4A`, el PADRÓN, al que sólo se llega con el `FF37` que
                #       manda `enviar_equipos`.
                #   Y este `FF0C` **re-escribe la entrada entera del ocupante**, así que sin
                #   repintar detrás el asiento queda dibujado con la paleta de solo.
                #   ⇒ Se hace igual que en el camino de ENTRAR a la sala (`lobby_salas.py`,
                #     el `enviar_equipos` que va detrás del FF0C del recién llegado).
                #   ⚠ Es el QUINTO caso de esta familia: ver la memoria
                #     `estado-de-la-conexion-vs-la-sala` y la nota de `equipo_para_ff0c`
                #     (*"los dos hacen falta y no son intercambiables"*).
                #   ★ En solo no hace nada: `enviar_equipos` sale por `sala_por_equipos()`.
                if getattr(st, "room_id", None) is not None:
                    enviar_equipos(_c, st.room_id)
            except Exception as e:
                log("LOBBY", f"  ⚠ no pude refrescar el userlist de "
                             f"usn={getattr(_c,'usn','?')}: {e!r}")
        log("LOBBY", f"  ★★ ropa cambiada en sala {st.room_id} -> "
                     f"{'FF0E + ' if REFRESCO_ROPA_RESPAWN else ''}FF0C a "
                     f"{len(_dest1a or [st])} jugador(es)")


def h_ff7f_vestir_varios(st, cmd, data):
    """`FF7F` = `CmdEditAvatarMult` (nombre del 2019): ponerse VARIAS prendas de una. C→S y S→C `[u8 n][n × u32]`.

    ★ 11-oct, anonimo03: «Restaurar» del armario no hacía nada (caía en «SIN handler»). Lo mandan:
      · «Restaurar» (`0x4CA97E`): el SET BÁSICO, las prendas de la creación (`0x48E150` junta `[player+0xD8]`);
      · la creación del personaje (`0x57FAE4`), con las 4 que eligió;
      · al sacarse un personaje del gacha (`0x48E244`, detrás del `FF19`): la ropa de antes.
    El RX del cliente (`0x5E22B0`) se aplica A UNO MISMO (la ficha se elige antes de leer el paquete): pone cada
    prenda en su parte (`0x50E0B0` = la categoría) y redibuja ⇒ el eco va SÓLO al que lo pidió; a los demás, el
    repintado de siempre (`refrescar_ropa`). ⛔ Difundir el FF7F le pondría esa ropa a todos.
    Se ecoa sólo lo que se aceptó (`catalogo.db_equip_varios`: lo que posee, lo puesto y el set de la creación)."""
    from .catalogo import db_equip_varios                                   # noqa: PLC0415
    n = data[0] if data else 0
    if len(data) < 1 + 4 * n:
        log("LOBBY", f"  ⚠ FF7F que no cierra (n={n}, {len(data)} B): {hx(data)}")
        return
    items = [struct.unpack_from("<I", data, 1 + 4 * i)[0] for i in range(n)]
    puestas, rechazadas = db_equip_varios(getattr(st, "usn", 0), items)
    st.send_ff55(0x7F, bytes([len(puestas)]) + b"".join(struct.pack("<I", x) for x in puestas),
                 name=f"FF7F vestir varios {puestas}")
    log("LOBBY", f"  ★ FF7F vestir varios usn={getattr(st, 'usn', 0)}: pidió {items} -> puestas {puestas}"
                 + (f" · ⛔ rechazadas {rechazadas} (no las tiene)" if rechazadas else ""))
    if puestas:
        refrescar_ropa(st, f"FF7F {len(puestas)} prendas")


def h_42_ff51(st, cmd, data):
    # rama original:  cmd in (81, 175, 311)
    #   refresco SOLO si hubo una compra reciente (si no, inundaríamos con MyRecords de 1950B). Un único
    #   refresco por compra -> el panel de inventario se re-dibuja en vivo con lo recién comprado.
    if getattr(st, "buy_needs_refresh", False):
        st.buy_needs_refresh = False
        enviar_myrecord(st, f"MyRecord refresh (post-compra, gatillado por FF{cmd:02X})", con_personaje=False)
        log("LOBBY", f"  ↻ FF{cmd:02X} -> MyRecord (refresco de panel, 1 vez por compra)")
    # ★ 2026-09-01: el REFERENTE ADEMÁS contesta estos polls (medido): FF51 -> 5 ceros,
    #   FF137 -> 2 ceros. El FFAF ya se contesta en otro lado, no se toca acá.
    # ★★ 29-sep: el FF137 son las PREFERIDAS del jugador (`[u16 n][u16 canción]×n`, `0x5E19F0`), no un
    #   ack: los «2 ceros» del referente eran una lista VACÍA, y por eso se perdían. Ver `picker.py`.
    if RESPONDER_COMO_EL_REAL and cmd == 0x51:
        st.send_ff55(cmd, bytes(5), name=f"FF{cmd:02X} ack (copiado del REFERENTE)")
    if RESPONDER_COMO_EL_REAL and cmd == 0x137:
        from .picker import respuesta_ff137
        _pr = respuesta_ff137(int(getattr(st, "usn", 0) or 0))
        st.send_ff55(cmd, _pr, name=f"FF137 preferidas ({struct.unpack_from('<H', _pr)[0]})")
    # ★★★ EL FF137 TAMBIÉN MARCA "EL LOBBY YA ESTÁ ARMADO" — 2026-09-12.
    #   ⛔ Al principio até esa marca SÓLO al `FF1D`, porque en tres aterrizajes medidos era el
    #     último paquete de la secuencia. **A la primera prueba real dejó de serlo**: el cliente
    #     terminó con `FF137` + `FF13B` y el `FF1D` no llegó ⇒ el `FF41` quedó guardado para
    #     siempre y «Jugar Juntos» dejó de funcionar del todo.
    #   ⇒ La lección: **la cola de la secuencia del cliente VARÍA**, y colgar algo de UN paquete
    #     puntual es frágil. El `FF137` aparece en las dos secuencias medidas y siempre cerca del
    #     final, así que marcan LOS DOS y gana el primero que llegue. Ver `FF41_ESPERA_LOBBY`.
    if cmd == 0x137 and not getattr(st, "lobby_asentado", False):
        st.lobby_asentado = True
        from .lobby_salas import despachar_ff41_pendiente
        despachar_ff41_pendiente(st, motivo="llegó el FF137")



# ─────────────────── ★★★★★ EL CANJE DE MONEDAS GORILA (FF119) — 2026-09-10 ───────────────────
def h_ff119_canje_gorila(st, cmd, data):
    """`FF119` = `CNetwork::CmdExchangeGroupCoin` — el botón «Intercambio» del diálogo de monedas.

    ★★★ CÓMO SE CERRÓ. El nombre lo dio el cliente 2019 (`cmds2019.txt`) y el string dentro del
      propio handler del 2013 lo confirma: **`[GorillaCoin] Change : %u - %u = %u`** (`0x886B84`).
      ⛔ El candidato viejo `FF12A` de `MONEDA_GORILA.md` §3 estaba MAL: salía de "el cliente lo
        manda 3 veces y nadie contesta", que no prueba nada.

    ★ LO QUE MANDA EL CLIENTE (12 B, medido en vivo con los dos botones):
    ```
        botón de 70   1c 02 00 00 | 64 28 09 00 | 46 00 00 00
        botón de 200  1c 02 00 00 | 72 28 09 00 | c8 00 00 00
                      └ moneda 540  └ premio      └ precio
    ```
      `600164` = «Gorila Verde» (70) · `600178` = «Gorila Rosado» (200), los dos en `shop_lt.txt`.
      ⇒ **El cliente nos dice qué quiere y cuánto cuesta.** Nosotros validamos y confirmamos.

    ★ LO QUE ESPERA DE VUELTA (17 B), leído del handler `0x5E1A60` — orden de las 5 lecturas:
    ```
        [status:u8][premio:u32][end_time:u32][moneda:u32][precio:u32]
    ```
      · `status` tiene que ser **0** (`0x5E1AC2`), con otro se va por la rama de error.
      · el `premio` es el que pasa por `FindItem` (`0x511420`) — y acá **sí** chequea NULL
        (`0x5E1B5E`), pero se valida igual contra el catálogo antes de mandarlo.
      · el `end_time` es la **fecha empaquetada** de vencimiento; se arma con el mismo
        `_exp_to_wire` que usa la tienda. El diálogo dice «30 Días» ⇒ período **P30**.
      · con `moneda` + `precio` el cliente hace **él solo** `nuevo = actual − precio`
        (`0x5E1ADD`) y lo asigna con `SetInventory` (`0x48F5E0`). Nosotros no le decimos el saldo.

    ⚠ EL ORDEN IMPORTA: primero la respuesta, y **después** el `FF69` con el saldo ya descontado.
      Al revés, el cliente restaría dos veces. El `FF69` va igual porque es idempotente y deja el
      número en lo que dice la base, pase lo que pase.
    """
    if len(data) < 12:
        log("LOBBY", f"  ⚠ FF119 corto ({len(data)}B): {hx(data)} -> ignorado")
        return
    _moneda, _premio, _precio = struct.unpack("<III", data[:12])
    _usn = getattr(st, "usn", 0)
    _ch = db_get_char(_usn) or {}
    _saldo = int(_ch.get("monedas_gorila") or 0)

    def _no(motivo, status=1):
        # ⚠ Cualquier status != 0 lo manda por la rama de error, que es lo que queremos: el
        #   cliente NO descuenta nada. El cuerpo igual va completo para no dejarlo a medio leer.
        log("LOBBY", f"  ⚠ FF119 RECHAZADO ({motivo}): usn={_usn} premio={_premio} "
                     f"precio={_precio} saldo={_saldo}")
        st.send_ff55(0x119, bytes([status & 0xFF])
                     + struct.pack("<IIII", _premio, 0, _moneda, _precio),
                     name=f"FF119 canje RECHAZADO ({motivo})")

    if _moneda != MONEDA_GORILA_ITEM:
        return _no(f"la moneda no es la {MONEDA_GORILA_ITEM}")
    if _precio <= 0 or _precio > 0xFFFF:
        return _no("precio fuera de rango")
    if _saldo < _precio:
        return _no("no le alcanza")
    # ⛔⛔ EL PREMIO TIENE QUE EXISTIR EN EL CATÁLOGO. Acá este handler chequea NULL, pero la regla
    #   del proyecto vale igual: un itemId inventado mata al cliente en otros caminos (`0x57C038`
    #   usa FindItem sin chequear). Se valida SIEMPRE antes de mandar un ítem.
    #   ⚠ Con `exists()`, no con `_premio in shop_catalog.CATALOG`: el dict arranca VACÍO y se
    #     llena solo (`_ensure`). Mirarlo directo daba "no existe" para TODO y rechazaba el canje
    #     bueno — lo cazó la prueba.
    if not shop_catalog.exists(_premio):
        return _no(f"el premio {_premio} no está en el shop_lt")

    _exp = compute_expiry(2)                       # P30 = 30 días, lo que dice el diálogo
    _ch["monedas_gorila"] = _saldo - _precio
    db_save_uno(_usn, _ch)
    db_add_inventory(_usn, _premio, _exp)
    st.send_ff55(0x119, bytes([0])
                 + struct.pack("<IIII", _premio, _exp_to_wire(_exp), _moneda, _precio),
                 name=f"FF119 canje OK: {_premio} por {_precio} monedas (30 días)")
    # ★ Y el saldo real detrás, para que la pantalla no dependa de la resta del cliente.
    enviar_ff69_moneda_gorila(st)
    log("LOBBY", f"  ★★★ CANJE DE MONEDA GORILA: usn={_usn} entregó {_precio} y se llevó "
                 f"{_premio} ({(shop_catalog.get(_premio) or {}).get('name', '?')}) "
                 f"por 30 días. Saldo {_saldo} -> {_saldo - _precio}")
