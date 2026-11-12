# -*- coding: utf-8 -*-
"""autoplay_gm — `.autoplay`: el autoplay ESCONDIDO del cliente, prendido desde el server.

Ver el bloque `AUTOPLAY_GM` de `ajustes.py` para el porqué y lo medido. En corto:

    el server le manda al jugador   FF4E sub=0x01  A=(slot<<24)|(slot<<16)|(0x0A<<8)  B=0x64
    = "el asiento `slot` usó el ítem 0x0A sobre el asiento `slot`" — el mismo aviso que el cliente
    manda cuando se prende un ítem de carrera. Su handler no filtra el asiento propio ⇒ se lo aplica.

El ritmo es FIJO: uno cada `AUTOPLAY_CADA` (5,5 s), medio segundo antes de que se apague el
anterior (dura 6). ⛔ La 1ª versión esperaba que el cliente "confirmara" cada uno por red y
reintentaba cada segundo si no: el cliente NO confirma los que le manda el server, así que se
prendía uno por segundo — un spam de sonido (anonimo03, 24-sep). Ver `AUTOPLAY_CADA` en `ajustes.py`.

Un hilo por conexión, vivo mientras el comando esté prendido. Fuera de carrera no manda nada.
⚠ Y adentro de la carrera espera a que el jugador mande su PRIMER `FF4E`: hasta ahí el cliente
  está cargando la pista, y a un cliente que carga no se le manda nada (lo ensucia).
"""
import threading
import time

from .ajustes import (
    AUTOPLAY_B,
    AUTOPLAY_CADA,
    AUTOPLAY_GM,
    AUTOPLAY_TIPO,
)
from .registro import log

SUB_EFECTO = 0x01          # el `sub` del FF4E con el que viaja "usé un ítem de carrera"


def armar_a(slot, tipo=AUTOPLAY_TIPO):
    """El `A` del aviso: `(destino << 24) | (emisor << 16) | (tipo << 8) | 0` (`0x503A32`)."""
    s = int(slot) & 0xFF
    return (s << 24) | (s << 16) | ((int(tipo) & 0xFF) << 8)


def cuando_pedir(ahora, ultimo_pedido):
    """Cuántos segundos faltan para el próximo pedido (0 = ya). Pura, para poder probarla."""
    if not ultimo_pedido:
        return 0.0
    return max(0.0, ultimo_pedido + AUTOPLAY_CADA - ahora)


def puede_correr(st):
    """El jugador está corriendo de verdad: en carrera, ya mandó su primer `FF4E` (terminó de
    cargar), no mira, y la conexión vive."""
    return (bool(getattr(st, "en_carrera", False))
            and bool(getattr(st, "autoplay_ya_corre", False))
            and getattr(st, "room_slot", None) is not None
            and getattr(st, "slot_espectador", None) is None
            and not getattr(st, "cerrado", False))


def vio_ff4e(st):
    """Lo llama el relevo del `FF4E` con cada paquete de carrera que MANDA el jugador.

    El primero de la carrera dice que ya terminó de cargar la pista: recién ahí se le puede mandar.
    ⚠ No sirve para saber si el autoplay se prendió: el cliente no avisa los que le manda el server.
    """
    if getattr(st, "autoplay_gm", False) and getattr(st, "en_carrera", False):
        st.autoplay_ya_corre = True


def _hilo(st):
    ultimo = 0.0
    pedidos = 0
    en_carrera_antes = False
    log("LOBBY", f"  🤖 .autoplay: hilo prendido para usn={getattr(st, 'usn', '?')}")
    try:
        while getattr(st, "autoplay_gm", False) and not getattr(st, "cerrado", False):
            if not puede_correr(st):
                if en_carrera_antes:
                    log("LOBBY", f"  🤖 .autoplay: terminó la carrera de usn={getattr(st, 'usn', '?')} "
                                 f"— {pedidos} autoplays pedidos")
                en_carrera_antes = False
                ultimo = 0.0
                if not getattr(st, "en_carrera", False):
                    st.autoplay_ya_corre = False
                time.sleep(0.25)
                continue
            if not en_carrera_antes:
                en_carrera_antes = True
                pedidos = 0
            falta = cuando_pedir(time.time(), ultimo)
            if falta > 0:
                time.sleep(min(falta, 0.25))
                continue
            slot = st.room_slot
            st.send_ff4e(SUB_EFECTO, armar_a(slot), AUTOPLAY_B,
                         name=f".autoplay: asiento {slot} usa el 0x{AUTOPLAY_TIPO:02X} sobre sí mismo")
            ultimo = time.time()
            pedidos += 1
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⚠ .autoplay: el hilo se cayó: {e!r}")
    finally:
        st.autoplay_hilo = None
        log("LOBBY", f"  🤖 .autoplay: hilo apagado para usn={getattr(st, 'usn', '?')}")


def activar(st, prender):
    """Prende o apaga el `.autoplay` de ESA conexión. Devuelve las líneas para el chat."""
    if not AUTOPLAY_GM:
        return ["el .autoplay está apagado en ajustes (AUTOPLAY_GM)"]
    st.autoplay_gm = bool(prender)
    if not prender:
        return ["autoplay APAGADO (el que esté andando termina solo en ≤6 s)"]
    h = getattr(st, "autoplay_hilo", None)
    if h is None or not h.is_alive():
        st.autoplay_hilo = threading.Thread(target=_hilo, args=(st,), daemon=True,
                                            name=f"autoplay-{getattr(st, 'usn', '?')}")
        st.autoplay_hilo.start()
    return ["autoplay PRENDIDO: en la próxima carrera tu personaje juega solo",
            "(.autoplay off para apagarlo)"]
