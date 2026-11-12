# -*- coding: utf-8 -*-
r"""
lobby_campana.py — LAS CAMPANAS de oro y de plata (`FFA8`).

★★★ QUÉ ES Y DE DÓNDE SALIÓ
================================================================================
2026-09-15, pedido de anonimo03: *"vamos a mapear otro item, campanas de plata"*. Tenía 15 en el
inventario y al tocarlas el log decía lo de siempre:

    inner FFA8 len=16 : 30 01 00 00 00 00 c8 c2 00 00 0c c3 db 0f 49 40
    inner FFA8 SIN handler

Ahí está el pedido entero:

    C2S  FFA8 [u32 item][f32 x][f32 z][f32 rot]
              304        -100.0   -140.0   3.14159…

★ Las tres coordenadas las arma `0x443BC0`: le pregunta al mundo dónde estás y manda **x, z y
  rotación** — la altura no viaja. Para el server son informativas (van al log y nada más): el
  cartel no las usa. Se leen igual porque un campo que no se lee es un campo que mañana alguien
  interpreta al revés.

★★ Y NO HAY QUE ADIVINAR QUÉ HACE EL ÍTEM: lo dice el propio cliente
================================================================================
El cartel de confirmación que ve el jugador es el texto 553 (oro) / 638 (plata):

    «¡Hoy es su día de suerte! ¿Desea hacer sonar la campana? …
      TODOS LOS USUARIOS EN LA SALA RECIBIRÁN EL BONO RCOIN.»

y alrededor está el resto del reglamento, también escrito y ya traducido:

| texto | dice | quién lo hace cumplir |
|---|---|---|
| 640 | «sólo puede usarse en la sala de juego» | el CLIENTE (ni manda el `FFA8`) |
| 642 | «los espectadores pueden usar la campana» | el CLIENTE |
| 639 | «otro usuario ya hizo sonar la campana; intente nuevamente **luego de jugar un juego**» | ★ NOSOTROS |
| 641 | «¡La Campana de Plata! %s ha hecho sonar %s en la sala %d» | el cartel que difundimos |
| 643 | «%s ha recibido %d de RCoin por la Bonificación de Campana de Plata» | ídem, al que cobra |

⚠ El 639 dice *«luego de jugar un juego»*, **no** «luego de N minutos». El candado no es un reloj:
  se abre cuando la sala arranca una canción. Por eso `liberar_campana(rid)` lo llama la carrera.

★★★ CÓMO SABE EL CLIENTE QUE UN ÍTEM ES UNA CAMPANA
================================================================================
No por la familia del `shop_lt` (ahí son `coupon_buff`, mezcladas con los cupones de EXP). Tiene
dos preguntas cableadas, `0x444060` («¿es de oro?») y `0x444080` («¿es de plata?»), y después
**normaliza con aritmética** (`0x430420`):

    oro:    0xB5 + 2*plus   ->  181 «Campana de Oro»    / 183 «Campana de Oro+»
    plata:  0x130 - 7*!plus ->  297 «Campana de plata»  / 304 «Campana de plata+»

Esos cuatro números son exactamente los del `shop_lt`. La tabla `CAMPANAS` de `ajustes` es esa
misma tabla, copiada de su aritmética y no deducida de los nombres.

★★★★★ EL CIRCUITO COMPLETO (los nombres los puso el cliente 2019)
================================================================================
    C2S  FFA8  CmdUse                                     «usé este ítem»
    S2C  FFA9/FFC3  Cmd{Golden,Platinum}Bell              planta la campana EN LA SALA
    S2C  FFAA/FFC4  Cmd…BellNotifer                       el cartel, A TODO EL SERVER
    …se juega la canción…
    S2C  FFB4/FFC5  Cmd…BellHit                           «fulano recibió N»
         + el renglón `bonustype 67` en el cartel de resultado (`bonus.xml`: 플래티넘벨)

★★ EL REPARTO lo dictó anonimo03 de memoria del juego real, y **no está en ningún archivo**:
      · consuelo para todo el que jugó: 2500 / 3000 / 3500 / 4000 (valores cerrados)
      · premio gordo **para el que tocó la campana**, y **sólo con la «+»**:
        25.000 / 30.000 / 35.000 / 40.000, de más común a más raro
      · **sólo la «+» saca cartel**. La normal suena, se planta y reparte, pero no interrumpe.
   ⚠ Eso no contradice la descripción del ítem: el ítem dice el TECHO («Máximo N»), no el
     reparto. Del reparto no dice nada — y el que jugó sí se acuerda.

⏳ LO QUE SIGUE SIN MEDIR
================================================================================
1. **El texto del cartel dice «Campana de Oro» aunque sea de plata.** El DIBUJO sale bien
   (`notice.xml` lo elige por itemcode) y el TEXTO no: son dos búsquedas distintas dentro del
   cliente. Ya se probó con el itemcode del «+» y con el base, y con los dos sale oro.
   ⛔ **Cuatro intentos por lectura estática, cuatro fallos.** Lo que corresponde es enganchar
     `0x430420` / `0x430620` con frida y ver qué reciben. No volver a leer.
2. **El `u32` del final del `plantar`**, que el cliente guarda en `[0x9314C0+0x13038]`.
3. **El bonustype del ORO**: `bonus.xml` no trae ninguno con «골든벨», así que el oro cobra pero
   sin renglón en el cartel.
"""
import random
import struct

from .ajustes import (
    CAMPANA_ACTIVA,
    CAMPANA_BONO,
    CAMPANA_BONO_BASE,
    CAMPANA_BONUSTYPE,
    CAMPANA_GORDO,
    CAMPANA_SOLO_PLUS_ANUNCIA,
    CAMPANA_CARTEL_BASE,
    CAMPANA_MONEDA,
    CAMPANA_PROPIAS,
    CAMPANA_SPAWN_EXTRA,
    CAMPANA_UNA_POR_SALA,
    CAMPANA_DESCUENTA_EN_PANTALLA,
    CAMPANAS,
    SALA_VESTIBULO,
    SYNC_POSICION_ACCION,
    SYNC_POSICION_AL_ENTRAR,
)
from .basedatos import (
    db_add_rcoin,
    db_add_rpoint,
    db_del_inventory,
    db_get_char,
    db_get_rcoin,
    inv_cant,
)
from .registro import log
from .salas import (CONEXIONES, avisar_a_uno, conexiones_en_sala, difundir_roomlist,
                    mesa_de)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# El candado: una campana por sala hasta que la sala juegue
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ★ Es un `set` de room_id y no un diccionario con marca de tiempo **a propósito**: el texto 639
#   del cliente no habla de tiempo, habla de jugar. Guardar un reloj sería inventar una regla que
#   el juego no tiene, y después alguien la lee y la da por medida.
# ⚠ La clave es **(sala, metal)**, no la sala sola. anonimo03: *"debería poder tocar 1 de plata y 1
#   de oro, pero sólo me deja tocar 1 a la vez"*. Son dos ítems distintos con dos bonos distintos
#   (uno paga Rcoin y el otro Rpoint): candados separados.
_SONADA = set()

# ★★★★★ LA CAMPANA QUEDA **ESPERANDO A QUE LA SALA JUEGUE**. Lo dice la descripción del ítem:
#   «Si hace sonar la campana de plata **y comienza el juego**, todos reciben bonus…», y lo vio
#   anonimo03 en pantalla antes que yo: *"el cartel de quién recibió el bono salió antes; éste recién
#   debe salir al final de la partida"*.
#   ⇒ Al tocarla se planta y se anuncia. El bono lo paga `pagar_campana()`, que llama el cartel
#     de resultado (`FF28`). Por eso el que entra DESPUÉS de que sonó pero ANTES de jugar
#     también cobra —que es lo que dice el texto, «todos los usuarios en la sala»— y el que se
#     va antes de jugar, no.
#   (rid, metal) -> {"plus", "canon", "quien", "techo", "rolls": {usn: monto}}
_PENDIENTE = {}

# ★ El id que hay que poner en el cartel para cada (metal, plus). Son los cuatro que
#   `notice.xml` indexa; las variantes de temporada (774/775) NO están ahí, así que si alguien
#   toca una de ésas el cartel tiene que salir con el canónico o el cliente no encuentra el
#   dibujo. Sale de la misma aritmética del cliente (`0x430420`).
_ITEM_CANONICO = {
    ("oro",   False): 181,
    ("oro",   True):  183,
    ("plata", False): 297,
    ("plata", True):  304,
}

# ★★★★★ LOS TRES COMANDOS POR METAL. Los nombres los puso el CLIENTE 2019, que los trae
#   escritos en su tabla RX (`taller/_analisis/reg19b.json`) — nosotros sólo los leímos:
#
#       0xA8  CmdUse                 <- el que RECIBIMOS («usé este ítem»)
#       0xA9  CmdGoldenBell          0xC3  CmdPlatinumBell        plantar la campana
#       0xAA  CmdGoldenBellNotifer   0xC4  CmdPlatinumBellNotifer el cartel
#       0xB4  CmdGoldenBellHit       0xC5  CmdPlatinumBellHit     «fulano cobró N Rcoin»
#
#   ⚠ Hace falta un comando por metal porque el itemcode del `Hit` **no viaja**: el cliente lo
#     tiene cableado (`push 0xB5`=181 en `0x5D7A46`, `push 0x129`=297 en `0x5DD3A6`). Y los dos
#     `Notifer` comparten handler (`0x5DD2C0`), así que ahí el itemcode SÍ viaja.
#   ★ En el 2013 los handlers existen y coinciden: A9->0x5D6AD0, C3->0x5DD200 (idénticos salvo
#     `push 0x47`='G' contra `push 0x50`='P'), AA=C4->0x5DD2C0, B4->0x5D79F0, C5->0x5DD350.
CMDS_POR_METAL = {
    "oro":   (0xA9, 0xAA, 0xB4),
    "plata": (0xC3, 0xC4, 0xC5),
}


def _slot_en_sala(rid, usn):
    """El asiento del jugador en la sala. `0x444260` lo usa para saber DÓNDE plantar la campana.

    ⚠ Devuelve 0 si no está sentado (un espectador). El texto 642 dice que los espectadores
      pueden tocarla, así que el caso existe de verdad; qué dibuja el cliente con el asiento de
      otro está sin medir.
    """
    try:
        for _s, _u in (mesa_de(rid) or {}).items():
            if int(_u) == int(usn):
                return int(_s)
    except Exception:                                                # noqa: BLE001
        pass
    return 0


def liberar_campana(rid, motivo=""):
    """Se puede volver a tocar campana en esa sala (las dos, oro y plata).

    ⚠ Lo llama el ARRANQUE de la carrera, no el final: una partida abandonada a mitad de camino
      dejaría la campana trabada para siempre. Lo pendiente de cobrar NO se toca acá — eso lo
      limpia `cerrar_campana()` cuando sale el cartel de resultado.
    """
    if rid is None:
        return False
    _hubo = [_m for (_r, _m) in list(_SONADA) if _r == rid]
    for _m in _hubo:
        _SONADA.discard((rid, _m))
    if _hubo:
        log("SALA", f"  ★ CAMPANA: la sala {rid} arrancó ({motivo}) -> se puede volver a tocar "
                    f"({', '.join(_hubo)})")
    return bool(_hubo)


def campana_sonada(rid, metal):
    """¿Ya sonó una campana **de ese metal** en esa sala desde la última canción?

    ⚠ La pregunta es por metal, no por sala. anonimo03: *"debería poder tocar 1 de plata y 1 de oro,
      pero sólo me deja tocar 1 a la vez"*. Son dos ítems distintos, con dos bonos distintos y
      hasta con monedas distintas: el candado de uno no es el del otro.
    """
    return (rid, metal) in _SONADA


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ⏳ El sync de posiciones — `FFF5` (`CmdCurrentActionObject`)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ★ Lo ÚNICO que el cliente nos cuenta de dónde está parado alguien es el `FFA8` de la campana:
#   trae `(x, z, rot)`, que son justo los tres floats que el `FFF5` pide. Así que se guardan.
#   (rid, usn) -> (x, z, rot)
_POSICION = {}


def recordar_posicion(rid, usn, x, z, rot):
    """Guarda dónde estaba parado alguien. Hoy la única fuente es el `FFA8` de la campana."""
    if rid is None or not usn:
        return
    _POSICION[(rid, int(usn))] = (float(x), float(z), float(rot))


def s2c_sync_posiciones(entradas):
    """`FFF5 [u8 count] + count × [u8 slot][f32][f32][f32][u8 acción]`.

    ★★★ Es `CmdCurrentActionObject` — el nombre lo trae el cliente 2019. Su handler (`0x5DB900`)
      **vacía el mapa de posiciones, mete una entrada por cada uno y lo cierra**, o sea que es un
      «así están todos ahora», no un delta.
    ⏳ El orden de los tres floats y el byte del final salen del desensamblado, no de una captura.
    """
    _b = bytes([len(entradas) & 0xFF])
    for _slot, _x, _z, _rot in entradas:
        _b += (bytes([int(_slot) & 0xFF]) + struct.pack("<fff", _x, _z, _rot)
               + bytes([SYNC_POSICION_ACCION & 0xFF]))
    return _b


def sincronizar_posiciones(st, rid):
    """Le manda al que ENTRA las posiciones que conocemos de los que ya estaban.

    ⛔ anonimo03: *"el que entra no mira las posiciones pasadas de los usuarios hasta que se muevan …
      ve las campanas una encima de la otra"*. Y es exactamente eso: `0x444260` planta la campana
      en la posición **que el cliente tiene guardada para ese asiento**, y el que recién entró no
      tiene ninguna ⇒ `(0,0,0)` para todos ⇒ todas apiladas.

    ⚠ Hoy sólo sabemos la posición del que tocó una campana, porque su `FFA8` la trae. El resto
      de los jugadores **nunca nos dicen dónde están** (medido: de la sala sólo salen `FF00`
      vacío y `FF3D` de un byte). Así que esto arregla el apilado, no es un sync completo.
    """
    if not SYNC_POSICION_AL_ENTRAR or rid is None:
        return 0
    _yo = int(getattr(st, "usn", 0) or 0)
    _entradas = []
    for _slot, _u in (mesa_de(rid) or {}).items():
        if int(_u) == _yo:
            continue                      # su propia posición la sabe él, y mejor que nosotros
        _p = _POSICION.get((rid, int(_u)))
        if _p:
            _entradas.append((int(_slot), _p[0], _p[1], _p[2]))
    if not _entradas:
        return 0
    try:
        st.send_ff55(0xF5, s2c_sync_posiciones(_entradas),
                     name=f"FFF5 sync de {len(_entradas)} posición(es) de la sala {rid}")
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⚠ SYNC: no pude mandar las posiciones: {e!r}")
        return 0
    log("LOBBY", f"  ★★ SYNC: a usn={_yo} se le mandaron {len(_entradas)} posición(es) de la "
                 f"sala {rid} -> {_entradas}")
    return len(_entradas)


def reenviar_campanas(st, rid):
    """Le planta al que ENTRA las campanas que ya están sonando, **cada una en su lugar**.

    ⛔ anonimo03: *"el que entra a la sala no ve las campanas"*. Claro: el `plantar` se difundió una
      sola vez, cuando sonó, y el objeto **vive en el cliente**, no en el server.

    ⛔⛔ Y DESPUÉS: *"saqué a un usuario de la sala y al volver a entrar sólo se renderizó la
      campana de plata, mas no la de oro"*. Las dos se mandaban —está en el log— pero
      **quedaban una encima de la otra**: `0x444260` no usa las coordenadas del cable, plantа
      donde el cliente cree que está **ese asiento**, y las dos campanas eran del mismo jugador.
      Un solo asiento, una sola posición ⇒ las dos en el mismo punto, y la segunda tapa a la
      primera.
      ★ En vivo no pasaba porque entre una campana y la otra el jugador se movía de verdad.

    ⇒ EL TRUCO: el cliente lee el mapa **en el momento de plantar**. Así que antes de cada
      campana se le manda un `FFF5` que pone ese asiento **donde estaba cuando la tocó**, y
      recién ahí el `plantar`. Cada una cae en su lugar.
    ★ Y al final se le manda el sync de verdad, para que los avatares no queden donde los dejó
      la última campana.
    """
    _n = 0
    for _metal in ("oro", "plata"):
        _d = _PENDIENTE.get((rid, _metal))
        if not _d or not _d.get("spawn"):
            continue
        # ★ Primero MOVER, después PLANTAR. Al revés no sirve: la campana ya cayó.
        _pos = _d.get("pos")
        if SYNC_POSICION_AL_ENTRAR and _pos and _d.get("slot") is not None:
            try:
                st.send_ff55(0xF5, s2c_sync_posiciones([(_d["slot"], *_pos)]),
                             name=f"FFF5 donde estaba el que tocó la campana de {_metal}")
            except Exception as e:                                   # noqa: BLE001
                log("LOBBY", f"  ⚠ SYNC: no pude colocar el asiento de la campana: {e!r}")
        try:
            st.send_ff55(_d["cmd_spawn"], _d["spawn"],
                         name=f"FF{_d['cmd_spawn']:02X} re-planta la campana de {_metal} "
                              f"(entró a la sala {rid} con una ya sonando)")
            _n += 1
        except Exception as e:                                       # noqa: BLE001
            log("LOBBY", f"  ⚠ CAMPANA: no pude re-plantar para "
                         f"usn={getattr(st, 'usn', '?')}: {e!r}")
    if _n:
        log("LOBBY", f"  ★★ CAMPANA: a usn={getattr(st, 'usn', '?')} se le re-plantaron {_n} "
                     f"campana(s) al entrar a la sala {rid}")
        # ★★ Y SE DEJA EL MAPA COMO CORRESPONDE. Si esto no estuviera, los avatares quedarían
        #   parados donde se plantó la última campana.
        sincronizar_posiciones(st, rid)
    return _n


def campanas_para_ff13(rid):
    """`{"oro": (item, x, z, rot), "plata": (...)}` de las campanas que sonaron en la sala y no se cobraron.

    El item sale del propio `plantar` que se difundió (`[f32 x][f32 z][f32 rot][u32 item]…`), así el que
    entra ve exactamente la misma campana que vieron los que estaban.
    """
    out = {}
    for _metal in ("oro", "plata"):
        _d = _PENDIENTE.get((rid, _metal))
        if not _d or not _d.get("spawn") or not _d.get("pos"):
            continue
        _item = struct.unpack_from("<I", _d["spawn"], 12)[0]
        out[_metal] = (_item, *_d["pos"])
    return out


def campana_pendiente(rid, metal=None):
    """Lo que sonó en esa sala y todavía no se cobró. Sin `metal`, el dict de los dos."""
    if metal is not None:
        return _PENDIENTE.get((rid, metal))
    return {_m: _d for (_r, _m), _d in _PENDIENTE.items() if _r == rid}


def _gordo(metal, plus):
    """El premio gordo: `(monto, ...)` sorteado con pesos, o 0 si esa campana no lleva.

    ★★★ SÓLO LA «+» LO LLEVA. Dictado por anonimo03 de memoria del juego real: *"debemos distinguir
      entre campana de plata normal y la plata+, que **sólo ésta lleva el premio gordo**, y el
      premio gordo debe ir desde 25000 30000 35000 hasta 40000, siendo el drop rate más común
      25000 y el más raro 40000"*.
    ⚠ Eso **contradice** mi lectura de la descripción del ítem, que sólo habla de un techo que se
      duplica. No es que el archivo mienta: el archivo dice el TECHO, no el reparto. Del reparto
      no dice nada, y el que jugó sí se acuerda.
    """
    _tabla = CAMPANA_GORDO.get((metal, plus))
    if not _tabla:
        return 0
    _total = sum(_p for _m, _p in _tabla)
    _tiro = random.randint(1, _total)
    _acum = 0
    for _m, _p in _tabla:
        _acum += _p
        if _tiro <= _acum:
            return int(_m)
    return int(_tabla[-1][0])


def preparar_campana(rid, usns):
    """Sortea el reparto de las campanas de esa sala. Se llama UNA vez, al armar el cartel.

    ★★★★★ SE SORTEA ACÁ Y NO EN CADA FILA porque el **premio gordo es de UNO SOLO**, y para
      elegirlo hace falta saber quiénes jugaron. Si cada fila se sorteara sola no habría forma de
      que exactamente una se lo lleve.

    El reparto es el que dictó anonimo03:
      · **bono de consuelo** para todos los que jugaron (3000-4000 en la plata)
      · **premio gordo** para uno, y **sólo con la «+»** (25.000 / 30.000 / 35.000 / 40.000,
        de más común a más raro)

    ⚠ Idempotente: si ya se sorteó para esa sala, no vuelve a tirar. El cliente reintenta el
      `FF28` y un re-sorteo cambiaría el número entre la pantalla y el saldo.
    """
    _usns = [int(_u) for _u in usns if _u]
    for _metal in ("oro", "plata"):
        _d = _PENDIENTE.get((rid, _metal))
        if not _d or _d["rolls"] or not _usns:
            continue
        # ★ Valores CERRADOS: se elige uno de la lista, no un número dentro de una banda.
        #   anonimo03: *"usá cerrados 2500 3000 3500 4000, no uses valores como 2534 3152"*.
        # ★ Las de modelo propio (`CAMPANA_PROPIAS`) pagan × su factor: el consuelo y el gordo, con el techo ya
        #   multiplicado al tocarla.
        _factor = float(_d.get("factor") or 1)
        _tabla = tuple(int(_v * _factor) for _v in (CAMPANA_BONO_BASE.get((_metal, _d["plus"])) or (0,)))
        _techo = int(_d["techo"] or 0)
        _d["rolls"] = {_u: min(int(random.choice(_tabla)), _techo) for _u in _usns}
        # ★★★★★ EL PREMIO GORDO ES DEL QUE TOCÓ LA CAMPANA. Dictado por anonimo03, sin vueltas:
        #   *"el premio mayor se lo llevará el que toca la campana, los valores altos; los demás
        #   sí, entre los valores bajos"*.
        #   ⇒ No es un sorteo entre todos: el que puso el ítem se lleva el premio grande. Lo que
        #     se sortea es CUÁNTO (25.000 el más común, 40.000 el más raro).
        #   ⚠ Si el que la tocó NO jugó (por ejemplo un espectador, que el texto 642 permite), el
        #     gordo **no se reparte a otro**: no hay a quién dárselo, y regalárselo al de al lado
        #     sería inventar una regla.
        _dueno = int(_d.get("usn") or 0)
        _g = int(_gordo(_metal, _d["plus"]) * _factor) if _dueno in _d["rolls"] else 0
        if _g:
            _d["ganador"] = _dueno
            _d["gordo"] = min(_g, _techo)
            _d["rolls"][_dueno] = _d["gordo"]
        log("LOBBY", f"  🎲 CAMPANA de {_metal}{'+' if _d['plus'] else ''}: consuelo "
                     f"{_tabla} para {len(_usns)} · gordo "
                     + (f"{_d.get('gordo')} para {_d['quien']!r} (usn={_dueno}), que fue quien "
                        f"la tocó" if _g
                        else ("SIN gordo (esta campana no lleva)" if not CAMPANA_GORDO.get(
                            (_metal, _d["plus"]))
                            else f"SIN gordo: el que la tocó (usn={_dueno}) no jugó")))


def bono_de_campana(rid, fila):
    """Los renglones de bonus de campana para ESA fila del cartel: `[(bonustype, valor), …]`.

    ★★★★★ ES UN RENGLÓN DEL CARTEL, no un paquete suelto. Lo dijo anonimo03 viendo que el bono no
      llegaba: *"es un bonus como el de pareja, o como el de joya de amistad, pero ligado a la
      presencia del ítem en la sala"*. Y el nombre estaba esperando en `rnr_script/bonus.xml`:

          <bonus bonustype="67" type="3" … comment="플래티넘벨">     = «Platinum Bell»

    ★★ El `type="3"` de esa tabla es **Rpoint** (el encabezado del archivo dice
      `1-알코인, 3-알포인트`), o sea lo mismo que promete la descripción del ítem. Dos archivos
      distintos del cliente, la misma respuesta.

    ⚠ Sólo LEE lo que sorteó `preparar_campana`. El que se dibuja y el que se paga tienen que ser
      el mismo número; re-sortear acá los separaría.
    ⚠ No lo cobra el que no llegó (`fallo`): premiar al que abandonó sería regalarlo por sentarse
      al lado. Misma regla que el bono de pareja y el del alma.
    ⏳ El de ORO no tiene bonustype conocido (`bonus.xml` no trae ninguno con «골든벨»), así que
      no genera renglón. Inventarle un número sería peor: uno que no está en la tabla el cliente
      lo ignora con un warning.
    """
    _usn = fila.get("usn")
    if not _usn or fila.get("fallo"):
        return []
    _fuera = []
    for _metal in ("oro", "plata"):
        _d = _PENDIENTE.get((rid, _metal))
        if not _d:
            continue
        _monto = _d["rolls"].get(int(_usn))
        _bt = CAMPANA_BONUSTYPE.get(_metal)
        if _bt and _monto:
            _fuera.append((int(_bt), min(int(_monto), 0xFFFF)))
    return _fuera


def cerrar_campana(rid, usns):
    """Terminó la partida: anuncia **al afortunado** y borra las campanas pendientes.

    ★★★★★ UN SOLO AVISO, EL DEL QUE MÁS SACÓ. anonimo03: *"el bono que se anuncia en el cartel es el
      del **afortunado**, no el de todos"*, y *"el cartel se está repitiendo 2 veces"* — era eso:
      mandábamos un aviso por cada jugador.

    ⚠⚠ **ACÁ NO SE ACREDITA NADA.** El bono se paga por el renglón del cartel, en el mismo bucle
      que la exp y el rcoin. Acreditar en dos lugares es exactamente cómo se separan la pantalla
      y el saldo — la lección que este repo ya pagó con la exp y con el rcoin.

    ⚠ Se saca del diccionario ANTES de mandar nada: el cliente reintenta el `FF28` y sin esto el
      aviso saldría de nuevo en cada reintento.
    """
    _n = 0
    for _metal in ("oro", "plata"):
        _d = _PENDIENTE.pop((rid, _metal), None)
        if not _d:
            continue
        # ★ El afortunado sale de los MISMOS números que se dibujaron en el cartel.
        _rolls = {int(_u): _v for _u, _v in _d["rolls"].items()
                  if int(_u) in {int(x) for x in usns if x}}
        if not _rolls:
            continue
        # ★ El que se anuncia es **el del premio gordo** si esa campana lo lleva; si no, el que
        #   más sacó del consuelo. anonimo03: *"el bono que se anuncia es el del afortunado"*.
        # ★★★★★ SÓLO LA «+» SACA EL CARTEL DEL BONO. anonimo03, aclarando: *"con los anuncios me
        #   refería a los anuncios de BONOS AL TERMINAR LA PARTIDA, no a los anuncios iniciales
        #   de campanas tocadas — esos no tenían que quedar tapados"*.
        #   ⇒ La normal reparte igual (el renglón del cartel de resultado se dibuja y se paga),
        #     pero no saca el cartel del ganador: ése es del premio gordo, y sólo la «+» lo tiene.
        if CAMPANA_SOLO_PLUS_ANUNCIA and not _d["plus"]:
            log("LOBBY", f"  ★ CAMPANA de {_metal} (normal) en la sala {rid}: reparto "
                         f"{_rolls} · SIN cartel (sólo anuncian las «+»)")
            _n += 1
            continue
        _ganador = _d.get("ganador") if _d.get("ganador") in _rolls else max(
            _rolls, key=lambda _u: _rolls[_u])
        _monto = _rolls[_ganador]
        _nick = str((db_get_char(_ganador) or {}).get("nick", "") or "?")
        _pk = s2c_cobro_campana(_nick, _monto)
        _cmd = CMDS_POR_METAL[_metal][2]
        # ★★★★★ EL CARTEL DEL COBRO VA A TODO EL SERVER, igual que el de «fulano tocó la
        #   campana». anonimo03, probándolo: *"el cartel del pago de campana de oro+ no se está
        #   anunciando globalmente"*.
        #   ⛔ Estaba con `conexiones_en_sala(rid)`, o sea que el premio gordo sólo lo veía la
        #     gente que ya estaba adentro — justo los que no hace falta convencer. El cartel de
        #     «tocó la campana» ya iba global desde que anonimo03 lo pidió (*"abrí un tercer cliente
        #     en la lista de salas, el anuncio debería ser global, éste no lo vio"*), y este otro
        #     se quedó atrás.
        #   ★ Y tiene el mismo sentido que aquél: un premio de 25.000 que nadie fuera de la sala
        #     ve no vende la campana. Es el aviso que hace que otro la compre.
        _gc = 0
        for _c in list(CONEXIONES.values()):
            if _c is None or getattr(_c, "cerrado", False):
                continue
            try:
                _c.send_ff55(_cmd, _pk,
                             name=f"FF{_cmd:02X} cartel GLOBAL del afortunado: {_nick!r} "
                                  f"+{_monto} {CAMPANA_MONEDA.get(_metal)}")
                _gc += 1
            except Exception as e:                                   # noqa: BLE001
                log("LOBBY", f"  ⚠ CAMPANA: no pude mandar el aviso del afortunado a "
                             f"usn={getattr(_c, 'usn', '?')}: {e!r}")
        _n += 1
        log("LOBBY", f"  ★★★ CAMPANA de {_metal}{'+' if _d['plus'] else ''}: la tocó "
                     f"{_d['quien']!r} en la sala {rid} · "
                     f"techo {_d['techo']} · gordo {_d.get('gordo', 0)} · reparto "
                     f"{_rolls} -> AFORTUNADO {_nick!r} "
                     f"con {_monto} {CAMPANA_MONEDA.get(_metal)} · cartel a {_gc} (GLOBAL)")
    # ★★ Y SE APAGA LA MARCA DE LA LISTA. `_PENDIENTE` ya se vació con el `pop` de arriba, así
    #   que el `J`/`K` de la fila vuelve a 0 solo; sólo falta empujar la lista para que se vea.
    #   ⛔ SÓLO SI DE VERDAD SE CERRÓ ALGO. Lo cazó `probar_campana.py`: el cliente reintenta el
    #     `FF28`, así que `cerrar_campana` se llama de nuevo con nada que cerrar — y difundir ahí
    #     era mandarle la lista entera a TODO el server por cada reintento, gratis.
    if _n:
        try:
            difundir_roomlist()
        except Exception as e:                                           # noqa: BLE001
            log("LOBBY", f"  ⚠ CAMPANA: no pude refrescar la lista al cerrar: {e!r}")

    return _n


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# El cartel (S2C)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def s2c_spawn_campana(item, slot, x=0.0, z=0.0, rot=0.0, extra=0):
    """`FFA9`/`FFC3` — **planta la campana en la sala**. 21 bytes.

        [f32 x][f32 z][f32 rot][u32 itemcode][u8 slot][u32 extra]

    ★ El `slot` es lo que importa: `0x444260` NO usa las coordenadas del paquete —
      las lee él, del jugador de ese asiento (`0x595070(&pos, slot, &rot)`, la misma llamada
      que usa el emisor `0x443BC0`). O sea que la campana aparece **donde está parado el que la
      tocó**, y las coordenadas del cable son informativas.
    ⏳ El `extra` del final va a un global (`[0x9314C0+0x13038]`) y **no sabemos qué es**.
      Arranca en 0 y la sonda lo barre.
    """
    return (struct.pack("<fff", float(x), float(z), float(rot))
            + struct.pack("<I", int(item) & 0xFFFFFFFF)
            + bytes([int(slot) & 0xFF])
            + struct.pack("<I", int(extra) & 0xFFFFFFFF))


def s2c_cartel_campana(item, quien, rid):
    """`FFAA`/`FFC4` (`Cmd…BellNotifer`) — el cartel «¡La Campana!».

        [u16 sala][u8 len]<quién>[u32 itemcode]

    ★ Acá está **el número de sala que salía mal**: el cliente lo enmascara con `& 0x7FF`
      (`0x5DD322`) y lo mete en el `%d` del texto 641 («…en la sala %d»). El `itemcode` elige el
      nombre del ítem para el segundo `%s`.
    """
    _q = str(quien).encode("cp1252", "replace")[:30]
    return (struct.pack("<H", int(rid or 0) & 0xFFFF)
            + bytes([len(_q)]) + _q
            + struct.pack("<I", int(item) & 0xFFFFFFFF))


def s2c_cobro_campana(quien, rcoin):
    """`FFB4`/`FFC5` (`Cmd…BellHit`) — «%s ha recibido %d de RCoin» (texto 570 / 643).

        [u8 len]<quién>[u16 rcoin]

    ⚠ El itemcode **no viaja**: el cliente lo tiene cableado en el handler —`push 0xB5` (181,
      oro) en `0x5D7A46` y `push 0x129` (297, plata) en `0x5DD3A6`. Por eso hay un comando por
      metal en vez de un campo.
    """
    _q = str(quien).encode("cp1252", "replace")[:30]
    return bytes([len(_q)]) + _q + struct.pack("<H", int(rcoin) & 0xFFFF)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# El handler
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def h_ffa8_campana(st, cmd, data):
    """`FFA8 [u32 item][f32 x][f32 z][f32 rot]` — alguien hizo sonar una campana."""
    usn = int(getattr(st, "usn", 0) or 0)
    try:
        _item = struct.unpack("<I", data[0:4])[0]
        _x, _z, _rot = struct.unpack("<fff", data[4:16])
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⚠ CAMPANA: no pude leer el pedido ({e!r}) raw={data.hex(' ')}")
        return

    _rid = getattr(st, "room_id", None)
    _nick = str((db_get_char(usn) or {}).get("nick", "") or "?")
    log("LOBBY", f"  ★★ FFA8: usn={usn} {_nick!r} item={_item} en ({_x:.1f}, {_z:.1f}) "
                 f"rot={_rot:.4f} sala={_rid}")

    # ★★ EL MISMO `FFA8` LO USA LA LLAVE DE MI SALA. El handler de RECEPCIÓN del cliente
    #   (`0x5D6880`) sólo reacciona si el `u32` vale `0x23C` = 572 «Mi Sala Llave de repuesto»,
    #   y el emisor `0x5DD680` manda ese mismo ítem con un nick detrás. O sea que `FFA8` no es
    #   «la campana»: es «usé este ítem», y el ítem decide. Si no es campana, no es nuestro.
    if _item not in CAMPANAS:
        log("LOBBY", f"  ⚠ FFA8 con el ítem {_item}, que NO es una campana "
                     f"(la llave de Mi Sala viaja por acá también) -> sin handler todavía")
        return

    _metal, _plus = CAMPANAS[_item]
    _nombre = f"campana de {_metal}{'+' if _plus else ''}"

    if not CAMPANA_ACTIVA:
        log("LOBBY", "  ⚠ CAMPANA apagada por perilla (CAMPANA_ACTIVA) -> no se difunde")
        return

    # ⚠ «Sólo puede usarse en la sala de juego» (texto 640) lo comprueba el cliente: desde el
    #   lobby ni manda el paquete. Lo repetimos igual porque una regla que sólo vive en el
    #   cliente no es una regla — es una sugerencia para el que no lo modificó.
    if _rid is None or _rid == SALA_VESTIBULO:
        log("LOBBY", f"  ⛔ CAMPANA: usn={usn} la tocó FUERA de una sala (room_id={_rid}) "
                     f"-> no se difunde (¿cliente modificado?)")
        return

    # ⚠ El candado es POR METAL. anonimo03: *"debería poder tocar 1 de plata y 1 de oro, pero sólo me
    #   deja tocar 1 a la vez"*. Son dos ítems distintos, con dos bonos distintos y hasta con
    #   monedas distintas (Rcoin el oro, Rpoint la plata): el candado de uno no es el del otro.
    if CAMPANA_UNA_POR_SALA and campana_sonada(_rid, _metal):
        # ★ El cliente tiene el texto 639 para esto, pero no hay paquete conocido que se lo haga
        #   decir: el 639 está fuera del rango del `FF68` (255..510). Así que se lo decimos por
        #   el chat, que es la salida que ya existe y no inventa nada.
        avisar_a_uno(st, f"Ya sonó una campana de {_metal} en esta sala. "
                         f"Se puede volver a tocar después de jugar una canción.")
        log("LOBBY", f"  ⛔ CAMPANA: usn={usn} quiso tocar la {_nombre} pero en la sala {_rid} "
                     f"ya sonó una de {_metal} -> se le avisa y NO se le cobra")
        return

    # ★★ SE COBRA EL ÍTEM, Y EL RESULTADO DE COBRARLO ES LA AUTORIZACIÓN.
    #   Misma nota que el megáfono y que el gacha: `db_del_inventory` devuelve `False` si no lo
    #   tenía, así que mirar y gastar es **una sola operación** y no hay ventana entre las dos.
    if not db_del_inventory(usn, _item):
        # ★★ Y SE LE DICE. Antes rebotaba en silencio: el jugador clickeaba y no pasaba nada.
        #   No es un cliente modificado, es lo NORMAL: el ícono del panel «Mi Acción» no se
        #   repinta cuando el ítem se agota (sí se va al reabrir el juego), así que sigue ahí
        #   invitando a que lo toquen. anonimo03: *"hay muchos usuarios que intentan tocar sin
        #   cargas... los usuarios mayormente usan ese panel"*.
        #   ⏳ Lo que falta para que el ícono se vaya solo: el paquete que refresca ESE panel.
        #     El `FF3E` limpia el inventario pero no el panel; el candidato es el `FF73`
        #     (CmdInventorySet, 4 sub-tipos sin medir). Hasta entonces, avisar es la cura.
        avisar_a_uno(st, f"No te quedan cargas de la {_nombre}. "
                         f"Se compra en la tienda, y el ícono se actualiza al volver a entrar.")
        log("LOBBY", f"  ⛔ CAMPANA: usn={usn} pidió usar el ítem {_item} y NO LO TIENE "
                     f"-> no se difunde nada, y se le avisa por chat")
        return

    if CAMPANA_UNA_POR_SALA:
        _SONADA.add((_rid, _metal))

    # ★ Y SE ANOTA DÓNDE ESTABA PARADO. Es el único dato de posición que el cliente nos da, y es
    #   justo el que hace falta para que al que entre después no se le apilen las campanas.
    recordar_posicion(_rid, usn, _x, _z, _rot)

    # ★★★ Y SE LE AVISA CUÁNTAS LE QUEDAN. El inventario se manda al loguear y nunca más, así que
    #   sin esto el ícono se queda con el número viejo. Es la regla que ya nos costó dos veces:
    #   **el cliente dibuja las cantidades desde el `FF69`, no desde el MyRecord.**
    _avisar_cuantas_quedan(st, usn, _item, _nombre)

    # ═══ la difusión: PLANTAR + CARTEL. El bono NO se paga todavía ═══
    # ★★★★★ EL BONO SE PAGA **AL TERMINAR LA PARTIDA**, y lo dice el propio ítem:
    #     «Si hace sonar la campana de plata **y comienza el juego**, todos reciben bonus…»
    #   Lo vio anonimo03 antes que yo: *"el cartel de quién recibió el bono salió antes; éste recién
    #   debe salir al final de la partida"*. Acá sólo queda **anotada** la campana, y quien paga
    #   es `pagar_campana()`, llamada desde el cartel de resultado (`FF28`).
    #   ⇒ Así el que entra a la sala DESPUÉS de que sonó la campana pero ANTES de jugar también
    #     cobra, que es lo que dice el texto («todos los usuarios en la sala»), y el que se va
    #     antes de jugar no.
    #
    # ★★ Los nombres de los comandos salieron del CLIENTE 2019 (`taller/_analisis/reg19b.json`):
    #     FFA9 CmdGoldenBell / FFC3 CmdPlatinumBell             plantar la campana
    #     FFAA/FFC4 Cmd…BellNotifer                             el cartel
    #     FFB4/FFC5 Cmd…BellHit                                 «fulano cobró N»  -> al final
    #   y de paso confirmó que el `FFA8` que recibimos se llama **`CmdUse`**.
    # ★★ Las de modelo propio (`CAMPANA_PROPIAS`, 05-nov) van con SU código: el cliente elige la malla y el
    #   fondo del cartel por el código, y con el canónico saldría la campana vieja.
    _factor = CAMPANA_PROPIAS.get(_item)
    _canon = _item if _factor else _ITEM_CANONICO[(_metal, _plus)]
    # ⏳ El cartel puede querer el código BASE en vez del «+»: el cliente, en su propio `Hit`,
    #   cablea siempre el base (`push 0xB5`=181, `push 0x129`=297) y nunca el «+». El dibujo sí
    #   entiende el «+» (notice.xml lo indexa), pero el TEXTO salía como «Campana de Oro».
    _canon_cartel = _item if _factor else (_ITEM_CANONICO[(_metal, False)] if CAMPANA_CARTEL_BASE else _canon)
    _cmd_spawn, _cmd_cartel, _cmd_cobro = CMDS_POR_METAL[_metal]
    _slot = _slot_en_sala(_rid, usn)

    _pk_spawn = s2c_spawn_campana(_canon, _slot, _x, _z, _rot, CAMPANA_SPAWN_EXTRA)
    _pk_cartel = s2c_cartel_campana(_canon_cartel, _nick, _rid)

    # ★ PLANTAR va sólo a la SALA: es un objeto que aparece en ese escenario.
    _n = 0
    for _c in conexiones_en_sala(_rid):
        if _c is None:
            continue
        try:
            _c.send_ff55(_cmd_spawn, _pk_spawn,
                         name=f"FF{_cmd_spawn:02X} planta la {_nombre} (slot {_slot})")
            _n += 1
        except Exception as e:                                       # noqa: BLE001
            log("LOBBY", f"  ⚠ CAMPANA: no pude plantarla para "
                         f"usn={getattr(_c, 'usn', '?')}: {e!r}")

    # ★★★★★ EL CARTEL VA A **TODO EL SERVER**. anonimo03: *"abrí un tercer cliente en la lista de
    #   salas, el anuncio debería ser global, éste no lo vio"*. Y el propio texto del cliente lo
    #   estaba diciendo desde el principio: *«%s ha hecho sonar %s **en la sala %d**»* — nombrar
    #   la sala sólo tiene sentido si lo lee gente que NO está en ella.
    # ★★★ …y el cartel de «fulano hizo sonar la campana» va SIEMPRE, sea normal o «+».
    #   ⛔ Estuvo apagado para las normales durante un commit, por leerle mal la corrección a
    #     anonimo03: cuando dijo *"sólo las campanas+ se anuncian con cartel"* hablaba **del aviso
    #     del BONO, al terminar la partida**, no de éste. Él mismo lo aclaró: *"esos no tenían
    #     que quedar tapados"*.
    #   ⇒ Tocar una campana se anuncia siempre. Lo que distingue a la «+» es el premio gordo y
    #     el cartel del ganador, que está más abajo en `cerrar_campana`.
    _g = 0
    _anuncia = True
    for _c in list(CONEXIONES.values()):
        if _c is None or getattr(_c, "cerrado", False):
            continue
        try:
            _c.send_ff55(_cmd_cartel, _pk_cartel,
                         name=f"FF{_cmd_cartel:02X} cartel GLOBAL: {_nick!r} tocó la "
                              f"{_nombre} en la sala {_rid}")
            _g += 1
        except Exception as e:                                       # noqa: BLE001
            log("LOBBY", f"  ⚠ CAMPANA: no pude anunciar a "
                         f"usn={getattr(_c, 'usn', '?')}: {e!r}")

    _techo = int(int(CAMPANA_BONO.get((_metal, _plus), 0) or 0) * (_factor or 1))
    _PENDIENTE[(_rid, _metal)] = {"plus": _plus, "canon": _canon, "quien": _nick, "usn": usn,
                                  "techo": _techo, "rolls": {}, "factor": _factor or 1,
                                  "spawn": _pk_spawn, "cmd_spawn": _cmd_spawn,
                                  # ★ DÓNDE se tocó ESTA campana. Dos campanas del mismo jugador
                                  #   salen del mismo asiento; sin guardar la posición de cada
                                  #   una, al re-plantarlas caen las dos en el mismo punto.
                                  "slot": _slot, "pos": (_x, _z, _rot)}

    # ★★ Y SE REFRESCA LA LISTA DE SALAS, para que la sala salga marcada. El itemcode viaja en el
    #   `J` (oro) / `K` (plata) de la fila del `FF6E` — ver `salas._marcar_campana_en_la_lista`,
    #   que trae la medición. Sin este empuje la marca recién se vería cuando alguien refresque.
    try:
        difundir_roomlist()
    except Exception as e:                                               # noqa: BLE001
        log("LOBBY", f"  ⚠ CAMPANA: no pude refrescar la lista de salas: {e!r}")

    log("LOBBY", f"  ★★★ CAMPANA: {_nick!r} hizo sonar la {_nombre} (ítem {_item}) en la sala "
                 f"{_rid} -> plantada para {_n} · "
                 + (f"anunciada a {_g} (GLOBAL) · " if _anuncia
                    else "SIN anuncio (sólo anuncian las «+») · ")
                 + f"sorteo de hasta {_techo} {CAMPANA_MONEDA.get(_metal)} "
                   f"al terminar la partida")


def _avisar_cuantas_quedan(st, usn, item, nombre):
    """UN `FF6A` de cuatro bytes, y nada más. Es el mecanismo del propio juego.

    ★★★★★ `FF6A` (`CmdDecreaseItemCount`, `[u32 item]`) -> handler `0x5D0F30` -> `0x48FDA0`:

        0x48FE4F  add word [rec+6], 0xFFFF          ; una carga menos
        0x48FE57  test ax,ax / jne                  ; si quedan, sólo repinta
        0x48FE69  call 0x48B440                     ; llegó a 0 -> BORRA la fila del inventario
        0x48FE75  call 0x48E830(item, 0)            ; y de la lista de acción
        0x48FE7F  [0x9314CC]+0xAFFC -> vtbl[0x44]() ; repinta el panel de LA ESCENA ACTUAL

      Eso es, literal, lo que pidió anonimo03: *"en el juego original el ítem aparecía en el
      inventario sólo al tener cargas; al terminarse desaparecía hasta volverse a comprar"*.

    ⛔⛔ LO QUE HABÍA ACÁ ERA EL BUG, no la cura. Se mandaba `FF6A` **y después un `FF69`**, y el
      `FF69` (`0x48F350`) **borra la fila y la vuelve a crear** (`0x48B440` + push_back) con el
      count que le pasamos. Al llegar a cero eso **resucitaba el ítem con 0 cargas** — y el
      cliente lee un 0 como 1 (`0x5ED3D9`), así que quedaba dibujado y clickeable.
      ⇒ El "ítem fantasma" que reaparecía al entrar a una sala **lo mandábamos nosotros**. No era
        el `FF1C`, ni el MyRecord, ni la base (ahí la fila ya estaba borrada).

    ⚠ Y por eso parecía que *"el FF69 solo no redibuja nada"*: su repintado usa
      `mov ecx,[0x9314C4]` = **cLobby, clavado**. En una sala repinta el panel del LOBBY. El
      `FF6A` y el `FF3E` usan la escena actual. **El `FF69` es un paquete de lobby.**

    ⚠ No hace falta mandar el rcoin acá: usar una campana **no gasta rcoin**. El bono lo paga
      `pagar_campana()` al terminar la partida, por otro camino.
    ⏳ El megáfono y el gacha tienen el MISMO fantasma por la misma causa. Sin tocar.
    """
    try:
        _quedan = inv_cant(db_get_char(usn) or {}).get(item, 0)
        if CAMPANA_DESCUENTA_EN_PANTALLA:
            st.send_ff55(0x6A, struct.pack("<I", item & 0xFFFFFFFF),
                         name=f"FF6A CmdDecreaseItemCount item={item} "
                              f"(el cliente lo baja a {_quedan}" +
                              (" y lo DESLISTA)" if _quedan <= 0 else ")"))
        log("LOBBY", f"  ★ CAMPANA: a usn={usn} le quedan {_quedan} del ítem {item}"
                     + (" -> el cliente lo deslista solo" if _quedan <= 0 else ""))
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⚠ CAMPANA: no pude avisar cuántas quedan: {e!r}")
