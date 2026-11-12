# -*- coding: utf-8 -*-
"""pak — leer los .pak del R2Beat 2013 sin herramientas de afuera.

El formato, medido idéntico a lo que saca `r2pak.exe`:

    [datos de los archivos, uno detrás de otro]
    [la TABLA: un registro por archivo]
    [offset de la tabla: u32]  [5 bytes de cola]

    registro = [largo del nombre:u8][tipo:u8][offset:u32][guardado:u32][original:u32][nombre][\\0]
               tipo 1 = archivo · guardado != original => va comprimido con un LZSS propio

⛔ Sólo LEE. Nunca escribe en la carpeta del juego.
"""
import glob
import os
import struct


def _plausible(d, p, fin):
    out = []
    while p < fin:
        if p + 15 > fin:
            return None
        nl, ty = d[p], d[p + 1]
        if nl == 0 or ty > 2 or p + 14 + nl >= len(d):
            return None
        nombre = d[p + 14:p + 14 + nl]
        if d[p + 14 + nl] != 0 or any(b < 0x20 or b > 0x7E for b in nombre):
            return None
        off, guardado, original = struct.unpack_from("<III", d, p + 2)
        out.append((nombre.decode("latin-1").replace("\\", "/"), ty, off, guardado, original))
        p += nl + 15
    return out if p == fin else None


def tabla(pak):
    """[(nombre, tipo, offset, guardado, original)] leyendo SÓLO la cola del archivo."""
    with open(pak, "rb") as f:
        f.seek(0, 2)
        largo = f.tell()
        f.seek(largo - 9)
        idx_off = struct.unpack("<I", f.read(4))[0]
        if not 0 < idx_off < largo - 9:
            raise ValueError("no parece un .pak del R2Beat")
        f.seek(idx_off)
        cola = f.read(largo - idx_off)
    fin = len(cola) - 9
    for pre in range(64):
        reg = _plausible(cola, pre, fin)
        if reg:
            return reg
    raise ValueError("la tabla del .pak no encuadra")


def descomprimir(c, n):
    out = bytearray()
    i, largo = 0, len(c)
    while len(out) < n and i < largo:
        banderas = c[i]
        i += 1
        for b in range(8):
            if len(out) >= n or i >= largo:
                break
            if not (banderas >> b) & 1:
                out.append(c[i])
                i += 1
            else:
                v = c[i] | (c[i + 1] << 8)
                i += 2
                desde = len(out) - (v & 0xFFF)
                for k in range((v >> 12) + 2):
                    out.append(out[desde + k])
    if len(out) != n:
        raise ValueError("descomprimido %d bytes, se esperaban %d" % (len(out), n))
    return bytes(out)


class Paks:
    """El índice de TODOS los rnr_*.pak de una carpeta: ruta en minúsculas -> dónde está.
    ★ Gana el ÚLTIMO pak por nombre, igual que en el juego."""

    def __init__(self, carpeta):
        self.carpeta = carpeta
        self.ix = {}
        self.rotos = []
        for pak in sorted(glob.glob(os.path.join(carpeta, "rnr_*.pak"))):
            try:
                for nombre, ty, off, guardado, original in tabla(pak):
                    if ty == 1:
                        self.ix[nombre.lower()] = (pak, off, guardado, original)
            except (OSError, ValueError, struct.error):
                self.rotos.append(os.path.basename(pak))

    def tiene(self, ruta):
        return ruta.lower() in self.ix

    def sacar(self, ruta):
        pak, off, guardado, original = self.ix[ruta.lower()]
        with open(pak, "rb") as f:
            f.seek(off)
            crudo = f.read(guardado)
        return crudo if guardado == original else descomprimir(crudo, original)

    def de_donde(self, ruta):
        return os.path.basename(self.ix[ruta.lower()][0])
