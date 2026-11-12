# -*- coding: utf-8 -*-
"""grupo — la CARRERA EN GRUPO del 2013 (el 6vs6 recreado por nosotros, 10-oct-2026). Doc: documentacion/MODO_6VS6.md.

anonimo03 (10-oct): la sala de espera es una SALA DE CHARLA adaptada (cupo a gusto, sin espectadores) y de ahí el server
arma la carrera y LLEVA a todos los que estén ahí, como la cola del coreano. *«Un GM podría avisar por anuncio: vayan a
la sala de charla, y empezar la partida con los que estén ahí»*. Dos modos:
    «A» SOLO   — todos contra todos (el primero que se hace)
    «B» EQUIPO — se eligen los equipos parándose de un lado o del otro de la sala (anotado para después)

PASO A1 (esta versión): la PREGUNTA que decide el diseño — ¿el server puede LLEVAR a la carrera a alguien que está
en la sala de charla (o en el lobby), sin que él lo pida? El coreano lo hace con su FF164 (el cliente después pide
FF13 + FF0C como al entrar a una sala). El 2013 no tiene ese paquete; la apuesta es el `FF11` de entrar a una sala
(`[asiento][tipo 0x0D]`) mandado SIN pedido. `.grupo` (dev):
    1. arma una sala de carrera como el FF10 (sin su respuesta): el que lo pidió de anfitrión, carrera grande de 12
    2. si está en una estancia de charla, sube también a LOS DEMÁS de esa estancia (hasta 12); el resto, NPC
    3. a cada uno le manda el FF11 de «entraste» sin que lo haya pedido
    4. a los LARGADA_SEG el server aprieta el START él solo (`h_30_ff24`, el mismo del botón)
"""
import threading

from .registro import log

GRUPO_N = 12                 # corredores de la carrera en grupo (la carrera grande, `salas.GRANDE_TOPE`)
LARGADA_SEG = 15             # cuánto falta para largar desde que entra
NOMBRE = "Carrera en grupo"


def _orden_asientos():
    from .ajustes import ORDEN_ASIENTOS, ORDEN_ASIENTOS_12
    return list(ORDEN_ASIENTOS_12) if GRUPO_N == 12 else list(ORDEN_ASIENTOS) + list(range(6, GRUPO_N))


def _subir(c, rid, asiento):
    """Lo saca de donde esté (charla, otra sala) y lo sienta en la sala del grupo. Devuelve el asiento o None."""
    from .ajustes import MODE_VELOCIDAD
    from .lobby_salas import sacar_de_la_sala_anterior
    from .salas import sentar_jugador
    from . import charla
    sacar_de_la_sala_anterior(c, "ir a la carrera en grupo", menos=rid)
    charla.salir(c, "se fue a la carrera en grupo")        # el asiento y el FF0E en la charla
    c.lugar_tipo = None
    c.room_id = rid
    c.sala_poblada = None
    c.room_name = NOMBRE
    c.room_mode = MODE_VELOCIDAD
    c.room_colab = c.room_boss = False
    c.room_tipo = 0x0D
    c.ghost = False
    return sentar_jugador(c, rid, asiento)


def gente_de_la_charla(st):
    """Las conexiones de la estancia de charla de `st` (él primero), o sólo él si no está en una."""
    from . import charla
    otros = [c for c in charla.destinos(st, con_yo=True) if c is not st]
    return [st] + otros


def llevar(st, alto=False):
    """`.grupo`: arma la sala, sube a los de la charla, les manda el FF11 sin pedido y programa la largada.

    `alto` (`.grupo alto`, de PRUEBA): los demás humanos van a los asientos 6..11 — para medir qué hace un humano en
    un asiento que su propio cliente trata de espectador (`GetMyPlayer` mira `cGame+0xC01`)."""
    from .salas import mesa_de, nuevo_roomid, poner_anfitrion, poner_grande, poner_npcs, registrar_sala
    van = gente_de_la_charla(st)[:GRUPO_N]
    rid = nuevo_roomid()
    poner_grande(rid, GRUPO_N)
    orden = _orden_asientos()
    subidos = []
    for i, c in enumerate(van):
        o = orden if not (alto and i > 0) else list(range(6, GRUPO_N)) + orden
        libre = next((s for s in o if s not in mesa_de(rid)), None)
        if libre is None:
            break
        a = _subir(c, rid, libre)
        if a is not None:
            subidos.append((c, a))
    if not subidos:
        return ["no pude armar la sala del grupo"]
    poner_anfitrion(rid, st.usn)
    tomados = set(mesa_de(rid))
    libres = [s for s in orden if s not in tomados]
    poner_npcs(rid, libres)
    st.ghost, st.ghost_slots = True, libres
    registrar_sala(st)
    for c, a in subidos:
        c.send_ff55(0x11, bytes([a & 0xFF, 0x0D]),
                    name=f"FF11 ENTERROOM SIN PEDIDO -> sala del grupo {rid}, asiento {a} (tipo 13)")
    log("GRUPO", f"  ★ sala del grupo {rid}: {[(getattr(c, 'usn', 0), a) for c, a in subidos]} (usn, asiento) · "
                 f"NPC en {libres} · carrera grande de {GRUPO_N} · largada en {LARGADA_SEG} s")

    def largar():
        if getattr(st, "room_id", None) != rid or getattr(st, "cerrado", False):
            log("GRUPO", f"  la sala {rid} ya no es la del anfitrión: no se larga")
            return
        try:
            from .lobby_carrera import h_30_ff24
            log("GRUPO", f"  ★ LARGADA de la sala del grupo {rid} (el server aprieta START)")
            h_30_ff24(st, 0x24, b"")
        except Exception as e:                      # noqa: BLE001
            log("GRUPO", f"  ⚠ la largada falló: {e!r}")
    threading.Timer(LARGADA_SEG, largar).start()
    return [f"carrera en grupo: sala {rid}, {len(subidos)} jugador(es) + {len(libres)} NPC · largada en {LARGADA_SEG} s"]
