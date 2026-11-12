# -*- coding: utf-8 -*-
"""catalogo — tienda y cosméticos: shop_lt, wing.txt, face.txt y la cota del worn

Cortado de `server_login2013.py`. El código es el MISMO, movido tal cual.
"""
import os
import re
from . import shop_catalog

from .ajustes import (
    FAMILIAS_CON_CARGAS,
    ITEMS_CON_CARGAS,
    CATEGORIAS_WORN,
    WIRE_ID_CON_PERIODO,
    WIRE_ID_FAMILIAS,
    _MULTISLOT_FAMILIES,
)
from .registro import (
    log,
)
from .basedatos import (
    db_get_char,
    db_load,
    db_save,
    db_save_uno,
    inv_ids,
)

# El módulo se lee con rutas relativas a la RAÍZ del proyecto, no a
# `servidor/`. Viene de cuando todo era un archivo solo; sacarlo rompe la
# lectura de las tablas del cliente (wing.txt / face.txt).
__file__ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server_login2013.py")   # rutas relativas como en el original

def real_item_id(raw_item):
    """El id de COMPRA = Index del catálogo con el dígito de MILES (10^3) usado como código de período.
    El Index real lo tiene en 0. Se recupera poniendo SOLO ese dígito en 0 (NO cortar más: el prefijo del
    Index se conserva). Validado vs shop_lt.txt: 10329545->10320545 (Camiseta Bruja Rosa), 10429373->10420373
    (Falda Bruja Rosa), 10522236->10520236 (Pantuflas R2Star), 529644->520644, 10229303->10220303.
    Sin esto el validador 0x511d80 lo RECHAZA (existe=False) -> no entra al inventario/no renderiza.
    Los ids de CREACIÓN (FF04) ya tienen 10^3=0 -> idempotente (220585->220585)."""
    return raw_item - (raw_item // 1000 % 10) * 1000

def desempacar_pack(item_id):
    """`(id_contenido, PackCount)` de un ítem con `PackIndex`+`PackCount`, o `(item_id, 0)` si no es
    un pack.

    ⛔ **NO usar para decidir qué guardar en el inventario.** Se escribió el 2026-07-31 creyendo que el
    cliente expandía el pack y que había que guardar el contenido; **es al revés**: el PACK es el ítem
    del inventario y muestra su cantidad solo (ícono "Auto x100 Impulsor", tooltip
    "[Auto Impulsor X 100]") a partir del `PackCount` del catálogo. La compra de tienda (`FF50`)
    siempre guardó el pack crudo, y es lo correcto.
    ★ El duplicado que se vio ("contenido sin cargas" al lado del pack) NO lo causaba esto: lo creaba
    **`db_equip` -> `ensure_owned()`**, que mete en el inventario cualquier id que llegue por `FF1A`.
    El cliente expande el pack en memoria, el usuario clickea el contenido, manda `FF1A <contenido>`
    y el server lo INVENTA en la DB. Se deja la función porque el mapeo pack→contenido sirve para
    razonar sobre el `FF1A` de un contenido que nunca se otorgó."""
    d = shop_catalog.CATALOG.get(int(item_id)) or {}
    n = int(d.get("pack_count") or 0)
    dentro = int(d.get("pack_index") or 0)
    return (dentro, n) if (n > 0 and dentro) else (int(item_id), 0)

def tiene_cargas(item_id):
    """¿Este ítem se guarda con CARGAS (se gasta de a una) en vez de como prenda?

    ★ Dos listas y no una, a propósito:
      · `FAMILIAS_CON_CARGAS` — familias enteras ya probadas en pantalla (hoy: `megaphone`).
      · `ITEMS_CON_CARGAS`    — ítems sueltos cuya familia NO se puede abrir entera. Las campanas
        son `coupon_buff`, la misma familia que los cupones de EXP/Coin que nadie miró y que se
        venden por duración. Abrir la familia para que anden las campanas arrastraría los otros.

    ⚠ Existe esta función y no un `in` suelto porque la pregunta se hace en DOS lados (la entrega
      y el permiso de re-compra) y ya nos pasó con el sexo del personaje: la misma pregunta
      contestada en seis lugares distintos se desincroniza sola.
    """
    try:
        _iid = int(item_id)
    except Exception:                                            # noqa: BLE001
        return False
    # ★ Los GLOBOS, CRAYONES y LÁPICES del chat/apodo son de la familia «megaphone» (ShopIndex 0506)
    #   pero NO se gastan: son por FECHA (P30), como la ropa (anonimo03, 25-sep: *"estaba como por
    #   cargas de uso, cuando su duración debería ser por fecha"*).
    if _iid in GLOBOS_CHAT or _iid in CRAYONES_CHAT or _iid in LAPICES_APODO or _iid in LAPICES_CIRCULO:
        return False
    return (_iid in ITEMS_CON_CARGAS) or (shop_catalog.family(_iid) in FAMILIAS_CON_CARGAS)


def entregar_compra(usn, item_id, exp=0):
    r"""Mete en el inventario lo que se acaba de comprar, **abriendo el pack si lo es**.

    ⛔⛔ POR QUÉ EXISTE, Y POR QUÉ CONTRADICE LA NOTA DE ARRIBA — 2026-09-15.
      `desempacar_pack` tiene escrito, del 2026-07-31, que *"la compra de tienda siempre guardó el
      pack crudo, **y es lo correcto**"*, porque el cliente lo expande él y muestra «Auto x100».

      **anonimo03 lo desmintió en pantalla**: compró *"5 megáfonos de agregar amigos"* y le quedó en el
      inventario el **pack `486`** (`PackIndex=200 · PackCount=5`) en vez de 5 unidades del `200`.
      Resultado: *"no están funcionando como los que plantaste"* — los que yo le había puesto a
      mano eran el `200` suelto, y ésos **sí** andan.

      ★★ Y el log lo confirma por ausencia: al intentar usar el pack **el cliente no manda NADA**
        (ni un `FF40 0x0B`). O sea que no lo considera usable. Con el ítem suelto sí lo manda.

    ⇒ La nota del 31-jul no era falsa, era **parcial**: vale para el auto impulsor, que se usa
      *siendo* un pack con cargas. No vale para los packs cuyo contenido es un ítem que se gasta de
      a uno. Por eso esto va con perilla y no toca nada más que la compra.

    ⚠ Se guarda el contenido **con `cant` = PackCount**, que es el camino de cargas que
      `db_add_inventory` ya tenía para los impulsores: al comprar dos packs las cargas se SUMAN.
    """
    from .basedatos import db_add_inventory
    from .ajustes import TIENDA_ABRE_PACKS
    # ⚠⚠ RED: `desempacar_pack` lee `shop_catalog.CATALOG` directo, y si el catálogo **no está
    #   cargado** devuelve `{}` — o sea *"no es un pack"* — **sin quejarse**. Me pasó escribiendo
    #   esta misma función: la prueba decía que el pack no se abría y el código estaba bien.
    #   En el server real se carga al arrancar, pero si un día fallara, TODAS las compras
    #   entregarían packs sin abrir en silencio. Molde exacto de "el bug que no falla".
    if TIENDA_ABRE_PACKS and not shop_catalog.CATALOG:
        log("TIENDA", f"  ⛔ el catálogo está VACÍO: no puedo saber si el ítem {item_id} es un "
                      f"pack. Se entrega crudo — si esto se repite, el catálogo no cargó.")
    # ★★★ LOS PACKS DE ESCAPARATE (`setitem="1"`) SE ABREN — 2026-09-23. anonimo03 compró el «Pack de 4
    #   modos héroe» y recibió **el ítem de escaparate**, no los cuatro: *"eso le ocurrió mucho a
    #   usuarios en prod, y a nosotros con otros ítems de escaparate"*. Acá sólo se abrían los packs
    #   de UN ítem con cantidad (`PackIndex`/`PackCount`); los sets tienen VARIOS, listados en
    #   `setitem.txt` con su propio plazo. Cada contenido se entrega por esta MISMA función, así un
    #   contenido que es a su vez un pack con cantidad (Campana x5, Megáfono x5) también se abre, y
    #   uno de pareja (mascotas de los `Coupleitem="1"`) le llega también a la pareja.
    #   ⛔ El pack NO se guarda: es un envase, y en el inventario queda como un ítem muerto.
    from .ajustes import TIENDA_ABRE_SETS
    if TIENDA_ABRE_SETS and shop_catalog.es_set(item_id):
        _cont = shop_catalog.contenido_de_set(item_id)
        if _cont:
            from .basedatos import compute_expiry
            for _it, _compra in _cont:
                entregar_compra(usn, _it, compute_expiry(shop_catalog.period_code(_compra)))
            log("TIENDA", f"  ★★ SET ABIERTO: {item_id} -> {[i for i, _c in _cont]} (usn={usn})")
            return item_id, len(_cont)
        log("TIENDA", f"  ⚠ el set {item_id} no está en setitem.txt: se entrega crudo")
    _dentro, _n = desempacar_pack(item_id)
    if TIENDA_ABRE_PACKS and _n > 0 and _dentro != item_id:
        db_add_inventory(usn, _dentro, exp, cant=_n)
        log("TIENDA", f"  ★★ PACK ABIERTO: {item_id} -> {_n} x {_dentro} (usn={usn})")
        return _dentro, _n
    # ★★★★★ UN CONSUMIBLE SUELTO VALE **UNA CARGA** — 2026-09-15, lo vio anonimo03 comparando:
    #   el pack de 5 mostraba su número bien, *"pero los otros 2 se muestran como si fuera un ítem
    #   activado sin cargas, y si lo gasto pasa a tener 0 cargas"*. Los otros dos los había
    #   comprado **sueltos**, y a un ítem suelto lo guardábamos **sin `cant`** — o sea con cero
    #   usos. El pack andaba sólo porque el `PackCount` le ponía el número.
    #   ⇒ Comprar un megáfono suelto es comprar **una carga**. Con eso, además, comprar otro
    #     SUMA — que es lo que pidió: *"debería poder comprar más y acumular cargas tal cual hace
    #     el de 5"*. `db_add_inventory` ya sabe sumar cargas; sólo había que darle el 1.
    #   ⚠ La lista es corta y explícita a propósito. «No vestible» NO alcanza como regla: las
    #     cápsulas del gacha tampoco son vestibles y tienen su propio camino. Se agregan familias
    #     a medida que se prueben en pantalla, no por deducción.
    if TIENDA_ABRE_PACKS and tiene_cargas(item_id):
        db_add_inventory(usn, item_id, exp, cant=1)
        log("TIENDA", f"  ★ consumible suelto {item_id} -> +1 carga (usn={usn})")
        return item_id, 1
    db_add_inventory(usn, item_id, exp)
    _para_la_pareja(usn, item_id, exp)
    return item_id, 0


def _para_la_pareja(usn, item_id, exp):
    """Lo de PAREJA se compra para los dos, porque el cliente sólo lo «junta» si los dos lo tienen:
      · el MARCO: `0x595430` pide el mismo número en los dos (`MARCO_PAREJA_PARA_LOS_DOS`);
      · la MASCOTA: `0x524210` pide las dos `PetType=2` y el mismo `Id % 1000` (el par chico/chica,
        99 y 1099) para el «se encuentran» y los combos (`MASCOTA_PAREJA_PARA_LOS_DOS`).
    Molde del anillo (`PAREJA_ANILLO_AL_QUE_ACEPTA`). Cada uno lo equipa."""
    from .ajustes import MARCO_PAREJA_PARA_LOS_DOS, MASCOTA_PAREJA_PARA_LOS_DOS
    if es_marco_de_pareja(item_id):
        if not MARCO_PAREJA_PARA_LOS_DOS:
            return
        _que = "marco de pareja"
    elif es_mascota_de_pareja(item_id):
        if not MASCOTA_PAREJA_PARA_LOS_DOS:
            return
        _que = "mascota de pareja"
    else:
        return
    try:
        from .basedatos import db_add_inventory, db_pareja_de
        _pj = db_pareja_de(int(usn))
        if not _pj:
            log("TIENDA", f"  · {_que} {item_id} comprado SIN pareja (usn={usn}): "
                          f"se ve como uno simple hasta que tenga una")
            return
        if int(item_id) in inv_ids(db_get_char(int(_pj)) or {}):
            log("TIENDA", f"  · {_que} {item_id}: la pareja usn={_pj} ya lo tiene")
            return
        db_add_inventory(int(_pj), int(item_id), exp)
        from .salas import CONEXIONES                                      # noqa: PLC0415
        _cx = CONEXIONES.get(int(_pj))
        if _cx is not None and not getattr(_cx, "cerrado", False):
            # ★ Que le aparezca YA en el inventario (anonimo03, 23-sep: *"se comparte, pero no aparece
            #   hasta cambiar de servidor"*). Es el mismo refresco que recibe el que compra; en
            #   carrera se deja para el próximo poll: un paquete grande a destiempo mata a las
            #   máquinas lentas (ver `la-maquina-lenta-ve-las-carreras`).
            if getattr(_cx, "en_carrera", False):
                _cx.buy_needs_refresh = True
            else:
                from .myrecord import enviar_myrecord                          # noqa: PLC0415
                enviar_myrecord(_cx, f"MyRecord refresh ({_que} recibido)",
                                con_personaje=False)
        log("TIENDA", f"  ★★ {_que.upper()} {item_id}: comprado por usn={usn} -> también a su "
                      f"pareja usn={_pj}{' (conectada)' if _cx is not None else ''}")
    except Exception as e:                                               # noqa: BLE001
        log("TIENDA", f"  ⚠ no pude darle {_que} {item_id} a la pareja de usn={usn}: {e!r}")


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ★★ EL ESTILO DEL CHAT: el GLOBO y el COLOR DE LETRA (25-sep) — `documentacion/CHAT_GLOBO_Y_COLOR_EXE.md`
#     El FF08 S→C cierra con `[u8 globo][u8 color]` (handler `0x5CC980`):
#       globo = índice en `rnr_room/chat_0..7.tga` (`sala+0x148`, 8, SIN cota; 0 = el blanco de siempre)
#       color = índice en la tabla `0x886290` (9, SIN cota; 0 = el gris de siempre, `FF7B7B7B`)
#     ⛔ Se mandaba `asiento % 8` en el globo ⇒ cada asiento salía con un globo DE LA TIENDA
#       (anonimo03: *"aleatorio"*). El cliente manda sólo el texto: el estilo lo pone el server.
#     Se activa tildando el ítem en Mi Casa (`FF1A`); uno por grupo (`overlap.txt`).
# ══════════════════════════════════════════════════════════════════════════════════════════════
GLOBOS_CHAT = {1000013: 2, 1000014: 3, 1000015: 4, 1000016: 5, 1000024: 6, 1000025: 7}   # [M] mirando cada .tga
CRAYONES_CHAT = {i: i - 1000015 for i in range(1000017, 1000024)}   # 2..8 (los íconos coinciden) — ✅ el
#   «Crayon amarillo» (1000023 -> 8, naranja FFF7941C) salió en pantalla del color de su ícono (anonimo03, 25-sep)
CHAT_GLOBOS, CHAT_COLORES = 8, 9                                      # los topes del cliente
# ★ Los LÁPICES DEL APODO (1000349..1000354, «닉네임색연필»): pintan el NOMBRE (asiento y cabeza), no
#   el chat. `0x50DFC0` los lleva a 1..6 = la tabla `0x8820FC` (verde, rojo, azul, gris, púrpura,
#   naranja); 0 = blanco sin borde. El cliente NO pone cota arriba (7 = basura): sólo 0..6.
LAPICES_APODO = {1000349 + i: i + 1 for i in range(6)}
# ★ 23-oct · los «Crayón Mazino <color>» (crayon_crear.py, CRAYONES_MAZINO.md): colores 7..12 del apodo. El cliente
#   sólo tiene 6: la dll (crayones.c) apunta los 22 lectores a una tabla de 12 y le enseña estos códigos a 0x50DFC0.
#   ⛔ Sin esa dll, 7..12 leen basura ⇒ van JUNTOS.
LAPICES_APODO.update({1000780 + i: 7 + i for i in range(6)})
# ★ 23-oct · los ESTILOS de letra (crayon_crear.ESTILOS, ocultos): 13..23 del apodo = las marcas de estilo que pinta
#   la dll (`estilos_texto.c`: la letra propia, arcoíris animado). Mismo «van JUNTOS» que arriba.
#   ★ 24-oct: 11 = uno por color de slot del ID (Mazino + Flama) y los 2 arcoíris (CRAYONES_MAZINO.md §7).
ESTILOS_N = 11                                                        # len(crayon_crear.ESTILOS)
LAPICES_APODO.update({1000701 + i: 13 + i for i in range(ESTILOS_N)})
COLORES_APODO = 13 + ESTILOS_N
# ★ 23-oct · los «Crayón de Círculo <color>»: el color del NOMBRE DEL CÍRCULO (1..6 = la tabla de circulo_color.c).
#   Viaja como una marca '^'+letra al principio del nombre del círculo (paquetes._marca_circulo).
LAPICES_CIRCULO = {1000786 + i: 1 + i for i in range(6)}
LAPICES_CIRCULO.update({1000712 + i: 7 + i for i in range(ESTILOS_N)})   # ★ los estilos de letra: letras 7..17
COLORES_CIRCULO = 7 + ESTILOS_N


def _vigente(ch, item):
    """¿Lo tiene y no venció? (`exp` 0 = permanente)."""
    import time as _t                                                   # noqa: PLC0415
    from .basedatos import inv_pairs                                     # noqa: PLC0415
    return any(int(i) == int(item) and (not e or int(e) > _t.time()) for i, e in inv_pairs(ch or {}))


def estilo_chat_de(usn, ch=None):
    """`(globo, color)` para el FF08 de `usn`: los de sus ítems tildados si los tiene vigentes,
    si no `(0, 0)` = el globo y el color de siempre. Siempre dentro de los topes del cliente."""
    try:
        from .basedatos import db_estilo_chat                            # noqa: PLC0415
        g, c = db_estilo_chat(int(usn))
    except Exception:                                                     # noqa: BLE001
        return 0, 0
    if not (g or c):
        return 0, 0
    ch = ch if ch is not None else db_get_char(int(usn))
    globo = GLOBOS_CHAT.get(g, 0) if g and _vigente(ch, g) else 0
    color = CRAYONES_CHAT.get(c, 0) if c and _vigente(ch, c) else 0
    return (globo if 0 <= globo < CHAT_GLOBOS else 0), (color if 0 <= color < CHAT_COLORES else 0)


def color_apodo_de(usn, ch=None):
    """El color del APODO (0..6) de `usn`: el de su lápiz tildado si lo tiene vigente, si no 0."""
    try:
        from .basedatos import db_lapiz_apodo                            # noqa: PLC0415
        lap = db_lapiz_apodo(int(usn))
    except Exception:                                                     # noqa: BLE001
        return 0
    if not lap:
        return 0
    ch = ch if ch is not None else db_get_char(int(usn))
    c = LAPICES_APODO.get(lap, 0) if _vigente(ch, lap) else 0
    return c if 0 <= c < COLORES_APODO else 0


def color_circulo_de(usn, ch=None):
    """El color del NOMBRE DEL CÍRCULO (0 = blanco, el de siempre) de `usn`: el de su crayón de círculo tildado si lo
    tiene vigente."""
    try:
        from .basedatos import db_lapiz_circulo                          # noqa: PLC0415
        lap = db_lapiz_circulo(int(usn))
    except Exception:                                                     # noqa: BLE001
        return 0
    if not lap:
        return 0
    ch = ch if ch is not None else db_get_char(int(usn))
    c = LAPICES_CIRCULO.get(lap, 0) if _vigente(ch, lap) else 0
    return c if 0 <= c < COLORES_CIRCULO else 0


def estilos_activos(usn, ch=None):
    """Los ítems de estilo tildados y vigentes (globo, crayón, lápiz): van `in_use = 1` en el
    MyRecord (#37) para que el cliente los tenga tildados al reconectar (`0x48E830`, categoría 10)."""
    try:
        from .basedatos import db_estilo_chat, db_lapiz_apodo, db_lapiz_circulo   # noqa: PLC0415
        cands = list(db_estilo_chat(int(usn))) + [db_lapiz_apodo(int(usn)), db_lapiz_circulo(int(usn))]
    except Exception:                                                     # noqa: BLE001
        return set()
    ch = ch if ch is not None else db_get_char(int(usn))
    return {int(i) for i in cands if i and _vigente(ch, i)}


def tildar_estilo_chat(usn, item_id, activar):
    """El `FF1A` de un globo, un crayón o un lápiz del apodo: lo activa (si lo tiene vigente) o lo
    saca. -> None si no es de estilo (sigue el camino de la ropa), True/False si se atendió acá."""
    from .basedatos import db_estilo_chat, db_lapiz_apodo, db_poner_estilo_chat, db_poner_lapiz_apodo  # noqa: PLC0415
    item_id = int(item_id)
    campo = ("globo" if item_id in GLOBOS_CHAT else "crayon" if item_id in CRAYONES_CHAT
             else "apodo" if item_id in LAPICES_APODO else "circulo" if item_id in LAPICES_CIRCULO else None)
    if campo is None:
        return None
    try:                                                   # ★ el estilo guardado en la conexión, afuera
        from .salas import CONEXIONES                                    # noqa: PLC0415
        _c = CONEXIONES.get(int(usn))
        if _c is not None:
            _c.chat_cache = None
    except Exception:                                                     # noqa: BLE001
        pass
    if campo == "circulo":                                 # ★ 23-oct: el crayón de círculo, como el lápiz del apodo
        from .basedatos import db_lapiz_circulo, db_poner_lapiz_circulo  # noqa: PLC0415
        if activar and not _vigente(db_get_char(int(usn)), item_id):
            log("DB", f"⛔ FF1A crayón de círculo: usn={usn} no tiene vigente {item_id}")
            return False
        if activar:
            db_poner_lapiz_circulo(int(usn), item_id)
        elif db_lapiz_circulo(int(usn)) == item_id:
            db_poner_lapiz_circulo(int(usn), 0)
        log("DB", f"🖍 crayón de círculo usn={usn}: {'=' if activar else 'sin'} {item_id}")
        return True
    if campo == "apodo":
        if activar and not _vigente(db_get_char(int(usn)), item_id):
            log("DB", f"⛔ FF1A lápiz del apodo: usn={usn} no tiene vigente {item_id}")
            return False
        if activar:
            db_poner_lapiz_apodo(int(usn), item_id)
        elif db_lapiz_apodo(int(usn)) == item_id:
            db_poner_lapiz_apodo(int(usn), 0)
        log("DB", f"🖍 lápiz del apodo usn={usn}: {'=' if activar else 'sin'} {item_id}")
        return True
    if activar:
        if not _vigente(db_get_char(int(usn)), item_id):
            log("DB", f"⛔ FF1A estilo de chat: usn={usn} no tiene vigente {item_id}")
            return False
        db_poner_estilo_chat(int(usn), campo, item_id)
    elif db_estilo_chat(int(usn))[0 if campo == "globo" else 1] == item_id:
        db_poner_estilo_chat(int(usn), campo, 0)
    log("DB", f"💬 estilo de chat usn={usn}: {campo} {'=' if activar else 'sin'} {item_id}")
    return True


# ★★ 30-oct: LAS AURAS DE SUELO (`<AuraWing>` de VFUN, `documentacion/AURA_DE_SUELO.md`). El exe 2013 no las lee: las
#   dibuja la dll (`aura_suelo.c`) con la maquinaria de las alas. Viajan en el MISMO u32 que el Wing Id, en la mitad de
#   arriba: `Wing Id | (aura << 16)` (aura = 1..N, el orden de `aura_suelo_datos.h`). La tabla la escribe
#   `herramientas/aura_suelo_crear.py` en `tablas-cliente/aura_suelo.json` ({código: aura}).
#   Son de la tienda 1007, la familia de las alas, pero NO ocupan su lugar: un aura reemplaza a otra aura, no a un ala.
_AURAS = None


def auras_suelo():
    global _AURAS
    if _AURAS is None:
        _AURAS = {}
        try:
            import json                                                    # noqa: PLC0415
            from .ajustes import _DIR_SERVIDOR                             # noqa: PLC0415
            _AURAS = {int(k): int(v) for k, v in json.load(open(os.path.join(_DIR_SERVIDOR, "tablas-cliente",
                                                                          "aura_suelo.json"))).items()}
        except Exception as e:                                             # noqa: BLE001
            log("DB", f"⚠ no pude leer tablas-cliente/aura_suelo.json: {e!r} — las auras de suelo no viajan")
    return _AURAS


def es_aura(item_id):
    try:
        return int(item_id) in auras_suelo()
    except Exception:                                                      # noqa: BLE001
        return False


# ★★ (145) 31-oct: EL AURA DE UN SET (`setavatareffect.xml` de VFUN, `SetEffectType1="effect"`). El exe 2013 no tiene
#   bonos de set: con las piezas del set PUESTAS, el server manda el efecto del set en el mismo byte del aura de suelo
#   (bits 16-23 del Wing Id), con números de 0xF0 para arriba (las auras de ítem van de 1 para arriba: no se cruzan).
#   La dll lo dibuja con la misma maquinaria (`aura_suelo.c`, `AS_TABLA`). La tabla la escribe
#   `herramientas/aura_suelo_crear.py` en `tablas-cliente/sets_aura.json`: {byte: {"nombre", "piezas": [[…], […]]}}
#   (una lista de piezas por sexo). ⇒ `documentacion/SET_ESCOLAR.md`.
#   ★ Si tiene puesta un aura de ítem Y el set completo, GANA EL AURA DEL ÍTEM: la eligió él (y se la puede sacar).
#   ⛔ Sin bono de experiencia (el VFUN da ×3): anonimo03 no lo quiere.
AURA_SET_BASE = 0xF0
_SETS_AURA = None


def sets_aura():
    """[(byte, (frozenset(piezas), …), nombre)] de `tablas-cliente/sets_aura.json`."""
    global _SETS_AURA
    if _SETS_AURA is None:
        _SETS_AURA = []
        try:
            import json                                                    # noqa: PLC0415
            from .ajustes import _DIR_SERVIDOR                             # noqa: PLC0415
            for b, v in json.load(open(os.path.join(_DIR_SERVIDOR, "tablas-cliente", "sets_aura.json"),
                                       encoding="utf-8")).items():
                b = int(b)
                if not AURA_SET_BASE <= b <= 0xFF:
                    raise ValueError(f"el set {v.get('nombre')!r} trae el byte {b}: fuera de 0xF0..0xFF")
                _SETS_AURA.append((b, tuple(frozenset(int(x) for x in p) for p in v["piezas"]), v.get("nombre", "")))
        except Exception as e:                                             # noqa: BLE001
            _SETS_AURA = []
            log("DB", f"⚠ no pude leer tablas-cliente/sets_aura.json: {e!r} — el aura de los sets no viaja")
    return _SETS_AURA


def aura_de_set(partes):
    """El byte del aura del set que tiene COMPLETO (todas las piezas de una de sus listas puestas), o 0."""
    nums = set()
    for p in partes or ():
        try:
            nums.add(int(p))
        except (TypeError, ValueError):
            continue
    for b, listas, _n in sets_aura():
        if any(p and p <= nums for p in listas):
            return b
    return 0


# ★★ 30-oct: FLOTAR (`fly.txt` del 2019, `documentacion/FLOTAR.md`). Lo hace la dll (`flotar.c`); viaja en el byte de
#   ARRIBA del mismo u32: `Wing Id | aura << 16 | flotar << 24` (flotar = 1..N, `tablas-cliente/flotar.json`, la escribe
#   `herramientas/flotar_crear.py`). La regla del 2019 (`overlap.txt`, igual en VFUN, 2019, muse y XYX): la Carta Nube
#   está en un grupo con los DOS Dash (Flama 1000406 · Hielo 1000639) — flotar no va con un Dash — y con nada más.
_FLOTAR = None
DASH = (1000406, 1000639)


def flotar_items():
    global _FLOTAR
    if _FLOTAR is None:
        _FLOTAR = {}
        try:
            import json                                                    # noqa: PLC0415
            from .ajustes import _DIR_SERVIDOR                             # noqa: PLC0415
            _FLOTAR = {int(k): int(v) for k, v in json.load(open(os.path.join(_DIR_SERVIDOR, "tablas-cliente",
                                                                           "flotar.json"))).items()}
        except Exception as e:                                             # noqa: BLE001
            log("DB", f"⚠ no pude leer tablas-cliente/flotar.json: {e!r} — flotar no viaja")
    return _FLOTAR


def es_flotar(item_id):
    try:
        return int(item_id) in flotar_items()
    except Exception:                                                      # noqa: BLE001
        return False


CARTA_NUBE = 1000729                     # la única de flotar que en el 2019 está en un grupo: con los Dash


# ★★ 30-oct: LAS CEREMONIAS DE ENTRAR A LA SALA (`specialentrance.xml`, `Location="Room"`). El 2013 las tiene enteras
#   (`0x5B2260`, al terminar de aparecer en la sala): para uno mismo mira su inventario, y para los DEMÁS lee el
#   `Index` de la fila en un byte del `FF0C` (`cola[17]` -> `0x5E85D7` -> `sRoomUser+0x163`). Lo escribe
#   `herramientas/ceremonias_crear.py` en `tablas-cliente/entrada_sala.json` ({código: Index}).
#   Ver `documentacion/CEREMONIAS_AURAS_Y_FLOTAR.md` §7.
_ENTRADAS = None


def entradas_sala():
    global _ENTRADAS
    if _ENTRADAS is None:
        _ENTRADAS = {}
        try:
            import json                                                    # noqa: PLC0415
            from .ajustes import _DIR_SERVIDOR                             # noqa: PLC0415
            _ENTRADAS = {int(k): int(v) for k, v in json.load(open(os.path.join(_DIR_SERVIDOR, "tablas-cliente",
                                                                             "entrada_sala.json"))).items()}
        except Exception as e:                                             # noqa: BLE001
            log("DB", f"⚠ no pude leer tablas-cliente/entrada_sala.json: {e!r} — las entradas a la sala no viajan")
    return _ENTRADAS


def entrada_de_sala(parts):
    """El `Index` de `specialentrance.xml` de la ceremonia de sala que tiene ACTIVADA (0 = ninguna)."""
    _t = entradas_sala()
    for p in parts or ():
        try:
            if int(p) in _t:
                return _t[int(p)] & 0xFF
        except (TypeError, ValueError):
            continue
    return 0


def mismo_lugar(a, b, fam_a=None):
    """¿`b` ocupa el mismo lugar que `a`? Misma familia, y las dos auras de suelo o ninguna. Flotar, como el 2019
    (overlap.txt): la Carta Nube sólo choca con los Dash; la Piedra Sónica, con nada; el Paso de Estrella es una MANO
    (lo reemplaza otra mano, como a cualquiera)."""
    x, y = int(a), int(b)
    if (es_flotar(x) and x // 10000 == 100) or (es_flotar(y) and y // 10000 == 100):   # la Carta o la Piedra (0509)
        grupo = {CARTA_NUBE, *DASH}
        return x in grupo and y in grupo
    fa = fam_a or shop_catalog.family(a)
    if fa == "dance_emote" and shop_catalog.family(b) == "dance_emote":
        # ★ (141) 30-oct: las ceremonias en DOS lugares, como los dos grupos de overlap.txt (los del VFUN): entrar a la
        #   sala (entrada_sala.json) por un lado; largada / meta y las poses de pareja por el otro
        return (x in entradas_sala()) == (y in entradas_sala())
    return fa == shop_catalog.family(b) and es_aura(a) == es_aura(b)


def wing_id_con_aura(partes, usn=None):
    """el u32 del Wing Id con el aura de suelo y flotar arriba (ver `auras_suelo` y `flotar_items`).
    ★ (142) y LA MONTURA en el mismo byte de arriba (`monturas.byte_de`): 0x80 | 0x40 (la tiene) | modo << 4 | k, con
    el modo (parado / en la suya / en la de la pareja) de ESTA sala — por eso hace falta el `usn`. Si tiene las dos,
    gana la montura (el 2019 tampoco vuela montado). Sin `usn` (el popup del perfil) va «invocada, parada».
    ★ (145) Sin aura de ítem puesta, el byte del aura lleva el del SET completo (`aura_de_set`, 0xF0..)."""
    partes = partes or []
    nums = [int(p) for p in partes if str(p).lstrip("-").isdigit()]
    wid = next((w for w in (wing_id(p) for p in partes) if w), 0)
    aura = next((a for a in (auras_suelo().get(p, 0) for p in nums) if a), 0)
    if not aura:                                     # ★ (145) el aura del SET: sólo si no tiene un aura de ítem puesta
        aura = aura_de_set(nums)
    vuela = next((f for f in (flotar_items().get(p, 0) for p in nums) if f), 0)
    k = next((m for m in (monturas().get(p) for p in nums) if m is not None), None)
    from .monturas import byte_de                                          # noqa: PLC0415
    from .monturas import codificar                                        # noqa: PLC0415
    mo = byte_de(usn, k) if usn else (codificar(k) if k is not None else 0)
    if mo:
        vuela = mo
    return (wid & 0xFFFF) | ((aura & 0xFF) << 16) | ((vuela & 0xFF) << 24)


_MONTURAS = None
_MONTURAS_FLAGS = {}


def monturas():
    """{código: k} de `tablas-cliente/monturas.json` (lo escribe `herramientas/monturas_crear.py`). El valor puede ser
    el k a secas (la 1.ª versión) o {"k", "pareja", "ani_change"} — las banderas del callobject.txt del 2019."""
    global _MONTURAS
    if _MONTURAS is None:
        _MONTURAS = {}
        try:
            import json                                                    # noqa: PLC0415
            from .ajustes import _DIR_SERVIDOR                             # noqa: PLC0415
            for c, v in json.load(open(os.path.join(_DIR_SERVIDOR, "tablas-cliente", "monturas.json"))).items():
                k = int(v["k"]) if isinstance(v, dict) else int(v)
                _MONTURAS[int(c)] = k
                if isinstance(v, dict):
                    _MONTURAS_FLAGS[k] = {"pareja": int(v.get("pareja", 0)), "ani_change": int(v.get("ani_change", 0))}
        except Exception as e:                                             # noqa: BLE001
            log("DB", f"⚠ no pude leer tablas-cliente/monturas.json: {e!r} — las monturas no viajan")
    return _MONTURAS


def montura_flags(k):
    """{"pareja": Couple, "ani_change": AniChange} de la montura k (callobject.txt del 2019)."""
    monturas()
    return _MONTURAS_FLAGS.get(k, {})


def se_suma(item_id, fam=None):
    """¿Este ítem se activa JUNTO a los de su familia (no reemplaza ni lo reemplazan)? Las familias que se
    suman (modos héroe, profecías) y las AYUDAS DE CARRERA por su efecto (`ajustes.AYUDAS_DE_CARRERA_EFECTOS`, (96))."""
    from .ajustes import AYUDAS_DE_CARRERA_EFECTOS, FAMILIAS_QUE_SE_SUMAN               # noqa: PLC0415
    if (fam or shop_catalog.family(item_id)) in FAMILIAS_QUE_SE_SUMAN:
        return True
    it = shop_catalog.CATALOG.get(int(item_id)) or {}
    return it.get("effect") in AYUDAS_DE_CARRERA_EFECTOS


def db_equip(usn, item_id, equip=True):
    """Persiste equipar/quitar una prenda VESTIBLE en chars_db.json -> ch['parts'] (lo puesto).

    Slot = familia del catálogo (una prenda por familia). Al equipar: saca la del mismo slot (que queda
    OWNED en inventario, no se pierde) y pone la nueva. Sin esto, lo equipado NO queda puesto al re-loguear.
    Soporta N slots (cara/mano/alas/mascota), no solo los 4 base. Devuelve True si cambió algo."""
    if not shop_catalog.is_wearable(item_id):
        return False                                   # consumibles/cupones/etc no se 'visten'
    fam = shop_catalog.family(item_id)
    if fam in _MULTISLOT_FAMILIES:
        return False                                   # multi-slot: se maneja en fase posterior
    # ★ 2026-09-05: era `d = db_load(); ch = d.get(str(usn))` — los 4806 personajes para vestir a
    #   UNO. py-spy lo midió como el **25% del CPU del servidor**. Ahora una consulta por uid.
    ch = db_get_char(usn)
    if not ch:
        return False
    parts = ch.setdefault("parts", [])
    inv = ch.setdefault("inventory", [])
    # ★★ CANDADO (2026-07-31). `ensure_owned` metía en el inventario CUALQUIER id que llegara por
    #   `FF1A` ⇒ un cliente podía **hacerse dar cualquier ítem** mandando un equip de algo que no
    #   tiene. Así apareció el "Auto Impulsor" fantasma: el cliente expande el pack en memoria, el
    #   usuario clickea el contenido, manda `FF1A <contenido>` y el server lo INVENTABA.
    #   Ahora sólo se acepta lo que el jugador realmente posee — o el CONTENIDO de un pack que posee,
    #   que es legítimo (el pack es el envase y lo usable es lo de adentro).
    # ★ 11-oct: también lo que YA tiene puesto (jugador50 se re-ponía su pelo al sacarse el personaje y se rechazaba:
    #   la ropa puesta de las cuentas viejas no figura en el inventario) y su set básico.
    _poseidos = set(inv_ids(ch)) | {int(x) for x in parts} | set(basico_de(ch))
    _contenidos = {desempacar_pack(i)[0] for i in _poseidos if desempacar_pack(i)[1]}
    if int(item_id) not in _poseidos and int(item_id) not in _contenidos:
        log("DB", f"⛔ FF1A rechazado: item={item_id} NO está en el inventario de usn={usn} "
                  f"(ni es contenido de un pack poseído) — no se inventa")
        return False
    _bas = set(basico_de(ch))

    def ensure_owned(iid):                             # asegura iid en inventario (permanente si es nuevo)
        if iid not in inv_ids(ch) and iid not in _bas:  # ★ la básica no: viaja aparte (`basico`)
            inv.append({"id": iid, "exp": 0})
    changed = False
    if not equip:                                      # QUITAR: sale de puestas, queda en inventario
        if item_id in parts:
            parts.remove(item_id)
            ensure_owned(item_id)
            changed = True
    else:                                              # EQUIPAR: reemplaza la del mismo slot
        _saca = [] if se_suma(item_id, fam) else [
            x for x in parts if mismo_lugar(item_id, x, fam) and x != item_id and not se_suma(x)]
        for p in _saca:
            parts.remove(p)
            ensure_owned(p)                            # la reemplazada NO se pierde (queda owned)
            changed = True
        if item_id not in parts:
            parts.append(item_id); changed = True
        ensure_owned(item_id)                          # asegurar que también figure como owned
    if changed:
        db_save_uno(usn, ch)
        log("DB", f"equip usn={usn} item={item_id} fam={fam} equip={equip} -> parts={parts}")
    return changed

# ★ LAS PRENDAS DE LA CREACIÓN (11-oct, «Restaurar» del armario = `FF7F`). Son las 24 primeras filas de
#   `shop_lt.txt`: `Show="0"`, tiendas 0301-0304 (hombre) y 0401-0404 (mujer), 3 por parte (las A/B/C de la
#   pantalla de crear personaje). El cliente las guarda como su «set básico» (`[player+0xD8]`, una por parte,
#   `0x48F693`) y «Restaurar» las manda con el `FF7F`. ⚠ NO están en el inventario del jugador (la creación las
#   pone puestas y nada más), así que el candado de `db_equip` las rechazaría.
_TIENDAS_BASICAS = {"0301", "0302", "0303", "0304", "0401", "0402", "0403", "0404"}
_BASICOS = None


def basicos_de_creacion():
    """El set de la creación: la tanda de filas `Show="0"` de las tiendas básicas con que ARRANCA `shop_lt.txt`
    (derivado del archivo, no clavado: si el catálogo cambia, cambia con él)."""
    global _BASICOS
    if _BASICOS is None:
        shop_catalog._ensure()
        b = set()
        for it in shop_catalog.CATALOG.values():
            if it["raw"].get("Show") == "0" and it["shop_index"] in _TIENDAS_BASICAS:
                b.add(it["index"])
            else:
                break
        if not b:                                    # ⚠ catálogo vacío: no se cachea un «no hay básicos»
            log("TIENDA", "  ⛔ basicos_de_creacion: el catálogo no tiene las filas de la creación")
            return frozenset()
        _BASICOS = frozenset(b)
    return _BASICOS


# ★★ EL SET BÁSICO DE CADA CUENTA (11-oct, anonimo03: *«muchos jugadores crearon su char sin que la ropa básica se haya
#   guardado; jugador50 no tiene la que eligió al crearse»*). Medido: jugador50 lleva un pelo y unas bermudas compradas;
#   de la creación le quedan sólo la musculosa y los zapatos (puestos), y su «Restaurar» mandó 2 prendas, no 4.
#   La creación deja las 4 PUESTAS y nada más: al cambiarse, la básica desaparecía para siempre.
#   ⇒ Se guarda en las columnas `hair/top/bottom/skates` de `chars` (del CBT; hasta hoy siempre 0) como
#     `ch["basico"]` = [pelo, arriba, abajo, patines], y viaja en la lista del inventario (MyRecord #37 y FF49) para
#     que el cliente arme su `[player+0xD8]` (`0x48F693`) y «Restaurar» mande las 4.
#   Para una cuenta que no lo tiene: por parte, la básica de su sexo que tenga puesta o en el inventario (sólo
#   pudo venir de la creación); si no queda ninguna, la opción A. ⚠ La A es una SUPOSICIÓN: lo que eligió de verdad
#   sólo está en los logs de la creación (`CREATE_CHAR OK: … parts`), si todavía existen.
_PARTES_BASICAS = ("01", "02", "03", "04")              # pelo · arriba · abajo · patines (las tiendas x301..x304)


def _tienda_sexo(gender):
    return "04" if int(gender or 0) == 1 else "03"


_POR_PARTE = {}


def basicas_por_parte(gender):
    """{parte: [A, B, C]} del set de la creación de ese sexo, en el orden de `shop_lt.txt` (cacheado: corre en cada
    login y cada equip, y el VPS tiene presupuesto de CPU)."""
    t = _tienda_sexo(gender)
    if t in _POR_PARTE:
        return _POR_PARTE[t]
    bas = basicos_de_creacion()
    out = {p: [] for p in _PARTES_BASICAS}
    for x in shop_catalog.CATALOG:                       # el orden del archivo = A, B, C
        if x in bas:
            si = shop_catalog.CATALOG[x]["shop_index"]
            if si[:2] == t and si[2:] in out:
                out[si[2:]].append(x)
    if bas:
        _POR_PARTE[t] = out
    return out


def basico_de(ch):
    """El set básico de la cuenta: el guardado si está completo; si no, el deducido (ver arriba). Lista de 4."""
    g = basicas_por_parte(ch.get("gender", 0))
    guardado = list(ch.get("basico") or [])
    tiene = [int(x) for x in ch.get("parts", [])] + list(inv_ids(ch))
    out = []
    for i, parte in enumerate(_PARTES_BASICAS):
        if i < len(guardado) and guardado[i] in g[parte]:
            out.append(guardado[i])
            continue
        suyas = [x for x in tiene if x in g[parte]]
        out.append(suyas[0] if suyas else (g[parte][0] if g[parte] else 0))
    return out


def asegurar_basico(usn, ch=None):
    """Deja guardado el set básico de `usn` (una sola escritura, la primera vez). -> la lista de 4."""
    ch = ch if ch is not None else db_get_char(usn)
    if not ch:
        return []
    b = basico_de(ch)
    if list(ch.get("basico") or []) != b:
        _deducido = not ch.get("basico")
        ch["basico"] = b
        db_save_uno(usn, ch)
        log("DB", f"★ set básico de usn={usn} {'DEDUCIDO' if _deducido else 'corregido'} y guardado: {b}")
    return b


FAMILIAS_CAT10_VISIBLES = {"wardrobe_face", "aura_summon", "skin"}


def db_quitar_todo(usn):
    """`FF1A [02][0]` = «quitar todo» (lo manda «Restaurar», `0x4CA935`, antes del `FF7F` con el set básico).
    Saca TODO lo puesto: lo comprado vuelve al inventario, lo básico no (viaja en `basico`). -> lo que sacó.
    ★ 11-oct, anonimo03: *«las alas no se desequiparon»* — se contestaba result=1 (poner el ítem 0) y no se guardaba
      nada: el cliente escondió lo demás por su cuenta, pero las alas se dibujan de otro lado (el Wing Id del
      FF0C) y quedaron; en la base seguía todo puesto."""
    ch = db_get_char(usn)
    if not ch:
        return []
    parts = ch.setdefault("parts", [])
    inv = ch.setdefault("inventory", [])
    # ⚠ el set básico se fija ANTES de vaciar: en una cuenta vieja se deduce de lo que tiene PUESTO
    basico = basico_de(ch)
    nuevo_basico = list(ch.get("basico") or []) != basico
    ch["basico"] = basico
    # ★ 11-oct, 4.ª vuelta (anonimo03: «me puse otra ala y tampoco se desequipa»): la categoría 10 del cliente
    #   (`categoria_worn`, = `0x50E0B0`) NO está en las 11 partes que vacía el result 2: se prende y apaga aparte
    #   (`0x48E830(ítem, 1/0)`, `0x5E21EE`). Y mezcla lo que SE VE (caras, alas/auras, pieles) con lo que no (cupones,
    #   ranuras, modo héroe, emotes, crayones). «Restaurar» saca lo que se ve; lo otro queda como estaba (igual
    #   que en el cliente). Al que lo pidió, cada una de ésas le va con su `FF1A` de quitar (ver `h_37_ff1a`).
    # ⚠ 12-oct: y de la 11 para arriba (joyas de la amistad, anillos: 1200029/1200033 en el set de cuenta_admin) NO es
    #   ropa: el cliente las saltea (`cmp al, 0xB / jae`) y no tienen por qué salir.
    sacadas = [p for p in parts if categoria_worn(p) <= 9
               or (categoria_worn(p) == 10 and shop_catalog.family(p) in FAMILIAS_CAT10_VISIBLES)]
    for p in sacadas:
        parts.remove(p)
        if p not in basico and p not in inv_ids(ch):
            inv.append({"id": p, "exp": 0})
    if sacadas or nuevo_basico:
        db_save_uno(usn, ch)
        log("DB", f"FF1A QUITAR TODO usn={usn}: sacó {sacadas} (las compradas, al inventario)")
    return sacadas


def db_equip_varios(usn, items):
    """`FF7F`: ponerse VARIAS prendas de una (una por familia, la nueva reemplaza a la del mismo slot).
    Se acepta lo que el jugador posee, lo que ya tiene puesto y el set de la creación. -> (puestas, rechazadas)."""
    ch = db_get_char(usn)
    if not ch:
        return [], list(items)
    parts = ch.setdefault("parts", [])
    inv = ch.setdefault("inventory", [])
    _poseidos = set(inv_ids(ch)) | set(parts)
    _poseidos |= {desempacar_pack(i)[0] for i in list(_poseidos) if desempacar_pack(i)[1]}
    # ★ las básicas: SU set (el que eligió al crear, o el deducido — `basico_de`), no cualquiera de la creación:
    #   es lo que manda «Restaurar» y lo mismo que acepta el FF1A
    _basicos = set(basico_de(ch))
    puestas, rechazadas = [], []
    for item in items:
        item = int(item)
        fam = shop_catalog.family(item)
        if not shop_catalog.is_wearable(item) or fam in _MULTISLOT_FAMILIES:
            rechazadas.append(item)
            continue
        if item not in _poseidos and item not in _basicos:
            rechazadas.append(item)
            continue
        for p in ([] if se_suma(item, fam) else
                  [x for x in parts if mismo_lugar(item, x, fam) and x != item and not se_suma(x)]):
            parts.remove(p)
            if p not in _basicos and p not in inv_ids(ch):                      # la que sale NO se pierde
                inv.append({"id": p, "exp": 0})
        if item not in parts:
            parts.append(item)
        puestas.append(item)
    # ★ 12-oct (anonimo03: «mirá, 2 alas»): si la lista trae dos de la misma familia (el cliente mandó un set con dos
    #   alas), la 2.ª reemplaza a la 1.ª en `parts`, pero el eco las llevaba a las DOS y el cliente prendía las dos.
    #   El eco = lo que QUEDÓ puesto.
    puestas = [x for x in puestas if x in parts]
    if puestas:
        db_save_uno(usn, ch)
        log("DB", f"FF7F equip varios usn={usn} {puestas} (rechazadas {rechazadas}) -> parts={parts}")
    return puestas, rechazadas


# ★★★★★ 2026-09-01 — EL `rel5` DE LA COLA DEL FF0C ES EL **Wing Id** DEL PROPIO CLIENTE.
#   Cómo se cerró: primero se vio que ese u32 valía 56 en 5/5 de los paquetes de un jugador con
#   alas y 0/37 sin ellas, así que se mandó 56 fijo... y al jugador le salieron **las alas de la
#   captura** (las de jugador36) en vez de las suyas. O sea que no era una bandera: era un ID.
#   La tabla está en el cliente, en `R2Beat/rnr_script/wing.txt`:
#       <Wing Id="56"  ItemCode="1000513" ItemEffect="1145" FxEffect="393">   "Alas de jugador36"
#       <Wing Id="115" ItemCode="1000690" ItemEffect="1818" FxEffect="528">   "Alas Fenix Duo"
#   El 56 del wire es EXACTAMENTE el Id de las alas que llevaba ese jugador. Confirmado.
#   ⇒ se manda el `Wing Id` que le corresponde al ítem equipado. Sin entrada en la tabla, 0.
# ★ COPIA DE ESCRITORIO: las tablas del cliente se buscan en varios lugares (ver abajo).
PROYECTO_RNR = os.path.join("D:", os.sep, "R2Beat", "client", "Proyecto R2beat 2013",
                            "R2Beat", "rnr_script")


def _tabla_cliente(nombre):
    """Las tablas del cliente (wing.txt = alas, face.txt = caras). Se buscan en varios
    lugares porque esta carpeta se reorganiza seguido y una ruta unica se rompe sola:
    ya paso dos veces que `tablas-cliente/` desaparecio y las alas dejaron de verse.
    El primer lugar es el cliente que vive DENTRO de esta carpeta, que es el natural."""
    base = os.path.dirname(os.path.abspath(__file__))     # `__file__` re-apuntado a la raiz
    # ★ `servidor/tablas-cliente/` va PRIMERO desde el 2026-09-16: las tablas se mudaron adentro
    #   del server (antes estaban partidas en DOS —la raíz y `documentacion/`— y la mitad las leía
    #   `gacha.py` por su cuenta). Se dejan las de siempre detrás, que es la razón de ser de esta
    #   lista: el comentario de arriba avisa que esto ya se rompió dos veces.
    from .ajustes import _DIR_SERVIDOR                                      # noqa: PLC0415
    for cand in (os.path.join(_DIR_SERVIDOR, "tablas-cliente", nombre),
                 os.path.join(base, "R2Beat", "rnr_script", nombre),
                 os.path.join(base, "tablas-cliente", nombre),
                 os.path.join(base, "..", "R2Beat", "rnr_script", nombre),
                 os.path.join(PROYECTO_RNR, nombre)):
        if os.path.isfile(cand):
            return cand
    return os.path.join(base, "R2Beat", "rnr_script", nombre)   # para que el error diga donde deberia estar

WING_TXT = _tabla_cliente("wing.txt")
_WINGS = None


def familia_de(item_id):
    """La familia del `shop_lt` de un ítem (`wardrobe_top`, `aura_summon`, …), o `""`.

    ⚠ Carga el catálogo si hace falta. Sin esto devuelve `"unknown"` para TODO cuando se
    llama desde un script suelto que no arrancó el server, y como `"unknown"` es un valor
    válido nadie se entera: las ranuras del avatar del `FF77`/`FF78` salen vacías y el
    paquete parece bien armado. (El server y la huella lo cargan por otro lado, así que
    ahí nunca se vio el problema.)
    """
    try:
        if not shop_catalog.CATALOG:
            shop_catalog.load()
        return shop_catalog.family(item_id) or ""
    except Exception:
        return ""


def wing_id(item_id):
    """`Wing Id` del cliente para un ítem de alas/aura. 0 si no está en la tabla."""
    global _WINGS
    if _WINGS is None:
        _WINGS = {}
        try:
            txt = open(WING_TXT, "rb").read().decode("cp1252", "replace")
            for m in re.finditer(r'<Wing\s+Id="(\d+)"\s+ItemCode="(\d+)"', txt):
                _WINGS[int(m.group(2))] = int(m.group(1))
            log("DB", f"wing.txt: {len(_WINGS)} alas/auras cargadas de {WING_TXT}")
        except Exception as e:
            log("DB", f"⚠ no pude leer {WING_TXT}: {e!r} — las alas no se van a ver")
    try:
        iid = int(item_id)
    except Exception:
        return 0
    return _WINGS.get(iid) or _WINGS.get(shop_catalog.normalize_id(iid) or 0) or 0


# ★★★★★ 2026-09-01 — LA CARA/OJOS VIAJA IGUAL QUE LAS ALAS, pero en `rel11` y por ItemEffect.
#   Misma pregunta, misma respuesta: el cliente tiene `R2Beat/rnr_script/face.txt`, con
#       <Face Index="81" ItemEffect="669">     -> ItemEffect 669 = ítem 1010302 "Chico sombra"
#   y en la captura los DOS jugadores que traían `rel11 = 81` (jugador12 y jugador13) **no llevaban
#   ningún ítem de cara en la lista**: la cara no va en el array de prendas, va como ÍNDICE en la
#   cola. En los 42 paquetes reales no aparece NI UN ítem `wardrobe_face` en la lista.
#   ⚠ Diferencia con las alas: la tabla de caras mapea por **ItemEffect**, no por ItemCode, así que
#     hay que ir ítem -> ItemEffect (catálogo) -> Index (face.txt).
FACE_TXT = _tabla_cliente("face.txt")
_FACES = None


def face_id(item_id):
    """`Face Index` del cliente para un ítem de cara/ojos. 0 si no está en la tabla."""
    global _FACES
    if _FACES is None:
        _FACES = {}
        try:
            txt = open(FACE_TXT, "rb").read().decode("cp1252", "replace")
            for m in re.finditer(r'<Face\s+Index="(\d+)"\s+ItemEffect="(\d+)"', txt):
                _FACES[int(m.group(2))] = int(m.group(1))     # ItemEffect -> Index
            log("DB", f"face.txt: {len(_FACES)} caras cargadas de {FACE_TXT}")
        except Exception as e:
            log("DB", f"⚠ no pude leer {FACE_TXT}: {e!r} — los ojos no se van a ver")
    try:
        iid = int(item_id)
    except Exception:
        return 0
    # ⚠ La tabla indexa por **ItemEffect**, que no está garantizado único entre familias (a
    #   diferencia de wing.txt, que indexa por ItemCode). El filtro por familia es preventivo:
    #   sin él, cualquier prenda que compartiera ItemEffect con una cara devolvería un índice ajeno.
    if shop_catalog.family(iid) != "wardrobe_face":
        return 0
    d = shop_catalog.CATALOG.get(iid) or shop_catalog.CATALOG.get(
        shop_catalog.normalize_id(iid) or 0) or {}
    return _FACES.get(d.get("effect"), 0) if d else 0


def id_wire(iid):
    """El id tal como lo pone un server que anda: con su código de período si le corresponde."""
    try:
        iid = int(iid)
        if not WIRE_ID_CON_PERIODO or shop_catalog.period_code(iid):
            return iid                                   # apagado, o ya trae código
        if shop_catalog.family(iid) not in WIRE_ID_FAMILIAS:
            return iid
        durs = (shop_catalog.CATALOG.get(iid) or {}).get("durations") or {}
        codigos = [c for c, a in shop_catalog.PERIOD_TO_ATTR.items() if a in durs]
        if len(codigos) == 1:                            # una sola duración -> no hay ambigüedad
            return iid + codigos[0] * 1000
        return iid
    except Exception:
        return iid


def marco_puesto(parts):
    """`(numero, item_id)` del marco de asiento que tiene puesto, o `(0, 0)`.

    ★ El `numero` es el `Index` de `slotpack.txt` y es LO ÚNICO que viaja (`FF0C cola[10]` al
      entrar, `FF15 #11` en vivo). El cliente busca el dibujo con él (`0x50F8C0`), y si la pareja
      está al lado **con el mismo número** y la fila dice `Couple`, pinta el cuadro de pareja y el
      efecto (`0x595430` + `0x527720`). Ver `documentacion/MARCOS_DE_ASIENTO.md`.
    """
    if not shop_catalog.CATALOG:
        shop_catalog.load()
    for p in parts or ():
        try:
            m = shop_catalog.MARCOS.get(int(p))
        except (TypeError, ValueError):
            continue
        if m:
            return int(m["numero"]) & 0xFF, int(p)
    return 0, 0


def tarjeta_puesta(parts):
    """El `index` de `namecard.xml` de la tarjeta de nombre puesta («Slot para Game id …»), o 0.

    ★ Viaja en el `FF78` (la ficha que abre la «i»): 2º de los cuatro `u8` tras las siete
      ranuras -> `R+0xE8` -> `0x451621` -> el recuadro del apodo (`0x450840`). Para uno mismo el
      cliente la aplica solo al equiparla (`0x48E830` -> `0x485840` -> `[yo+0xD16]`).
    """
    if not shop_catalog.CATALOG:
        shop_catalog.load()
    for p in parts or ():
        try:
            t = shop_catalog.TARJETAS.get(int(p))
        except (TypeError, ValueError):
            continue
        if t:
            return int(t) & 0xFF
    return 0


def cupones_de_partida(parts):
    """Los ítems ACTIVADOS que viajan en el `FF80` (ver `FF80_CUPONES_DE_PARTIDA`)."""
    from .ajustes import FAMILIAS_EN_FF80
    if not shop_catalog.CATALOG:
        shop_catalog.load()
    out = []
    for p in parts or ():
        try:
            if shop_catalog.family(int(p)) in FAMILIAS_EN_FF80:
                out.append(int(p))
        except (TypeError, ValueError):
            continue
    return out


def es_mascota_de_pareja(item_id):
    """¿Es una mascota de PAREJA? (`pet.xml`: `PetType="2"`, ítem = 600000 + `Id % 1000`)."""
    if not shop_catalog.CATALOG:
        shop_catalog.load()
    try:
        return int(item_id) in shop_catalog.MASCOTAS_PAREJA
    except (TypeError, ValueError):
        return False


def es_marco_de_pareja(item_id):
    try:
        return bool((shop_catalog.MARCOS.get(int(item_id)) or {}).get("pareja"))
    except (TypeError, ValueError):
        return False


def categoria_worn(item_id):
    """Cómo clasifica el cliente una pieza del worn. Devuelve 0..99."""
    return (int(item_id) % 10_000_000) // 100_000


def worn_seguro(worn, motivo=""):
    """Saca del worn lo que el cliente no puede clasificar sin salirse del arreglo de pila."""
    limpio = [i for i in worn if categoria_worn(i) < CATEGORIAS_WORN]
    if len(limpio) != len(worn):
        fuera = [(i, categoria_worn(i)) for i in worn if categoria_worn(i) >= CATEGORIAS_WORN]
        log("LOBBY", f"  ⛔ worn FILTRADO{(' ' + motivo) if motivo else ''}: {fuera} — "
                     f"categoría >= {CATEGORIAS_WORN}, el cliente escribiría fuera de la pila")
    return limpio


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★ ANILLOS DE PAREJA Y JOYAS DE AMISTAD — `rnr_script/ring.txt` (2026-09-12)
#
#   Es **la misma tabla que lee el cliente**, y de acá sale todo lo que el juego necesita para
#   dibujar una pareja. El propio cliente traduce el ítem que clickeás a su `ChargeId`, y si no
#   está en esta tabla devuelve 0 y **ni siquiera abre el popup de proponer**.
#
#   ⛔⛔ LA TRAMPA, y es exactamente la que el proyecto ya tiene anotada como *"la receta ajena no
#     aplica a este build"*: **el CBT busca `<Ring …>` y el 2013 NO TIENE NI UNO.** Acá las
#     etiquetas son `<Couple>` (20) y `<Friend>` (4). Calcar el lector del CBT habría devuelto una
#     tabla VACÍA, y el síntoma —toda propuesta rechazada con *"no tiene un anillo válido"*— es
#     idéntico al de "el archivo no existe". Medido antes de escribir una línea.
#
#   ★★★★★ Y EL CHARGEID NO SE CALCULA. Con dos muestras parecía `Index + 6000`:
#         30216 -> 36216   ·   30478 -> 36478
#       pero el **Anillo de corazón lo rompe**:  30027 -> **31027**  (+1000)
#     ⇒ Es un número escrito a mano, fila por fila. Programar la "fórmula" habría hecho fallar ese
#       anillo con un síntoma sin pistas. El CBT ya lo había dejado anotado.
#
#   Los otros tres campos son los que dibujan la pareja, **y los dibuja el CLIENTE solo**:
#       RoomFx      = el efecto del anillo en la sala
#       SlotBackId  = ★ el fondo/color del slot   (es un FRAME de `rnr_room_image/02.spr`)
#       MsgId       = el renglón del anuncio
#     ⇒ Por eso no hay que "mandar el color": alcanza con que el cliente sepa QUÉ anillo es.
# ══════════════════════════════════════════════════════════════════════════════════════════════
RING_TXT = _tabla_cliente("ring.txt")
_ANILLOS = None          # item_id -> {"charge", "roomfx", "slotback", "msgid", "tipo"}
_POR_CHARGE = None       # ChargeId -> item_id


def _cargar_anillos():
    global _ANILLOS, _POR_CHARGE
    _ANILLOS, _POR_CHARGE = {}, {}
    try:
        raw = open(RING_TXT, "rb").read().decode("cp1252", "replace")
    except OSError as e:
        log("SHOP ", f"  ⚠ no pude leer {RING_TXT}: {e} -> NADIE va a poder proponer pareja")
        return
    # ★ `<Couple>` = anillos de pareja · `<Friend>` = joyas de amistad del alma.
    #   ⚠ Los `<Friend>` NO tienen ChargeId: su `Id` (1|3|4) es lo que viaja. Son dos sistemas
    #     distintos, no el mismo con otro número.
    for tipo, pat in (("couple", r"<Couple\s+([^>]*?)>"), ("friend", r"<Friend\s+([^>]*?)>")):
        for m in re.finditer(pat, raw):
            at = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            _idx = at.get("Index", "")
            if not _idx.isdigit():
                continue
            _iid = int(_idx)
            _ch = int(at["ChargeId"]) if at.get("ChargeId", "").isdigit() else 0
            _ANILLOS[_iid] = {
                "charge":   _ch,
                "roomfx":   int(at["RoomFx"]) if at.get("RoomFx", "").isdigit() else 0,
                "slotback": int(at["SlotBackId"]) if at.get("SlotBackId", "").isdigit() else 0,
                "msgid":    int(at["MsgId"]) if at.get("MsgId", "").isdigit() else 0,
                "id":       int(at["Id"]) if at.get("Id", "").isdigit() else 0,
                "tipo":     tipo,
            }
            if _ch:
                _POR_CHARGE[_ch] = _iid
    log("SHOP ", f"  ★ ANILLOS: {len(_ANILLOS)} de ring.txt "
                 f"({sum(1 for v in _ANILLOS.values() if v['tipo'] == 'couple')} de pareja, "
                 f"{sum(1 for v in _ANILLOS.values() if v['tipo'] == 'friend')} del alma)")


def anillo_de(item_id):
    """La fila de `ring.txt` de ese ítem, o `{}`."""
    if _ANILLOS is None:
        _cargar_anillos()
    # ⚠ Tolera basura a propósito: la llaman desde recorridos de inventario, donde un elemento
    #   puede venir como dict, None o texto. Reventar acá tumbaría el recorrido entero por un
    #   ítem raro — y este dato es un adorno, no algo por lo que valga la pena caerse.
    try:
        _k = int(item_id)
    except (TypeError, ValueError):
        return {}
    return dict(_ANILLOS.get(_k) or {})


def anillo_por_charge(charge):
    """El **item_id** del anillo cuyo `ChargeId` es ése, o 0.

    ★ Es la traducción que hace falta para el enlace en la sala: por el cable viaja el ChargeId
      (es lo que el cliente manda al proponer), pero el que dibuja el anillo quiere el **Index**.
    """
    if _POR_CHARGE is None:
        _cargar_anillos()
    return int(_POR_CHARGE.get(int(charge), 0))


def es_anillo_de_pareja(item_id):
    return anillo_de(item_id).get("tipo") == "couple"
