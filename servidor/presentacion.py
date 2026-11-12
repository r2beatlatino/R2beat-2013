# -*- coding: utf-8 -*-
"""presentacion — la PRESENTACIÓN PERSONAL y el cartel que salía en cada entrada (29-sep).

EL SÍNTOMA
----------
anonimo03: *"cada vez que abro el juego me sale este popup"* — «Hemos añadido Buscar amigos en el
sistema. Escriba una presentación suya… ¿Desea escribirla ahora?». Y la pestaña «Presentación
personal» del perfil no guardaba nada.

LO QUE HAY, LEÍDO DEL EXE 2013 (detalle en `documentacion/PRESENTACION_PERSONAL.md`)
-----------------------------------------------------------------------------------
Todo gira alrededor de UNA LETRA, la de «Buscar amigos» (`cAccount+0x397`, la escribe `0x485680`):

    ''  0   nunca contestó       -> el cartel sale en CADA vuelta al vestíbulo (nivel ≥ 6, `0x4C07FE`)
    'Y' 1   anotado, SALE en la lista de «Buscar amigos»
    'N' 2   anotado, NO sale
    'X' 3   contestó el cartel (con OK o con Cancelar: los dos mandan lo mismo, `0x4C0710`/`0x4BDFA0`)
    'Z' 4   todavía no tenía nivel 6 (`0x4C08A7`); al llegar a 6 le sale otro cartel (texto 0x1F6)

y con 'Y'/'N' además queda «ya tiene presentación» (`cAccount+0x395 = 1`), que decide si guardar
manda el tipo 3 (registrar) o el 6 (editar) — `0x425CC2`.

    C→S `FF94`  [u8 tipo][u8 letra][u8 edad][u8 largo][texto]          emisor `0x5D4930`
    S→C `FF94`  [u8 tipo][u8 resultado][u8 letra][u8 edad][u8 largo][texto]   `0x5E0FA0`
                tipo 3 registrar · 4 sólo la letra · 6 editar (pedía un vale, resultado 8)
                resultado 0 = bien · 1 = «error de la base» · 2 = «ya tenés una registrada»
    `FF03`      la letra + edad + largo + texto, en la cola (ver `bloque_ff03`)

⇒ Nosotros mandábamos la letra en 0 y NO contestábamos el `FF94`: el cliente nunca se enteraba de que
  había contestado, y preguntaba de nuevo.
"""
from .ajustes import PRESENTACION_CAMBIO_GRATIS
from .basedatos import db_get_char, db_poner_presentacion, db_presentacion_de
from .registro import log, hx

LETRAS = "YNXZ"
TIPO_REGISTRAR, TIPO_LETRA, TIPO_EDITAR = 3, 4, 6
TEXTO_MAX = 0x9F          # el cliente sólo lee el texto si el largo es < 0xA0 (`0x5E100B`)
EDAD_MAX = 100            # el FF03 descarta una edad > 100 (`0x5ED8F7`)


def _texto_wire(texto):
    return str(texto or "").encode("cp1252", "replace")[:TEXTO_MAX]


def estado(uid):
    """`(letra, edad, texto)` del jugador.

    Sin fila en `presentacion` se mira lo viejo: el handler de antes ya guardaba la edad y el texto
    del tipo 3 en `chars.age`/`chars.bio` (sin la letra). Quien tiene algo ahí YA se registró ⇒ 'N'
    (anotado, sin salir en la lista: lo prudente, porque no sabemos qué eligió).
    """
    r = db_presentacion_de(uid)
    if r is not None:
        return r
    ch = db_get_char(uid) or {}
    edad, texto = int(ch.get("age") or 0), str(ch.get("bio") or "")
    return ("N", edad, texto) if (edad or texto) else ("", 0, "")


def armar(letra, edad, texto):
    """`[u8 letra][u8 edad][u8 largo][texto]` — lo que comparten el FF03 y la respuesta del FF94."""
    t = _texto_wire(texto)
    e = int(edad or 0)
    return bytes([ord(letra) if letra else 0, e if 0 <= e <= EDAD_MAX else 0, len(t)]) + t


def bloque_ff03(uid):
    return armar(*estado(uid))


def respuesta(tipo, resultado, letra, edad, texto):
    return bytes([tipo & 0xFF, resultado & 0xFF]) + armar(letra, edad, texto)


def atender_ff94(st, data):
    """El `FF94` entero: guarda y contesta. Devuelve la respuesta (o None si no hay que contestar)."""
    uid = int(getattr(st, "usn", 0) or 0)
    if len(data) < 4:
        log("LOBBY", f"  FF94 corto ({len(data)} B), se ignora: {hx(data)}")
        return None
    tipo, letra, edad, largo = data[0], chr(data[1]), data[2], data[3]
    texto = data[4:4 + largo].decode("cp1252", "replace")
    letra = letra if letra in LETRAS else ""
    v_letra, v_edad, v_texto = estado(uid)
    if tipo in (TIPO_REGISTRAR, TIPO_EDITAR):
        if tipo == TIPO_EDITAR and not PRESENTACION_CAMBIO_GRATIS:
            log("LOBBY", f"  FF94 editar sin vale usn={uid} -> resultado 8")
            return respuesta(tipo, 8, v_letra, v_edad, v_texto)
        n_letra = letra if letra in "YN" else (v_letra if v_letra in "YN" else "N")
        n_edad = min(int(edad), EDAD_MAX)
        db_poner_presentacion(uid, n_letra, n_edad, texto)
        log("LOBBY", f"  ★ FF94 PRESENTACIÓN ({'registrar' if tipo == 3 else 'editar'}) usn={uid}: "
                     f"letra={n_letra} edad={n_edad} texto={texto!r}")
        return respuesta(tipo, 0, n_letra, n_edad, texto)
    if tipo == TIPO_LETRA:
        if not letra:
            log("LOBBY", f"  FF94 tipo 4 con letra desconocida usn={uid}: {hx(data)}")
            return None
        db_poner_presentacion(uid, letra, v_edad, v_texto)
        log("LOBBY", f"  ★ FF94 letra de «Buscar amigos» usn={uid}: {v_letra or '-'} -> {letra}"
                     + ("  (contestó el cartel)" if letra == "X" else "")
                     + ("  (todavía sin nivel 6)" if letra == "Z" else ""))
        return respuesta(tipo, 0, letra, v_edad, v_texto)
    log("LOBBY", f"  FF94 tipo {tipo} desconocido usn={uid}, se ignora: {hx(data)}")
    return None
