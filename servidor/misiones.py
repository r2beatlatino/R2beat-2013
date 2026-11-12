# -*- coding: utf-8 -*-
"""misiones — las 19 misiones: alta del personaje, grados, premios y el cartel.

Qué hay acá:
  · el alta de un personaje nuevo (`db_create_char`): es lo que le fija las misiones y
    la licencia iniciales, por eso vive con las misiones y no en `basedatos`
  · marcar una misión como hecha, por id o por máscara (`db_add_mision*`)
  · el premio: elegir la pieza, ajustarle el género y entregarla
  · el grado (S/A/B/…) y su reenvío al reconectar (`replay_misiones`)

La tabla de las 19 misiones —id, máscara, nivel y premio— está en
`documentacion/mapeo_misiones.md`, que es EL documento del tema.

★ Cada misión pide su canción por ÍNDICE FIJO (`Music="519"` en `rnr_script/mission/*.txt`
  del cliente). Esos índices no se pueden reusar al importar música: la lista está en
  `taller/importador2013/importar2013.py` (constante `MISIONES`).
"""
import json
import time

from . import shop_catalog

from .ajustes import (
    CUENTA_NUEVA,
    LECCIONES,
    MASCARA_DE_MISION,
    ORDEN_GRADOS,
    PREMIOS_MISION,
    PREMIO_SET_DIAS,
    RECUADRO_DESDE_WIRE,
    SETS_POR_MISION,
    SETS_PREMIO_MISION,
)
from .basedatos import (
    db_add_exp,
    db_add_inventory,
    db_get_char,
    db_get_grados,
    db_get_nibbles,
    db_load,
    db_marcar_premio,
    db_premio_cobrado,
    db_save,
    db_save_uno,
)
from .catalogo import desempacar_pack
from .gacha import genero_del_jugador
from .progresion import licencia_actual, nivel_de_exp
from .registro import log


def db_create_char(usn, char):
    # ★ 2026-07-31: inicializar EXPLÍCITO lo que define el arranque de una cuenta. Antes el char nuevo
    #   se guardaba con sólo char_id/nick/parts y todo lo demás salía de los DEFAULTS repartidos por el
    #   código — y uno de ellos era `exp = 20000` = **nivel 5**. Un personaje virgen tiene que nacer en
    #   CERO y que se vea en la DB, no depender de un default escondido.
    char.setdefault("exp", 0)
    char.setdefault("rcoin", 0)
    char.setdefault("licencia", 0)
    # ★ la plantilla PISA los ceros de arriba (copy() por campo: si no, todas las cuentas
    #   compartirían la MISMA lista de misiones y editar una las editaría a todas)
    import copy as _copy
    for _k, _v in CUENTA_NUEVA.items():
        char[_k] = _copy.deepcopy(_v)
    db_save_uno(usn, char)      # ★ 2026-09-05: era db_load()+db_save() = los 4806 para guardar UNO
    log("DB", f"personaje GUARDADO usn={usn}: {char}")
    if CUENTA_NUEVA:
        log("DB", f"  ★ nace con la plantilla: nivel {nivel_de_exp(char['exp'])}, "
                  f"licencia {char.get('licencia')} (banda {licencia_actual(usn)[0]!r})")
def grupo_y_peso(mask):
    """(índice de grupo 0..2, valor que debe alcanzar ese nibble) para una máscara, o None si esa
    máscara NO se otorga por nibbles (licencias, tutoriales 0xF00X, lecciones 6-8, y la huérfana 5)."""
    if not mask or (mask & 0x0F00) == 0x0F00 or mask >= 0xF000 or mask in LECCIONES or mask == 5:
        return None
    if mask >= 0x100:
        return 2, mask >> 8
    if mask >= 0x10:
        return 1, mask >> 4
    return 0, mask                       # 1..4 = la cadena de historia

def db_add_mision_por_mascara(usn, mask):
    """★ Registra una misión de la que sabemos la MÁSCARA pero NO el id (las de `id 0` en
    `MISIONES_2013`, que no viajan por `FF125`). La máscara llega en el pedido del `FF3A` de FIN.
    Recalcula los nibbles reusando la misma lógica de `db_add_mision`."""
    mask = int(mask or 0)
    if grupo_y_peso(mask) is None:               # licencias/tutoriales/lecciones: no van por nibble
        return db_get_nibbles(usn)
    # ★ 2026-09-05: `d` se arma con UN personaje en vez de leer los 4806. El resto del cuerpo
    #   sigue usando `d[k]` igual, y `db_save(d)` con un solo elemento escribe sólo ése.
    k = str(usn); _ch = db_get_char(usn)
    if not _ch:
        return db_get_nibbles(usn)
    d = {k: _ch}
    ms = d[k].setdefault("misiones_mascaras", [])
    if mask not in ms:
        ms.append(mask)
    db_save(d)
    return db_add_mision(usn, -1)                # -1 = id inexistente: sólo dispara el recálculo


def db_add_mision(usn, mid, grupo=None):
    """★ Registra la misión `mid` como HECHA y recalcula el nibble de su grupo.
    ⚠⚠ DOS ERRORES CORREGIDOS ACÁ, los dos por no tener la tabla del cliente:
      1) CONTAR estaba mal: rehacer una misión la sumaba dos veces. -> conjunto de ids.
      2) ★ Y contar **seguía** estando mal aunque fuera idempotente: el bucle del login otorga las
         máscaras **1..n consecutivas**, así que el nibble no es "cuántas hice" sino **hasta qué
         máscara llegué**. Las máscaras del grupo 1 son 1=Tutorial, 2=Ritmo, 3=King, 4=Anillo,
         5=Tutorial-repetir, 6/7=¡Repasemos!, 8=Velocidades — o sea el orden de las máscaras NO es
         el orden de los ids. Con ids {10, 20} (máscaras 1 y 5) el contador daba n0=2, que otorga las
         máscaras 1 y 2: marcaba "Ritmo de la competencia" (que no se jugó) y dejaba la id 20 en
         "reto". Es exactamente el síntoma que se vio. ⇒ **nibble = MÁXIMO peso, no cantidad**.
    `grupo` se ignora (queda por compatibilidad): el grupo sale de la máscara de la misión."""
    # ★ 2026-09-05: idem — un personaje, no los 4806.
    k = str(usn); _ch = db_get_char(usn)
    if not _ch:
        return db_get_nibbles(usn)
    d = {k: _ch}
    hechas = d[k].setdefault("misiones_hechas", [[], [], []])
    while len(hechas) < 3:
        hechas.append([])
    mask = MASCARA_DE_MISION.get(int(mid))
    gp = grupo_y_peso(mask) if mask else None
    if gp is not None:
        g, _peso = gp
        if mid not in hechas[g]:
            hechas[g].append(mid)
    elif mask in LECCIONES:                     # lección de la escuela -> [player+0x335], no nibble
        lec = d[k].setdefault("lecciones", [])
        if mid not in lec:
            lec.append(mid)
    # el nibble de cada grupo = el PESO MÁS ALTO alcanzado en ese grupo (avance lineal, no cantidad)
    n = [0, 0, 0]
    for g in range(3):
        for x in hechas[g]:
            gp2 = grupo_y_peso(MASCARA_DE_MISION.get(int(x), 0) or 0)
            if gp2 and gp2[0] == g:
                n[g] = max(n[g], min(gp2[1], 0xF))
    for m in d[k].get("misiones_mascaras", []):     # ★ las registradas por MÁSCARA (sin id conocido)
        gp3 = grupo_y_peso(int(m))
        if gp3:
            n[gp3[0]] = max(n[gp3[0]], min(gp3[1], 0xF))
    d[k]["mision_nibbles"] = n
    # y el contador de LECCIONES = la máscara más alta de {6,7,8} alcanzada (destino: [player+0x335])
    d[k]["leccion_max"] = max([MASCARA_DE_MISION.get(int(x), 0) for x in d[k].get("lecciones", [])]
                              + [0])
    db_save(d)
    return n

def premio_de(mask):
    """Los campos del premio de esa máscara, con los defaults puestos."""
    p = PREMIOS_MISION.get(mask, {})
    return (int(p.get("rcoin", 0)), int(p.get("exp", 0)), p.get("item"),
            int(p.get("dias", PREMIO_SET_DIAS)))

def sets_del_cartel(mask, genero):
    """Los 4 recuadros que corresponden a esa misión y género."""
    porm = SETS_POR_MISION.get(mask)
    if porm is not None:
        return porm.get(genero, {})
    return SETS_PREMIO_MISION.get(genero, {})

def ajustar_genero_item(item_id, usn=0):
    """★ Los ítems vestibles vienen en pareja por GÉNERO: el 2º dígito es 1=hombre / 2=mujer
    (`910003` = "Guantes de King (H)", `920003` = "(M)"). El script de la misión trae UNO solo, así
    que hay que elegir el del personaje. Si el gemelo no existe en el catálogo, se deja el original."""
    s = str(int(item_id))
    if len(s) != 6 or s[1] not in "12":
        return int(item_id)
    # ⛔ ACÁ DECÍA `char_id & 1` — y el `char_id` deja de decir quién es el jugador apenas se pone
    #   un personaje del gacha (2026-09-09). Con uno del sexo contrario puesto, la misión le
    #   entregaba **la prenda del otro género, permanente y sin poder usarla**. No es cosmético
    #   como el ícono: es un ítem equivocado que le queda en el inventario para siempre.
    #   ⇒ Va `genero_del_jugador`, que sale del personaje BASE (la columna `gender`), no del
    #     disfraz que tenga encima. Ver `gacha.genero_del_jugador`.
    genero = genero_del_jugador(db_get_char(usn) or {})               # 0 = hombre, 1 = mujer
    quiero = "2" if genero else "1"
    if s[1] == quiero:
        return int(item_id)
    gemelo = int(s[0] + quiero + s[2:])
    return gemelo if shop_catalog.exists(gemelo) else int(item_id)

def entregar_premio_mision(usn, mid, premio_elegido=0):
    """Entrega el premio de la misión `mid`: ítem del script + set elegido + EXP. Devuelve un
    resumen para el log. El Rcoin NO se entrega acá — llega aparte, con el FFAB.
    ★ De UNA SOLA VEZ: si ya se cobró el premio en ítems de esta misión, no entrega nada."""
    mask = MASCARA_DE_MISION.get(int(mid), 0)
    rcoin, exp, item, dias = premio_de(mask)
    dado, exp_nuevo = [], None
    # ★ `dias <= 0` = PERMANENTE (0 es el centinela que usa toda la cadena: db_add_inventory lo trata
    #   como "no expira" y `_exp_to_wire(0)` manda PERM_SENTINEL). Sin este guard, `dias: 0` daba
    #   `caduca = ahora` ⇒ el premio nacía CADUCADO. Hace falta para los premios por CANTIDAD
    #   (packs de impulsor), que en la tienda son de período `P` (permanente), no de N días.
    caduca = (int(time.time()) + dias * 86400) if dias > 0 else 0
    genero = genero_del_jugador(db_get_char(usn) or {})   # ★ el del jugador, no el del disfraz
    if db_premio_cobrado(usn, mid, "items"):
        return {"mask": mask, "rcoin": rcoin, "exp": exp, "exp_nuevo": None, "items": [],
                "caduca": caduca, "genero": genero, "dias": dias,
                "recuadro": RECUADRO_DESDE_WIRE.get(genero, {}).get(int(premio_elegido), 0),
                "repetida": True}
    if item:
        # dict = pareja H/M explícita (cuando no se deduce cambiando el 2º dígito)
        real = int(item[genero]) if isinstance(item, dict) else ajustar_genero_item(item, usn)
        # ★★ PACKS (2026-07-31). El PACK se guarda TAL CUAL —igual que en la compra de tienda— y el
        #   cliente lo muestra con su cantidad en el ícono y el tooltip ("[Auto Impulsor X 100]"),
        #   sacada del `PackCount` del catálogo.
        #   Se entrega ADEMÁS el CONTENIDO (`PackIndex`), que hoy es lo único que responde al clic.
        #   Antes eso pasaba por ACCIDENTE (el `ensure_owned` de db_equip lo inventaba al recibir el
        #   `FF1A`); ahora se hace a propósito.
        #   ⛔ NO concluir de acá que "el pack es sólo un envase que no se usa": **eso es FALSO**.
        #   El usuario confirmó que en el juego ORIGINAL los packs SÍ se activaban y desactivaban.
        #   Que hoy clickearlos no mande ningún `FF1A` es un síntoma de que los estamos sirviendo
        #   mal, no un rasgo del diseño. ⏳ PENDIENTE: averiguar qué les falta para ser usables.
        # ⛔⛔ 2026-09-24: YA NO SE GUARDA EL PACK CRUDO, sólo el contenido — como la tienda desde
        #   el 15-sep (`TIENDA_ABRE_PACKS`). Guardar los dos dejaba un envase muerto en el inventario
        #   (el censo de prod: 112 «Pack de Auto Impulsor» x30 al lado de sus 30 cargas ya dadas).
        #   El pack se sigue anotando en `dado`: es lo que dibuja el cartel del premio (`FF126`).
        #   Los que ya quedaron los limpia `herramientas/barrer_inventario.py`.
        dado.append(real)
        _dentro, _n = desempacar_pack(real)
        if _n:                                          # es un pack -> sólo el contenido, con sus cargas
            db_add_inventory(usn, _dentro, 0, cant=_n)
            log("LOBBY", f"  ★ pack {real} -> entrego el CONTENIDO {_dentro} x{_n} (el envase no se guarda)")
        else:
            db_add_inventory(usn, real, caduca)
    # ★★ el cliente REMAPEA el número del recuadro antes de mandarlo, con una tabla distinta por
    #    género (ver RECUADRO_DESDE_WIRE). Y los sets también son por género: el cartel muestra
    #    conjuntos completamente distintos a hombre y a mujer.
    recuadro = RECUADRO_DESDE_WIRE.get(genero, {}).get(int(premio_elegido), 0)
    for pieza in sets_del_cartel(mask, genero).get(recuadro, []):
        db_add_inventory(usn, int(pieza), caduca)   # ya vienen del género correcto, no se ajustan
        dado.append(int(pieza))
    if exp and dado:
        exp_nuevo = db_add_exp(usn, exp)
    if dado:
        db_marcar_premio(usn, mid, "items")        # cobrado: no se vuelve a entregar
    return {"mask": mask, "rcoin": rcoin, "exp": exp, "exp_nuevo": exp_nuevo,
            "items": dado, "caduca": caduca, "genero": genero, "recuadro": recuadro,
            "dias": dias, "repetida": False}

def _rank(g):
    g = (g or "").upper()[:1]
    return ORDEN_GRADOS.index(g) if g in ORDEN_GRADOS else len(ORDEN_GRADOS)

def db_set_grado(usn, mid, grado):
    """Guarda el grado de la misión QUEDÁNDOSE CON EL MEJOR. Pedido del usuario: si quedó en A o C,
    tiene que seguir en A o C entre relogins, y sólo mejorar — la S es el estado terminal."""
    g = chr(grado) if isinstance(grado, int) else str(grado)
    # ★ 2026-09-05: idem — un personaje, no los 4806.
    k = str(usn); _ch = db_get_char(usn)
    if not _ch:
        return g
    d = {k: _ch}
    tabla = d[k].setdefault("misiones_grado", {})
    prev = tabla.get(str(mid))
    if prev is None or _rank(g) < _rank(prev):
        tabla[str(mid)] = g
        db_save(d)
        return g
    return prev

def replay_misiones(st, usn=None):
    """Reenvía un `FF125` por cada misión hecha: restaura la máscara Y el grado.
    ⛔ Sin `usn` usa el de la conexión, NUNCA el 0 (29-sep: el 0 dejó el replay mudo desde la base
    por cuenta — ver `lobby_menu`)."""
    if usn is None:
        usn = getattr(st, "usn", 0)
    grados = db_get_grados(usn)
    if not grados:
        return
    for mid, g in sorted(grados.items(), key=lambda kv: int(kv[0])):
        b = (g or "S").encode("latin-1", "replace")[:1] or b"S"
        st.send_ff55(0x125, bytes([int(mid) & 0xFF, b[0]]),
                     name=f"FF125 replay misión {mid} grado {g!r}")
    log("LOBBY", f"  ★★ REPLAY DE MISIONES: {len(grados)} enviadas {dict(grados)} "
                 f"(otorga la máscara exacta + restaura el grado en [struct+0x78])")

def item_para_el_cartel(items):
    """El cartel muestra UN solo recuadro. Con un set entero, en el juego original se ve **el
    calzado** (lo notó el usuario mirando un video), así que se elige esa pieza si está."""
    for it in items:
        try:
            if shop_catalog.family(int(it)) == "wardrobe_shoes":
                return int(it)
        except Exception:
            pass
    return int(items[-1]) if items else None
