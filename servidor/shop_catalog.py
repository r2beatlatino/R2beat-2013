# -*- coding: cp1252 -*-
"""shop_catalog.py -- Fuente de verdad de la tienda R2Beat 2013.

Carga server/shop_lt.txt (codificado cp1252) y expone una API por Index para que el server NO tenga que
hardcodear item por item. Cada item declara su comportamiento via ShopIndex + ItemEffect + atributos
(PackCount=cargas, ExtraType=SUMMON, Seed, setitem=pack). Ver docs/PLAN_TIENDA.md.

★ VIVE EN `servidor/` desde el 2026-09-16, con su `shop_lt.txt` al lado (lo ubica por su propio
  `__file__`, así que los dos viajan juntos). Antes estaba suelto en la raíz.

Uso:
    from servidor import shop_catalog as cat     # desde afuera
    from . import shop_catalog as cat            # desde otro módulo de `servidor/`
    cat.load()                      # una vez al arrancar el server
    cat.exists(320565)              # True/False
    cat.get(320565)                 # dict con todos los campos
    cat.normalize_id(10329545)      # -> 10320545 (quita el codigo de periodo del digito de MILES)
    cat.family(320565)              # 'wardrobe_top'
    cat.is_wearable(320565)         # True

Ejecutado directo (`python shop_catalog.py`) imprime estadisticas de auto-test.
"""
import os, re

_HERE = os.path.dirname(os.path.abspath(__file__))
SHOP_LT = os.path.join(_HERE, "shop_lt.txt")

# Index(int) -> dict(campos del <Item>)
CATALOG = {}
_LOADED = False

# ItemIndex(int) -> {"numero": SlotPack Index, "pareja": bool}   (de `tablas-cliente/slotpack.txt`)
MARCOS = {}
SLOTPACK_TXT = os.path.join(_HERE, "tablas-cliente", "slotpack.txt")
# itemcode(int) -> index de la tarjeta de nombre   (de `tablas-cliente/namecard.xml`)
TARJETAS = {}
NAMECARD_XML = os.path.join(_HERE, "tablas-cliente", "namecard.xml")
# los Modos Héroe   (de `tablas-cliente/setitem.txt`: el contenido del «Pack de 4 modos héroe»)
MODOS_HEROE = set()
# las Profecías   (las de `ajustes.PROFECIAS` que están en la tienda)
PROFECIAS = set()
SETITEM_TXT = os.path.join(_HERE, "tablas-cliente", "setitem.txt")


def _leer_contenido_de_pack(pack, path=None):
    """Los `Item` que `setitem.txt` pone adentro del `<setItem ItemIndex="pack">`."""
    try:
        with open(path or SETITEM_TXT, encoding="cp1252", errors="replace") as f:
            txt = f.read()
    except OSError:
        return set()
    m = re.search(r'<setItem\b[^>]*ItemIndex\s*=\s*"%d"[^>]*>(.*?)</setItem>' % int(pack), txt, re.S)
    if not m:
        return set()
    return {int(x) for x in re.findall(r'\bItem\s*=\s*"(\d+)"', m.group(1))}


def contenido_de_set(pack, path=None):
    """Lo que trae un pack de ESCAPARATE (`setitem="1"` en la tienda): `[(ítem, id_de_compra), …]`.

    Sale de `setitem.txt` del cliente: `<Wear|nonWear Item="1000206" Itemid="1002206">`. El `Itemid`
    es el id de COMPRA, con el plazo en el dígito de las miles (`period_code`), igual que lo que
    manda el cliente al comprar suelto: 1002206 = el ítem 1000206 por 30 días.
    `[]` si no es un set o la tabla no está.
    """
    try:
        with open(path or SETITEM_TXT, encoding="cp1252", errors="replace") as f:
            txt = f.read()
    except OSError:
        return []
    m = re.search(r'<setItem\b[^>]*ItemIndex\s*=\s*"%d"[^>]*>(.*?)</setItem>' % int(pack), txt, re.S)
    if not m:
        return []
    return [(int(a), int(b)) for a, b in
            re.findall(r'<(?:Wear|nonWear)\b[^>]*\bItem\s*=\s*"(\d+)"[^>]*\bItemid\s*=\s*"(\d+)"', m.group(1))]


def es_set(idx):
    """¿Es un pack de escaparate? (`setitem="1"` en `shop_lt.txt`)."""
    _ensure()
    return (CATALOG.get(int(idx)) or {}).get("setitem") == "1"


# los ítems de las mascotas de PAREJA   (de `tablas-cliente/pet.xml`)
MASCOTAS_PAREJA = set()
PET_XML = os.path.join(_HERE, "tablas-cliente", "pet.xml")


def _leer_mascotas_pareja(path=None):
    """`pet.xml` del cliente: las `<Pet Id=.. PetType="2">` son de PAREJA, en dos versiones
    (chico `Id`, chica `Id + 1000`, p. ej. 99 y 1099). El ítem de la tienda es `600000 + Id % 1000`
    («ggomi y Yami» = 600099). ⚠ Medido: los 13 de la tienda con nombre de par («X y Y», «X & Y»)
    son exactamente los `PetType=2`, sin sobrantes ni faltantes."""
    try:
        with open(path or PET_XML, encoding="cp949", errors="replace") as f:
            txt = f.read()
    except OSError:
        return set()
    out = set()
    for m in re.finditer(r"<Pet\b(.*?)>", txt, re.S):
        a = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', m.group(1)))
        if a.get("PetType") == "2" and a.get("Id", "").isdigit():
            out.add(600000 + int(a["Id"]) % 1000)
    return out


def _leer_namecard(path=None):
    """`namecard.xml` del cliente: `<namecard index="2" itemcode="1000411" roomspr=.. roomcut=..>`.

    ★ La «tarjeta de nombre» (los «Slot para Game id …»): el fondo del recuadro del apodo. El
      `index` es lo que viaja (el `FF78`, 2º de los cuatro `u8`); el dibujo lo pone el cliente.
    """
    out = {}
    try:
        with open(path or NAMECARD_XML, encoding="cp1252", errors="replace") as f:
            txt = f.read()
    except OSError:
        return out
    for m in re.finditer(r"<namecard\b([^>]*)>", txt):
        a = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', m.group(1)))
        try:
            out[int(a["itemcode"])] = int(a["index"])
        except (KeyError, ValueError):
            continue
    return out


def _leer_slotpack(path=None):
    """`slotpack.txt` del cliente: `<SlotPack Index="18" ItemIndex="1000380" ... Couple="1">`.

    ★ El `Index` es **el número que manda el server** (lo dice el comentario coreano del propio archivo:
      "el número que se recibe del servidor, puede repetirse").
      Es lo único que viaja: el dibujo, el cuadro de pareja y el efecto los pone el cliente.
    ⚠ Si la tabla no está, devuelve `{}` y los marcos siguen siendo `megaphone` como antes — no
      rompe la tienda, sólo no se dibujan.
    """
    out = {}
    try:
        with open(path or SLOTPACK_TXT, encoding="cp1252", errors="replace") as f:
            txt = f.read()
    except OSError:
        return out
    for m in re.finditer(r"<SlotPack\b([^>]*)>", txt):
        a = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', m.group(1)))
        try:
            out[int(a["ItemIndex"])] = {"numero": int(a["Index"]), "pareja": a.get("Couple") == "1"}
        except (KeyError, ValueError):
            continue
    return out

# ---- Familias (comportamiento del server). Derivadas de ShopIndex; ver PLAN_TIENDA.md §2-3 ----
# wardrobe_* y skin/wand/aura/fullset/head_accessory/pet_worn ocupan SLOT de apariencia (vestibles).
# El resto NO se viste: se consumen / activan / otorgan por rutas FF propias.
WEARABLE_FAMILIES = {
    "wardrobe_hair", "wardrobe_top", "wardrobe_bottom", "wardrobe_shoes",
    "wardrobe_hand", "wardrobe_face", "wardrobe_couplelook",
    "head_accessory", "skin", "wand", "aura_summon", "fullset", "pet",
    "slot_pack", "namecard", "hero_mode", "prophecy",
    # ★ (141) 30-oct: las CEREMONIAS y las poses de pareja (0504 / las de 0507 de pareja_poses.json). Se marcan y tienen
    #   que quedar PUESTAS: viajan en lo puesto (el FF0C) y de ahí las ven los demás — la entrada a la sala
    #   (`entrada_de_sala`) y la pose de pareja (`0x5285D0` lee lo puesto del otro). Antes no se guardaban: el FF1A
    #   contestaba y `db_equip` las descartaba por «no vestibles» (y al volver a entrar se perdía la marca).
    "dance_emote",
    # ★ (142) 30-oct: las MONTURAS (monturas.json): se marcan y quedan puestas; una a la vez (su familia = su lugar).
    "montura",
}
# sub-categoria de guardarropa por ULTIMO digito del ShopIndex (03x/04x/01x/02x)
_WARDROBE_SUB = {
    "1": "wardrobe_hair", "2": "wardrobe_top", "3": "wardrobe_bottom", "4": "wardrobe_shoes",
    "5": "wardrobe_hand", "6": "wardrobe_face", "7": "wardrobe_couplelook",
}
# ShopIndex exacto -> familia (los que no son guardarropa 01/02/03/04)
_SHOP_FAMILY = {
    "0501": "head_accessory",
    "0502": "gift_levelup",      # regalo por subir de nivel (consumible)
    "0503": "coupon_buff",       # Coin Up / EXP Up
    "0504": "dance_emote",
    "0505": "pet",
    "0506": "megaphone",         # con PackCount = cargas
    "0507": "ring_couple",
    "0508": "friendship_gem",
    "0509": "skin",
    "0600": "seasonal",
    "0905": "wand",
    "1007": "aura_summon",       # ExtraType=SUMMON
    "1301": "capsule_gacha",
    "1401": "fullset",
    "2211": "room_key",
}


def family(idx):
    """Devuelve la familia (str) de un Index, o 'unknown'."""
    it = CATALOG.get(int(idx))
    if not it:
        return "unknown"
    return it["family"]


def sexo_de(idx):
    """★ 28-oct (132): 0 = de chico · 1 = de chica · None = para los dos. La ropa, por su TIENDA (los botones ♂/♀ de la
    tienda del juego muestran la `03xx` o la `04xx`); lo demás, por el dígito de las decenas de mil del id base (medido
    contra el catálogo: 4447 de la 03 tienen un 1, 4934 de la 04 un 2; 4/5 son los «(H)/(M)», 0/3 los de los dos)."""
    it = CATALOG.get(int(idx))
    si = (it or {}).get("shop_index", "")[:2]
    if si == "03":
        return 0
    if si == "04":
        return 1
    d = (int(idx) % 1000000) // 10000 % 10
    return 0 if d in (1, 4) else 1 if d in (2, 5) else None


def _derive_family(shop_index):
    si = (shop_index or "").strip()
    if len(si) == 4 and si[:2] in ("01", "02", "03", "04"):
        return _WARDROBE_SUB.get(si[3], "wardrobe_top")
    return _SHOP_FAMILY.get(si, "misc")


def _to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def load(path=None, verbose=False):
    """Parsea shop_lt.txt -> CATALOG. Idempotente."""
    global _LOADED
    CATALOG.clear()
    p = path or SHOP_LT
    with open(p, encoding="cp1252") as f:
        for line in f:
            if "Index=" not in line:
                continue
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', line))
            m = re.search(r'(?<!Shop)Index="(\d+)"', line)  # Index real (no ShopIndex)
            if not m:
                continue
            idx = int(m.group(1))
            shop_index = attrs.get("ShopIndex", "")
            # precios por duracion presentes (P7/P30/P365/P100/PI/PN/...) -> {clave: precio}
            durations = {k: _to_int(v) for k, v in attrs.items()
                         if re.fullmatch(r'P\d+|PI|PN|P', k)}
            CATALOG[idx] = {
                "index": idx,
                "name": attrs.get("Name", ""),
                "shop_index": shop_index,
                "family": _derive_family(shop_index),
                "effect": _to_int(attrs.get("ItemEffect"), None),
                "cash": attrs.get("Cash") == "1",
                "pack_count": _to_int(attrs.get("PackCount"), 0),   # cargas (0 = no aplica)
                "pack_index": _to_int(attrs.get("PackIndex"), 0),
                "extra_type": attrs.get("ExtraType"),               # ej 'SUMMON'
                "extra_value": _to_int(attrs.get("ExtraValue"), 0),
                "seed": attrs.get("Seed") == "1",
                "setitem": attrs.get("setitem") or attrs.get("Setitem"),
                "durations": durations,
                "raw": attrs,
            }
    # ★ LOS MARCOS DE ASIENTO (2026-09-23). Viven en la pestaña `0506` junto a los megáfonos, y por
    #   el ShopIndex salían `megaphone` = consumible con cargas. Los declara la tabla del CLIENTE
    #   (`slotpack.txt`): lo que está ahí se equipa (uno por jugador) y se dibuja en la sala.
    MARCOS.clear()
    MARCOS.update(_leer_slotpack())
    for _it in MARCOS:
        if _it in CATALOG:
            CATALOG[_it]["family"] = "slot_pack"
    # ★ Y LAS TARJETAS DE NOMBRE, mismo caso y misma pestaña (`namecard.xml`).
    TARJETAS.clear()
    TARJETAS.update(_leer_namecard())
    for _it in TARJETAS:
        if _it in CATALOG:
            CATALOG[_it]["family"] = "namecard"
    # ★ Y LOS MODOS HÉROE: se ACTIVAN (no se visten) y se pueden combinar. Ver `FF80_CUPONES_DE_PARTIDA`.
    try:
        from .ajustes import PACK_MODOS_HEROE, MODOS_HEROE_SUELTOS
    except ImportError:                                          # suelto, sin el paquete
        PACK_MODOS_HEROE, MODOS_HEROE_SUELTOS = 491, (1000210,)
    MODOS_HEROE.clear()
    MODOS_HEROE.update(i for i in _leer_contenido_de_pack(PACK_MODOS_HEROE) if i in CATALOG)
    # ★ (136) y los que no vienen en el pack (el Modo Aleatorio)
    MODOS_HEROE.update(i for i in MODOS_HEROE_SUELTOS if i in CATALOG)
    for _it in MODOS_HEROE:
        CATALOG[_it]["family"] = "hero_mode"
    # ★ Y LAS PROFECIAS, igual: se activan (no se visten) y se combinan. Ver `PROFECIAS`.
    try:
        from .ajustes import PROFECIAS as _PROF
    except ImportError:                                          # suelto, sin el paquete
        _PROF = {}
    PROFECIAS.clear()
    PROFECIAS.update(i for i in _PROF if i in CATALOG)
    for _it in PROFECIAS:
        CATALOG[_it]["family"] = "prophecy"
    # ★★ (141) 30-oct · LAS POSES DE PAREJA viven en la pestaña «Pareja» (`0507`, anonimo03) pero NO son anillos: se marcan
    #   como las ceremonias (`dance_emote`) y chocan con ellas, como en el VFUN (overlap.txt). Con la familia de la pestaña
    #   (`ring_couple`) marcar una pose le sacaba el anillo a la pareja. La lista: `tablas-cliente/pareja_poses.json`
    #   (la escribe `herramientas/poses_pareja_crear.py`). Ver `documentacion/PAREJA_POSES.md`.
    POSES_PAREJA.clear()
    POSES_PAREJA.update(i for i in _leer_poses_pareja() if i in CATALOG)
    for _it in POSES_PAREJA:
        CATALOG[_it]["family"] = "dance_emote"
    # ★ (142) 30-oct · LAS MONTURAS (`tablas-cliente/monturas.json`, de `herramientas/monturas_crear.py`): viven en la 0504
    #   (como en el VFUN) pero NO son ceremonias — su propio lugar, una a la vez (el grupo propio de overlap.txt).
    for _it in _leer_json_codigos("monturas.json"):
        if _it in CATALOG:
            CATALOG[_it]["family"] = "montura"
    # ★ Y LAS MASCOTAS DE PAREJA (siguen siendo `pet`: se equipan igual que cualquier mascota).
    # * LA TIENDA SEED (ShopIndex 0600) NO DICE QUE ES CADA ITEM (2026-09-24). anonimo03: *"al comprar
    #   un item de la tienda seed, no llega al inventario"*. Son alas, pelos y varas comunes, pero
    #   la pestania no dice cuales, y quedaban todos en `seasonal` (no vestible): el cliente los
    #   auto-equipa al comprar (FF1A), el server contestaba "equipado" y NO lo guardaba puesto.
    #   => cada uno toma la familia de SUS IGUALES del resto de la tienda. Ver `familia_seed`.
    for _it, _fam in familias_seed().items():
        CATALOG[_it]["family"] = _fam
    MASCOTAS_PAREJA.clear()
    MASCOTAS_PAREJA.update(i for i in _leer_mascotas_pareja() if i in CATALOG)
    _LOADED = True
    if verbose:
        print(f"[shop_catalog] {len(CATALOG)} items cargados de {p}")
    return CATALOG


POSES_PAREJA = set()


def _leer_json_codigos(nombre):
    """Los códigos (las claves) de un `tablas-cliente/<nombre>`; vacío si no está."""
    try:
        import json                                                     # noqa: PLC0415
        return {int(k) for k in json.load(open(os.path.join(_HERE, "tablas-cliente", nombre)))}
    except (OSError, ValueError):
        return set()


def _leer_poses_pareja():
    """Los códigos de `tablas-cliente/pareja_poses.json` ({código: Id de la pose}); vacío si no está."""
    try:
        import json                                                     # noqa: PLC0415
        return {int(k) for k in json.load(open(os.path.join(_HERE, "tablas-cliente", "pareja_poses.json")))}
    except (OSError, ValueError):
        return set()


WING_TXT = os.path.join(_HERE, "tablas-cliente", "wing.txt")
SHOP_SEED = "0600"


def familias_seed(path_wing=None):
    """`{item: familia}` para los items de la Tienda SEED que se pueden clasificar. Todo DERIVADO:

      * un ala (su ItemCode esta en `wing.txt` del cliente) -> la familia de las OTRAS alas de la
        tienda (hoy las 12 son `aura_summon`);
      * el resto -> la familia de los items con el MISMO prefijo de numero (`id // 10000`: 91 =
        mano de chico, 92 = de chica, 21/22 y 1021/1022 = pelo…) fuera de la SEED, SOLO si una
        familia vestible junta al menos el 95% (en el 21 hay 170 pelos y 3 "look de pareja").
        Si no hay acuerdo, se deja como estaba (`seasonal`).
    Las campanas y llaves "S" (774-777) no tienen iguales vestibles: quedan como estaban.
    """
    from collections import Counter
    try:
        with open(path_wing or WING_TXT, encoding="cp1252", errors="replace") as f:
            alas = {int(x) for x in re.findall(r'ItemCode="(\d+)"', f.read())}
    except OSError:
        alas = set()
    fuera = {i: c for i, c in CATALOG.items() if c.get("shop_index") != SHOP_SEED}
    fam_alas = Counter(c["family"] for i, c in fuera.items() if i in alas)
    por_prefijo = {}
    for i, c in fuera.items():
        por_prefijo.setdefault(i // 10000, Counter())[c["family"]] += 1
    out = {}
    for i, c in CATALOG.items():
        if c.get("shop_index") != SHOP_SEED:
            continue
        votos = fam_alas if i in alas else por_prefijo.get(i // 10000, Counter())
        if not votos:
            continue
        fam, n = votos.most_common(1)[0]
        if fam in WEARABLE_FAMILIES and n >= 0.95 * sum(votos.values()):
            out[i] = fam
    return out


def _ensure():
    if not _LOADED:
        load()


def exists(idx):
    _ensure()
    return int(idx) in CATALOG


def get(idx):
    _ensure()
    return CATALOG.get(int(idx))


def normalize_id(raw):
    """Convierte un id de COMPRA al Index real del catalogo.

    El id de compra = Index con el digito de MILES (10^3) usado como codigo de periodo/duracion; el Index
    real lo tiene en 0 (verificado: los 2866 Index del catalogo tienen miles=0). Estrategia:
      1) si raw ya existe tal cual -> raw (ids de creacion ya tienen miles=0, idempotente).
      2) si no, poner el digito de miles en 0 y revalidar.
      3) si tampoco existe -> None (id desconocido).
    """
    _ensure()
    raw = int(raw)
    if raw in CATALOG:
        return raw
    z = raw - (raw // 1000 % 10) * 1000
    if z in CATALOG:
        return z
    return None


def period_code(raw):
    """El digito de MILES del id de compra = codigo de periodo/duracion (0 si permanente/creacion)."""
    return (int(raw) // 1000) % 10


def is_wearable(idx):
    """True si el item ocupa un slot de apariencia (ropa/cara/mano/alas/mascota/aura/set/skin)."""
    return family(idx) in WEARABLE_FAMILIES


# ---- Fase B: periodo (digito de MILES del id de compra) -> atributo de precio/duracion del catalogo ----
# Medido en vivo 2026-07-11 (modo DISCOVER_DURATION): compre el mismo tipo a distintas duraciones y correlacione.
#   1=P7(7d)  2=P30(30d)  9=PI(permanente)  5=P(pack/cantidad x10/x100)  6=PN(uso unico: llaves/anillo/gameid)
# PENDIENTE confirmar: 3/4 = duraciones largas (P100/P365). Se leen del log normal (dur=) al comprar una.
PERIOD_TO_ATTR = {1: "P7", 2: "P30", 9: "PI", 5: "P", 6: "PN"}
ATTR_DAYS = {"P1": 1, "P3": 3, "P7": 7, "P15": 15, "P30": 30, "P90": 90,
             "P100": 100, "P180": 180, "P365": 365}


def duration_days(period):
    """Dias de duracion para un codigo de periodo. None = permanente / consumible (sin expiry por tiempo).
    PI(permanente), P(pack), PN(uso unico) -> None. Codigo desconocido -> None (se trata como permanente)."""
    attr = PERIOD_TO_ATTR.get(int(period))
    if attr in ATTR_DAYS:
        return ATTR_DAYS[attr]
    return None  # PI / P / PN / desconocido -> sin expiry por tiempo


if __name__ == "__main__":
    import collections
    load(verbose=True)
    fam = collections.Counter(it["family"] for it in CATALOG.values())
    print("\n=== items por familia ===")
    for f, n in fam.most_common():
        wear = " (vestible)" if f in WEARABLE_FAMILIES else ""
        print(f"  {f:22} {n:4}{wear}")
    print("\n=== pruebas normalize_id ===")
    for raw, name in [(10329545, "Camiseta Bruja Rosa"), (10429373, "Falda Bruja Rosa"),
                      (10522236, "Pantuflas R2Star"), (529644, "Botas Joya"),
                      (220585, "Cabello creacion"), (999999999, "desconocido")]:
        n = normalize_id(raw)
        it = get(n) if n else None
        print(f"  {raw:>10} -> {str(n):>10}  fam={family(n) if n else '-':16} {it['name'] if it else 'None'}")
