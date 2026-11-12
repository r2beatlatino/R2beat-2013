#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""combo_exe — el blob FF57 y el combo, tal como los lee el cliente 2013.

Todo lo de acá está medido sobre `R2Beat.exe.pristino`; el detalle con las direcciones
está en `documentacion/RECETA_NOTAS_2013.md`. Este módulo es la contraparte en Python de
ese disasm: si algún día el documento y este archivo no coinciden, el documento manda.
"""
import struct
import zlib

TOPE_BLOB = 0xFFFF          # el `len` del paquete FF57 es u16 (handler 0x5D01F0)


def combo_del_exe(notas):
    """El `Combo` que el cliente calcula para un chart. NO es la cantidad de notas.

    Las tres ramas del bucle de notas de `0x56E3D0`, cada una con su guarda de autoplay:
        autoplay (Fx & 0x8000)                          -> 0   (0x56E52C / 0x56E758 / 0x56E77A)
        Kind == 0x18                                    -> +2  (0x56E768  add ecx, 2)
        Kind >= 0x80 y (Kind-0x80) % 3 != 1             -> +1  (0x56E53C / 0x56E54B)
        resto                                           -> +1  (0x56E78A  inc edx)

    ⚠ En el cliente 2013 NO existe el popup `올콤카운트에러` (el string sólo está en los
      exes del CBT), así que un Combo que no cierre no muestra ningún cartel. Sigue siendo
      la mejor prueba de que el chart es de esa canción: son dos archivos independientes
      dando el mismo número.
    """
    total = 0
    for _coord, kind, _level, fx in notas:
        if fx & 0x8000:
            continue
        if kind >= 0x80:
            if (kind - 0x80) % 3 != 1:
                total += 1
        elif kind == 0x18:
            total += 2
        else:
            total += 1
    return total


def leer_blob(datos):
    """`(bpms, notas)` de un blob FF57. Levanta ValueError si no lo puede leer entero.

    Se lee igual que el cliente: `count` crudo del offset 0, el Bloque A SIN descomprimir,
    y recién desde `4 + count*8` el zlib (`lea eax,[ebp*8+4]` en 0x574465).
    """
    if len(datos) < 4:
        raise ValueError("blob más corto que el count")
    count = struct.unpack_from("<i", datos, 0)[0]
    if count < 0 or 4 + count * 8 > len(datos):
        raise ValueError(f"count={count} no entra en {len(datos)} bytes")
    bpms = [struct.unpack_from("<if", datos, 4 + 8 * i) for i in range(count)]
    crudo = zlib.decompress(datos[4 + count * 8:])
    if len(crudo) % 6:
        # el bucle del cliente corta por `consumido < tamaño`, no por múltiplo de 6: un
        # tamaño impar le hace leer hasta 5 bytes fuera del buffer
        raise ValueError(f"el inflado ({len(crudo)} B) no es múltiplo de 6")
    notas = [struct.unpack_from("<HBBH", crudo, i) for i in range(0, len(crudo), 6)]
    return bpms, notas


def armar_blob(bpms, notas):
    """El blob FF57 a partir de `bpms` y `notas`. Inverso exacto de `leer_blob`."""
    if not bpms:
        bpms = [(0.0, 120.0)]                      # sin timeline el cliente no arranca
    a = bytearray(struct.pack("<i", len(bpms)))
    for frame, bpm in bpms:
        a += struct.pack("<if", int(round(frame)), bpm)
    crudo = bytearray()
    for coord, kind, level, fx in notas:
        crudo += struct.pack("<HBBH", coord & 0xFFFF, kind & 0xFF, level & 0xFF, fx & 0xFFFF)
    return bytes(a) + zlib.compress(bytes(crudo), 9)


def leer_bin(path):
    with open(path, "rb") as f:
        return leer_blob(f.read())
