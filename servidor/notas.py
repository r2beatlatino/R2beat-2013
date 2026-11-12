# -*- coding: utf-8 -*-
"""notas — los charts que el server manda por `FF57`.

El cliente 2013 no trae las notas de sus canciones: las pide al server, una por canción,
y las espera en el formato que documenta `documentacion/RECETA_NOTAS_2013.md`. Acá vive
todo lo que hace falta para responder ese pedido: el mapa de qué `.bin` es de cada
canción y la lectura del archivo.

Los `.bin` los produce `taller/importador2013/` (ver su LEEME). Este módulo sólo los sirve.

⛔ **Una canción ofrecida en el picker SIN chart mata al cliente.** El handler `0x5D01F0`
   baja el contador de pedidos pendientes aunque el `result` no sea 1, y al llegar a cero
   corre `0x56E080` con los vectores vacíos: el proceso se auto-mata, sin excepción ni
   log. Por eso `cargar()` devuelve la lista de canciones jugables y el picker se arma
   con ESA, nunca con una lista escrita a mano.

★ Este módulo NO exporta estado mutable, a propósito. El mapa vive en `_MAPA` (privado) y
  se consulta por funciones. Exportarlo como `NOTES_MAP` era lo que había antes y estaba
  roto: `lobby_carrera` se lo llevaba por `from .lobby import *` **antes** de que
  `cargar()` corriera, y como `cargar()` lo REASIGNABA, se quedaba para siempre con el
  diccionario vacío. Las notas se servían bien igual, pero el log decía
  `SIN MAPA -> puede ser otra canción` en las 814 canciones. Un dato falso en un log
  cuesta una sesión entera de alguien buscando un problema que no existe.
"""
import json
import os
import re
import struct
import zlib

from .ajustes import NOTES_DIR_2013, NOTES_MAP_FILE
from .registro import log

_MAPA = {}          # songid del cliente 2013 -> songid del .bin (hoy: la identidad)
_TITULOS = {}       # songid -> nombre, sólo para que el log se lea
_OTRA_REVISION = set()   # la canción es la correcta, pero el chart es otra edición


def cargar():
    """Lee `notes_map_2013.json`. Devuelve las canciones jugables, o `None` si no pudo.

    Lo llama el arranque. La lista que devuelve es la única fuente válida para el picker.
    """
    global _MAPA, _TITULOS, _OTRA_REVISION
    try:
        with open(NOTES_MAP_FILE, encoding="utf-8") as f:
            j = json.load(f)
    except Exception as e:
        log("MAIN", f"⚠ notes_map_2013.json NO se pudo leer ({e}) -> el FF57 va a servir por "
                    f"índice CRUDO, que es el chart de otra canción. "
                    f"Regeneralo: python taller/importador2013/importar2013.py --apply --con-revisar")
        return None
    _MAPA = {int(k): int(v) for k, v in j.get("map", {}).items()}
    _TITULOS = {int(k): v for k, v in j.get("titles", {}).items()}
    _OTRA_REVISION = {int(x) for x in j.get("combo_mismatch", [])}
    jugables = j.get("owned_songs") or None
    log("MAIN", f"notas: {len(_MAPA)} canciones mapeadas, {len(jugables or [])} jugables")
    # Las de "otra revisión" casan por el `File` del music_lt (o sea: son la canción
    # correcta y del largo correcto) pero el chart es otra edición, con distinto combo.
    # No hay síntoma visible: el popup del combo NO existe en este cliente — el string
    # `올콤카운트에러` está en los exes del CBT y en el de 2013 no está. Ver la receta.
    if _OTRA_REVISION:
        log("MAIN", f"notas: {len(jugables or []) - len(_OTRA_REVISION)} con el combo exacto y "
                    f"{len(_OTRA_REVISION)} de otra revisión del chart {sorted(_OTRA_REVISION)}")
    return jugables


def chart_de(song_id):
    """Los bytes del chart de esa canción, o `None` si no lo tenemos."""
    path = os.path.join(NOTES_DIR_2013, f"{_MAPA.get(song_id, song_id)}.bin")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


# ★★ 06-nov (161) — EL TECHO DE 4096 DE LA DLL VIEJA. El cliente de fábrica copia el chart del FF57 en una caja de
#   la PILA de 4096 bytes sin mirar el largo: uno de 4097 lo MATA sin rastro (`CHART_TECHO_4096.md`). La dll nueva
#   (`chart_grande.c`) le da una caja de 64 KB y lo avisa en el FF59 («R2DLL … chart64k=1» → `salas.DLL_CHART64K`).
#   A quien no lo avisó, un chart más grande le va RECORTADO: se sacan notas del final hasta que entra. La canción
#   se juega (sin el final) y nadie se cae. El recorte se calcula una vez por chart.
TECHO_FF57_VIEJO = 4096
_RECORTADOS = {}                      # blob entero -> (blob recortado, notas antes, notas después)


def recortar_al_techo(blob, techo=TECHO_FF57_VIEJO):
    """`(blob, antes, despues)`: el mismo blob si entra; si no, con notas de menos AL FINAL hasta que entra.

    El blob es `[i32 n][n × (i32 frame, f32 bpm)] + zlib(notas de 6 bytes)` (`RECETA_NOTAS_2013.md`). Se cortan
    notas, nunca BPM; y no queda colgado un hold (Kind ≥ 0x80) al final. `None` en el blob si no hay forma.
    """
    if len(blob) <= techo:
        return blob, None, None
    if blob in _RECORTADOS:
        return _RECORTADOS[blob]
    try:
        n = struct.unpack_from("<i", blob, 0)[0]
        corte = 4 + 8 * n
        crudo = zlib.decompress(blob[corte:])
    except Exception:                                                  # noqa: BLE001
        _RECORTADOS[blob] = (None, None, None)
        return _RECORTADOS[blob]
    total = len(crudo) // 6

    def armar(k):
        while k > 0 and crudo[6 * (k - 1) + 2] >= 0x80:                # sin un hold colgado al final
            k -= 1
        return blob[:corte] + zlib.compress(crudo[:6 * k], 9), k

    lo, hi, mejor = 0, total, None                                     # la mayor cantidad de notas que entra
    while lo <= hi:
        mid = (lo + hi) // 2
        b, k = armar(mid)
        if len(b) <= techo:
            mejor, lo = (b, k), mid + 1
        else:
            hi = mid - 1
    res = (mejor[0], total, mejor[1]) if mejor and mejor[1] > 0 else (None, total, 0)
    _RECORTADOS[blob] = res
    return res


def hay_chart(song_id):
    """Si la canción se puede jugar. Barato: no lee el archivo entero."""
    return os.path.exists(os.path.join(NOTES_DIR_2013, f"{_MAPA.get(song_id, song_id)}.bin"))


def origen_de(song_id):
    """De qué `.bin` sale el chart, para el log. `None` = no está en el mapa."""
    return _MAPA.get(song_id)


def titulo_de(song_id):
    """El nombre de la canción, para que el log se pueda leer."""
    return _TITULOS.get(song_id, "?")


def es_otra_revision(song_id):
    """La canción es la correcta pero el chart es otra edición (distinto combo)."""
    return song_id in _OTRA_REVISION


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ EL NIVEL (dificultad) DE CADA CANCIÓN — `music_lt.txt` del propio cliente
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Lo pidió el usuario el 2026-09-05: *"en el cooperativo a veces salen músicas MUY fáciles, y en el
# original las muy fáciles casi no salían"*. Tenía razón, y la prueba está en el catálogo del juego.
#
# ★★★ EL DATO: `music_lt.txt` trae `Level="N"` por canción, **y trae DOS entradas de "Aleatoria"**:
#
#       Index="0"  Name="Aleatoria"  Image="…/random_chobo.bmp"  Level="0"
#       Index="1"  Name="Aleatoria"  Image="…/random_gosu.bmp"   Level="7"
#
#   `chobo` (초보) = **novato** · `gosu` (고수) = **experto**. O sea: el juego **parte su propia
#   biblioteca en dos bolsas**, y el corte está en **el nivel 7**. Lo mismo, idéntico, en el
#   cliente chino de 2018/2019 (que además agrega el par `Loop` chobo/gosu con el mismo 7).
#   ⇒ El sorteo del original NO era plano sobre todo el catálogo.
#
# ⚠⚠ LO QUE **NO** ESTÁ MEDIDO: qué bolsa usaba el COOPERATIVO. El sorteo del chase lo hace el
#    servidor y no tenemos ninguna captura del server original haciéndolo. El 7 sale del catálogo
#    del juego, **no** de una captura del modo. Por eso es una perilla (`CHASE_NIVEL_MIN`) y no
#    una constante, y por eso el default es prudente. Ver [[el-referente-no-es-la-ley]].
#
# Lo que sí está medido, de nuestras 814 canciones jugables:
#       nivel 1: 63 · 2: 30 · 3: 15 · 4: 9   ⇒ 117 canciones (14 %) de nivel ≤ 4
#   Con 3 canciones por partida, eso es ~38 % de las partidas con al menos una muy fácil. Que es
#   exactamente la frecuencia que describió el usuario.
_NIVELES = None


def _buscar_music_lt():
    """Dónde está `music_lt.txt`. Vive DENTRO de `rnr_script.pak`, así que lo normal es que esté
    en la carpeta que dejó el desempacador o el importador, no suelto en el cliente."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (
        os.path.join(raiz, "R2Beat", "rnr_script", "music_lt.txt"),
        os.path.join(raiz, "taller", "importador2013", "_tmp", "2013", "rnr_script", "music_lt.txt"),
        os.path.join(raiz, "taller", "importador2013", "_tmp", "pak", "rnr_script", "rnr_script",
                     "music_lt.txt"),
        # ★ desde el 2026-09-16 las tablas del cliente viven en `servidor/tablas-cliente/`;
        #   se deja la de la raíz detrás por si queda una copia vieja en algún lado.
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "tablas-cliente", "music_lt.txt"),
        os.path.join(raiz, "tablas-cliente", "music_lt.txt"),
    ):
        if os.path.isfile(cand):
            return cand
    return None


def cargar_niveles():
    """`{songid: nivel}` del `music_lt.txt` del cliente. `{}` si no aparece el archivo.

    ⚠ No revienta si falta: sin niveles el sorteo simplemente vuelve a ser plano, que es lo que
      hacía antes. Un filtro que se cae y tumba el arranque sería peor que no tenerlo.
    """
    global _NIVELES
    if _NIVELES is not None:
        return _NIVELES
    _NIVELES = {}
    path = _buscar_music_lt()
    if not path:
        log("MAIN", "  ⚠ music_lt.txt no aparece: el sorteo del cooperativo va SIN filtro de "
                    "nivel. Se saca con `python taller/re2013/desempacar.py rnr_script`.")
        return _NIVELES
    try:
        crudo = open(path, "rb").read().decode("cp949", "replace")
    except Exception as e:                                   # noqa: BLE001
        log("MAIN", f"  ⚠ no pude leer {path}: {e!r} — sorteo sin filtro de nivel")
        return _NIVELES
    # ⚠ El 2013 escribe cada `<Music>` en VARIAS líneas y el chino de 2018 en una sola. El regex
    #   que sólo cubría el de una línea encontraba 236 de 822 y parecía que faltaban niveles.
    for bloque in re.findall(r"<Music(.*?)</Music>", crudo, re.S):
        i = re.search(r'Index="(\d+)"', bloque)
        n = re.search(r'Level="(\d+)"', bloque)
        f = re.search(r'File="([^"]*)"', bloque)
        if i and n and f and f.group(1):                     # sin File son las entradas especiales
            _NIVELES[int(i.group(1))] = int(n.group(1))
    log("MAIN", f"niveles de música: {len(_NIVELES)} canciones con dificultad, de {path}")
    return _NIVELES


def nivel_de(song_id, por_defecto=None):
    """El nivel (dificultad) de una canción según el catálogo del cliente, o `por_defecto`."""
    return cargar_niveles().get(song_id, por_defecto)


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★ EL COMBO TOTAL DE UNA CANCIÓN — el del chart QUE SERVIMOS, con la fórmula del exe (2026-09-24)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Lo necesita la «Profecía Allcombo»: allcombo = el combo del reporte llega al total de la canción.
# ⚠ NO se usa el `Combo=` del `music_lt`: en las 15 de `combo_mismatch` el chart es otra edición y
#   ese número no es el que el cliente cuenta. Se cuenta sobre el `.bin` que mandamos por `FF57`,
#   igual que el cliente (`0x56E3D0`, ver `RECETA_NOTAS_2013.md` §3):
#       autoplay (Fx & 0x8000) -> 0 · Kind 0x18 -> +2 · Kind >= 0x80 y (Kind-0x80) % 3 != 1 -> +1
#       · resto -> +1
# Es copia de `taller/importador2013/combo_exe.py` (que no sube a prod); si no coinciden, manda
# la receta. `pruebas/probar_profecias.py` compara los dos.
_COMBOS = {}

# ★ (97) Cuántos `<EFFECT>` (samples de Miles) trae el XML de cada canción del cliente: el cooperativo los carga todos
#   de una y pasado el tope se cae (`ajustes.CHASE_EFECTOS_TOPE`). Tabla de `herramientas/efectos_por_cancion.py`.
_EFECTOS = None


def efectos_de(song_id):
    """Los `<EFFECT>` de la canción (0 si no está en la tabla o no hay tabla)."""
    global _EFECTOS
    if _EFECTOS is None:
        from .ajustes import _DIR_SERVIDOR
        try:
            with open(os.path.join(_DIR_SERVIDOR, "tablas-cliente", "efectos_por_cancion.json"), encoding="utf-8") as f:
                _EFECTOS = {int(k): int(v) for k, v in json.load(f)["canciones"].items()}
        except Exception as e:                                       # noqa: BLE001
            log("MAIN", f"⚠ no pude leer efectos_por_cancion.json ({e!r}): el cooperativo sortea SIN el tope de sonidos")
            _EFECTOS = {}
    return _EFECTOS.get(int(song_id), 0)


def combo_total_de(song_id):
    """El combo máximo de la canción, contado sobre SU chart. `None` si no hay chart o no se lee."""
    if song_id in _COMBOS:
        return _COMBOS[song_id]
    total = None
    datos = chart_de(song_id)
    if datos and len(datos) >= 4:
        try:
            count = struct.unpack_from("<i", datos, 0)[0]
            if 0 <= count and 4 + count * 8 <= len(datos):
                crudo = zlib.decompress(datos[4 + count * 8:])
                total = 0
                for i in range(0, len(crudo) - len(crudo) % 6, 6):
                    _coord, kind, _lv, fx = struct.unpack_from("<HBBH", crudo, i)
                    if fx & 0x8000:
                        continue
                    if kind >= 0x80:
                        total += 1 if (kind - 0x80) % 3 != 1 else 0
                    else:
                        total += 2 if kind == 0x18 else 1
        except Exception as e:                               # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude contar el combo del chart de {song_id}: {e!r}")
            total = None
    _COMBOS[song_id] = total
    return total


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ NIVEL → BANDA (el "canal" del picker) — LEÍDO DEL CLIENTE 2013, `0x40C5C0`
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# El nivel no es una escala suelta: el cliente lo convierte en una **banda**, que es el casillero
# del picker. La función es una cascada de comparaciones, y está DOS veces en el binario — como
# función suelta en `0x40C5C0` (llamada desde `0x413994`) y otra vez inlineada en `0x40D840`:
#
#       cmp al, 2   -> banda 8        cmp al, 0xA -> banda 4
#       cmp al, 4   -> banda 1        cmp al, 0xE -> banda 5
#       cmp al, 5   -> banda 2        cmp al, 0x11-> banda 6
#       cmp al, 7   -> banda 3        (resto)     -> banda 7
#
# ⇒ **El 2013 tiene OCHO bandas** (la 8 es la primera y la más fácil; después 1..7 en orden):
#
#       banda 8 = niveles 1-2      banda 4 = 8-10
#       banda 1 = niveles 3-4      banda 5 = 11-14
#       banda 2 = nivel   5        banda 6 = 15-17
#       banda 3 = niveles 6-7      banda 7 = 18-20
#
# ★ Y encaja con lo que ya teníamos anotado del otro lado: *"la banda debe ser 1..8; `LevelToMask`
#   devuelve un solo bit para ese rango — banda 8 -> bit0, bandas 1..7 -> bit N"* (ver el `FFC9` en
#   `lobby_salas.py`). Dos caminos independientes que dan el mismo 1..8.
#   ⚠ La dirección `0x5BA360` que esa nota le pone a `LevelToMask` **NO es esa función**: cae en
#     medio de una rutina de UI. Es de otro build, como la tabla RX vieja. La que sí está
#     verificada acá es `0x40C5C0`.
#
# ★★ CONTRA EL CBT 2011 (`D:\Nueva carpeta\importador-musica\SESION_2026-07-22_tiers.md`, que hizo
#    el RE del gate `0x451c60` de aquel exe): el CBT tiene **7** tiers con topes 4/5/7/10/14/17/20.
#    El 2013 tiene los MISMOS topes de la mitad para arriba y **parte en dos el primero**:
#    el "novato 1-4" del CBT es acá **1-2 (banda 8)** y **3-4 (banda 1)**.
#    ⇒ Es la contraparte del 2013 que faltaba. Los canales visibles del CBT (Estrella/Luna/Sol)
#      agrupan estas bandas; qué banda cae en qué canal en el 2013 **todavía no está medido**.
#
# ★★★★★ Y EL NOMBRE DE CADA BANDA — confirmado por el usuario con una CAPTURA (2026-09-05).
#   Mandó la lista de canales del cliente y la fila de iconos del picker: **ocho**, en cuatro
#   pares (casita verde ×2, estrella amarilla ×2, luna azul ×2, sol rojo ×2), que son exactamente
#   los mismos ocho de nuestra tabla `CANALES_2013` en `ajustes.py`, y en el mismo orden:
#
#       banda 8 = Principiante     niveles 1-2      banda 4 = Novato Luna    niveles 8-10
#       banda 1 = Novato           niveles 3-4      banda 5 = Luna           niveles 11-14
#       banda 2 = Novato Estrella  nivel   5        banda 6 = Novato Sol     niveles 15-17
#       banda 3 = Estrella         niveles 6-7      banda 7 = Sol            niveles 18-20
#
#   ⇒ Los 7 tiers del CBT calzan uno a uno con las bandas 1..7 del 2013, y el 2013 agrega la
#     **Principiante** partiendo en dos el "novato 1-4" del CBT. Tres fuentes independientes —el
#     disasm, la tabla de canales que ya teníamos, y la captura— dicen lo mismo.
_TOPES_BANDA = ((2, 8), (4, 1), (5, 2), (7, 3), (10, 4), (14, 5), (17, 6))
NOMBRE_BANDA = {8: "Principiante", 1: "Novato", 2: "Novato Estrella", 3: "Estrella",
                4: "Novato Luna", 5: "Luna", 6: "Novato Sol", 7: "Sol"}
# El orden de fácil a difícil, que NO es el orden numérico (la 8 va primero).
ORDEN_BANDAS = (8, 1, 2, 3, 4, 5, 6, 7)


def rango_de_banda(banda):
    """`(nivel_min, nivel_max)` de una banda. Se deriva de los mismos topes que usa el cliente."""
    piso = 1
    for tope, b in _TOPES_BANDA:
        if b == banda:
            return (piso, tope)
        piso = tope + 1
    return (piso, 99) if banda == 7 else None


def banda_de_nivel(nivel):
    """La banda (casillero del picker) de un nivel. Calca `0x40C5C0` del cliente 2013."""
    if nivel is None:
        return None
    for tope, banda in _TOPES_BANDA:
        if nivel <= tope:
            return banda
    return 7


def banda_de(song_id):
    """La banda del picker de una canción, o `None` si no sabemos su nivel."""
    return banda_de_nivel(nivel_de(song_id))
