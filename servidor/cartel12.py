# -*- coding: utf-8 -*-
"""cartel12 — LA COLA DEL CARTEL DE LA CARRERA DE 12 (11-oct-2026). Doc: documentacion/MODO_6VS6.md §17.

El cartel de fábrica (`FF28`, handler `0x5E8C40`) es de 6: con 12 filas se le encimaban (anonimo03, 11-oct). El nuestro lo
dibuja la dll (`herramientas/dll_d3d9/fuente/cartel12.c`) ENCIMA del de fábrica, y sus datos viajan PEGADOS al final del
`FF28`, detrás del byte del grado, que es lo último que lee el juego (`0x5E8F29`). La dll los lee ahí mismo, con el
lector del juego (`0x67D200`), igual que la cola «T5» del TOP 5 detrás del FF139.

⛔ EL ORDEN ES UN CONTRATO con `cartel12.c` (`k12_cola`):
    b"C2" · u16 largo · [largo B]:
      u8 versión (1) · u8 modo (1 = equipo, 0 = personal) · u8 equipo ganador (1 rojo / 2 azul / 0)
      · u8 victorias del 1 · u8 victorias del 2 (el SCORE de la serie = `MARCADOR`, el «1 VS 0» de fábrica)
      · u16 canción · u8 nivel (dificultad, 0..10) · u16 pista · u8 L · título de la canción (L B, cp1252)
      · u8 n · n × FILA
    FILA = u8 asiento · u8 puesto (1..12; 0 = no llegó) · u8 equipo (1/2; 0 en personal) · u8 L · apodo (L B, cp1252)
           · u32 llegada (cuadros; 0xFFFFFFFF = no llegó) · u32 exp · u16 puntos de ranking · u32 precisión ×1000
           · u8 estrella · u16 combo · u32 rcoin (lo que ganó: coin + la base fija)
Sólo va en la sala de 12 (`asientos_de_la_sala == 12`): un cliente sin la dll nueva no la lee y no pasa nada (el juego
deja de leer en el grado).
★ 14-oct · EL RELEVO DE 12 (4 equipos, RELEVO_12.md F5): detrás de las filas, OPCIONAL, `b"E4" · u8 m1 · m2 · m3 · m4`
  (las victorias de los 4 equipos). El equipo de la fila y el ganador ya van 1..4. Una dll vieja no lo lee (no lo pide).
"""
import struct

MAGIA = b"C2"
VERSION = 1


def _txt(s, tope=40):
    b = str(s or "").encode("cp1252", "replace")[:tope]
    return bytes([len(b)]) + b


def fila(slot, puesto, equipo, apodo, frame, exp, rank, pd_mil, star, combo, rcoin):
    return (bytes([slot & 0xFF, puesto & 0xFF, equipo & 0xFF]) + _txt(apodo, 24)
            + struct.pack("<IIHIBHI", frame & 0xFFFFFFFF, max(0, int(exp)) & 0xFFFFFFFF, max(0, int(rank)) & 0xFFFF,
                          max(0, int(pd_mil)) & 0xFFFFFFFF, max(0, int(star)) & 0xFF, max(0, int(combo)) & 0xFFFF,
                          max(0, int(rcoin)) & 0xFFFFFFFF))


def cola(modo_equipo, gana, m1, m2, cancion, nivel, pista, titulo, filas, cuatro=None):
    """`filas` = lista de bytes armados con `fila()`, ya en el orden del cartel. `cuatro` = las victorias de los 4
    equipos (relevo de 12) o None."""
    cuerpo = (bytes([VERSION, 1 if modo_equipo else 0, gana & 0xFF, m1 & 0xFF, m2 & 0xFF])
              + struct.pack("<H", cancion & 0xFFFF) + bytes([max(0, min(255, int(nivel or 0)))])
              + struct.pack("<H", pista & 0xFFFF) + _txt(titulo, 60)
              + bytes([len(filas) & 0xFF]) + b"".join(filas))
    if cuatro:
        cuerpo += b"E4" + bytes(max(0, min(255, int(v))) for v in list(cuatro)[:4])
    return MAGIA + struct.pack("<H", len(cuerpo)) + cuerpo


def leer(b):
    """El lector del contrato, en Python (para el banco: lo que arma `cola()` se tiene que poder desarmar igual que
    lo hace `cartel12.c`). Devuelve un dict, o None si no hay cola."""
    if len(b) < 4 or b[:2] != MAGIA:
        return None
    largo = struct.unpack_from("<H", b, 2)[0]
    c = b[4:4 + largo]
    if len(c) != largo:
        return None
    d = {"version": c[0], "equipo": c[1], "gana": c[2], "m1": c[3], "m2": c[4],
         "cancion": struct.unpack_from("<H", c, 5)[0], "nivel": c[7], "pista": struct.unpack_from("<H", c, 8)[0]}
    p = 10
    L = c[p]
    d["titulo"] = c[p + 1:p + 1 + L].decode("cp1252")
    p += 1 + L
    n = c[p]
    p += 1
    d["filas"] = []
    for _ in range(n):
        slot, puesto, eq, L = c[p], c[p + 1], c[p + 2], c[p + 3]
        apodo = c[p + 4:p + 4 + L].decode("cp1252")
        p += 4 + L
        fr, exp, rank, pd, star, combo, rc = struct.unpack_from("<IIHIBHI", c, p)
        p += struct.calcsize("<IIHIBHI")
        d["filas"].append({"slot": slot, "puesto": puesto, "equipo": eq, "apodo": apodo, "frame": fr, "exp": exp,
                           "rank": rank, "pd": pd, "star": star, "combo": combo, "rcoin": rc})
    if p + 6 == largo and c[p:p + 2] == b"E4":                  # ★ 14-oct: el marcador de los 4 equipos
        d["cuatro"] = list(c[p + 2:p + 6])
        p += 6
    if p != largo:
        return None
    return d
