# -*- coding: utf-8 -*-
"""carrera — el modo de juego: el modo de sala, las canciones del chase y el cartel final.

Está separado de `lobby_carrera.py` a propósito: acá van las piezas que ARMAN cosas y
que usan dos módulos de handlers distintos (`lobby_carrera` y `lobby_salas`); allá van
los handlers `FFxx` propiamente dichos. Si estás persiguiendo un comando, empezá por
`despacho.py`, no por acá.

Qué hay:
  · `calc_bymode` / `enviar_ff4b` — el `FF4B` es LO QUE FIJA EL MODO de la sala
  · `elegir_canciones_chase`      — las 3 canciones del cooperativo
  · `build_ff28_*` / `grado_de`   — el cartel de resultado y la nota (S/A/B/…)

⛔ `elegir_canciones_chase` verifica que la canción TENGA chart, una por una, en vez de
   confiar en la lista del picker. No es paranoia: en el chase, una canción sin chart
   hace que el cliente se auto-mate al terminar de pedir las notas (ver `notas.py`).
"""
import random
import struct
import threading

from . import notas
from .ajustes import (
    JEFE_CARGA_CAPITAN,
    JEFE_CARGA_COMPANERO,
    JEFE_CARGA_MS_AGRUPAR,
    JEFE_CARGA_POR_COMBO,
    JEFE_CARGA_POR_ITEM,
    JEFE_CARGA_POR_ITEM_CAPITAN,
    JEFE_EFECTOS_QUE_NO_CARGAN,
    JEFE_EFECTO_ID_MAX,
    JEFE_IMPULSOR,
    JEFE_IMPULSOR_TOPE,
    CHASE_FF1C_TYPE,
    CHASE_FILTRO_BANDAS,
    CHASE_BANDA_DEL_CANAL,
    CHASE_BANDA_MINIMO,
    CHASE_NIVEL_MAX,
    CHASE_NIVEL_MIN,
    CHASE_NUM_CANCIONES,
    COOP_EFECTOS_AYUDA,
    COOP_EFECTOS_BOOSTER,
    COOP_EFECTO_IMPULSOR,
    DEFAULT_ROOM_SONG,
    FF28_BASECOIN,
    CHASE_MEDALLON_POR_CAPTURA,
    CHASE_MEDALLON_POR_RONDA,
    FF28_CENTINELAS,
    FF28_BONUSTYPE_MILESIMAS,
    FF28_DERROTA_CEROS,
    PRECISION_MILESIMAS,
    FF28_CENTINELA_VALORES,
    FF28_WINTEAM,
    FF4B_BYMODE_ENC,
    FF4B_COLA_COLAB,
    FF4B_COLA_JEFE,
    FF4B_COLA_PROBE,
    FF4B_COLA_RELEVO,
    FF4B_RELEVO_BITS,
    FF4B_RELEVO_R7,
    FF4B_STR1_NOMBRE,
    HOST_SLOT,
    MODE_EQUIPO,
    MODE_RELEVO,
    MODE_VELOCIDAD,
    OWNED_SONGS_2013,
    RANK_BONUS_POR_PUESTO,
)
from .progresion import licencia_actual, modo_texto
from .registro import log
from .salas import (
    CONEXIONES,
    canciones_chase,
    conexiones_en_sala,
    dificultad_de,
    enviar_ready_npcs,
    mesa_de,
    poner_canciones_chase,
)


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ EL IMPULSOR DEL MODO JEFE — el server es el que lo carga
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# El porqué entero está en `ajustes.py`, arriba de `JEFE_IMPULSOR`. El resumen:
#   · en jefe el cliente NO carga la barra (`0x504F85`: si es jefe, sale)
#   · pero SÍ avisa cada 40 de combo (`FF4E sub=0x32`, `0x5050E7`)
#   · y `FF176 [n]` (`0x5DFEA0`) le SUMA `n` a la barra (`0x4FF9A0`), con tope 100
#   · ⚠ si se pasa del tope, el cliente **vacía** la barra ⇒ el server lleva su propio espejo
#
# El espejo vive en la SALA, no en la conexión: la barra es del equipo y la decisión mira a los
# tres. (Misma razón por la que la pista, la canción y los capitanes también son de la sala.)
IMPULSOR_JEFE = {}          # roomid -> {slot: carga 0..TOPE}          ★ nuestro espejo
_PEND_IMPULSOR = {}         # roomid -> {slot: cuánto falta mandarle}  (ventana de agrupado)
_TIMER_IMPULSOR = {}        # roomid -> threading.Timer vivo
_lock_impulsor = threading.RLock()


def reiniciar_impulsor(rid, motivo=""):
    """Pone en cero el espejo del impulsor de una sala. Va al arrancar cada carrera."""
    if rid is None:
        return
    with _lock_impulsor:
        IMPULSOR_JEFE.pop(rid, None)
        _PEND_IMPULSOR.pop(rid, None)
        _t = _TIMER_IMPULSOR.pop(rid, None)
    if _t is not None:
        _t.cancel()
    log("LOBBY", f"  ★ impulsor del jefe: espejo de la sala {rid} en cero{motivo}")


def impulsor_gastado(rid, slot):
    """El jugador disparó su impulsor (`FF4E sub=0x01`): su barra vuelve a cero."""
    if rid is None:
        return
    with _lock_impulsor:
        _sala = IMPULSOR_JEFE.get(rid)
        if not _sala or not _sala.get(slot):
            return
        _antes = _sala[slot]
        _sala[slot] = 0
    log("LOBBY", f"  ★ impulsor GASTADO por el slot {slot} (estaba en {_antes}) -> su barra a 0")


def _mandar_impulsor(rid):
    """Manda UN `FF176` por jugador con todo lo que se le juntó en la ventana."""
    from .salas import CONEXIONES, mesa_de          # tarde a propósito: `salas` no conoce a `carrera`
    with _lock_impulsor:
        _TIMER_IMPULSOR.pop(rid, None)
        _pend = _PEND_IMPULSOR.pop(rid, None) or {}
    if not _pend:
        return
    _mesa = mesa_de(rid)
    for _slot, _n in sorted(_pend.items()):
        _usn = _mesa.get(_slot)
        _c = CONEXIONES.get(_usn) if _usn is not None else None
        if _c is None or getattr(_c, "cerrado", False):
            continue
        try:
            # ★ `FF176` = `CmdPlusSpecialBooster`. UN byte, y es un INCREMENTO, no un total.
            #   Va UNICAST: el cliente sólo se lo aplica a su propio corredor (`0x4EB06A`:
            #   `cmp mi_slot, [racer+0x49]`), así que mandárselo a otro no hace nada.
            _c.send_ff55(0x176, bytes([_n & 0xFF]),
                         name=f"FF176 impulsor +{_n} al slot {_slot} "
                              f"(queda en {IMPULSOR_JEFE.get(rid, {}).get(_slot, 0)}/"
                              f"{JEFE_IMPULSOR_TOPE})")
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandar el FF176 al slot {_slot}: {e!r}")


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ LAS TRES COLUMNAS DEL CARTEL DE COOPERATIVO — las cuenta EL SERVER
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 2026-09-05. Cerrado con el `SendGameOver` del cliente 2019 (`0xCC43B0`, sin optimizar), que
# calza **62 de 62 bytes** con el reporte que nos manda el 2013:
#
#     @0  u32 frame · @4 u16 combo · @6 precisión · @7 estrella · @8 u16 coin · @10,@11 u8
#     @12 **32 bytes de hash MD5**
#     @44 u8
#     @45 ┌ u8, u8, u16, u16, u16, u16, u16  = ★ LOS MISMOS 12 BYTES DEL BLOQUE DEL CARTEL
#     @57 └ 5 u8  (en la captura: 49, 30, 37, 16, 121 — pinta de conteo de juicios)
#
# ⇒ El bloque de 12 del cartel **es el mismo que el cliente reporta**. Pero en la partida medida
#   vino **TODO EN CERO**, con el jugador habiendo usado **37 ítems**. O sea: el cliente NO los
#   cuenta. Los contaba el SERVIDOR original, con los avisos que ya recibe, y los devolvía en el
#   cartel para que todos vieran los de todos. Es el mismo patrón de siempre en este juego.
#
# Y los avisos ya los tenemos: `FF4E sub=0x01` trae **id del efecto + quién lo usó + a quién le
# pegó** (`A = destino<<24 | emisor<<16 | id<<8`). En una partida real llegaron 37.
#
# LAS TRES COLUMNAS, según el usuario (que las juega):
#   · **Usar Booster (x/y)** = cuántas veces apretó Control = disparó el impulsor
#   · **Ayuda (n)**          = ítems que benefician AL GRUPO (la inyección que purga los efectos
#                              del gorila, y los boosters rojo y celeste que impulsan al equipo)
#   · **Usar Item (x/y)**    = ítems usados en total
#
# ⏳ LO QUE FALTA, y se mide en UNA partida: qué id de efecto es el impulsor, y cuáles son los
#   ítems de grupo. Por eso `_tally_efectos` guarda el conteo POR ID y lo escupe al log al final:
#   se juega usando el impulsor a propósito y se mira qué id aparece.
EFECTOS_COOP = {}          # roomid -> {slot: {"ids": {id: n}, "a_otros": n, "total": n}}


AVANCE_COOP = {}                       # rid -> {slot: último avance en la pista (float)}


def anotar_avance(rid, slot, x):
    """Guarda dónde va ese corredor. Lo llama el relevo del `FF4E sub=0x05`.

    ★★★★★ PARA QUÉ (2026-09-10). anonimo03 corrigió la regla del modo: *"el que 'atrapó' es el que
      llega a estar lo más cerca del gorila y activa el minijuego"*. El server nunca supo eso —
      **y no lo sabe por ningún paquete**: el minijuego nace DENTRO del cliente y el referente no
      manda absolutamente nada para arrancarlo (medido en `mitm_20260909_181537`, el `FF10F` del
      cliente aparece sin que el server haya dicho una palabra).
      ⇒ Lo único que se puede hacer es **deducirlo**: el gorila corre adelante por la misma pista,
        así que el que va más adelante es el que lo tiene más cerca. Este es el dato que faltaba.
    ⚠ Es una INFERENCIA, no una medición: nadie comprobó en el exe que el disparador sea la
      proximidad. Por eso vive detrás de `CHASE_PRIMERO_EL_QUE_ACTIVA`, que se apaga en una línea.
    """
    if rid is None or slot is None:
        return
    with _lock_impulsor:
        AVANCE_COOP.setdefault(rid, {})[slot] = float(x)


def avance_de(rid):
    with _lock_impulsor:
        return dict(AVANCE_COOP.get(rid) or {})


def olvidar_avance(rid):
    with _lock_impulsor:
        AVANCE_COOP.pop(rid, None)


def anotar_efecto(rid, emisor, destino, id_efecto):
    """Anota un `FF4E sub=0x01` para el cartel. Barato y sin efectos: sólo cuenta."""
    if rid is None or emisor is None:
        return
    with _lock_impulsor:
        _sala = EFECTOS_COOP.setdefault(rid, {})
        _j = _sala.setdefault(emisor, {"ids": {}, "a_otros": 0, "total": 0, "orden": []})
        _j["ids"][id_efecto] = _j["ids"].get(id_efecto, 0) + 1
        _j["total"] += 1
        # ★ Y la SECUENCIA, no sólo el total. Los ítems salen al azar, así que pedirle al
        #   usuario cantidades exactas no es realista — pero acordarse del ORDEN sí. Con la
        #   secuencia acá, alcanza con que diga "primero el rojo, después el azul" y sale solo.
        # ⚠ Se guarda TAMBIÉN el destino: en cooperativo, apuntarle a otro slot es la firma de un
        #   ítem de AYUDA. Sin eso, la secuencia dice "qué" pero no "a quién", que es justo la
        #   mitad que hace falta para separar los de grupo de los individuales.
        _j["orden"].append((id_efecto, destino))
        # ★ En cooperativo son todos del mismo lado: apuntarle a OTRO slot es ayudar.
        #   ⚠ El `destino` también trae valores que NO son slots (se vio un `252` = 0xFC). Por eso
        #     sólo se cuenta 0..5, y lo demás se ignora en vez de sumarlo a ciegas.
        if destino != emisor and 0 <= destino <= 5:
            _j["a_otros"] += 1


def efectos_de(rid):
    with _lock_impulsor:
        return {k: dict(v) for k, v in (EFECTOS_COOP.get(rid) or {}).items()}


def cuentas_del_cartel(rid, slot):
    """Los tres números de las columnas del cooperativo, para un jugador.

    ★ EL ORDEN DEL PAR, ya no es opinión: **izquierda = usados · derecha = recibidos**. El
    cliente dibuja `(blk0 − blk1) / blk0` con `blk0` = boosters que te entraron y `blk1` =
    fallos con el booster puesto (`cHero::PushFailStat*`). Ver `COOP_ITEMS_Y_CONTADORES.md` §1.

    ⛔ `*_obtenidos` NO se puede contar hoy, y ahora se sabe POR QUÉ: agarrar un ítem no manda
    nada. `0x4F65A0` (`cGame::PickItem`) no llama al anunciador ni a `AddEffect` en sus 2.500
    bytes. Y el candidato viejo `FF4E sub=0x05` quedó descartado: esa función empuja el evento
    `0x00` y es una colisión contra un obstáculo.
    ⇒ Se devuelve el mismo valor que "usados" para que la columna salga "N/N" en vez de un `255`
    dado vuelta. Para tener "recibidos" de verdad hay que contarlos acá, del `sub=0x01`.
    """
    _d = (efectos_de(rid) or {}).get(slot) or {}
    _ids = _d.get("ids") or {}
    _items = _d.get("total", 0)
    _boost = sum(n for k, n in _ids.items() if k in COOP_EFECTOS_BOOSTER)
    _ayuda = sum(n for k, n in _ids.items() if k in COOP_EFECTOS_AYUDA)
    return {"items": _items, "items_obtenidos": _items,
            "boosters": _boost, "boosters_obtenidos": _boost,
            "ayuda": _ayuda}


def olvidar_efectos(rid):
    with _lock_impulsor:
        EFECTOS_COOP.pop(rid, None)


def efecto_del_jefe(st, rid, id_efecto):
    """`FF4E sub=0x01` = se aplicó un efecto. Decide qué hacer según CUÁL efecto.

    ★★ Son dos cosas distintas viajando por el mismo aviso, y separarlas es todo el truco:

      · efecto **`0xF3`** = el jugador DISPARÓ el impulsor del jefe (`0x50C7E5`). Su barra
        vuelve a cero, y **no se le carga nada** — si no, el impulsor se recargaría a sí mismo.
      · cualquier **otro** efecto = usó un ítem (o le cayó uno encima) ⇒ **carga**.

    Devuelve `"disparo"`, `"item"` o `None`.
    """
    if rid is None or not getattr(st, "room_boss", False):
        return None
    _slot = getattr(st, "room_slot", None)
    if _slot is None:
        return None
    if id_efecto in JEFE_EFECTOS_QUE_NO_CARGAN:
        impulsor_gastado(rid, _slot)
        return "disparo"
    if not JEFE_IMPULSOR or JEFE_CARGA_POR_ITEM <= 0:
        return None
    # ★ La red de seguridad: si el id no cae en el rango de los efectos, es que estamos leyendo
    #   el campo equivocado. Mejor no cargar que cargar de más (ver `JEFE_EFECTO_ID_MAX`).
    if not (0 < id_efecto <= JEFE_EFECTO_ID_MAX):
        log("LOBBY", f"  ⚠ IMPULSOR JEFE: efecto id={id_efecto} fuera de rango -> NO cargo. "
                     f"Si esto se repite, el id del efecto no viaja en el campo que creemos.")
        return None
    # ★ El ítem carga a TODO el equipo — es lo que describe el usuario del video (*"recarga a sí
    #   mismo o aliados"*) — y el CAPITÁN un poco más.
    _repartir(st, rid,
              lambda _s, _cap: (JEFE_CARGA_POR_ITEM_CAPITAN if _s == _cap
                                else JEFE_CARGA_POR_ITEM),
              f"el slot {_slot} usó un ÍTEM (efecto {id_efecto}/0x{id_efecto:X})")
    return "item"


def _repartir(st, rid, cuanto_para, motivo):
    """Le suma impulsor a TODO el equipo del que disparó el evento. Devuelve a cuántos.

    `cuanto_para(slot, slot_del_capitan)` decide el monto de cada uno — así la regla de los
    combos (capitán +25 / resto +20) y la de los ítems (plano) comparten toda la mecánica.

    ⚠ No manda nada acá: acumula y arranca la ventana de agrupado. El byte del `FF176` se
      consume por frame en el cliente, y los tres compañeros cruzan la nota 40 casi juntos —
      sin agrupar, cada uno recibiría tres paquetes pegados y perdería dos.
    """
    from .salas import capitanes_de, equipo_de, mesa_de
    if not JEFE_IMPULSOR or rid is None or not getattr(st, "room_boss", False):
        return 0
    _slot = getattr(st, "room_slot", None)
    if _slot is None:
        return 0
    _eq = equipo_de(rid, _slot)
    _cap_slot = capitanes_de(rid).get(_eq)
    _companeros = [s for s in sorted(mesa_de(rid)) if equipo_de(rid, s) == _eq]
    _detalle = []
    with _lock_impulsor:
        _sala = IMPULSOR_JEFE.setdefault(rid, {})
        _pend = _PEND_IMPULSOR.setdefault(rid, {})
        for _s in _companeros:
            _cuanto = cuanto_para(_s, _cap_slot)
            _antes = _sala.get(_s, 0)
            # ★★ EL RECORTE ES LO QUE EVITA QUE EL CLIENTE VACÍE LA BARRA. `0x4FF9A0` compara
            #    contra el tope DESPUÉS de sumar y, si se pasó, la pone en cero. Mandamos sólo lo
            #    que falta para llegar a 100, ni un byte más.
            _real = min(_cuanto, JEFE_IMPULSOR_TOPE - _antes)
            if _real <= 0:
                _detalle.append(f"slot {_s}: LLENA")
                continue
            _sala[_s] = _antes + _real
            _pend[_s] = _pend.get(_s, 0) + _real
            _detalle.append(f"slot {_s}{'★' if _s == _cap_slot else ''}: "
                            f"{_antes}->{_sala[_s]} (+{_real})")
        _hay = bool(_pend)
        _ya = _TIMER_IMPULSOR.get(rid) is not None
    log("LOBBY", f"  ★★★ IMPULSOR JEFE: {motivo} -> equipo {_eq} "
                 f"(capitán slot {_cap_slot}) | " + " · ".join(_detalle))
    if _hay and not _ya:
        if JEFE_CARGA_MS_AGRUPAR > 0:
            _t = threading.Timer(JEFE_CARGA_MS_AGRUPAR / 1000.0, _mandar_impulsor, args=(rid,))
            _t.daemon = True
            with _lock_impulsor:
                _TIMER_IMPULSOR[rid] = _t
            _t.start()
        else:
            _mandar_impulsor(rid)
    return len(_companeros)


def cargar_impulsor_jefe(st, rid):
    """★ Un jugador llegó a un múltiplo de 40 de combo (`FF4E sub=0x32`).

    Le carga el impulsor a TODO su equipo, y al **capitán un poco más**. Es la regla NUESTRA
    (ver el bloque de `JEFE_IMPULSOR` en `ajustes.py`); del juego son sólo los dos números,
    el 40 del aviso y el 100 del tope.

    ⛔ **APAGADA por defecto** (`JEFE_CARGA_POR_COMBO = False`): el usuario se quedó con la
       fuente de los ítems sola. La función queda entera y probada; la señal `sub=0x32` se
       sigue logueando, así que se la ve pasar aunque no cargue.
    """
    if not JEFE_CARGA_POR_COMBO:
        return 0
    return _repartir(st, rid,
                     lambda _s, _cap: (JEFE_CARGA_CAPITAN if _s == _cap
                                       else JEFE_CARGA_COMPANERO),
                     f"el slot {getattr(st, 'room_slot', '?')} llegó a otro x40 de combo")


def calc_bymode(flags):
    if FF4B_BYMODE_ENC == "eco":
        return flags & 0xFF
    equipo = bool(flags & MODE_EQUIPO) or bool(flags & MODE_RELEVO)
    item   = not (flags & MODE_VELOCIDAD)
    by = (0x10 if equipo else 0) | (0x04 if item else 0)     # ✅ confirmados en vivo
    if flags & MODE_RELEVO:
        by |= FF4B_RELEVO_BITS
    return by & 0xFF


def elegir_canciones_chase(n=CHASE_NUM_CANCIONES, banda=None):
    """n canciones al azar de las que TIENEN chart (OWNED_SONGS_2013 = validadas por el mapa de notas)."""
    # ⚠⚠ CADA cancion del chase DEBE tener chart servible: el cliente pide un FF57 por cancion del
    #   FF25 y un result=0 lo AUTO-MATA (ver el handler del 0x57). Por eso se verifica de verdad
    #   (notas.hay_chart) en vez de confiar en que OWNED_SONGS_2013 este completo.
    from .ajustes import CHASE_CANCIONES_PRUEBA
    if CHASE_CANCIONES_PRUEBA:                      # ★ 16-oct: sólo pruebas (R2_CHASE_CANCIONES), ver ajustes
        return (CHASE_CANCIONES_PRUEBA * n)[:n]
    pool = list(OWNED_SONGS_2013 or [DEFAULT_ROOM_SONG])
    # ★★★ EL SORTEO SIGUE LA BANDA DEL CANAL (2026-09-05). Regla del usuario, con la captura de la
    #   lista de canales en la mano: *"si estamos en Luna = músicas Luna; si la licencia del master
    #   es Novato Luna = músicas Novato Luna"*. Ver `CHASE_BANDA_DEL_CANAL` en `ajustes.py`.
    #   ⚠ Si esa banda tiene poco, se AMPLÍA hacia abajo banda por banda y se dice en el log: la
    #     banda 7 (Sol) tiene 3 canciones nuestras, justo las de una partida.
    if CHASE_BANDA_DEL_CANAL and banda:
        _orden = list(notas.ORDEN_BANDAS)
        if banda in _orden:
            _usadas, _fil = [], []
            for _b in reversed(_orden[:_orden.index(banda) + 1]):     # la pedida y hacia abajo
                _r = notas.rango_de_banda(_b)
                if not _r:
                    continue
                _usadas.append(_b)
                _fil += [s for s in pool if _r[0] <= (notas.nivel_de(s) or 0) <= _r[1]]
                if len(_fil) >= max(CHASE_BANDA_MINIMO, n):
                    break
            if len(_fil) >= n:
                pool = _fil
                _txt = " + ".join(f"{notas.NOMBRE_BANDA.get(x, x)}" for x in _usadas)
                log("LOBBY", f"  ★ sorteo en la banda {banda} ({notas.NOMBRE_BANDA.get(banda, '?')})"
                             + (f" — ampliada a [{_txt}] porque sola no llegaba a "
                                f"{max(CHASE_BANDA_MINIMO, n)}" if len(_usadas) > 1 else "")
                             + f": {len(pool)} canciones")
            else:
                log("LOBBY", f"  ⚠ la banda {banda} y las de abajo dan {len(_fil)} canciones y "
                             f"hacen falta {n} -> sorteo SIN filtro")
    elif CHASE_NIVEL_MIN is not None or CHASE_NIVEL_MAX is not None:
        # Modo manual: un rango de niveles a dedo (sólo con `CHASE_BANDA_DEL_CANAL = False`).
        _fil = [s for s in pool
                if (CHASE_NIVEL_MIN is None
                    or (notas.nivel_de(s) or 0) >= CHASE_NIVEL_MIN)
                and (CHASE_NIVEL_MAX is None
                     or (notas.nivel_de(s) or 99) <= CHASE_NIVEL_MAX)]
        if len(_fil) >= n:
            pool = _fil
        else:
            log("LOBBY", f"  ⚠ filtro de nivel [{CHASE_NIVEL_MIN}..{CHASE_NIVEL_MAX}] deja sólo "
                         f"{len(_fil)} canciones y hacen falta {n} -> sorteo SIN filtro")
    random.shuffle(pool)
    # ★ (97) el tope de sonidos: las 3 juntas no pueden pasar CHASE_EFECTOS_TOPE `<EFFECT>` (si no, el BGM de la
    #   siguiente no entra en Miles y la sala entera se cae, ver ajustes). Una que haría pasar el tope se saltea.
    from .ajustes import CHASE_EFECTOS_TOPE
    elegidas, salteadas = [], 0
    for sid in pool:
        if notas.hay_chart(sid):
            if (CHASE_EFECTOS_TOPE is not None
                    and sum(notas.efectos_de(x) for x in elegidas) + notas.efectos_de(sid) > CHASE_EFECTOS_TOPE):
                salteadas += 1
                continue
            elegidas.append(sid)
            if len(elegidas) >= n:
                break
    if salteadas:
        log("LOBBY", f"  ★ cooperativo: {salteadas} canción(es) salteada(s) por el tope de sonidos "
                     f"({CHASE_EFECTOS_TOPE} efectos entre las {n})")
    if CHASE_EFECTOS_TOPE is not None and elegidas and len(elegidas) < n:
        # ★ 07-nov: con una pesada adentro (The Festival of Ghost 2: 598 sonidos) puede que ninguna otra entre. Se
        #   completa con las MÁS LIVIANAS del pozo mientras no pase el tope (antes se repetía la pesada: 598+598+…).
        for sid in sorted((s for s in pool if s not in elegidas and notas.hay_chart(s)), key=notas.efectos_de):
            if len(elegidas) >= n or sum(notas.efectos_de(x) for x in elegidas) + notas.efectos_de(sid) > CHASE_EFECTOS_TOPE:
                break
            elegidas.append(sid)
    if not elegidas:
        elegidas = [DEFAULT_ROOM_SONG]
    while len(elegidas) < n:                     # si no alcanzan, se repiten (mejor que un result=0)
        elegidas.append(min(elegidas, key=notas.efectos_de) if CHASE_EFECTOS_TOPE is not None   # ★ la más liviana
                        else elegidas[len(elegidas) % len(elegidas)])
    if CHASE_EFECTOS_TOPE is not None:           # ★ (97) la de MÁS sonidos al final: sus efectos van después de los BGM
        elegidas = sorted(elegidas[:n], key=notas.efectos_de)
    return elegidas[:n]


_centinelas_avisadas = False


def _avisar_centinelas():
    """Escribe la leyenda de las centinelas del cartel, UNA vez por corrida del server.

    ⛔ POR QUÉ — 2026-09-05. `FF28_CENTINELAS` quedó prendido desde el 02-sep y nadie anotó el
    resultado: tres días mandando números de sonda al cartel sin cobrar el mapeo. El usuario lo
    detectó porque *"el valor de booster - item - ayuda siempre son los mismos"*.
    Ahora, si están prendidas, el log dice qué número es qué campo. Así una foto del cartel
    alcanza para mapear las tres columnas que faltan, sin tener que acordarse de nada.
    """
    global _centinelas_avisadas
    if _centinelas_avisadas or not FF28_CENTINELAS:
        return
    _centinelas_avisadas = True
    log("LOBBY", "  ⚠⚠ FF28 CON CENTINELAS PRENDIDAS — el cartel va con números de SONDA, no con "
                 "datos. SACÁ LA FOTO del cartel y cruzala contra esta leyenda:")
    _campo = {}
    for k, v in FF28_CENTINELA_VALORES.items():
        if k.startswith("b12_"):
            _campo[v] = f"byte {k[4:]} del bloque de 12"
        elif k.startswith("c"):
            _campo[v] = f"campo `{k}` del bloque"
        else:
            _campo[v] = f"`{k}` (suelto del final de la fila)"
    for v in sorted(_campo):
        log("LOBBY", f"       {v:>4}  = {_campo[v]}")
    log("LOBBY", "     ★ YA CONFIRMADO con la foto del 2026-09-05:  'Ayuda (n)' = `b_f`  ·  "
                 "'Usar Item (x/y)' = `b_d` / `b_e`.  Falta SÓLO 'Usar Booster (x/y)'.")
    log("LOBBY", "     ⇒ Cuando tengas la foto, APAGÁ `FF28_CENTINELAS` en el mismo día.")


def asegurar_canciones_chase(st, motivo, resortear=False):
    """Deja la sala con sus 3 canciones del cooperativo. Devuelve la lista.

    ★★★★★ POR QUÉ EXISTE — 2026-09-05, dos bugs del usuario con la misma raíz.
    El sorteo vivía en `st.chase_songs` y se hacía **sólo** en el handler del `FF4B` (cambio de
    modo). De ahí salían las dos cosas que reportó:

      1. *"al crear la sala YA en cooperativo y dar START se carga 1 música en vez de 3, y
         siempre la misma"* — creando la sala en cooperativo el `FF4B` nunca corre, así que no
         había sorteo y el `FF25` caía al `[song]` de una sola canción. Por eso andaba si
         cambiabas a otro modo y volvías: recién ahí pasaba por el `FF4B`.
      2. *"al volver a la sala y empezar otra partida se repiten las 3"* — sin cambio de modo,
         nadie volvía a sortear.

    ⇒ Ahora el sorteo es **de la sala** (`CANCIONES_CHASE`, ver `salas.py`) y se llama desde los
      tres lados: al crear la sala en cooperativo, al cambiar el modo, y **en cada START** con
      `resortear=True`. La copia en `st.chase_songs` se mantiene sincronizada en TODAS las
      conexiones de la sala porque el panel de música la lee de ahí.
    """
    rid = getattr(st, "room_id", None)
    canciones = None if resortear else canciones_chase(rid)
    if not canciones:
        # ★★★★★ MANDA LA TUERCA, Y SI NADIE LA TOCÓ, LA LICENCIA DEL ANFITRIÓN (2026-09-10).
        #
        #   ⛔ EL BUG QUE ESTO ARREGLA, cazado por anonimo03 probando en vivo: *"soy master Sol, puse
        #     la tuerca en Novato Luna, y las músicas que se cargaron son de Sol"*. Y el log local
        #     lo dice sin lugar a dudas:
        #         12:55:07  FFC9 eco dificultad=4 (la pidió él)     ← movió la tuerca a 4
        #         12:55:07  FF13 ROOMINFO ... banda=4               ← la sala se guardó en 4
        #         12:55:09  ★ sorteo en la banda 7 (Sol)            ⛔ sorteó en 7 igual
        #
        #   CAUSA: acá se leía **sólo** la licencia (`licencia_actual`), que para un Sol es 7
        #   siempre. La tuerca se guardaba en la sala (`DIFICULTAD_SALA`) y **nadie la miraba** a
        #   la hora de sortear.
        #
        #   ★ Y que la tuerca mande es lo COHERENTE, no una preferencia mía: ese mismo valor ya le
        #     reaplica el filtro al picker de música (`FFC9 banda=N EN SALA` -> `[cRoom+0x9512]`).
        #     O sea que en los modos normales la tuerca YA decide qué canciones se pueden elegir.
        #     En cooperativo elige el server: tiene que respetar el mismo filtro.
        #   ⚠ `dificultad_de` devuelve `None` si nadie la tocó — y ahí sigue mandando la licencia,
        #     que es como venía. Las salas que no usan la tuerca no cambian en nada.
        _banda = dificultad_de(rid) or licencia_actual(getattr(st, "usn", 0))[1]
        canciones = elegir_canciones_chase(
            getattr(st, "chase_n", None) or CHASE_NUM_CANCIONES, banda=_banda)
        poner_canciones_chase(rid, canciones)
        # ★ Con el nivel al lado: es la única forma de ver de un vistazo si el filtro de
        #   dificultad está haciendo lo suyo (ver `CHASE_NIVEL_MIN` en `ajustes.py`).
        _det = ", ".join(f"{s} (niv {notas.nivel_de(s, '?')} = banda {notas.banda_de(s)}, "
                         f"{notas.titulo_de(s)})" for s in canciones)
        log("LOBBY", f"  ★★ CHASE: {len(canciones)} canciones sorteadas para la sala {rid} "
                     f"[nivel mín {CHASE_NIVEL_MIN}] -> {_det} — {motivo}")
    # ★ Espejo en cada conexión de la sala: si sólo se lo pongo al que disparó, el panel de
    #   música del invitado muestra otra canción. Es el error de siempre en este server.
    # ★ Y los que MIRAN: el panel de música de la sala es el mismo para ellos (2026-09-08).
    destinos = conexiones_en_sala(rid) if rid is not None else []
    for c in [c for c in destinos if c is not None] or [st]:
        c.chase_songs = list(canciones)
        c.room_song = canciones[0]
    st.chase_songs = list(canciones)
    st.room_song = canciones[0]
    return canciones


def enviar_ff4b(st, flags, rname, colab, boss):
    """★★★ Respuesta del FF4B CmdChangeRoomMode = LO QUE FIJA EL MODO DE LA SALA (handler cliente
    0x5CFE20, applier 0x5971F0). Layout por conteo de lecturas:
        [result:u8=1]  ⚠ si != 1 el handler ABORTA en 0x5CFE68
        [byMode:u8]    bit2 = ITEM · bit4 = EQUIPO   (los dos CONFIRMADOS en vivo 2026-07-30)
        [len1:u8][str1]   str1 = ★TITULO de la sala (confirmado por el usuario en vivo)
        [len2:u8][str2]
        [r7][r8][r9][r10][r11]  5 u8 · en el handler: r9!=0 -> flags|=4 · r11!=0 -> flags|=8, y esos
                                flags viajan como bySuperRoomCoupons (test bl,4 -> cRoom+0x951C)
    ★ MEDIDO: con r7=r8=r10=1 la sala se fue a **modo COOPERATIVO** ⇒ el colab sale de alguno de
      esos tres (NO de r9, como suponia). Se bisecta con FF4B_COLA_PROBE."""
    bymode = calc_bymode(flags)
    # ★★ 29-sep: y el candado (bit 0x01), igual que el @8 del FF13 que este byte espeja: si no, al tocar
    #   la configuración el cliente se quedaría con el modo nuevo SIN el candado. Ver `lobby_salas`.
    from .salas import CLAVE_SALA
    if CLAVE_SALA.get(getattr(st, "room_id", None)):
        bymode |= 0x01
    nb = rname.encode("cp1252", "replace")[:0xFF]
    s1 = nb if FF4B_STR1_NOMBRE else b""
    cola5 = [0, 0, 0, 0, 0]                       # r7 r8 r9 r10 r11
    if colab:
        for _i in FF4B_COLA_COLAB:
            cola5[_i] = 1
    if boss:
        for _i in FF4B_COLA_JEFE:
            cola5[_i] = 1
    if flags & MODE_RELEVO:
        for _i in FF4B_COLA_RELEVO:
            cola5[_i] = 1
        if FF4B_RELEVO_R7:                        # ★ hipotesis: r7 = enum de modo de equipo
            cola5[0] = FF4B_RELEVO_R7 & 0xFF
    if FF4B_COLA_PROBE:                           # sonda manual: pone en 1 los indices que se pidan
        for _i in FF4B_COLA_PROBE:
            cola5[_i] = 1
    resp = (bytes([1, bymode & 0xFF]) + bytes([len(s1)]) + s1 + bytes([0]) + bytes(cola5))
    st.send_ff55(0x4B, resp, name=f"FF4B ChangeRoomMode result=1 byMode=0x{bymode:02X} cola={cola5}")
    log("LOBBY", f"  ★★★ FF4B modo = {modo_texto(flags, colab, boss)} [flags=0x{flags:02X}] -> "
                 f"result=1 byMode=0x{bymode:02X} (enc '{FF4B_BYMODE_ENC}') cola={cola5} "
                 f"titulo={rname!r}")
    # ★★★ COOPERATIVO (chase) — RESUELTO 2026-08-04, MEDIDO EN VIVO CON FRIDA.
    #
    #   El muro era el BOTON START del cliente (`0x59b570`), que se frena SOLO y ni siquiera manda el
    #   FF24 (medido: cero trafico al server). Su gate, en `0x59b5b2`:
    #       mov eax,[[0x9314ec]+0x48] ; cmp eax,2 -> ok ; cmp eax,3 -> ok
    #       cmp dword [[0x9314ec]+0x4c],0 ; jle -> CARTEL 98 ("seleccione musica")
    #   ⇒ traducido: *"si la MANERA DE LISTA es 2 o 3, arranca sin seleccionar nada; si no, tenes que
    #     tener al menos una cancion elegida"*.
    #
    #   ★ Los dos campos son literalmente el panel "Info Musica" del cliente (lo confirmo una captura):
    #       `+0x48` = **"Manera de Lista de juego"**: 1 En orden · 2 Aleatorio · 3 TOP 20 ALEATORIO ·
    #                 4 NUEVOS 20 ALEATORIO   ← el default en sala es **4**, y por eso pedia seleccion
    #       `+0x4c` = **"Musica seleccionada"** (el contador que se ve abajo a la izquierda)
    #   ⇒ el cooperativo no necesita ningun contador inventado: necesita la manera de lista en
    #     **ALEATORIO**, que es exactamente lo que el modo hace por diseño.
    #   ✅ VERIFICADO EN VIVO: escribiendo `+0x48 = 2` con el contador en 0, el START arranco la
    #      partida entera (FF24 -> FF25 -> FF57 -> FF24 GO). Sin parchear el exe.
    #
    #   ⚠ LO QUE FALTA CONFIRMAR: que el server pueda fijar ese `+0x48` por PROTOCOLO. El candidato es
    #     el `FF1C CmdEditMusic`, cuyo 4º campo los devs llamaron `byMusicLoopType` (nombre sacado del
    #     log del propio cliente) — o sea, la misma "manera de lista". Se manda abajo y se MIDE.
    if colab:
        # ★ `resortear=True`: cambiar el modo A cooperativo es un arranque limpio, se sortea de
        #   nuevo. El START vuelve a sortear igual (ver `asegurar_canciones_chase`).
        asegurar_canciones_chase(st, "cambio de modo a cooperativo (FF4B)", resortear=True)
        # ★ Fijar la MANERA DE LISTA en aleatorio + abrir el filtro de bandas del picker.
        #   Layout del FF1C: [type:u8][music:u16][byMusicLoopType:u8][byMusicLevelFilter:u8]
        #   El `type` es el mismo 5 que usa el cliente cuando toca el picker (`SendEditMusicFromRoom`).
        if CHASE_FF1C_TYPE is not None:
            _ff1c = (bytes([CHASE_FF1C_TYPE & 0xFF]) + struct.pack("<H", 0)
                     + bytes([0, CHASE_FILTRO_BANDAS & 0xFF]))
            st.send_ff55(0x1C, _ff1c, name=f"FF1C type=0x{CHASE_FF1C_TYPE:02X} (play sequence)")
            log("LOBBY", f"  ★★★ CHASE: FF1C type=0x{CHASE_FF1C_TYPE:02X} -> SetPlaySequence("
                         f"{2 if CHASE_FF1C_TYPE == 0x1F else 3}) ⇒ [[0x9314ec]+0x48] deberia pasar a "
                         f"{2 if CHASE_FF1C_TYPE == 0x1F else 3} y el START se destraba")
    # ★ RE-AFIRMAR EL LISTO DEL NPC: al aplicar un cambio de modo el cliente REARMA los slots y el
    #   NPC vuelve a "no listo" (lo reporto el usuario). Se le manda de nuevo el FF17 para que el
    #   botón START del host no se traben. Mismo paquete que tras el FF0C.
    if getattr(st, "ghost", False):
        enviar_ready_npcs(st, " tras cambio de modo")

def build_ff28_cartel(frame, combo, pd, star, coin, exp, perdio):
    """★★ EL CARTEL DE RESULTADO (S->C FF28). Devuelve `(grado, body)`.

    Layout REAL, trazado byte a byte del handler `0x5E9360` (2026-08-04). Con 1 fila e `inner_count=0`
    el cliente consume **46 bytes**:

        [b0][b1][b2][count]
        por fila: [pos:u8][rank:u8][rank_bonus:u16][exp:u16][combo:u16][pd:u8][star:u8][coin:u16]
                  [basecoin:u32][frame:u32][12 bytes][inner_count:u16]  + inner_count x [u16]
                  [b_a][★b_b = LETRA DEL MEDALLÓN][b_c][b_d][b_e][b_f][b_g]
        [grade:u8]   <- el de las CAJAS del chase (`0x57EAA0`), también ASCII

    ★★★ La letra del medallón es `b_b` (-> `struct+0x3C` -> `fila_ui+0xA3` -> draw `0x578C33` ->
    `0x5789B0`). **`0x5789B0` NO recibe un índice: recibe el CARÁCTER ASCII** y lo mapea con un
    `switch` ('S'->0 'A'->1 'B'->2 'C'->3 'D'->4 'F'->5) cuyo **`default` es 0 = 'S'**.
    ⇒ mandar el paquete CORTO (o un 0x00) cae en el default ⇒ **medallón "S" siempre**. Ésa era la
    "S pegada": no era un cálculo del cliente, era nuestro paquete quedándose corto.
    ⚠ ERROR PROPIO: la 1ª versión puso la letra como byte 39 = el final del paquete; cayó en `b_a` y
      los 6 siguientes se leyeron de un buffer agotado. El byte no sobraba: estaba mal ubicado.
    ✅ Ningún valor de estos bytes puede crashear: el `switch` acota (`cmp eax,0x12 / ja default`).

    ★ El EXP y el RCOIN que se VEN salen tal cual de acá (`0x579E92` y `0x579E70`): el cliente no
      calcula nada. El Rcoin mostrado es `(u16)(coin + basecoin)` -> se trunca a 16 bits.
    ⏳ ABIERTO: `0x5E9414` -> si `0x4A0C50()` devuelve 6, el handler lee 8 bytes EXTRA en el prefijo y
      todo se desalinea. Hoy no nos pasa; medirlo si algún día el cartel sale con basura."""
    if perdio:   grado = 0x46                             # 'F'
    elif pd >= 95: grado = 0x53                           # 'S'
    elif pd >= 90: grado = 0x41                           # 'A'
    elif pd >= 80: grado = 0x42                           # 'B'
    elif pd >= 70: grado = 0x43                           # 'C'
    elif pd >= 60: grado = 0x44                           # 'D'
    else:          grado = 0x46                           # 'F'
    row = build_ff28_fila(frame, combo, pd, star, coin, exp, perdio, slot=HOST_SLOT, puesto=1)
    return grado, bytes([FF28_WINTEAM & 0xFF, 0, 0, 1]) + row + bytes([grado])


def medallon_del_gorila(ronda_captura):
    """La letra del medallón en COOPERATIVO: sale de **qué tan rápido atraparon al gorila**.

    ★★★ LA REGLA LA DIO ANONIMO03, que es el que lo juega (2026-09-15):
      *"si lo atrapan durante la primera canción es un S, si durante la segunda un B, si durante
      la tercera un D"*, y *"si no lo atrapan es F = perder — lo que ocurre cuando las canciones
      se acaban y el gorila escapa"*.

    ⛔⛔ EL BUG QUE ESTO ARREGLA, medido en el log de PROD (partida de las 15:49:19, 6 jugadores):

          slot 4  pd=97 -> S      ← el que lo atrapó
          slot 2  pd=91 -> A
          slot 1  pd=85 -> B      slot 5  pd=86 -> B
          slot 0  pd=88 -> B      slot 3  pd=88 -> B

      **Cinco de seis sacaron B habiendo atrapado al gorila**, porque el medallón salía de
      `grado_de(pd)` — la precisión personal — y no de la captura. Y la S del slot 4 fue por su
      97 de precisión, **no por haberlo atrapado**: con 90 habría sacado A igual que el otro.
      ⇒ Era justamente lo que anonimo03 reportó: *"reciben rangos bajos aunque lo hayan capturado en
        la primera canción"*.

    ★★ Y EL MEDALLÓN LO MANDA EL SERVER, no lo calcula el cliente: es el byte `b_b` de la fila
      (`0x5789B0` recibe el CARÁCTER ASCII y lo mapea con un switch). O sea que esto es nuestro
      de punta a punta — no hay nada que pedirle al cliente.

    ⚠⚠ `ronda_captura` es **la ronda del minijuego**, no la canción. Que una ronda sea una canción
      es lo más probable pero **no está medido**: en prod aparecen rondas 0..5 con 3 canciones
      (14473 · 8882 · 3096 · 606 · 6 apariciones), así que puede haber más de una ronda por
      canción. Por eso los cortes son **perillas** (`CHASE_MEDALLON_POR_RONDA`) y no números
      escritos acá: se afinan jugando, que es como anonimo03 los puede corregir sin tocar código.
    """
    if ronda_captura is None:
        return 0x46                                       # 'F' — el gorila se escapó
    for _corte, _letra in CHASE_MEDALLON_POR_RONDA:
        if ronda_captura <= _corte:
            return _letra
    return 0x46


def grado_de(pd, perdio):
    """La LETRA del medallón, en ASCII. El cliente no la calcula: la muestra tal cual."""
    if perdio:     return 0x46                            # 'F'
    if pd >= 95:   return 0x53                            # 'S'
    if pd >= 90:   return 0x41                            # 'A'
    if pd >= 80:   return 0x42                            # 'B'
    if pd >= 70:   return 0x43                            # 'C'
    if pd >= 60:   return 0x44                            # 'D'
    return 0x46                                           # 'F'


def build_ff28_fila(frame, combo, pd, star, coin, exp, perdio, slot=HOST_SLOT, puesto=1,
                    rank_bonus=None, cuentas=None, bonus=(), milesimas=0,
                    ronda_captura=None, es_coop=False):
    """UNA fila del cartel = 34 bytes. Ver el layout completo en build_ff28_cartel().

    `rank_bonus=None` = escalera por puesto (el modo SOLO). Los modos por equipos pasan el valor
    a mano, porque ahí no hay escalera: es 700 al ganador y 300 al perdedor, plano. Ver
    `RANK_BONUS_SOLO` / `RANK_BONUS_GANADOR` en `ajustes.py`.

    ★ `milesimas` (0..999) = la parte decimal de la precisión. La precisión entera sigue viajando
      en su byte de siempre; esto viaja aparte, como un renglón de bonus de tipo reservado.
      Con 0 (o con `PRECISION_MILESIMAS = False`) la fila sale **byte por byte igual que antes**.
      Ver el bloque `PRECISION_MILESIMAS` en `ajustes.py` para el porqué de este carril.
    """
    # ★★★★★ EN COOPERATIVO EL MEDALLÓN NO SALE DE LA PRECISIÓN: sale de qué tan rápido
    #   atraparon al gorila. Ver `medallon_del_gorila` para el porqué y el dato de prod que lo
    #   destapó (cinco de seis sacaban B habiendo atrapado al gorila).
    if es_coop and CHASE_MEDALLON_POR_CAPTURA:
        grado = medallon_del_gorila(ronda_captura)
    else:
        grado = grado_de(pd, perdio)
    row  = bytes([slot & 0xFF, puesto & 0xFF])            # pos (slot), rank (PUESTO, no el medallón)
    if rank_bonus is None:
        rank_bonus = RANK_BONUS_POR_PUESTO.get(puesto, 100)
    # ⏳ SOSPECHOSO DEL "CARTEL DE DERROTA CORRIDO" (2026-09-05). Comparados byte a byte, el
    #   cartel de victoria y el de derrota **miden exactamente lo mismo** (41 B por fila, mismo
    #   layout): lo único que cambia son TRES valores — este `rank_bonus`, el `basecoin` de abajo
    #   y la letra del medallón. O sea que el corrimiento **no puede ser un desfase de bytes
    #   nuestro**: o el cliente arma otra pantalla al perder, o una de estas dos columnas en CERO
    #   se colapsa y arrastra la vista.
    #   ⇒ `FF28_DERROTA_CEROS = False` manda en derrota los mismos valores que en victoria. Si con
    #     eso el cartel deja de salir corrido, la causa está acá. Es una prueba de UNA línea.
    row += struct.pack("<H", 0 if (perdio and FF28_DERROTA_CEROS) else rank_bonus)
    row += struct.pack("<H", exp & 0xFFFF)
    row += struct.pack("<H", combo & 0xFFFF)
    row += bytes([pd & 0xFF, star & 0xFF])
    row += struct.pack("<H", coin & 0xFFFF)
    row += struct.pack("<I", 0 if (perdio and FF28_DERROTA_CEROS) else FF28_BASECOIN)  # ★ real 25..40
    row += struct.pack("<I", frame & 0xFFFFFFFF)
    # ★ El cartel de COOPERATIVO tiene tres columnas más —Usar Booster · Ayuda · Usar Item—
    #   que hoy salen vacías porque estos campos van en cero. Cuáles son exactamente se
    #   decide con una corrida de centinelas (ver FF28_CENTINELAS en ajustes.py).
    _c = FF28_CENTINELA_VALORES if FF28_CENTINELAS else {}
    _avisar_centinelas()
    # ★★★★★ EL BLOQUE DE 12 NO SON 12 BYTES SUELTOS: SON 7 CAMPOS (2026-09-05).
    #   El cliente 2013 lo lee de un saque (UNA lectura de 12 en `0x5E8C40`), así que desde acá
    #   parecía una bolsa opaca. **El cliente 2019 lo lee campo por campo** y ahí se ve la forma:
    #
    #       00d03d99  +0  leer 1        ┐ dos bytes sueltos
    #       00d03dad  +1  leer 1        ┘
    #       00d03dc1  +2  leer 2        ┐
    #       00d03dd5  +4  leer 2        │
    #       00d03de9  +6  leer 2        ├ cinco u16
    #       00d03dfd  +8  leer 2        │
    #       00d03e11  +10 leer 2        ┘
    #
    #   ⇒ **u8, u8, u16, u16, u16, u16, u16.** Y las columnas del cooperativo que faltan mapear
    #     son dos pares `x/y` y un número suelto — o sea que encajan justo con esta forma.
    #   ⚠ Por eso la sonda de bytes sueltos no servía: escribir 103 y 104 en los bytes 2 y 3 le
    #     llega al cliente como el u16 **26727**, que en pantalla no se parece a nada.
    #   ⚠ Es una inferencia razonable, no un hecho: doy por sentado que el bloque de 12 del 2019
    #     es el MISMO struct que el del 2013 (mismo tamaño, misma posición entre `frame` y el
    #     `inner_count`, mismo paquete). Muy probable, pero no comprobado.
    if any(f"b12_{i}" in _c for i in range(12)):
        # ★ MODO BYTE (centinelas): un número distinto POR BYTE. Se usa cuando el modo campo
        #   deja una celda ambigua — un u16 con valor 301 se ve como "45" si el cliente lo lee
        #   como byte, y ahí no se sabe cuál de los dos es.
        b12 = bytes(_c.get(f"b12_{i}", 0) & 0xFF for i in range(12))
    elif _c:
        b12 = (bytes([_c.get("c0", 0) & 0xFF, _c.get("c1", 0) & 0xFF])
               + b"".join(struct.pack("<H", _c.get(f"c{i}", 0) & 0xFFFF) for i in range(2, 7)))
    else:
        # ★★★★★ LA COLUMNA "USAR BOOSTER" — 2026-09-05, ya conectada.
        #   El cliente NO muestra los dos bytes tal cual: muestra **`(byte0 − byte1) / byte0`**
        #   (`0x577246`: `mov dl,[ebx+0x20]` / `sub dl,[ebx+0x21]`). O sea que el número de la
        #   izquierda **no lo controlamos directo**: mandamos los dos y el cliente resta.
        #   ⇒ Para que diga **usados / obtenidos**:  byte0 = obtenidos · byte1 = obtenidos − usados
        #   ⚠ Si `byte1 > byte0` la resta da la vuelta (255, 254…). Es exactamente lo que pasó en
        #     el ensayo de centinelas, donde mandamos 51 y 52 y el cartel mostró 255.
        #   ⏳ HOY "obtenidos" NO SE PUEDE CONTAR: agarrar un ítem no genera ningún aviso
        #     (medido: el usuario agarró 3 boosters y usó 1, y llegó UN solo evento). Así que por
        #     ahora obtenidos = usados y la columna sale "N/N". Cuando se identifique el aviso de
        #     "agarré uno" (candidato: `FF4E sub=0x05`), se cambia sólo esta línea.
        _cu = cuentas or {}
        _bo_us = _cu.get("boosters", 0) & 0xFF
        _bo_ob = max(_bo_us, _cu.get("boosters_obtenidos", _bo_us)) & 0xFF
        b12 = bytes([_bo_ob, (_bo_ob - _bo_us) & 0xFF]) + bytes(10)
    row += bytes(b12)                                     # bloque de 12B sin mapear
    # ★★★★★ LOS RENGLONES DE BONUS — el campo que llamábamos `inner_count` y mandábamos en 0.
    #   Es **la cantidad de renglones** que vienen atrás, `[bonustype:u16][valor:u16]` cada uno.
    #   Medido en NUESTRO handler (`0x5e8dfa` lee M · `0x5e8e19`/`0x5e8e27` el par · `0x5e8e35` lo
    #   mete en el vector de ese jugador). Con la lista vacía el stream sigue igual que siempre.
    #   ⚠ Un bonustype que no esté en `bonus.xml` el cliente lo IGNORA con un warning — no crashea.
    _bon = [(int(t) & 0xFFFF, int(v) & 0xFFFF) for t, v in (bonus or ())]
    # ★★★ LAS MILÉSIMAS DE LA PRECISIÓN VIAJAN ACÁ — 2026-09-13. Ver `PRECISION_MILESIMAS`.
    #   ⚠ Se acota a 0..999 ANTES de mandarlo: son milésimas, no un número libre. Un valor de
    #     1500 no significa "1,5 más": significa que alguien contó mal, y mandarlo tal cual
    #     esconde el error adentro del cartel en vez de dejarlo a la vista en el log.
    #   ⛔ Y SE ACOTA **ANTES** DE PREGUNTAR SI HAY ALGO QUE MANDAR. Al revés —preguntar primero
    #     y acotar después— un valor negativo pasaba el `if` (es "verdadero") y salía como un
    #     renglón de milésimas **en cero**: un renglón de más, por un número que era basura.
    #     Lo cazó la §4 del banco; en pantalla habría sido invisible.
    _mil = max(0, min(int(milesimas or 0), 999))
    if PRECISION_MILESIMAS and _mil:
        _bon = list(_bon) + [(FF28_BONUSTYPE_MILESIMAS & 0xFFFF, _mil)]
    row += struct.pack("<H", len(_bon) & 0xFFFF)
    for _t, _v in _bon:
        row += struct.pack("<HH", _t, _v)
    # ★★★★★ "USAR ITEM (x/y)" y "AYUDA (n)" — el cliente los imprime CRUDOS (2026-09-05).
    #   Posiciones confirmadas con dos fotos del cartel: `b_d`/`b_e` = el par de "Usar Item",
    #   `b_f` = "Ayuda". Y **no viajan en el reporte C→S**: los cuenta el server o nadie.
    #   ⏳ Igual que arriba, "obtenidos" todavía no se puede contar, así que el par sale "N/N".
    _cu = cuentas or {}
    _it_us = _cu.get("items", 0) & 0xFF
    _it_ob = max(_it_us, _cu.get("items_obtenidos", _it_us)) & 0xFF
    _ayuda = _cu.get("ayuda", 0) & 0xFF
    row += bytes([0, grado, 0,
                  _c.get("b_d", _it_us) & 0xFF,       # b_d = "Usar Item" izquierda
                  _c.get("b_e", _it_ob) & 0xFF,       # b_e = "Usar Item" derecha
                  _c.get("b_f", _ayuda) & 0xFF,       # b_f = "Ayuda (n)"
                  0])                                 # b_g
    return row

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★ EL MATCHER — lista de salas del lobby (FF6E ROOMLIST2)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Formato sacado del parser del cliente `0x5E0F70` leyendo los `0x67CFE0(dst,size)` en orden.
# ⚠ TRAMPA del lector: el `push size` va ANTES del `lea dst`, así que todo `lea [esp+N]` que se ve
#   en el disasm apunta en realidad a `esp0 + N - 4`.
#
#   CABECERA:  [tipo:u8][count:u16]      (con count=0 el loop no corre: es la "lista vacía")
#   POR SALA (el nombre de cada campo es HIPÓTESIS a medir en pantalla salvo donde se aclara):
#     u16 A   -> bits 0..10 = ★ROOM ID (`and 0x7FF`, va al +0x00 de la sala)   ·  bits 11..15 -> +0x1A
#     u8  B   -> flags crudos a +0x09; bit0 -> bool +0x08 ; bit1 -> bool +0x14
#     u16 C   -> +0x18
#     u16 D   -> +0x16
#     u8  E   -> +0x0C = E − F     ★ojo: el cliente RESTA F a E
#     u8  F   (sólo se usa para esa resta)
#     u8  G   -> +0x10 = G − 6     ★ojo: el cliente le resta 6
#     u8  LN  + nombre (LN bytes)  -> +0x04 (puntero al buffer)
#     u8  H   -> +0x1B
#     u8  I   -> +0x1D  (si trae bit2: se lo saca y prende +0x28 |= 4)
#     ── sólo si la lista es de tipo CircleBattle (`0x4A0C50()==6`): [LN2][str][u8][LN3][str],
#        con los que arma "%s vs %s". En las listas normales estos campos NO van. ──
#     u32 J   -> +0x20
#     u32 K   -> +0x24
#     u8  L   -> +0x29
#     u8  M   -> si !=0 prende +0x2B |= 4
#     u8  N   -> +0x2E
#     u8  O   -> si !=0 prende +0x2B |= 8
#
# ★ Los valores de abajo son CENTINELAS: números distintos y reconocibles para leer en pantalla qué
#   campo es cuál en UNA sola corrida (3/8, 1/6 y 6/8 de ocupación, etc.).
#
