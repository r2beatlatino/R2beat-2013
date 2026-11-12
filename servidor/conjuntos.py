# -*- coding: utf-8 -*-
"""conjuntos — los 4 SETS del armario (SET1..SET4: «Guardar» y «Cargar»), `FF73` = `CmdInventorySet` (12-oct).

★ anonimo03: *«el armario deja guardar sets, un total de 4 espacios para un cambio rápido de ropa; tenemos que hacer que
  funcionen»*. Caía en «SIN handler» (en prod: 254 en 3 días de septiembre). Doc: `documentacion/ARMARIO_CONJUNTOS.md`.

EL PROTOCOLO (todo del exe 2013)
  C→S (emisor `0x5E3220`): `[u8 sub][u8 set 0..3][u8 n][n × u32 ítem]` (si sub = 0xFF no va el set)
    sub 1 = GUARDAR (`0x4CA5AE`): la ropa puesta AHORA (`0x48E980`: el cuerpo, las partes y los efectos); el cliente
            ya la anotó en su memoria (`0x492740`)
    sub 3 = CARGAR  (`0x4CBD25`): ⚠ NO manda el set: manda LO PUESTO AHORA (`0x48E980`, la misma de guardar) — el
            contenido del set lo tiene que saber el SERVER (medido 12-oct: «cargar» el SET1 mandaba el ala que tenía
            puesta, 1000129, no la del SET1, 1000127)
  S→C (`0x5EAAD0`), por sub:
    1 → `[1][u8 res]`: 0 = texto 299 «Su Armario actual ha sido guardado como un CONJUNTO» · 1 = texto 300 «No se puede»
    2 → `[2][u8 nº sets]` × `[u8 set][u8 n][n × u32]`: TODOS los sets (borra y carga, `0x5E9FA0` + `0x4927F0`)
    3 → `[3][u8 modo][u32 cuerpo][u8 n][n × u32]`: modo 0 = ponerse la lista (apaga los efectos `0x48ACC0`, prende los
        de la categoría 10 `0x48E830`, el resto a su parte por `0x50E0B0`; la 1 = el cuerpo y ≥ 11 se saltean) y redibuja
    4 → `[4][u8][u8]`: sólo arma una línea de log

LO QUE HACE EL SERVER
  · guardar: se queda con lo que es SUYO (lo posee, lo tiene puesto, su set básico, el cuerpo que lleva) — hasta
    `CONJUNTOS_MAX` sets; los que manda el cliente de categoría ≥ 11 (los pone él solo) no se guardan;
  · cargar: «quitar todo» lo que se ve (`catalogo.db_quitar_todo`) + ponerse lo suyo (`db_equip_varios`), eco sub 3 con
    lo que quedó puesto, y el repintado de la sala;
  · al entrar al lobby: el sub 2 con los sets guardados.
  ⚠ El CUERPO (un personaje del gacha) no se cambia desde un set: queda el que lleva (ver el doc, §4).
"""
import struct

from . import almacen
from .ajustes import CONJUNTOS_ACTIVO, CONJUNTOS_MAX
from .registro import hx, log

GUARDAR, LISTA, CARGAR = 1, 2, 3


def leer_c2s(data):
    """-> (sub, set, [ítems]) o None si no cierra."""
    if not data:
        return None
    sub, i = data[0], 1
    conj = None
    if sub != 0xFF:
        if len(data) < 2:
            return None
        conj, i = data[1], 2
    if len(data) < i + 1:
        return None
    n = data[i]
    i += 1
    if len(data) < i + 4 * n:
        return None
    return sub, conj, [struct.unpack_from("<I", data, i + 4 * k)[0] for k in range(n)]


def _lista(items):
    return bytes([len(items) & 0xFF]) + b"".join(struct.pack("<I", x & 0xFFFFFFFF) for x in items)


def armar_lista(conjuntos):
    """S→C sub 2: `{set: [ítems]}` -> `[2][n][set][n][ítems]…`."""
    p = bytes([LISTA, len(conjuntos) & 0xFF])
    for k in sorted(conjuntos):
        p += bytes([k & 0xFF]) + _lista(conjuntos[k])
    return p


def armar_cargado(cuerpo, items):
    """S→C sub 3, modo 0: `[3][0][u32 cuerpo][n][ítems]`."""
    return bytes([CARGAR, 0]) + struct.pack("<I", int(cuerpo) & 0xFFFFFFFF) + _lista(items)


def _suyos(usn, items):
    """Lo de la lista que es del jugador: (aceptados, rechazados). El cuerpo vale si es el que lleva puesto."""
    from .basedatos import db_get_char, inv_ids
    from .catalogo import basico_de, categoria_worn, desempacar_pack
    ch = db_get_char(usn) or {}
    tiene = set(inv_ids(ch)) | {int(x) for x in ch.get("parts", [])} | set(basico_de(ch)) if ch else set()
    tiene |= {desempacar_pack(i)[0] for i in list(tiene) if desempacar_pack(i)[1]}
    cuerpo = int(ch.get("char_id", 0) or 0)
    ok, no = [], []
    for x in items:
        x = int(x)
        cat = categoria_worn(x)
        if cat >= 11:
            continue                                   # joyas/anillos: el cliente las saltea (medido: 1200029, 1200033)
        if (cat == 1 and x == cuerpo) or (cat != 1 and x in tiene):
            if x not in ok:
                ok.append(x)
        else:
            no.append(x)
    return ok, no


def _una_por_familia(items):
    """Una por familia (la ÚLTIMA), como queda puesto: el cliente llegó a guardar un set con DOS alas (12-oct, anonimo03).
    Lo que se suma (modos héroe, profecías y las ayudas de carrera (96), `catalogo.se_suma`) ni saca ni sale."""
    from . import shop_catalog
    from .catalogo import categoria_worn, mismo_lugar, se_suma
    out = []
    for x in items:
        fam = shop_catalog.family(x)
        if categoria_worn(x) != 1 and fam and not se_suma(x, fam):
            out = [y for y in out if not mismo_lugar(x, y, fam) or se_suma(y)]
        out.append(x)
    return out


def enviar_lista(st, motivo="al entrar"):
    """S→C sub 2 con los sets guardados. Idempotente por conexión (llega el FF03 y el FF06)."""
    if not CONJUNTOS_ACTIVO or getattr(st, "_conjuntos_enviados", False):
        return
    st._conjuntos_enviados = True
    usn = int(getattr(st, "usn", 0) or 0)
    cj = almacen.conjuntos_de(usn)
    if not cj:
        return
    st.send_ff55(0x73, armar_lista(cj), name=f"FF73/2 los {len(cj)} sets del armario ({motivo})")
    log("LOBBY", f"  👕 FF73 sets del armario a usn={usn}: {sorted(cj)} ({motivo})")


def sobre_el_cuerpo(ch, items):
    """Lo de `items` que puede ir encima del cuerpo de `ch` en un FF73/3.

    ⛔ 27-oct (anonimo03: *«uid 9679 crashea antes de cargar por completo el lobby»*). Con un cuerpo del gacha (Ann:
      120161 Rosita) y la ropa común encima, el «ponerse esta lista» del personaje elegido tumbaba el juego al copiar
      el muñeco: `_invalid_parameter` en `0x65041F` (pila `0x652744 ← 0x653B6D`), la MISMA caída que el 25-oct se
      arregló sólo en la lista del selector (`cuenta_personajes.lista`). Desde la subida del 26-oct: ~130 cajas negras
      de ~40 jugadores, todos con un cuerpo del gacha. ⇒ La misma regla: va lo que se DIBUJA (`gacha.apariencia`:
      mascota y alas) y lo de la categoría 10 que no se ve (fondo de slot, cupones, y las AYUDAS DE CARRERA aunque
      sean de la familia «skin», que es un cajón: el Auto Impulsor), que el sub 3 apaga y hay que volver a prender.
      La ropa no se toca en la base. Con un cuerpo común pasa todo, como antes."""
    from .ajustes import AYUDAS_DE_CARRERA_EFECTOS
    from .catalogo import FAMILIAS_CAT10_VISIBLES, categoria_worn
    from .gacha import apariencia, es_personaje
    from . import shop_catalog
    if not es_personaje(int(ch.get("char_id", 0) or 0)):
        return list(items)
    se_ve = set(apariencia(ch)[1])

    def no_se_ve(x):
        return categoria_worn(x) == 10 and (shop_catalog.family(x) not in FAMILIAS_CAT10_VISIBLES
                                            or (shop_catalog.CATALOG.get(int(x)) or {}).get("effect")
                                            in AYUDAS_DE_CARRERA_EFECTOS)
    return [x for x in items if x in se_ve or no_se_ve(x)]


def sincronizar_al_elegir(st):
    """★ 25-oct — EL PERSONAJE ELEGIDO EN EL SELECTOR, CON SU ROPA Y SUS SETS, NO LOS DEL ANTERIOR.

    anonimo03, con «Cambiar personaje» (el selector en el mismo juego): *«las 2 nuevas cuentas se quedan con la licencia,
    el fondo de slot, crayón y mascota de la anterior»*. La ficha (`FF03`) SUMA lo suyo pero no saca lo que el anterior
    tenía puesto: los efectos (alas, crayón, fondo) y los casilleros que el nuevo no trae (la mascota). Y los sets van
    sólo si hay (`enviar_lista`), así que los del anterior quedaban.
    ⇒ anonimo03: *«seguramente sólo es reenviar un ponerse/vestirse por detrás»*. Es el sub 3 modo 0 (`0x5EAC46`): parte de
      un atuendo EN CERO (`memset` 0x30), APAGA todos los efectos (`0x48ACC0`), prende los de la categoría 10 de la
      lista (`0x48E830`), pone el resto en su casillero y se lo pasa a la escena y al armario (`vt+0x34`, `0x4D8140`).
      Y el sub 2 con TODOS los sets, aunque sean cero: «borra y carga» (`0x5E9FA0`).
    Va en el lobby (con el FFC9 guardado, `lobby_salas.h_08_ff6e`): el sub 3 se lo da a la escena que esté."""
    from .basedatos import db_get_char
    from .catalogo import categoria_worn, estilos_activos
    from .ajustes import SELECTOR_SYNC_ROPA, SELECTOR_SYNC_SETS
    usn = int(getattr(st, "usn", 0) or 0)
    ch = db_get_char(usn) or {}
    cj = almacen.conjuntos_de(usn) if CONJUNTOS_ACTIVO else {}
    if SELECTOR_SYNC_SETS:
        st.send_ff55(0x73, armar_lista(cj), name=f"FF73/2 los {len(cj)} sets (personaje elegido en el selector)")
    if not SELECTOR_SYNC_ROPA:
        log("LOBBY", f"  👕 FF73 personaje elegido usn={usn}: sets {'sí' if SELECTOR_SYNC_SETS else 'NO'} · ropa NO (apagado)")
        return
    puesto = [int(x) for x in ch.get("parts", []) if categoria_worn(int(x)) not in (1,) and categoria_worn(int(x)) < 11]
    puesto = sobre_el_cuerpo(ch, puesto)
    puesto += [x for x in sorted(estilos_activos(usn, ch)) if x not in puesto]
    st.send_ff55(0x73, armar_cargado(int(ch.get("char_id", 0) or 0), puesto),
                 name=f"FF73/3 su ropa ({len(puesto)} ítems): limpia lo del personaje anterior")
    log("LOBBY", f"  👕 FF73 personaje elegido usn={usn}: sets {sorted(cj)} · puesto {puesto}")


def atender(st, data):
    """C→S `FF73`."""
    usn = int(getattr(st, "usn", 0) or 0)
    leido = leer_c2s(data)
    if leido is None:
        log("LOBBY", f"  ⚠ FF73 que no cierra de usn={usn}: {hx(data)}")
        return
    sub, conj, items = leido
    if not CONJUNTOS_ACTIVO:
        if sub == GUARDAR:
            st.send_ff55(0x73, bytes([GUARDAR, 1]), name="FF73/1 NO (CONJUNTOS_ACTIVO = False)")
        return
    if sub == GUARDAR:
        ok, no = _suyos(usn, items)
        ok = _una_por_familia(ok)
        if conj is None or conj >= CONJUNTOS_MAX or not ok:
            st.send_ff55(0x73, bytes([GUARDAR, 1]), name=f"FF73/1 NO se guarda el set {conj}")
            log("LOBBY", f"  👕 FF73 GUARDAR set {conj} usn={usn} -> NO (máx {CONJUNTOS_MAX}, aceptados {ok})")
            return
        almacen.guardar_conjunto(usn, conj, ok)
        st.send_ff55(0x73, bytes([GUARDAR, 0]), name=f"FF73/1 set {conj} guardado ({len(ok)} ítems)")
        log("LOBBY", f"  👕 FF73 GUARDAR set {conj} usn={usn}: {ok}" + (f" · ⛔ no eran suyos {no}" if no else ""))
        return
    if sub == CARGAR:
        from .basedatos import db_get_char
        from .catalogo import FAMILIAS_CAT10_VISIBLES, categoria_worn, db_equip_varios, db_quitar_todo
        from . import shop_catalog
        # ★ 12-oct, 3.ª vuelta (anonimo03: «guardé un cabello diferente en el 1 y el 2 y al cargar no se actualizó»): la
        #   lista del paquete es lo PUESTO AHORA, no el set (`0x4CBC80` llama a `0x48E980` antes de mandar). Se usa el
        #   set GUARDADO en la base; si ese set no existe, no se toca nada y se devuelve lo puesto.
        guardado = almacen.conjuntos_de(usn).get(conj)
        if guardado is None:
            ch0 = db_get_char(usn) or {}
            st.send_ff55(0x73, armar_cargado(int(ch0.get("char_id", 0) or 0), list(ch0.get("parts", []))),
                         name=f"FF73/3 set {conj} VACÍO: se devuelve lo puesto")
            log("LOBBY", f"  👕 FF73 CARGAR set {conj} usn={usn}: no hay nada guardado ahí — no se toca la ropa")
            return
        ok, no = _suyos(usn, guardado)
        db_quitar_todo(usn)
        puestas, rech = db_equip_varios(usn, [x for x in ok if categoria_worn(x) != 1])
        ch = db_get_char(usn) or {}
        cuerpo = int(ch.get("char_id", 0) or 0)
        # lo que quedó puesto: lo del set + lo de la categoría 10 que no se ve (cupones, ranuras), que el cliente
        #   apaga con `0x48ACC0` al cargar y hay que volver a prenderle
        func = [x for x in ch.get("parts", []) if categoria_worn(x) == 10
                and shop_catalog.family(x) not in FAMILIAS_CAT10_VISIBLES and x not in puestas]
        eco = puestas + func
        st.send_ff55(0x73, armar_cargado(cuerpo, eco), name=f"FF73/3 set {conj} puesto ({len(eco)} ítems)")
        log("LOBBY", f"  👕 FF73 CARGAR set {conj} usn={usn}: puestas {puestas}"
                     + (f" · ⛔ no eran suyos {no + rech}" if (no or rech) else ""))
        from .lobby_tienda import refrescar_ropa
        refrescar_ropa(st, f"FF73 set {conj}")
        return
    log("LOBBY", f"  ⚠ FF73 sub {sub} sin mapear de usn={usn}: {hx(data)}")
