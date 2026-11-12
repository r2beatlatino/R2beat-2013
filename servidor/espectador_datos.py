# -*- coding: utf-8 -*-
"""espectador_datos — la TRANSMISIÓN al espectador (`FF98`, `SendObserverData`), 12-oct.

anonimo03: *«sospecho que es algo de los datos que el corredor envía al server y el server no manda al espectador: creo
recordar que se veían los combos y el gameplay completo»*. Era eso: el `FF98` caía en «SIN handler» (247.510 veces en
12 días de prod, el comando que más llega) y el que mira nunca recibía lo que los corredores le mandaban.
Doc: `documentacion/MODO_ESPECTADOR.md` §9 · prueba: `pruebas/probar_espectador_datos.py` · `ESPECTADOR_DATOS`.

  QUIÉN LO MANDA: el corredor, sólo si hay espectadores (`[cGame+0xC1C]`, lo prende el `FFBB` > 0) y él no lo es
      (`+0xC01` = 0). Cada evento lo anota `0x503920` en la grabadora del jugador (`cPlayer+0x2DC`) y `0x5641F0`
      la vacía con el `FF98`. Ej. `0x564130`: `(t = [cPlayer+0x18], tipo 0x62, a = (código<<8 | asiento) << 16,
      b = [cPlayer+0x68] + 1)` — el asiento del corredor viaja en `a`.
  C→S `[u8 0][u8 n]` + n × 13 B (emisor `0x5E3630`, `0x5E3757`), cada registro OFUSCADO con el magic de la carrera
      (`[cGame+0x85C] ^ [0x904210]` = el `magic` del `FF25`; las mismas constantes que el `FF4E`):
          [u32 t ^ M ^ 0xBA] [u8 tipo ^ M ^ 0xCA] [u32 a ^ M ^ 0xEF] [u32 b ^ M ^ 0xAB]
  S→C `[u8 n]` + n × `[f32 t][u8 tipo][u32 a][u32 b]` EN CLARO (RX `0x5D5190` → `0x563CD0` → la cola del que mira,
      `cGame+0xC04`).
  Medido con prod (03:01:56, magic 0xB1BA766E): `00 01 d4 76 ba b1 a4 81 76 ba b6 c4 76 ba b1` → t 0.0 · tipo 0 ·
      a 0x07000000 · b 1 — limpio, y los `b` siguen la secuencia (8, 29, 50).
"""
import struct

from .registro import RESUMIR, log

LARGO_REGISTRO = 13
ASIENTOS_FILAS = 6        # ⛔ el que mira tiene 6 filas (0x563BC0 / 0x563EF9): un asiento ≥ 6 lo cierra (0x74FF1F)


def asiento_del_registro(tipo, a, b):
    """El asiento que el cliente que mira saca de cada registro (`0x562FD0`, tabla 0x563014): tipos 0, 1 y 0x62 →
    `a>>16`; 5 → `b>>8`; el resto (y > 0x62) → `a>>8` (el byte bajo de cada uno)."""
    if tipo in (0, 1, 0x62):
        return (a >> 16) & 0xFF
    if tipo == 5:
        return (b >> 8) & 0xFF
    return (a >> 8) & 0xFF
_vistos = {"n": 0, "registros": 0, "sin_espectador": 0, "rotos": 0}


def descifrar(data, magic):
    """C→S -> [(t_bits, tipo, a, b)] o None si no cierra."""
    if len(data) < 2 or data[0] != 0:
        return None
    n = data[1]
    if len(data) != 2 + LARGO_REGISTRO * n:
        return None
    m = int(magic) & 0xFFFFFFFF
    out = []
    for i in range(n):
        o = 2 + LARGO_REGISTRO * i
        w1, = struct.unpack_from("<I", data, o)
        w2, w3 = struct.unpack_from("<II", data, o + 5)
        out.append((w1 ^ m ^ 0xBA, data[o + 4] ^ (m & 0xFF) ^ 0xCA, w2 ^ m ^ 0xEF, w3 ^ m ^ 0xAB))
    return out


def armar(registros):
    """S→C `FF98` para el que mira: [n] + n × [f32 t][u8 tipo][u32 a][u32 b] en claro."""
    regs = list(registros)[:0xFF]
    return bytes([len(regs)]) + b"".join(struct.pack("<IBII", t & 0xFFFFFFFF, tipo & 0xFF, a & 0xFFFFFFFF,
                                                      b & 0xFFFFFFFF) for t, tipo, a, b in regs)


def atender(st, data):
    from .ajustes import ESPECTADOR_DATOS
    from .salas import espectadores_de
    _vistos["n"] += 1
    if not ESPECTADOR_DATOS:
        return
    rid = getattr(st, "room_id", None)
    if getattr(st, "slot_espectador", None) is not None:
        return                                       # el que mira no transmite (y si lo hiciera, no se reenvía)
    mirones = [c for c in espectadores_de(rid) if c is not st]
    if not mirones:
        _vistos["sin_espectador"] += 1
        return
    regs = descifrar(bytes(data), getattr(st, "game_magic", 0))
    if regs is None:
        _vistos["rotos"] += 1
        if _vistos["rotos"] <= 5:
            log("LOBBY", f"  ⚠ FF98 que no cierra de usn={getattr(st, 'usn', '?')} ({len(data)} B): {bytes(data[:20]).hex(' ')}")
        return
    # ★ esta carrera, este corredor manda su transmisión: el FF4E en vivo deja de ir a los que miran (ver lobby.py)
    if getattr(st, "ff98_magic", None) != getattr(st, "game_magic", None):   # ★ 16-oct: una línea por corredor y carrera
        log("LOBBY", f"  📺 FF98: usn={getattr(st, 'usn', None)} transmite en la sala {rid} "
                     f"(a {len(mirones)} que miran)")
    st.ff98_magic = getattr(st, "game_magic", None)
    # ★ 14-oct · la sala de 12: la dll (espectador12.c) crea 12 filas (0x563EF9: 6 → 12) — ahí no se tira ninguno
    from .salas import asientos_de_la_sala
    _filas = 12 if asientos_de_la_sala(rid) == 12 else ASIENTOS_FILAS
    buenos = [r for r in regs if asiento_del_registro(r[1], r[2], r[3]) < _filas]
    if len(buenos) != len(regs):
        _vistos["fuera_de_rango"] = _vistos.get("fuera_de_rango", 0) + len(regs) - len(buenos)
        regs = buenos
    if not regs:
        return
    _vistos["registros"] += len(regs)
    cuerpo = armar(regs)
    for c in mirones:
        try:
            c.send_ff55(0x98, cuerpo, name=RESUMIR)
        except Exception as e:                                            # noqa: BLE001
            log("LOBBY", f"  ⚠ FF98 no pude pasárselo a usn={getattr(c, 'usn', '?')}: {e!r}")
    if _vistos["n"] % 2000 == 1:
        log("LOBBY", f"  📺 FF98 transmisión al espectador: {_vistos['n']} paquetes, {_vistos['registros']} registros "
                     f"reenviados · {_vistos['sin_espectador']} sin nadie mirando · {_vistos['rotos']} rotos")
