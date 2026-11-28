# -*- coding: utf-8 -*-
"""antitrampa_firmas — ★ 28-nov (anonimo03: «que el panel diga qué está usando de acuerdo a lo que modifica la RAM»).

La dll informa la PRIMERA dirección del exe que cambió (`R2AT codigo=0x…`) o un gancho conocido (`gancho=…`). Cada
programa de trampas parchea SIEMPRE las mismas direcciones, así que la dirección dice el programa y la función:

    identificar(0x0054F31A) -> Firma(programa="Ñ2Hock (permitido)", funcion="Sin piedra…", clase="permitida", …)

Las clases (lo que hace el server con cada una, `ANTITRAMPA_REGLAS`):
    · "trampa"    -> lo que NO es de Ñ2Hock y da ventaja (los automáticos, el resultado falso de R2AutoRouteLab, el auto
                     listo / auto relevo del ToolBit viejo): su regla propia o `trampa_conocida` (expulsar = en modo
                     silencioso, retener y dejar pendiente para la tanda)
    · "permitida" -> ★ 28-nov, una función de Ñ2Hock (anonimo03: «todo lo que tenemos en Ñ2Hock está permitido»):
                     `n2hock_permitido` (registrar). No retiene ni correlaciona.
    · "arranque"  -> el punto de entrada del exe tocado al abrir el juego (un inyector o un launcher que carga algo
                     antes que el juego). Si los bytes de ahora son los de fábrica, se restauró: `arranque_restaurado`.

Fuentes (las direcciones son RVA del R2Beat.exe del launcher, md5 0f79000e…, sha256 7184FA94…):
    · Ñ2Hock y el ToolBit viejo: `_analisis/ToolBit_src/ToolBit.Patches/*.cs` y `Ñ2Hock-codigo-fuente/src/ToolBit.Patches`.
    · R2AutoRouteLab2013: INFORME_LABORATORIO.md y ★ 28-nov la versión «Release-next» (su perfil «SpaceWander» es el
      sha256 de NUESTRO exe; engancha el resultado en +0x101451, 7 bytes antes que la versión vieja).
"""
from collections import namedtuple

BASE = 0x400000
Firma = namedtuple("Firma", "rva largo programa funcion clase")

N2HOCK = "Ñ2Hock (permitido)"
TOOLBIT_VIEJO = "ToolBit / Ñ2Hock viejo (automático, ya quitado de Ñ2Hock)"
LAB = "R2AutoRouteLab2013"

FIRMAS = (
    # ── juego automático y resultado (ya tienen su regla propia: juego_automatico / resultado_alterado)
    Firma(0x1080B5, 5, TOOLBIT_VIEJO, "Juego automático", "trampa"),
    Firma(0x10A170, 6, f"{LAB} / {TOOLBIT_VIEJO}", "Automático Normal (tick de la meta)", "trampa"),
    Firma(0x109130, 6, LAB, "Automático Normal (auxiliar)", "trampa"),
    Firma(0x1003D0, 6, LAB, "Automático PD0 silencioso", "trampa"),
    Firma(0x1060B1, 10, LAB, "Automático largas A", "trampa"),
    Firma(0x1064F1, 11, LAB, "Automático largas B", "trampa"),
    Firma(0x10CAB6, 6, LAB, "Activador del juego automático (ítem 1000659)", "trampa"),
    Firma(0x101451, 7, LAB, "Resultado personalizado (precisión falsa)", "trampa"),
    Firma(0x101458, 8, LAB, "Resultado personalizado (precisión / combo falsos)", "trampa"),
    Firma(0x1C887B, 5, LAB, "Resultado de Juego Solo falso", "trampa"),
    Firma(0x1AEDD4, 6, TOOLBIT_VIEJO, "Auto listo / inicio, anfitrión al azar, misma canción", "trampa"),
    Firma(0x105340, 5, TOOLBIT_VIEJO, "Auto relevo", "trampa"),
    # ── ★ 28-nov (anonimo03: «todo lo que tenemos en Ñ2Hock está permitido»): las funciones de Ñ2Hock, aunque las
    #   ponga desde afuera el Ñ2Hock.exe, sólo se REGISTRAN (`n2hock_permitido`) y no correlacionan.
    Firma(0x0EB210, 1, N2HOCK, "Autoimpulso (booster solo)", "permitida"),
    Firma(0x103F82, 2, N2HOCK, "Sin obstáculos en los carriles", "permitida"),
    Firma(0x14F31A, 6, N2HOCK, "Sin piedra (inmune al ítem piedra)", "permitida"),
    Firma(0x150B31, 2, N2HOCK, "Sin piedra (inmune al ítem piedra)", "permitida"),
    Firma(0x171B5A, 2, N2HOCK, "Sin niebla (inmune al ítem niebla)", "permitida"),
    Firma(0x171B6D, 5, N2HOCK, "Supr niebla (inmune al ítem niebla)", "permitida"),
    Firma(0x171BBA, 2, N2HOCK, "Sin locura (inmune al ítem locura)", "permitida"),
    Firma(0x171BCD, 5, N2HOCK, "Supr (inmune a los ítems)", "permitida"),
    Firma(0x16DA5C, 2, N2HOCK, "Supr aleatorio (inmune a los ítems)", "permitida"),
    Firma(0x0FFF05, 4, N2HOCK, "Obstáculos transparentes", "permitida"),
    Firma(0x107EFD, 4, N2HOCK, "Obstáculos transparentes", "permitida"),
    Firma(0x107F11, 4, N2HOCK, "Obstáculos transparentes", "permitida"),
    Firma(0x107FEC, 4, N2HOCK, "Obstáculos transparentes", "permitida"),
    Firma(0x16D9CD, 8, N2HOCK, "Cambio de modo (ModeMapper)", "permitida"),
    Firma(0x0E63B0, 6, N2HOCK, "Cambio de modo (ModeMapper)", "permitida"),
    Firma(0x1010E5, 6, N2HOCK, "Cambio de modo (ModeMapper)", "permitida"),
    Firma(0x105447, 5, N2HOCK, "Precisión estilo Valofe (ajuste del cálculo)", "permitida"),
    Firma(0x105486, 5, N2HOCK, "Precisión estilo Valofe (ajuste del cálculo)", "permitida"),
    Firma(0x150B05, 5, N2HOCK, "Precisión estilo Valofe (ajuste del cálculo)", "permitida"),
    Firma(0x1054C9, 5, N2HOCK, "Panel de precisión (lectura)", "permitida"),
    Firma(0x10C490, 5, N2HOCK, "Panel de precisión (cuadro)", "permitida"),
    Firma(0x16DAF3, 5, N2HOCK, "Panel de precisión (bloque)", "permitida"),
    Firma(0x094FA9, 29, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x094FD9, 29, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x095009, 29, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x095039, 29, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x095274, 29, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x0952A4, 29, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x0952D4, 29, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x095304, 29, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x09543D, 31, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x095470, 32, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x0954A3, 33, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x0954C4, 31, N2HOCK, "Teclado doble (teclas cambiadas)", "permitida"),
    Firma(0x010484, 8, N2HOCK, "Velocidad de práctica (reloj del juego)", "permitida"),
    Firma(0x174080, 8, N2HOCK, "Velocidad de práctica (ritmo)", "permitida"),
    Firma(0x0FE3A0, 5, N2HOCK, "Cámara fija", "permitida"),
    Firma(0x131510, 5, N2HOCK, "Sin efecto del booster", "permitida"),
    Firma(0x10BF76, 6, N2HOCK, "Sin efecto fantasma", "permitida"),
    Firma(0x10C146, 6, N2HOCK, "Sin efecto fantasma", "permitida"),
    Firma(0x0ED601, 2, N2HOCK, "Resultados rápidos", "permitida"),
    Firma(0x02A37B, 5, N2HOCK, "Far automático", "permitida"),
    Firma(0x0EA99D, 5, N2HOCK, "Far automático", "permitida"),
    Firma(0x5D45D8, 16, N2HOCK, "Far ampliado (mínimo / máximo)", "permitida"),
    Firma(0x0E9F61, 6, N2HOCK, "Efecto de velocidad", "permitida"),
    Firma(0x0FBE14, 7, N2HOCK, "Efecto de velocidad", "permitida"),
    Firma(0x100C43, 2, N2HOCK, "Ocultar nombres", "permitida"),
    Firma(0x16D526, 7, N2HOCK, "Sonido del booster", "permitida"),
    Firma(0x16D6B4, 7, N2HOCK, "Sonido del booster", "permitida"),
    Firma(0x1B9AC0, 6, N2HOCK, "Lista de música", "permitida"),
    Firma(0x1BB3A4, 6, N2HOCK, "Lista de música", "permitida"),
    Firma(0x1BFC30, 7, N2HOCK, "Lista de música", "permitida"),
    # ── el arranque del exe (el punto de entrada: call __security_init_cookie; jmp __tmainCRTStartup)
    Firma(0x3532F5, 10, "un inyector o launcher al abrir el juego", "Punto de entrada del exe", "arranque"),
)

# Los bytes de fábrica del punto de entrada (para saber si lo que se ve ahora es la restauración).
ARRANQUE_FABRICA = bytes.fromhex("E8D3F20000E978FEFFFF")
ARRANQUE_VA = BASE + 0x3532F5

# Un parche a veces deja igual su primer byte: la primera diferencia cae unos bytes más adentro. Margen después del
# final de cada firma (no antes: una diferencia ANTES del comienzo no es de ese parche).
_MARGEN = 2


def identificar(va):
    """La firma que cubre la dirección absoluta `va` (int), o None."""
    try:
        rva = int(va) - BASE
    except (TypeError, ValueError):
        return None
    mejor = None
    for f in FIRMAS:
        if f.rva <= rva < f.rva + f.largo + _MARGEN and (mejor is None or f.rva > mejor.rva):
            mejor = f
    return mejor


def arranque_restaurado(va, bytes_hex):
    """¿Lo que se ve ahora en el punto de entrada (`bytes_hex`, «E8_D3_…» desde `va`) es lo de fábrica?"""
    try:
        va, b = int(va), bytes.fromhex(str(bytes_hex).replace("_", "").replace(" ", ""))
    except (TypeError, ValueError):
        return False
    d = va - ARRANQUE_VA
    if not b or d < 0 or d >= len(ARRANQUE_FABRICA):
        return False
    esperado = ARRANQUE_FABRICA[d:d + len(b)]
    return b[:len(esperado)] == esperado


def texto(f):
    """«Ñ2Hock (permitido) · Sin piedra (inmune al ítem piedra)» para el panel."""
    return f"{f.programa} · {f.funcion}"
