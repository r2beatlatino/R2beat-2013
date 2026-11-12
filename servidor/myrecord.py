# -*- coding: utf-8 -*-
"""myrecord — el `FF03`, el paquete más grande y más delicado del server.

Es la ficha completa del jugador: monedas, licencia, apodo, gremio, lo que lleva puesto,
el inventario, las canciones que puede elegir y los escenarios. El cliente lo parsea
SECUENCIAL (handler `0x5ED3C0`), así que **el orden de los campos es el formato**: mover
uno corre todos los que siguen y el paquete se lee mal de ahí en adelante, sin error.

Estructura, en orden:
    prefijo de 69 bytes   escalares + 4 strings   (`build_prefix`)
    char_id + worn        el cuerpo va PRIMERO en el array, si no sale sin ropa
    LOOP A                las canciones del picker   ← `OWNED_SONGS_2013`
    LOOP B                los escenarios
    cola                  inventario y el resto de los escalares

⚠ El `FF49` tiene que llegar ANTES que esto: adentro del handler hay un bounds-check
  contra `word[G+0x8C]`, que arranca en `0xFFFF` y sólo lo escribe el SelectByKey de ese
  paquete. Si el MyRecord llega primero, el cliente se mata solo (`0xC0000417`).
  Ver `paquetes.build_ff49`.

⚠ `OWNED_SONGS_2013` se MUTA en el arranque (`lista[:] = ...`), nunca se reasigna: el
  nombre viaja por `import *` a varios módulos y reasignarlo dejaba a este con la lista
  vacía. Eso es lo que hacía llegar el picker sin una sola canción.
"""
import struct

from . import shop_catalog

from .ajustes import (
    MYRECORD_MANDA_CARGAS,
    FF69_CARGAS_AL_ENTRAR,
    CASH,
    CASH_OFF,
    CHARID_OVERRIDE,
    COIN_OFF,
    DEBUG_ENDTIME_MAP,
    GENDER_OVERRIDE,
    INV_LISTA2,
    LICENSE_OFF,
    LICENSE_TEST,
    LICENSE_VAL,
    MONEDA_GORILA_ITEM,
    MONEDA_GORILA_POR_FF69,
    MYRECORD_SALDO_EN_CADA_REFRESCO,
    GACHA_LISTA_PERSONAJES,
    GACHA_PERSONAJES_OFF,
    GACHA_PERSONAJE_HP,
    MR_CHARCOUNT_OFF,
    MYREC_MISION_OFF,
    OWNED_SONGS_2013,
    OWNED_STAGES_2013,
    POPULATE_INVENTORY,
    PREFIX_U32_OFFS,
    PRESENTACION_EN_FF03,
    PRESENTACION_OFF_FF03,
    PROBE_CURRENCY,
    PROBE_MISION_OFF,
    PROBE_SEED,
    RCOIN,
    REST_TEST,
    SEED,
    SEED_DELTA,
    SEED_OFF,
    SONDA_PREFIJO,
    STORE_MAP,
    TAIL_U32_DELTAS,
    WORN_PANEL_MODE,
    WORN_PREPEND_CHARID,
)
from .basedatos import _exp_to_wire, db_get_char, db_get_rcoin, inv_cant, inv_ids, inv_pairs
from .medallas import medalla_puesta
from .gacha import personajes_de, parts_visibles, genero_visible
from .progresion import licencia_actual
from .registro import log

TIEMPO_HOY_EN_HUECO = 9     # ★ 15-oct, MEDIDO: el u32 del tiempo de hoy en el hueco presentación → gacha (ver abajo)


def build_prefix(g, nick="", guild="", usn=0):
    """Prefijo del MyRecord como SECUENCIA de campos (re/myrec_reads.txt). Strings CONFIRMADOS
    (probe 2026-07-11): @27 = APODO (nick de la DB), @44 = GREMIO/círculo (guild de la DB);
    @45 y @63 = strings vacíos (sin mapear aún). Escalares: @9 rcoin, @13 cash, @19 licencia.
    El cliente lee secuencial -> los strings con len>0 corren los offsets pero parsea bien."""
    def s(txt):
        b = (txt or "").encode("cp1252", "replace")[:255]
        return bytes([len(b) & 0xFF]) + b

    def u32(off, valor=0):
        """u32 del prefijo, con la SONDA FINA encima si está puesta para ese offset.

        ⚠ Acá NO se puede `pack_into` por offset como hace el modo `PROBE_CURRENCY`: este
        prefijo es una SECUENCIA con strings de largo variable, así que los `@N` son posiciones
        NOMINALES (las del prefijo de ceros), no offsets reales del buffer. Por eso la sonda se
        aplica campo por campo mientras se arma. Ver `SONDA_PREFIJO` en ajustes.py.
        """
        return struct.pack("<I", SONDA_PREFIJO.get(off, valor) & 0xFFFFFFFF)

    o = bytearray()
    o += bytes([g & 0xFF])              # @0  gender
    o += u32(1)                         # @1
    o += u32(5)                         # @5
    o += u32(9, db_get_rcoin(usn))      # @9  rcoin (★ de la DB: los premios de misión lo suben)
    o += u32(13, CASH)                  # @13 cash
    o += struct.pack("<H", 0)           # @17
    o += u32(19, licencia_actual(usn)[2])   # @19 ★ LICENCIA — YA NO ES FIJA: sale del NIVEL
                                        #   (BANDAS_LICENCIA). Era el valor huérfano clavado en SOL.
    o += u32(23)                        # @23
    o += s(nick)                         # @27 ★ APODO
    o += u32(28)                        # @28
    o += struct.pack("<H", 0)           # @32
    o += struct.pack("<H", 0)           # @34
    o += u32(36)                        # @36
    o += u32(40)                        # @40
    o += s(guild)                        # @44 ★ GREMIO
    o += s("")                           # @45 (vacío, sin mapear)
    o += u32(46)                        # @46
    o += bytes([0])                      # @50 u8
    o += u32(51)                        # @51
    o += u32(55)                        # @55
    o += u32(59)                        # @59
    o += s("")                           # @63 (vacío, sin mapear)
    o += bytes([0])                      # @64 u8
    # @65 ★ LA MEDALLA PUESTA (24-sep): el handler la escribe en `cfg+0x644` (`0x5EDB16`), que es la
    #   que el cliente dibuja como suya. La elige el jugador con el `FFD2`. Ver `medallas.py`.
    o += u32(65, medalla_puesta(usn))
    return bytes(o)


def build_myrecord(gender=1, usn=0, con_personaje=True, moneda_gorila=False):
    """MyRecord (inner FF03) — handler cliente 0x5ED3C0.

    ⛔⛔⛔ `moneda_gorila` SÓLO EN VERDADERO PARA EL PRIMER MyRecord DE LA SESIÓN (2026-09-10).

      EL BUG, cazado por anonimo03 con dos números limpios: le puse **500** monedas gorila en la base
      y el cliente le mostró **1000**. Antes había pasado lo mismo con 3 → 6. **Exactamente el
      doble, las dos veces.**

      CAUSA: la cantidad de monedas viaja en el `count` de la entrada del ítem 540 de la lista de
      inventario, y el cliente **la ACUMULA**: cada entrada que le llega la SUMA (`0x48FFB0`
      registra el ítem). Nosotros mandamos el MyRecord **más de una vez por sesión** — el login,
      el que va detrás del `FF49`, y cinco refrescos más (compra, gacha, premio de misión…).
      ⇒ Cada reenvío le regalaba otras 500. No es 2×: **crece toda la sesión**.
      ★ Y no se notaba con los demás ítems porque a todos les mandamos `count = 0`; el 540 es el
        único que lleva número.

    ⚠ EL DEFAULT ES `False` A PROPÓSITO. Si mañana alguien agrega un octavo llamador y se olvida
      de este parámetro, el peor caso es que **no se vea el saldo** (visible, y se arregla). Con
      el default al revés, el peor caso es **inflar la moneda en silencio**, que es plata.

    Layout: [69 bytes prefijo (gender + ceros)][u16 char_count][por char: u32 char_id, u8 partcount,
    partcount×u32 part_id] --> [u16 songs_count][u16 songid×n] (LOOP A, off 92) --> [u16 stages_count]
    [(u16 stageid)(u8 flag)×n] (LOOP B) --> resto ceros. Los loops A/B pueblan los PICKERS de musica/stage.
    (El resto de counts/lens sigue en 0 -> loops vacios; ver historial del cuelgue por count basura.)"""
    char = db_get_char(usn)                     # ★ identidad REAL (argv[1] del cliente)
    # ★★ 25-oct: el juego con SELECTOR (la dll avisó con el FFF6) recibe la ficha VACÍA de la cuenta: sin personaje
    #   abre la creación, y encima está el selector. Al elegir, entra con el usn del elegido (cuenta_personajes.py).
    from .cuenta_personajes import eligiendo
    if eligiendo(usn):
        char = None
    if not char:
        return bytes([gender & 0xFF]) + b"\x00" * 220   # sin personaje -> creacion
    # ★★ EL SEXO SALE DE `hero.txt`, NO DEL ÚLTIMO DÍGITO — corregido el 2026-09-09.
    #   La regla vieja (`char_id & 1`) vale para los personajes BASE (130900 hombre / 130901 mujer)
    #   pero NO para los del gacha: `130029` y `130031` son impares y de HOMBRE. Al equipar uno se
    #   pisa el `char_id` y el ícono se daba vuelta. Ver `gacha.genero_visible`.
    g = genero_visible(char)
    if GENDER_OVERRIDE is not None:             # override para confirmar el campo gender @0
        g = GENDER_OVERRIDE & 1
    pre = bytearray(MR_CHARCOUNT_OFF)           # off 0..68: prefijo (69B ceros)
    pre[0] = g                                  # off 0: gender
    if STORE_MAP:
        for off in PREFIX_U32_OFFS:             # centinela 0xF0000000|off en cada u32 escalar del prefijo
            struct.pack_into("<I", pre, off, (0xF0000000 | off) & 0xFFFFFFFF)
    elif PROBE_CURRENCY:
        for off in PREFIX_U32_OFFS:             # centinela 1000000+off en cada u32 -> identificar rcoin/cash/seed
            struct.pack_into("<I", pre, off, 1000000 + off)
    else:
        for off, val in ((COIN_OFF, RCOIN), (CASH_OFF, CASH), (SEED_OFF, SEED)):
            if off is not None:
                struct.pack_into("<I", pre, off, val & 0xFFFFFFFF)
        # licencia: bisección (LICENSE_TEST) o valor fijo permanente (LICENSE_OFF)
        if LICENSE_TEST:
            for off in LICENSE_TEST:
                struct.pack_into("<I", pre, off, LICENSE_VAL & 0xFFFFFFFF)
        elif LICENSE_OFF is not None:
            struct.pack_into("<I", pre, LICENSE_OFF, licencia_actual(usn)[2] & 0xFFFFFFFF)
    if not (STORE_MAP or PROBE_CURRENCY):       # modo normal: prefijo-secuencia real (apodo + gremio de la DB)
        pre = bytearray(build_prefix(g, char.get("nick", ""), char.get("guild", ""), usn=usn))
    p  = bytearray(pre)
    # ★★★★★ `con_personaje=False` -> `char_count = 0` y NO va el registro de personaje.
    #   ⛔ EL PROBLEMA MEDIDO (informe del agente, §1.5): este bucle **sólo AGREGA** al vector de
    #     personajes del cliente. Lo único que lo VACÍA es el `FF49` (`0x48BD30`); lo que el
    #     MyRecord limpia (`0x48BCA0`) toca `cAccount+0x514/+0x52C`, **no** el vector
    #     (`+0xBC/+0xC8/+0xCC`) — comprobado leyendo las dos funciones.
    #   ⇒ **Cada `FF03` de refresco duplica un registro.** En una sesión con compras, cápsulas y
    #     cambios de personaje la lista pasa de 2 a 5, 8, 12… y cada realloc mueve el buffer. Ése es
    #     uno de los caminos por los que el índice `word[+0xC8...]` puede quedar apuntando afuera.
    #   ★ El MyRecord del LOGIN sí lo manda (va detrás del `FF49`, que acaba de vaciar la lista).
    #     Los REFRESCOS —compra, cápsula, premio— no: van a actualizar monedas e inventario, y el
    #     cuerpo ya está puesto.
    #   ⚠ Con 0 el cliente saltea el bucle limpio (`005ecfe0 cmp word,0 / je`), no es un caso raro.
    if not con_personaje:
        p += struct.pack("<H", 0)               # off 69: char_count = 0 -> no se agrega nada
        _resto_char = False
    else:
        _resto_char = True
        p += struct.pack("<H", 1)               # off 69: char_count = 1
    cid = char["char_id"]
    if CHARID_OVERRIDE is not None:             # test género visual: 130900=macho / 130901=hembra
        cid = CHARID_OVERRIDE
    # ★ Si tiene puesto un personaje del GACHA, la ropa NO se dibuja: ese personaje es un cuerpo
    #   entero. Ver `gacha.apariencia` — la ropa sigue guardada, sólo no se manda.
    parts = parts_visibles(char)[:255]
    # ★ FIX vestido-en-login (guía CBT): el constructor del char 0x580580 clasifica cada part por
    #   SLOT (0x50e6e0) y espera el CUERPO (char_id->slot1) como primer part. Mandando solo la ropa
    #   (slots 2-5) el array de apariencia queda [char_id,0,0,0,0,0,0] (ropa vacía -> render default).
    #   worn = [char_id] + ropa  => partcount=5, parts[0]=char_id (cuerpo). Espejo del CBT worn=[char_id]+parts.
    worn = ([cid] + list(parts)) if WORN_PREPEND_CHARID else list(parts)
    if _resto_char:                             # el registro entero, sólo si el contador dijo 1
        p += struct.pack("<I", cid & 0xFFFFFFFF)   # off 71: char_id (define cuerpo/género visual)
        p += bytes([len(worn) & 0xFF])          # partcount (5 con el fix)
        for pid in worn:
            p += struct.pack("<I", pid & 0xFFFFFFFF)   # cada part (1º = char_id = cuerpo)
    # ── LOOP A: OWNED SONGS (off 92) ──
    songs = OWNED_SONGS_2013[:0xFFFF]
    p += struct.pack("<H", len(songs))          # u16 songs_count
    for sid in songs:
        p += struct.pack("<H", sid & 0xFFFF)    # u16 songid
    # ── LOOP B: OWNED STAGES ──
    stages = OWNED_STAGES_2013[:0xFFFF]
    p += struct.pack("<H", len(stages))         # u16 stages_count
    for stid in stages:
        p += struct.pack("<H", stid & 0xFFFF)   # u16 stageid
        p += b"\x00"                            # u8 flag
    # ── COLA: campos escalares post-pickers (aqui vive el SEED) ──
    tail_start = len(p)                         # inicio de la cola (=1687 con las listas actuales)
    probing = STORE_MAP or PROBE_SEED or REST_TEST
    if POPULATE_INVENTORY and not probing:
        # ★ INVENTARIO POSEÍDO — loop 0x5edf34 del handler: [count:u16] + count×([item_id:u32][dur:u16]).
        #   Cada ítem -> 0x48ffb0 REGISTRA: setea el slot worn [obj+0xd8+slot*4] Y lo mete al inventario
        #   (manager 0x9314f0+0xe84). Sin esto (count=0) los slots quedan vacíos -> render default +
        #   inventario vacío + mi-info sin ropa. Los slots worn los pone ESTE loop, no el 0x48fe60.
        #   ★ Es el #37 INVENTARIO/CLÓSET del CBT (build_myrecord_honesto): [count:u16] + por ítem
        #   [item_id:u32][end_time:u32][in_use:u8][count:u16] (11B). in_use=1 = equipado (renderiza),
        #   =0 = solo poseído (aparece en el panel). end_time=PERMANENT 0xEEFFCBB8. TODOS los ítems aquí.
        exp_by_id = {i: e for i, e in inv_pairs(char)}                    # id -> exp (0=permanente)
        cant_by_id = inv_cant(char)                                       # id -> cargas (consumibles)
        worn  = list(char.get("parts", []))                              # puestas -> in_use=1
        owned = [i for i in inv_ids(char) if i not in worn]              # comprados-no-puestos -> in_use=0
        # ★ 11-oct: el SET BÁSICO (la ropa de la creación) también, como poseído: de esta lista el cliente arma su
        #   `[player+0xD8]` y con eso «Restaurar» (FF7F) sabe qué ponerle. Ver `catalogo.asegurar_basico`.
        from .catalogo import asegurar_basico                              # noqa: PLC0415
        owned += [b for b in asegurar_basico(usn, char) if b and b not in worn and b not in owned]
        if WORN_PANEL_MODE == "dup":                                     # equipado 2x: in_use=1 (render) + 0 (panel)
            items = [(it, 1) for it in worn] + [(it, 0) for it in worn] + [(it, 0) for it in owned]
        else:
            items = [(it, 1) for it in worn] + [(it, 0) for it in owned]
        # ★ el GLOBO, el CRAYÓN y el LÁPIZ del apodo tildados (25-sep): `in_use = 1` -> `0x48F720` ->
        #   `0x48E830` (categoría 10) los deja tildados en Mi Casa al reconectar. No son ropa: no
        #   van en `parts`/el worn del FF0C (ver `catalogo.estilos_activos`).
        try:
            from .catalogo import estilos_activos                      # noqa: PLC0415
            _act = estilos_activos(usn, char)
        except Exception:                                              # noqa: BLE001
            _act = set()
        if _act:
            items = [(it, 1 if (it in _act and not iu) else iu) for it, iu in items]
        # ★★★★★ LA MONEDA GORILA (2026-09-02). No es una moneda aparte: es el ÍTEM 540
        #   ("Monedas Gorila" en shop_lt.txt) y la CANTIDAD viaja en el `count` de su entrada de
        #   esta misma lista. Salió de comparar los cinco MyRecord de la captura: el único otro
        #   byte que cambia entre logins es ese `count`, que va 1 → 2 → 6 → 6. Ver
        #   `MONEDA_GORILA_ITEM` en ajustes.py.
        #   Se sintetiza la entrada (no se toca el inventario de la DB): el saldo vive en
        #   `monedas_gorila`, que es lo que suma la caja del gorila.
        _gor = int((char.get("monedas_gorila") or 0))
        if MONEDA_GORILA_POR_FF69:
            # ⛔⛔ SE SACA ENTERA, NO SE MANDA EN 0. `0x5ED3D9` hace `test ax,ax / jne / mov eax,1`:
            #   **un `count` de 0 se convierte en 1**, así que dejar la entrada en cero sumaría
            #   +1 en cada MyRecord — y el MyRecord va por `AddInventory`, que SUMA.
            #   Sacarla es seguro: el `FF69` va por `SetInventory`, que **crea** la entrada si no
            #   existe. Ver `MONEDA_GORILA_POR_FF69` en `ajustes.py`.
            items = [(_it, _iu) for _it, _iu in items if _it != MONEDA_GORILA_ITEM]
        elif _gor > 0 and MONEDA_GORILA_ITEM not in worn and MONEDA_GORILA_ITEM not in owned:
            items.append((MONEDA_GORILA_ITEM, 0))
        p += struct.pack("<H", len(items) & 0xFFFF)        # #37 count
        for it, inuse in items:
            _exp = exp_by_id.get(it, 0)
            end_time = _exp_to_wire(_exp)                  # expiry real (o centinela permanente)
            if it == MONEDA_GORILA_ITEM:
                # ★ La captura manda la moneda gorila con `end_time = 0`, NO con el centinela de
                #   permanente (`0xEEFFCBB8`). Se copia tal cual: es una moneda, no una prenda con
                #   vencimiento, y no hay razón para inventar un valor distinto al medido.
                end_time = 0
            if it in DEBUG_ENDTIME_MAP:                    # probe de debug para descifrar el formato de fecha
                end_time = DEBUG_ENDTIME_MAP[it]
                log("LOBBY", f"  ⏱ PROBE item={it} -> wire={end_time:#010x}")
            elif _exp:                                     # ítem temporal real: log del valor enviado
                log("LOBBY", f"  ⏱ inv item={it} exp_unix={_exp} -> wire={end_time} ({end_time:#010x})")
            p += struct.pack("<I", it & 0xFFFFFFFF)        # [0:4]  item_id
            p += struct.pack("<I", end_time)               # [4:8]  end_time (UNIX exp / permanente 0xeeffcbb8)
            p += struct.pack("<B", inuse & 0xFF)           # [8]    in_use (1=equipado / 0=poseído)
            # [9:11] count -> ⛔ NO son las cargas del consumible. MEDIDO 2026-07-31: se mandó 30 acá
            #   para el Auto Impulsor (1000999) y el cliente lo siguió mostrando **sin cargas**.
            #   ★ El candidato real es la **2ª LISTA** de abajo (`0x5edf34`), cuyas entradas son
            #   `[item:u32][u16]` = id + número, y que hoy mandamos VACÍA. Ver nota ahí.
            #   Se deja en 0 para no escribir a ciegas un campo de significado desconocido.
            #   ★ EXCEPCIÓN MEDIDA: para el ítem 540 ("Monedas Gorila") ese `count` **SÍ** es la
            #     cantidad. Lo prueba la captura: es el único byte que cambia entre logins del
            #     server de referencia (1 → 2 → 6 → 6) y acompaña las cajas ganadas. Por eso se
            #     llena sólo acá y no para todos.
            # ⛔ El `count` del 540 SÓLO en el primer MyRecord: el cliente lo ACUMULA (ver el
            #   docstring). En un refresco va 0 y el saldo de pantalla queda como estaba.
            #
            # ★★★★★ Y LAS CARGAS DE LOS CONSUMIBLES VAN ACÁ MISMO — 2026-09-15, lo vio anonimo03:
            #   compró megáfonos y *"no lista directamente cuántos usos tiene, ni el de 5 ni los
            #   otros 2 que compré y son de 1 carga"*. Y el motivo estaba en esta línea: el
            #   `count` iba **0 para todos** salvo la moneda gorila, así que el cliente nunca se
            #   enteraba de cuántos usos tenía un consumible.
            #   ★ El dato ya estaba calculado arriba (`cant_by_id`) y el propio comentario de
            #     `inv_cant` decía a dónde iba: *"al campo `count:u16` del #37 del MyRecord, que
            #     hasta 2026-07-31 mandábamos clavado en 0 porque sólo teníamos ropa"*. Ya no.
            #   ⚠ La ropa sigue yendo en 0: no tiene cargas y `cant_by_id` no la incluye.
            #   ⚠⚠ Y OJO CON EL 0: `0x5ED3D9` hace `test ax,ax / jne / mov eax,1` — **un `count`
            #     de 0 el cliente lo lee como 1**. Por eso un consumible agotado no se puede
            #     "apagar" mandando 0: hay que sacarlo de la lista, que es lo que hace
            #     `db_del_inventory` al llegar a cero. Ver `MYRECORD_MANDA_CARGAS`.
            _cnt37 = (_gor if (it == MONEDA_GORILA_ITEM and moneda_gorila)
                      else (cant_by_id.get(it, 0) if MYRECORD_MANDA_CARGAS else 0))
            p += struct.pack("<H", _cnt37 & 0xFFFF)
        # ★★★ 2ª LISTA DE INVENTARIO (`0x5EDF34`) — verificada en el disasm 2026-07-31:
        #       [count:u16] + count × ([item_id:u32][u16])        <- entradas de 6 BYTES
        #   y cada entrada llama a **`0x48FFB0`, la MISMA rutina de registro que la lista #37**.
        #   O sea: es una segunda vía de alta de ítems, con un `u16` extra por ítem.
        #   HIPÓTESIS: es la de CONSUMIBLES/utilidad y ese `u16` son las CARGAS. Encaja con el
        #   síntoma: los packs de impulsor se VEN (van en la #37) pero clickearlos no manda ningún
        #   `FF1A` — se muestran pero no están habilitados como usables.
        #   ⚠ Acá arranca la COLA del MyRecord (zona de la bisección REST_TEST/TAIL_U32_DELTAS,
        #   los puntos de descanso). Por eso la cola se emite ENTERA E INTACTA después de la lista:
        #   sólo se inserta `6 × count` bytes, nada se pisa ni se corre de lugar.
        lista2 = []
        if INV_LISTA2:
            for _id, _e in inv_pairs(char):
                _n = int((shop_catalog.CATALOG.get(_id) or {}).get("pack_count") or 0)
                if _n > 0:                                  # packs = los únicos con cantidad propia
                    lista2.append((_id, _n))
        p += struct.pack("<H", len(lista2) & 0xFFFF)        # 2º count
        for _id, _n in lista2:
            p += struct.pack("<I", _id & 0xFFFFFFFF) + struct.pack("<H", _n & 0xFFFF)
        if lista2:
            log("LOBBY", f"  ★ 2ª lista de inventario: {lista2} (sonda de consumibles, INV_LISTA2)")
        # ★★★★★ LA PESTAÑA "PERSONAJE" DEL ARMARIO — 2026-09-08.
        #   ⛔ EL BUG: anonimo03 ganó un personaje en el gacha, el server lo guardó bien… y la pestaña
        #     seguía VACÍA. Y la captura mostró más de lo que él creía: estaba vacía **también de
        #     lo que ya tenía**. No faltaba el premio: esa lista no se mandaba NUNCA.
        #
        #   ★ QUÉ ES: los premios del gacha **no son ropa, son PERSONAJES** — están en `hero.txt`
        #     del cliente (`<Char Index="130030" Model="rnr_char/SP/SP0030A/...">`) y en `spec.txt`.
        #     Por eso no aparecían en las pestañas de prendas: no son prendas.
        #
        #   ★★ DÓNDE VA, leído del parser del MyRecord (`0x5EC8A0`), casi al final:
        #         005edcf0  read(1)          ← el CONTADOR, un BYTE (con 0 no lee nada)
        #         005edd0c  read(4)          ← el personaje
        #         005edd1d  read(8)          ← ocho bytes por personaje
        #         005edd38  call 0x46f4e0    ← lo registra en el padrón `[0x934354]`
        #     y **`0x46F4E0` es del gacha**: adentro tiene el texto `[GACHA] Spec data error : %u`,
        #     que es lo que escribe cuando el id no está en `spec.txt`. Esa es la atadura que
        #     convierte la corazonada en un hecho.
        #
        #   ★ EL OFFSET ES 45, y está MEDIDO — no contado. Acá decía "46, CONTADO, no adivinado",
        #     y era 46 y estaba mal: **un byte**, cuatro horas de cacería y un crash a los 4 s.
        #     Después lo "corregí" a 84 comparando el offset absoluto de una cuenta contra la
        #     lectura medida de OTRA, y quedó 39 bytes peor.
        #     Lo cerró frida, mirando dónde lee el cliente de verdad (byte 5590 del paquete) y
        #     probando 44 / 45 / 46 / 84. Ver `GACHA_PERSONAJES_OFF` en `ajustes.py`.
        #   ⚠⚠ SI EL CLIENTE CAMBIA, ESTE NÚMERO SE MIDE, NO SE CUENTA. Contarlo ya falló dos veces;
        #     el contador es un solo byte y errarle mueve TODA la lista.
        #
        #   ⚠ Va sólo lo que está en `spec.txt`: el personaje BASE del jugador (el `char_id`, p.ej.
        #     130900) **no está ahí** y mandarlo daría "Spec data error". Y eso explica por qué la
        #     pestaña ya estaba vacía antes del gacha: no es una lista de "mis personajes", es la
        #     de **los que ganaste**.
        _pjs = personajes_de(char) if GACHA_LISTA_PERSONAJES else []
        # ★★ LA PRESENTACIÓN PERSONAL (29-sep) va ADENTRO de esos 45: en el byte 27 tras la 2ª lista
        #   (`0x5ED8B0`) el cliente lee `[letra][edad][largo][texto]`. Contado sobre el disasm y
        #   CRUZADO con el 45 medido del gacha: con el texto vacío las lecturas suman justo 45
        #   (`documentacion/PRESENTACION_PERSONAL.md` §3). ⚠ El texto CORRE el contador del gacha, y
        #   está bien: el cliente lee en secuencia. Sin esto la letra va en 0 y el cartel de
        #   «¿Desea escribirla ahora?» sale en cada entrada.
        if PRESENTACION_EN_FF03:
            from .presentacion import bloque_ff03               # noqa: PLC0415
            _pres = bloque_ff03(usn)
        else:
            _pres = bytes(3)                                    # letra 0 · edad 0 · largo 0
        # ★ 15-oct · EL TIEMPO DE HOY del cartel de la Misión de hoy («Hoy tu inicio de sesión continúa por X horas»):
        #   MEDIDO con frida (`_trabajo/cartel_tiempo/medida2.txt`): el cliente lo lee (`0x5EDB29` → `0x480CA0`) 12 bytes
        #   después de la LETRA de la presentación = en el byte `TIEMPO_HOY_EN_HUECO` (9) de los 15 en cero que van
        #   entre la presentación y el contador del gacha. Corre con el texto de la presentación, igual que el gacha.
        _hueco = bytearray(GACHA_PERSONAJES_OFF - PRESENTACION_OFF_FF03 - 3)
        try:
            from .mision_hoy import segundos_hoy_de                 # noqa: PLC0415
            struct.pack_into("<I", _hueco, TIEMPO_HOY_EN_HUECO, segundos_hoy_de(usn) & 0xFFFFFFFF)
        except Exception as _e_mh:                                  # noqa: BLE001
            log("LOBBY", f"  ⚠ misión de hoy (tiempo del FF03): {_e_mh!r}")
        p += bytes(PRESENTACION_OFF_FF03) + _pres + bytes(_hueco)
        p += bytes([len(_pjs) & 0xFF])                      # contador (u8)
        for _pj in _pjs:
            # ★ LOS 8 BYTES: los primeros 4 son la **VIDA (HP) ×10** — medido en `0x46F5BF`, que
            #   hace `ceil(valor/10)`, con `0x64` (=100) por defecto. Lo confirma el 2019, cuyos
            #   `CmdDecreasCharacterHP` / `RecoverCharacterHP` llaman a la función gemela.
            #   ⛔ Iban en CERO, o sea: el personaje llegaba con la vida en 0. Los otros 4 esa
            #     función no los lee — quedan en cero hasta que aparezca para qué son.
            p += (struct.pack("<I", _pj & 0xFFFFFFFF)
                  + struct.pack("<I", GACHA_PERSONAJE_HP * 10) + b"\x00" * 4)
        if _pjs:
            log("LOBBY", f"  ★★★ PERSONAJES del gacha en el MyRecord: {_pjs} "
                         f"(pestaña «Personaje» del armario)")
        p += b"\x00" * (158 - GACHA_PERSONAJES_OFF - 1)     # resto de la cola, INTACTO
    else:
        p += b"\x00" * 160                          # cola holgada (cubre hasta ~1847 > read total 1740)
        if STORE_MAP:                               # centinela 0xF0000000|offset en cada u32 escalar de la cola
            for d in TAIL_U32_DELTAS:
                struct.pack_into("<I", p, tail_start + d, (0xF0000000 | (tail_start + d)) & 0xFFFFFFFF)
        else:
            probe_deltas = TAIL_U32_DELTAS if PROBE_SEED else (REST_TEST or ())
            if probe_deltas:                        # centinela 7000000+offset en cada u32 de cola elegido
                for d in probe_deltas:              #   (deltas desde tail_start, del mapa myrec_reads.txt)
                    struct.pack_into("<I", p, tail_start + d, (7000000 + tail_start + d) & 0xFFFFFFFF)
            elif SEED_DELTA is not None:           # valor real de seed una vez ubicado el offset
                struct.pack_into("<I", p, tail_start + SEED_DELTA, SEED & 0xFFFFFFFF)
    # ★★★ PROGRESO DE MISIÓN (2026-07-30). MEDIDO con `re/trace_myrec_mision.py`: el cliente lee UN
    #   BYTE en el **offset 2083 (0x823)** del payload (call `0x5EE300`) y hace `[player+0x335] = ese
    #   byte` (`0x5EE30E`). Es el equivalente 2013 del `#64 -> player+0x331` del CBT, que allá también
    #   sale de la DB (`chars.mission`). Y es lo que otorga las licencias con máscara {6,7,8} en el
    #   bucle `0x489103` — que corre en el LOGIN, por eso mandarlo por FF81 después llegaba TARDE.
    _mis = int((db_get_char(usn) or {}).get("mission", 0) or 0)
    if PROBE_MISION_OFF:
        # ★ sonda: cada byte de la zona lleva su PROPIO índice (mod 256). El valor que aparezca en
        #   [player+0x335] delata el offset exacto, sin depender de mi aritmetica del ring.
        for _i in range(1900, min(2200, len(p))):
            p[_i] = _i & 0xFF
    elif MYREC_MISION_OFF is not None and MYREC_MISION_OFF < len(p):
        p[MYREC_MISION_OFF] = _mis & 0xFF
    return bytes(p)


def enviar_myrecord(st, name, con_personaje=True, saldo=False):
    """Manda el MyRecord. **El saldo de monedas gorila SÓLO va cuando `saldo=True`.**

    ★★★★★ LA REGLA, Y LAS DOS VECES QUE LA ERRÉ ANTES DE MEDIRLA (2026-09-10).

      El saldo viaja en el `count` del ítem 540 y **el cliente lo ACUMULA**: cada MyRecord que le
      llega con un número ahí se lo SUMA al que ya tenía (500 en la base -> 1000 en pantalla).

      · **Intento 1** — "sólo el llamador del login". Lo cambié porque VI en el log que al cambiar
        de canal el cliente no pide el `FF03`, y **supuse** que entonces se quedaría sin saldo.
      · **Intento 2** — "el primero de cada conexión". ⛔ Y un cambio de canal **abre una conexión
        nueva**, así que le mandaba el saldo otra vez. anonimo03 lo midió en el acto: *"aún se me está
        sumando 500 entre cambio de canales"*. Tres cambios de canal = +1500.

      ⇒ Lo que faltaba era el dato, no una idea mejor: **el cliente NO reinicia su contador al
        cambiar de canal.** Lo prueba justamente que se sumara. Así que el saldo tiene que ir
        UNA sola vez por **vida del cliente**, y la firma de eso está en el log:

            login de verdad   ->  RX FF03   (el cliente arma su ficha de cero)
            cambio de canal   ->  RX FF49, sin FF03

        Sólo la respuesta a un `RX FF03` lleva el saldo. Todo lo demás va en 0.

      ★ La lección, para no repetirla una tercera vez: **el intento 1 estaba bien**, y lo rompí
        actuando sobre una deducción mía (*"se quedaría sin saldo"*) que nadie había medido.
        anonimo03 nunca reportó que se le fueran las monedas: reportó otra cosa.

    ⚠ El default es `False`: un llamador nuevo que se olvide muestra de MENOS (se ve, se arregla),
      no infla la moneda en silencio.
    """
    # ⚠ Ver `MYRECORD_SALDO_EN_CADA_REFRESCO`: en `True` (el default, y como venía desde siempre)
    #   el saldo va en TODOS. Se dejó así al no sostenerse el diagnóstico de la duplicación.
    _con_saldo = bool(saldo or MYRECORD_SALDO_EN_CADA_REFRESCO)
    st.send_ff55(0x03, build_myrecord(usn=getattr(st, "usn", 0),
                                      con_personaje=con_personaje,
                                      moneda_gorila=_con_saldo),
                 name=name + ("" if _con_saldo else " (sin saldo de moneda: el cliente ya lo tiene)"))
    # ★★★ Y EL SALDO DE MONEDA GORILA, DETRÁS DE CADA MyRecord.
    #   Va acá y no en los llamadores para que **no se pueda olvidar**: los 8 sitios que mandan un
    #   MyRecord pasan por esta función. Y es idempotente, así que mandarlo de más no hace nada.
    # ⛔ 25-oct (anonimo03: el cartel «Ha recibido 4955438 Rcoin.» al abrir el juego): en el modo ELEGIR (el selector de
    #   personaje) el MyRecord va VACÍO — Rcoin 0 —, y el FF69 lleva el saldo REAL: el cliente compara (`0x5D0EBE`) y
    #   muestra la DIFERENCIA como si se la regalaran (texto 241). Sin personaje elegido no hay ítems que contar: no va.
    from .cuenta_personajes import eligiendo
    if eligiendo(getattr(st, "usn", 0)):
        return
    enviar_ff69_moneda_gorila(st)
    enviar_ff69_cargas(st)


def enviar_ff69_cargas(st):
    r"""Un `FF69` por cada CONSUMIBLE con cargas, para que el ícono muestre cuántos usos tiene.

    ⛔⛔ POR QUÉ HACE FALTA, Y ES EXACTAMENTE EL MISMO CASO DE LA MONEDA GORILA — 2026-09-15.
      anonimo03, con dos capturas al lado: *"cuando lo uso por primera vez recién marca el contador de
      usos; sin usarlo, la primera vista sale sin número"*.

      Y ese contraste lo dice todo: al **usar** un megáfono le mandamos un `FF69` con lo que le
      queda, y ahí sí aparece el número. Al **entrar** sólo le llega el MyRecord… y el número no
      aparece. ⇒ **El cliente dibuja la cantidad desde el `FF69`, no desde el `count` del
      MyRecord.**

    ★★ Es la misma conclusión que ya estaba escrita para el saldo de monedas
      (`MONEDA_GORILA_POR_FF69`): *"el MyRecord entra por `cAccount::AddInventory`…"*. Lo que no
      sabíamos es que valía para **todos** los consumibles, no sólo para el ítem 540.

    ⚠ Va DETRÁS del MyRecord y dentro de `enviar_myrecord`, por el mismo motivo que la moneda:
      los 8 sitios que mandan un MyRecord pasan por ahí, así que **no se puede olvidar**. Y es
      idempotente: mandarlo de más no suma nada (a diferencia del `count` del MyRecord, que el
      cliente ACUMULA — ver la nota de arriba).
    """
    if not FF69_CARGAS_AL_ENTRAR:
        return 0
    _usn = getattr(st, "usn", 0)
    _cargas = inv_cant(db_get_char(_usn) or {})
    _n = 0
    for _it, _c in _cargas.items():
        if _it == MONEDA_GORILA_ITEM or _c <= 0:
            continue                                  # la moneda ya va por su propia función
        st.send_ff55(0x69, (bytes([1]) + struct.pack("<I", _it & 0xFFFFFFFF)
                            + struct.pack("<H", _c & 0xFFFF)
                            + struct.pack("<I", db_get_rcoin(_usn) & 0xFFFFFFFF)),
                     name=f"FF69 cargas: {_c} del item {_it}")
        _n += 1
    if _n:
        log("LOBBY", f"  ★★ FF69 CARGAS: avisadas {_n} entrada(s) de consumible a usn={_usn} "
                     f"{dict(_cargas)} — sin esto el ícono sale SIN número hasta que lo usan")
    return _n


def enviar_ff69_moneda_gorila(st):
    """Le FIJA al cliente el saldo de monedas gorila con un `FF69` (`CmdGetItemCount`).

    ★★★★★ POR QUÉ ESTE PAQUETE Y NO EL MyRecord — ver `MONEDA_GORILA_POR_FF69` en `ajustes.py`,
      que tiene el porqué entero. En dos líneas: el MyRecord entra por `cAccount::AddInventory`,
      que **SUMA**; el `FF69` entra por `cAccount::SetInventory`, que **ASIGNA**. Los nombres son
      del cliente 2019 sin optimizar, y el reparto es idéntico en los dos builds.

    ★ Y es lo que hace el server de referencia: capturado con el ítem 540 adentro, con el
      contador subiendo a lo largo de la tarde (1 · 3 · 4 · 5 · 6).

    Layout (`0x5D0E00`):  `[modo:u8=1][item_id:u32][count:u16][rcoin_total:u32]` = 11 B
      · `modo` tiene que ser **1**, si no el handler se va por la rama de error (`0x5D0E67`).
      · el `rcoin_total` se manda **real**: si no coincide con el que el cliente ya tiene
        (`0x5D0EBE`) le sale un cartel de "+delta" que acá no queremos.

    ⚠ Es IDEMPOTENTE: mandarlo de más no cambia el número. Por eso va sin condiciones detrás de
      cada MyRecord, y no hay que llevar ninguna cuenta de cuántas veces se envió.
    """
    if not MONEDA_GORILA_POR_FF69:
        return
    _usn = getattr(st, "usn", 0)
    _gor = int(((db_get_char(_usn) or {}).get("monedas_gorila") or 0))
    _p = (bytes([1]) + struct.pack("<I", MONEDA_GORILA_ITEM & 0xFFFFFFFF)
          + struct.pack("<H", _gor & 0xFFFF)
          + struct.pack("<I", db_get_rcoin(_usn) & 0xFFFFFFFF))
    st.send_ff55(0x69, _p,
                 name=f"FF69 CmdGetItemCount: FIJA {_gor} Moneda(s) Gorila (item "
                      f"{MONEDA_GORILA_ITEM}) — asigna, no suma")
