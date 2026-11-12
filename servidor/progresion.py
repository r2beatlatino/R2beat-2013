# -*- coding: utf-8 -*-
"""progresion — exp, nivel, licencia, banda de canal y misiones

Cortado de `server_login2013.py`. El código es el MISMO, movido tal cual.
"""
import os
import struct

from .ajustes import (
    ANCLA_UMBRALES,
    BANDAS_LICENCIA,
    CANAL_FORZADO,
    CUENTA_NUEVA,
    EXE_CLIENTE,
    EXP_UMBRALES_OFF,
    LICENCIA_A_CANAL,
    LICENCIA_SOLO_POR_MISION,
    LICENCIA_VAL_FIJA,
    MODE_EQUIPO,
    MODE_RELEVO,
    MODE_VELOCIDAD,
)
from .registro import (
    log,
)
from .basedatos import (
    db_get_char,
)

# El módulo se lee con rutas relativas a la RAÍZ del proyecto, no a
# `servidor/`. Viene de cuando todo era un archivo solo; sacarlo rompe la
# lectura de las tablas del cliente (wing.txt / face.txt).
__file__ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server_login2013.py")   # rutas relativas como en el original
                                  #   banda sin mentirle el código al cliente (ver arriba por qué).
# ⏳ Calibración vieja del @19, guardada por si algún día se quiere licencia REAL client-side:
#    0 = sin licencia (el código sale del nivel) · 1 = estrella · 1000000 = sol  (probe 2026-07-11).
#    Con valores != 0 el ícono cambia PERO se rompe el botón Multi (gate 0x4A1D20). No usar.

def licencia_de_nivel(nivel):
    """(clave del canal, byte del FFC9, LICENSE_VAL del MyRecord) para ese nivel."""
    b = BANDAS_LICENCIA[0]
    for x in BANDAS_LICENCIA:
        if nivel >= x[0]:
            b = x
    if CANAL_FORZADO:
        b = next((x for x in BANDAS_LICENCIA if x[1] == CANAL_FORZADO), b)
    return b[1], b[2], b[3]

def char_para_banda(usn):
    """El personaje del usn; si TODAVÍA NO EXISTE, la plantilla con la que va a nacer.

    ★★ 2026-08-06 — POR QUÉ: la banda se decide en el **LOGIN**, y el personaje se crea DESPUÉS
       (FF04, ya adentro del lobby). En la primerísima sesión de una cuenta nueva no hay char, así
       que leíamos `exp=0` ⇒ el jugador aterrizaba en **'Principiante'** aunque su personaje
       naciera nivel 50. Se acomodaba solo al volver a entrar, pero la primera vuelta quedaba en la
       banda equivocada. Con la plantilla puesta acá, la cuenta nueva entra derecho a la que le toca.
    (`CUENTA_NUEVA` se define más abajo, en el bloque de la DB: Python resuelve el global al llamar.)
    """
    return db_get_char(usn) or dict(CUENTA_NUEVA)

def nibbles_a_campoE(n):
    """[n0,n1,n2] -> el u16 del campo E del RESP-1."""
    return (n[0] & 0xF) | ((n[1] & 0xF) << 4) | ((n[2] & 0xF) << 8)

def nibble_historia(char):
    """★ 29-sep: el nibble del GRUPO 1 que se puede mandar SIN sobre-marcar.

    El bucle del login otorga las máscaras 1..n EN FILA, y por eso el grupo 1 iba en 0: con sólo la
    3 hecha habría marcado también la 1 y la 2. Pero con 0 el «Anillo del Amor» (máscara 4, id 0: el
    replay del FF125 no la alcanza) se borraba en cada login, y detrás de él se trababa la cadena.
    ⇒ Se manda el tramo CONTIGUO: el mayor k tal que las máscaras 1..k están TODAS hechas. Nunca
      marca una que no se jugó; en el peor caso se queda corto, que es lo que pasaba antes."""
    from .ajustes import MASCARA_DE_MISION
    hechas = set()
    for grupo in char.get("misiones_hechas") or []:
        for mid in grupo or []:
            m = MASCARA_DE_MISION.get(int(mid))
            if m:
                hechas.add(m)
    hechas.update(int(m) for m in char.get("misiones_mascaras") or [])
    k = 0
    while k < 4 and (k + 1) in hechas:
        k += 1
    return k


def modo_texto(flags, colab=False, boss=False):
    """Descripcion legible del modo elegido (para el log)."""
    if boss:  return "modo JEFE"
    if colab: return "modo COLABORACION"
    equipo = "relevo" if flags & MODE_RELEVO else ("equipo" if flags & MODE_EQUIPO else "solo")
    return f"{equipo} + {'velocidad' if flags & MODE_VELOCIDAD else 'item'}"


# ── NIVEL Y LICENCIA ──────────────────────────────────────────────────────────
# Vivian en `lobby.py`, que no tenia nada que ver. La tabla de umbrales se lee del
# EXE del cliente al arrancar (no esta en ningun archivo de datos), asi que este
# modulo depende de `EXE_CLIENTE` de ajustes.
_UMBRALES = []      # los 99 umbrales de exp, leidos del exe al arrancar

def cargar_umbrales_exp():
    """Lee del exe los 99 umbrales de nivel. Si falla, deja la lista vacía (nivel=1 siempre)."""
    global _UMBRALES
    try:
        with open(EXE_CLIENTE, "rb") as f:
            datos = f.read()
    except Exception as e:
        log("MAIN", f"⚠ no pude abrir el exe para la tabla de niveles: {e!r} -> TODOS nivel 1")
        return _UMBRALES

    off = EXP_UMBRALES_OFF
    if datos[off:off + len(ANCLA_UMBRALES)] != ANCLA_UMBRALES:
        hallado = datos.find(ANCLA_UMBRALES)
        if hallado < 0:
            log("MAIN", "⚠ NO encontré la tabla de niveles en el exe -> TODOS nivel 1")
            return _UMBRALES
        log("MAIN", f"⚠ la tabla de niveles se movió: 0x{off:X} -> 0x{hallado:X} "
                    f"(¿build nueva del cliente?)")
        off = hallado

    v = list(struct.unpack("<99I", datos[off:off + 99 * 4]))
    if not all(v[i] < v[i + 1] for i in range(98)):
        log("MAIN", f"⚠ la tabla en 0x{off:X} NO es creciente -> la descarto, TODOS nivel 1")
        return _UMBRALES
    _UMBRALES = v
    return _UMBRALES

def nivel_de_exp(exp):
    """nivel = cantidad de umbrales <= exp (mínimo 1)."""
    n = sum(1 for u in _UMBRALES if u <= int(exp or 0))
    return max(1, n)


def licencia_actual(usn=0):
    """Licencia vigente: la GANADA por misión (DB). El nivel sólo decide la BANDA, no la máscara."""
    ch = char_para_banda(usn)
    cl, ti, li = licencia_de_nivel(nivel_de_exp(int(ch.get("exp", 0))))
    ganada = int(ch.get("licencia", 0) or 0)
    if ganada:                                   # ★ la misión manda sobre el nivel
        for bit in (4, 2, 1):                    # gana el bit más alto
            if ganada & bit:
                cl, ti = LICENCIA_A_CANAL[bit]
                break
        li = ganada
    elif LICENCIA_SOLO_POR_MISION:
        li = 0                                   # ★ sin misión hecha => SIN licencia, aunque el nivel alcance
    if LICENCIA_VAL_FIJA is not None:
        li = LICENCIA_VAL_FIJA
    return cl, ti, li

def codigo_cliente(nivel, licencia=0):
    """El código que va a calcular `0x486E90` en el CLIENTE.
       ★★ La LICENCIA manda sobre el nivel, y es una MÁSCARA DE 3 BITS (medida con re/barrido_licencia.py
       leyendo a qué canal conecta el cliente solo):  bit0=1 -> ESTRELLA (código 3) · bit1=2 -> LUNA
       (código 5) · bit2=4 -> SOL (código 7); gana el bit más alto. Sin licencia, el código sale del
       NIVEL y **nunca pasa de 2 (`starchobo`)**.
       ⏳ Los códigos 4 (`moonchobo`) y 6 (`sunchobo`) salen de ÍTEMS (0x0D / 0x0A) y no de este valor:
          para esas dos bandas todavía hace falta el canje de cat."""
    if licencia & 4: return 7
    if licencia & 2: return 5
    if licencia & 1: return 3
    return 8 if nivel < 4 else (1 if nivel <= 10 else 2)

# --- Respuestas (recetas FASE 2) ---
