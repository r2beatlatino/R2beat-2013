# -*- coding: utf-8 -*-
"""lobby_carrera — la partida: cargar, correr, el gorila y el cartel de resultado.

Cada función es UNA rama del `handle_inner` original, movida tal cual.
El orden y las condiciones viven en `despacho.py`.
"""
import os
import random
import re
import struct
import threading
from . import notas

from .ajustes import (
    FF80_CUPONES_DE_PARTIDA,
    CAMPANA_BONUSTYPE,
    CAMPANA_MONEDA,
    CHASE_CAJA_PREMIOS,
    CHASE_GORILA_CAJAS,
    CHASE_EXPERIMENTAL,
    CHASE_EXP_ACERCA_AL_MEJOR,
    CHASE_EXP_DERROTA,
    CHASE_EXP_DESCUENTO,
    BONO_POR_JUGADORES,
    CHASE_EXP_MULT,
    CHASE_MAP,
    CHASE_MAP_FIJO,
    CHASE_NPC_APORTES,
    CHASE_NPC_AVANCE,
    CHASE_PRIMERO_EL_QUE_ACTIVA,
    CHASE_NPC_CAJAS,
    CHASE_NPC_CARTEL,
    CHASE_NPC_COMBO,
    CHASE_NPC_PD,
    CHASE_NPC_PUNTAJES,
    CHASE_NPC_RITMO,
    CHASE_NPC_REALISTA,
    CHASE_RELLENO,
    CHASE_RELLENO_ACIERTOS,
    CHASE_RELLENO_PUNTAJE,
    CHASE_RELLENO_PUNTAJE_OK,
    CHASE_RELLENO_SLOTS,
    CHASE_RONDAS,
    COOP_EFECTOS_AYUDA,
    COOP_EFECTO_IMPULSOR,
    COOP_NOMBRES_EFECTO,
    FF28_BASECOIN,
    RANK_BONUS_POR_PUESTO,
    RATE_MAX,
    RATE_MIN,
    rate_de,
    FF28_C2S_OFF_MILESIMAS,
    PRECISION_MILESIMAS_FORZADAS,
    PRECISION_MILESIMAS,
    ALMA_BONO_NIVEL_MAX,
    MASCOTA_GORILA_BONO,
    ALMA_BONO_RCOIN,
    ALMA_BONO_TIPO_BASE,
    PAREJA_BONO_EXP,
    PAREJA_BONO_RCOIN,
    PAREJA_BONO_TIPO_EXP,
    PAREJA_BONO_TIPO_RCOIN,
    COOP_MIN_JUGADORES,
    COOP_MIN_SOLO_AVISAR,
    CHASE_USAR_MAP_FIJO,
    DEFAULT_ROOM_MAP,
    DEFAULT_ROOM_SONG,
    FF10F_ESPERA,
    FF139_SENTINEL,
    FF23_SLOT_AL_FRENTE,
    FF25_SENTINEL,
    FF27_AL_PRIMER_FINALISTA,
    FF25_ESPERA_MAX,
    FF28_ESPERA_MAX,
    FF27_PEDIR_RESULTADO,
    FF10E_DERROTA_OP3,
    FF63_PROBE,
    FF63_RESPONDER,
    HOST_SLOT,
    MODE_EQUIPO,
    MODE_RELEVO,
    DOCE_GANA_CON,
    FF36_COMPOSICION,
    FF36_FALTAN_USUARIOS,
    FF36_RELEVO_1V1,
    JEFE_MIN_POR_EQUIPO,
    GORILA_TOPE_APERTURA,
    JEFE_SORTEAR_CAPITAN,
    FF68_BASE,
    EXP_MULT_GANADOR,
    EXP_MULT_PERDEDOR,
    RANK_BONUS_GANADOR,
    RANK_BONUS_PERDEDOR,
    RELEVO_MIN_POR_EQUIPO,
)
from .registro import (
    RESUMIR,
    hx,
    log,
)
from .basedatos import (
    db_add_exp,
    db_add_rcoin,
    db_almas_de,
    db_pareja_de,
    db_get_rcoin,
    db_get_char,
    db_load,
    db_save,
    db_save_uno,
)
from .paquetes import (
    build_ff28_multi,
    build_ff63,
    leer_ff63_pedido,
)
from .salas import (
    CARRERAS,
    asientos_de_la_sala,
    dificultad_de,
    marcar_en_juego,
    CONEXIONES,
    MARCADOR,
    _mesa_lock,
    capitanes_de,
    difundir_capitanes,
    equipo_de,
    grande_de,
    mapa_de_sala,
    pd_valofe_de,
    cola_ff25_jugador,
    pista_propia_de,
    pista_de_carrera,
    pista_coop_de_sala,
    poner_eleccion,
    anfitrion_de,
    rate_sala_de,
    poner_mapa_sala,
    espectadores_de,
    mesa_de,
    npcs_de,
    poner_seleccion,
    seleccion_de,
    slots_npc,
    marcar_sorteo_al_volver,
    reparar_capitanes,
)
from .lobby_salas import (
    difundir_roominfo,
    enviar_roominfo,
)
from .myrecord import enviar_ff69_moneda_gorila
from .carrera import (
    anotar_avance,
    avance_de,
    olvidar_avance,
    asegurar_canciones_chase,
    cuentas_del_cartel,
    efectos_de,
    olvidar_efectos,
    build_ff28_fila,
    grado_de,
    reiniciar_impulsor,
)


# ★ Los bonustypes de campana que este módulo tiene que ACREDITAR como Rpoint. Sale de
#   `ajustes.CAMPANA_BONUSTYPE` y no se escribe a mano: si mañana aparece el del oro, se agrega
#   allá y acá no hay que tocar nada. (Dos listas de lo mismo es como se despegan.)
# ★ Los de campana que se acreditan como EXPERIENCIA. El «Rpoint» del juego ES la exp (ver la
#   nota del 2026-09-10 unas líneas más abajo), así que el `type="3"` de `bonus.xml` —알포인트—
#   se paga con `db_add_exp`, no con la columna muerta `rpoint`.
_BONUSTYPES_CAMPANA = {int(_t) for _m, _t in CAMPANA_BONUSTYPE.items()
                       if _t and CAMPANA_MONEDA.get(_m) == "exp"}
# ★★ Y el del ORO paga RCOIN, no Rpoint: su entrada de `bonus.xml` es `type="1"` (알코인).
#   Por eso son dos conjuntos y no uno — el renglón se dibuja igual en los dos casos, pero el
#   bolsillo al que va es distinto.
_BONUSTYPES_CAMPANA_RCOIN = {int(_t) for _m, _t in CAMPANA_BONUSTYPE.items()
                             if _t and CAMPANA_MONEDA.get(_m) == "rcoin"}


def _bono_heroe(fila):
    """Los renglones del MODO HÉROE de esa fila: uno por modo activado. Ver `BONO_HEROE`.

    ⚠ No lo cobra el que no llegó (`fallo`), igual que los otros bonos: el modo es un desafío, y el
      premio es por haberlo corrido entero.
    """
    from .ajustes import BONO_HEROE, BONO_HEROE_PD_MIN
    _usn = fila.get("usn")
    if not _usn or fila.get("fallo") or not BONO_HEROE:
        return []
    try:
        _partes = (db_get_char(int(_usn)) or {}).get("parts") or []
    except Exception:                                            # noqa: BLE001
        return []
    _b = []
    for _it in _partes:
        try:
            _t, _v = BONO_HEROE.get(int(_it), (None, 0))
        except (TypeError, ValueError):
            continue
        if not _t or _v <= 0:
            continue
        if int(fila.get("pd") or 0) < int(BONO_HEROE_PD_MIN.get(int(_it), 0)):
            continue
        _b.append((_t, min(int(_v), 0xFFFF)))
    if _b:
        log("LOBBY", f"  🦸 BONO MODO HÉROE: usn={_usn} -> {_b} (pd={fila.get('pd')})")
    return _b


def _profecia_cumplida(que, fila, puesto, ctx):
    """¿Se cumplió lo que profetizaba? Devuelve la «unidad» del monto (rivales o nivel), o `None`.

    `ctx` = `{"coop", "jugadores", "cancion"}` de la carrera (lo arma el cartel, una vez).
    """
    from .ajustes import PROFECIA_GANADOR_MIN_JUGADORES, PROFECIA_NIVEL_TOPE, PROFECIA_PD_MIN
    if que == "primero":
        _n = int(ctx.get("jugadores") or 0)
        if puesto == 1 and _n >= PROFECIA_GANADOR_MIN_JUGADORES:
            return _n - 1
        return None
    _nivel = min(int(notas.nivel_de(ctx.get("cancion"), 1) or 1), PROFECIA_NIVEL_TOPE)   # 13★ paga como 10★
    if que == "97":
        return _nivel if int(fila.get("pd") or 0) >= PROFECIA_PD_MIN else None
    if que == "allcombo":
        # ★ allcombo = el combo del reporte llega al TOTAL del chart que servimos (contado como
        #   el exe). ⚠ Sin total conocido no se paga: mejor no pagar que regalar.
        _tot = notas.combo_total_de(ctx.get("cancion")) if ctx.get("cancion") else None
        return _nivel if (_tot and int(fila.get("combo") or 0) >= _tot) else None
    return None


def _bono_profecia(fila, puesto, ctx):
    """Los renglones de las PROFECÍAS de esa fila: EXP y Rcoin por cada una cumplida. Ver `PROFECIAS`.

    ★ El renglón de EXP (59/61/63) es además el que el cliente busca en su fila para FESTEJAR
      (`0x4FF830`): se manda sólo si se cumplió, y nunca en 0 (un ícono con «+0» y un festejo falso).
    ⚠ No cobra el que no llegó (`fallo`), y en cooperativo no aplica (lo dice el texto del ítem).
    """
    from .ajustes import PROFECIA_MONTO, PROFECIAS
    _usn = fila.get("usn")
    if not _usn or fila.get("fallo") or not PROFECIAS or ctx.get("coop"):
        return []
    try:
        _partes = (db_get_char(int(_usn)) or {}).get("parts") or []
    except Exception:                                            # noqa: BLE001
        return []
    _b = []
    for _it in _partes:
        try:
            _que, _te, _tr = PROFECIAS.get(int(_it), (None, 0, 0))
        except (TypeError, ValueError):
            continue
        if not _que:
            continue
        _u = _profecia_cumplida(_que, fila, puesto, ctx)
        if _u is None:
            log("LOBBY", f"  🔮 PROFECÍA {_que}: usn={_usn} NO se cumplió (puesto={puesto} "
                         f"pd={fila.get('pd')} combo={fila.get('combo')})")
            continue
        (_eb, _ep), (_rb, _rp) = PROFECIA_MONTO.get(_que, ((0, 0), (0, 0)))
        _exp, _rc = _eb + _ep * _u, _rb + _rp * _u
        if _exp <= 0:
            continue                               # sin el renglón de EXP el cliente no festeja
        _b.append((_te, min(int(_exp), 0xFFFF)))
        if _rc > 0:
            _b.append((_tr, min(int(_rc), 0xFFFF)))
    if _b:
        log("LOBBY", f"  🔮 PROFECÍA CUMPLIDA: usn={_usn} -> {_b} (puesto={puesto} pd={fila.get('pd')} "
                     f"combo={fila.get('combo')} canción={ctx.get('cancion')})")
    return _b


def _cupones_que_tiene(ch):
    """`{ítem: cargas}` de los cupones de premio que TIENE (en el inventario, sin vencer). Los
    que van por días dan cargas = 0. ⚠ No se activan: tenerlos es tenerlos activos."""
    import time as _t
    from .ajustes import BONO_DERROTA, CUPONES_PREMIO
    from .basedatos import inv_cant
    _cant = inv_cant(ch)
    _ahora = int(_t.time())
    out = {}
    for e in ch.get("inventory") or []:
        _it = int(e["id"]) if isinstance(e, dict) else int(e)
        if _it not in CUPONES_PREMIO and _it not in BONO_DERROTA:
            continue
        _vence = int(e.get("exp", 0) or 0) if isinstance(e, dict) else 0
        if _vence and _vence < _ahora:
            continue                                   # vencido (db_expire lo borra al entrar)
        out[_it] = _cant.get(_it, 0)
    return out


def _bono_cupon(fila, ctx):
    """Los renglones de los CUPONES DE PREMIO que tiene: EXP Up (9), Coin Up (10), Bono de derrota
    (58). Ver `CUPONES_PREMIO` y `BONO_DERROTA`.

    EXP Up / Coin Up: un % de lo que dio la carrera (EXP de la fila; Rcoin `coin + FF28_BASECOIN`),
    sólo si LLEGÓ. ⚠ El Coin Up va por cargas: sin cargas no se dibuja; la carga se GASTA al cobrar
    (`_gastar_cupones`), no acá — el cartel se puede re-armar, el pago corre una vez.
    Bono de derrota: 200 fijos si NO llegó (o perdió el cooperativo) habiendo jugado, fuera de
    equipo/relevo; y entonces el EXP Up no (el texto: no se usa con otros cupones de puntos).
    """
    from .ajustes import BONO_DERROTA, CUPON_PREMIO_PORCIENTO, CUPONES_PREMIO, ITEMS_CON_CARGAS
    _usn = fila.get("usn")
    if not _usn or not (CUPONES_PREMIO or BONO_DERROTA):
        return []
    try:
        _tiene = _cupones_que_tiene(db_get_char(int(_usn)) or {})
    except Exception:                                            # noqa: BLE001
        return []
    _b = []
    _perdio = bool(fila.get("fallo") or fila.get("perdio"))
    _jugo = int(fila.get("combo") or 0) > 0 or int(fila.get("pd") or 0) > 0
    for _it, (_t, _v) in BONO_DERROTA.items():
        if _it in _tiene and _perdio and _jugo and not ctx.get("equipo") and _v > 0:
            _b.append((_t, min(int(_v), 0xFFFF)))
    _hubo_derrota = bool(_b)
    if not fila.get("fallo"):
        for _it, (_que, _tipo) in CUPONES_PREMIO.items():
            if _it not in _tiene:
                continue
            if _it in ITEMS_CON_CARGAS and _tiene[_it] <= 0:
                continue                               # sin cargas: no paga
            if _que == "exp" and _hubo_derrota:
                continue                               # no se suma al bono de derrota
            _base = (int(fila.get("exp") or 0) if _que == "exp"
                     else int(fila.get("coin") or 0) + FF28_BASECOIN)
            _v = _base * int(CUPON_PREMIO_PORCIENTO.get(_que, 0)) // 100
            if _v > 0:
                _b.append((_tipo, min(_v, 0xFFFF)))
    if _b:
        log("LOBBY", f"  🎟 CUPONES: usn={_usn} -> {_b} (exp {fila.get('exp')}, coin {fila.get('coin')}"
                     f"{', NO llegó' if fila.get('fallo') else ''})")
    return _b


def _gastar_cupones(usn, renglones):
    """Gasta UNA carga de cada cupón con cargas que COBRÓ en esta carrera, y se lo dice al cliente
    con el `FF6A` (el de las campanas: baja el número y, al llegar a 0, lo saca del inventario)."""
    from .ajustes import CUPONES_PREMIO, ITEMS_CON_CARGAS
    from .basedatos import db_del_inventory, inv_cant
    _cobrados = {int(t) for t, _v in renglones or ()}
    for _it, (_que, _tipo) in CUPONES_PREMIO.items():
        if _it not in ITEMS_CON_CARGAS or _tipo not in _cobrados:
            continue
        if not db_del_inventory(usn, _it):
            log("LOBBY", f"  ⚠ CUPÓN {_it}: usn={usn} cobró pero no tenía carga que gastar")
            continue
        _quedan = inv_cant(db_get_char(usn) or {}).get(_it, 0)
        _cx = CONEXIONES.get(usn)
        if _cx is not None and not getattr(_cx, "cerrado", False):
            _cx.send_ff55(0x6A, struct.pack("<I", _it & 0xFFFFFFFF),
                          name=f"FF6A cupón {_it}: una carga menos (quedan {_quedan})")
        log("LOBBY", f"  🎟 CUPÓN {_it}: usn={usn} gastó 1 carga -> quedan {_quedan}")


def _bono_de_pareja(fila, mostrados):
    """Los renglones de bonus de pareja de ESA fila: `[(bonustype, valor), …]`, o `[]`.

    ★★★ LA REGLA, del CBT y con su motivo: el bono se da **sólo si los dos corrieron la misma
      carrera y los dos están EN EL CARTEL** — se mira sobre las filas que se muestran, **no sobre
      la sala**. Si uno se cayó, no hay bono para ninguno.
    ⚠ Y **no lo cobra el que no llegó** (`fallo`/puesto 7): premiar al que abandonó sería regalar
      el bono por sentarse al lado.

    ⚠⚠ El ícono del renglón **se dibuja aunque el valor sea 0** (medido en el CBT) ⇒ un bono de 0
      dejaría un "+0" colgado en el cartel. Por eso cada renglón se agrega **sólo si suma algo**.
    """
    _usn = fila.get("usn")
    if not _usn or fila.get("fallo"):
        return []
    try:
        _pj = db_pareja_de(int(_usn))
    except Exception:                                            # noqa: BLE001
        return []
    if not _pj:
        return []
    if not any(int(o.get("usn") or 0) == int(_pj) and not o.get("fallo") for o in mostrados):
        return []          # la pareja no corrió esta carrera, o no llegó
    # ⛔⛔ ACÁ IBA SÓLO `coin`, Y EL BONO SALÍA SIEMPRE 0 (2026-09-12). anonimo03 probó una partida y
    #   no apareció; el log lo cantó: `+400 (coin 0 + base 400)`. El `coin` es lo que se junta EN
    #   LA PISTA, y en muchas canciones/modos es **cero**: lo que el jugador cobra de verdad es
    #   `coin + FF28_BASECOIN`.
    #   ★ El CBT calculaba sobre `coin` porque allá la pista sí daba monedas. Portar la fórmula
    #     sin mirar nuestro propio dato habría dejado la función "hecha" y sin efecto — que es la
    #     peor clase de terminada: el banco en verde y nada en pantalla.
    _rc = int((int(fila.get("coin") or 0) + FF28_BASECOIN) * PAREJA_BONO_RCOIN)
    _xp = int(int(fila.get("exp") or 0) * PAREJA_BONO_EXP)
    _b = []
    if _rc > 0:
        _b.append((PAREJA_BONO_TIPO_RCOIN, min(_rc, 0xFFFF)))
    if _xp > 0:
        _b.append((PAREJA_BONO_TIPO_EXP, min(_xp, 0xFFFF)))
    if _b:
        log("LOBBY", f"  💞 BONO DE PAREJA: usn={_usn} con uid={_pj} -> {_b} "
                     f"(sobre coin={fila.get('coin')} exp={fila.get('exp')})")
    return _b


def _bono_circulo(fila):
    """El renglón del BONO DE CÍRCULO de esa fila: `[(70, EXP extra)]`, o `[]` (25-sep).
    N % de la EXP de la carrera, con N = el nivel del círculo (`cirlcelevelbonus.xml`, «Bono exp Lv
    N»). Como los otros: no lo cobra el que no llegó, y sólo si suma algo (el ícono se dibuja aunque
    valga 0). Una consulta (`db_insignia_circulo`), sólo para los que tienen círculo."""
    from .ajustes import CIRCULO_BONO_EXP_FACTOR, CIRCULO_BONO_TIPO_EXP, CIRCULOS
    _usn = fila.get("usn")
    if not _usn or fila.get("fallo") or not CIRCULOS or not CIRCULO_BONO_EXP_FACTOR:
        return []
    try:
        from .basedatos import db_insignia_circulo
        _marca, _nivel = db_insignia_circulo(int(_usn))
    except Exception:                                            # noqa: BLE001
        return []
    if not _nivel:
        return []
    _xp = int(int(fila.get("exp") or 0) * _nivel * CIRCULO_BONO_EXP_FACTOR / 100)
    if _xp <= 0:
        return []
    log("LOBBY", f"  ⭕ BONO DE CÍRCULO: usn={_usn} nivel {_nivel} -> +{_xp} EXP (sobre exp={fila.get('exp')})")
    return [(CIRCULO_BONO_TIPO_EXP, min(_xp, 0xFFFF))]


def _bono_del_alma(fila, mostrados):
    """El renglón de bonus del AMIGO DEL ALMA de esa fila: `[(bonustype, valor)]`, o `[]`.

    ★★★ LO PIDE LA AYUDA DEL JUEGO, con todas las letras: *"**Bonus de Amigo del Alma**: juega con
      tus amigos del alma para que tú y ellos puedan recibir Rcoin y Rpoint adicionales"*.

    ★★ Y LOS ÍCONOS EXISTEN EN LA TABLA DEL CLIENTE — `rnr_script/bonus.xml`, **[M]**:

          <bonus bonustype="132" type="1" x="626" y="-30" Image="7" frame="4"  우정보너스 레벨1
          <bonus bonustype="133" …                                   frame="5"  우정보너스 레벨2
          <bonus bonustype="134" …                                   frame="6"  레벨3
          <bonus bonustype="135" …                                   frame="7"  레벨4
          <bonus bonustype="136" …                                   frame="8"  레벨5

      `우정보너스` = *"bono de amistad"*. **Cinco niveles**, los cinco en la misma posición y con
      frames consecutivos ⇒ es **un ícono con cinco caras**, no cinco bonos distintos.
    ★ Y `type="1"` es **el mismo tipo que el bonustype 5**, el Rcoin de la pareja ⇒ el valor de
      este renglón se lee igual que aquél. Por eso se calca la fórmula y no se inventa una.

    ⚠⚠ EL NIVEL ES **NUESTRO**, y conviene saberlo: la tabla trae cinco caras pero **no dice qué
      las elige**. Acá se usa *cuántos amigos del alma llegaron al cartel*, que es lo que la ayuda
      sugiere (*"si tienes más amigos del alma, las joyas también aumentan"*). Con el tope del
      cliente en 2, hoy sólo se alcanzan los niveles 1 y 2 — los otros tres quedan para el día que
      se sepa de dónde salen de verdad.

    ★ La regla de quién cobra es **la misma de la pareja**, y por el mismo motivo: los dos tienen
      que estar EN EL CARTEL y ninguno haber fallado. Premiar al que abandonó sería regalar el
      bono por sentarse al lado.
    """
    _usn = fila.get("usn")
    if not (ALMA_BONO_RCOIN > 0) or not _usn or fila.get("fallo"):
        return []
    try:
        _mios = {int(f.get("otro_uid") or 0) for f in (db_almas_de(int(_usn)) or [])}
    except Exception:                                            # noqa: BLE001
        return []
    if not _mios:
        return []
    # ★ Cuántos de mis amigos del alma corrieron ESTA carrera y llegaron.
    _n = sum(1 for o in mostrados
             if int(o.get("usn") or 0) in _mios and not o.get("fallo"))
    if _n <= 0:
        return []
    # ⛔ Sobre `coin + FF28_BASECOIN`, no sobre `coin` a secas. Es la corrección que el bono de
    #   pareja ya pagó cara (2026-09-12): el `coin` de la pista es CERO en muchas canciones, así
    #   que calcular sobre él deja la función "hecha" y sin efecto — el banco en verde y nada en
    #   pantalla. Lo que el jugador cobra de verdad es la suma.
    _rc = int((int(fila.get("coin") or 0) + FF28_BASECOIN) * ALMA_BONO_RCOIN)
    if _rc <= 0:
        # ⚠ El ícono se dibuja aunque el valor sea 0 ⇒ un bono de 0 deja un "+0" colgado.
        return []
    _nivel = max(1, min(_n, ALMA_BONO_NIVEL_MAX))
    log("LOBBY", f"  💎 BONO DEL ALMA: usn={_usn} con {_n} amigo(s) del alma en el cartel "
                 f"-> nivel {_nivel} (bonustype {ALMA_BONO_TIPO_BASE + _nivel}), +{_rc} rcoin")
    return [(ALMA_BONO_TIPO_BASE + _nivel, min(_rc, 0xFFFF))]


def ganador_por_llegada(todos, equipo_de_slot, n=3):
    """★ La regla de la sala de 12 por equipos (anonimo03, 13-oct; `DOCE_GANA_CON`): recorre la llegada en orden y gana el
    PRIMER equipo que mete `n` corredores en la meta. `todos` viene ordenado por llegada, con los que no llegaron
    (`fallo`) al final. Si ninguno junta `n` (llegaron pocos), gana el que metió más; empatados, el del 1.º.
    Devuelve (equipo ganador o 0, el puesto donde se decidió o None, {equipo: [slots en la meta, en orden]})."""
    meta = {}
    for k, r in enumerate(todos):
        if r.get("fallo"):
            continue
        e = equipo_de_slot(r["slot"])
        meta.setdefault(e, []).append(r["slot"])
        if len(meta[e]) == n:
            return e, k + 1, meta
    if not meta:
        return 0, None, meta
    mas = max(len(v) for v in meta.values())
    for r in todos:                                  # empate (o nadie llegó a n): el que metió más; si no, el del 1.º
        if not r.get("fallo") and len(meta[equipo_de_slot(r["slot"])]) == mas:
            return equipo_de_slot(r["slot"]), None, meta
    return 0, None, meta


def precision_fina(r):
    """La precisión como la ve el jugador en el cartel: entera ×1000 + milésimas (97.855 -> 97855).

    ★ 09-nov: los desempates comparaban sólo el `pd` entero y las milésimas (que el cartel sí muestra) no
      contaban ⇒ con el mismo entero ganaba cualquiera de los dos. Todo desempate por precisión pasa por acá."""
    return int(r.get("pd") or 0) * 1000 + int(r.get("milesimas") or 0)


def unificar_cartel_de_relevo(todos, rid):
    """CARTEL DE RELEVO: el equipo puntúa como UN SOLO jugador.

    ★ PORTADO del server del CBT (`lobby_carrera.py::unificar_cartel_de_relevo`), donde está
      **verificado contra una captura del juego ORIGINAL en 3v3** y afinado después con 762 equipos
      de relevo de producción. Acá se calca **el armado**, no el empaquetado: la fila del 2013 mide
      41 B contra las 23 B del CBT, así que lo único que se toma son las REGLAS.

    Dentro de un equipo, el cliente muestra a los tres con el MISMO tiempo, puesto, precisión,
    estrella y combo. Lo único personal es el **exp**, que escala con el nivel — y por eso acá no se
    toca: ya se calculó (y en el CBT ya estaba persistido) antes de llegar a esta función, y
    pisarlo dejaría lo que se ve distinto de lo que se ganó.

    **Gana el TIEMPO, no la puntuación.** En la captura del original el equipo ganador tenía peor
    precisión y menos combo que el perdedor. Es una carrera de postas.

    Sirve para 2v2 y 3v3: el puesto del perdedor sale del TAMAÑO del equipo ganador (`1º`/`4º` en
    3v3, `1º`/`3º` en 2v2), no de un número fijo.

    | campo | cómo se arma | por qué |
    |---|---|---|
    | `frame` | el **mínimo** de los que cruzaron | en relevo cruza uno solo: el del último tramo |
    | `combo` | el **MÁXIMO** de los integrantes | la cadena es del EQUIPO y sigue corriendo al pasar la batuta |
    | `pd` / `star` | **promedio** | son porcentajes |
    | `puesto` | 1 el ganador · tamaño(ganador)+1 el perdedor · 7 si no llegó nadie | |

    ⛔ DOS INTENTOS FALLIDOS DEL CBT con el combo, por si alguien quiere "mejorarlo":
      1. **Sumar** los tramos -> el cartel mostraba el doble de lo que había hecho nadie.
      2. **No tocarlo**, con la premisa *"el cliente ya lo manda unificado"*. ★ ERA FALSA, y salió de
         UNA sola prueba 2v2 que dio 50/50 y 40/40. En producción llega distinto dentro del equipo
         en el **54 %** de los casos (414 de 762), con diferencia mediana de 59 y picos de 350.
      ✅ `max()`, y el 1 % importa: de esos 414, el máximo es del último tramo en 410 y de un
         compañero en **4**. Ese 1 % apareció porque el usuario del CBT preguntó *"¿y si el tercero
         hace 25 y el primero hizo más?"*.

    ⏳ **Sin verificar en el 2013**: que `pd`/`star` vayan promediados. Si en pantalla el número no
       es ni el de uno ni el del otro y eso no coincide con el original, pasarlos a `max`.
    """
    equipos = {}
    for r in todos:
        equipos.setdefault(equipo_de(rid, r["slot"]), []).append(r)
    _ganador = None
    for r in todos:                                  # `todos` ya viene ordenado por llegada
        if not r.get("fallo"):
            _ganador = equipo_de(rid, r["slot"])
            break
    # ★ 14-oct · el puesto de cada equipo por su LLEGADA (relevo de 12: hasta 4 equipos). El 1.º = 1, cada uno de los
    #   demás = 1 + cuántos corredores tienen los equipos que llegaron antes (con 2 equipos: 1 y tamaño + 1, como siempre).
    _fin_eq = {eq: min([m["frame"] for m in ms if not m.get("fallo")] or [0xFFFFFFFF]) for eq, ms in equipos.items()}
    _orden_eq = sorted([eq for eq in equipos if _fin_eq[eq] != 0xFFFFFFFF], key=lambda e: (e != _ganador, _fin_eq[e]))
    _puesto_eq, _acum = {}, 1
    for eq in _orden_eq:
        _puesto_eq[eq] = _acum
        _acum += len(equipos[eq])
    # ★ 14-oct · relevo de 12 (anonimo03: «1ST, 2ND, 3RD a los 3 de cada equipo según su posición»): dentro del equipo, por
    #   la precisión PROPIA (antes de promediar; desempata el combo) ⇒ puestos seguidos (1-2-3, 4-5-6, …); el cartel de
    #   12 los rotula 1ST/2ND/3RD dentro del equipo y pone a la izquierda al mejor de cada uno (cartel12.c).
    from .salas import es_relevo12
    _r12 = es_relevo12(rid)
    _propio = {m["slot"]: (precision_fina(m), m["combo"]) for ms in equipos.values() for m in ms}
    for eq, miembros in equipos.items():
        _llegaron = [m["frame"] for m in miembros if not m.get("fallo")]
        _n = len(miembros)
        _frame = min(_llegaron) if _llegaron else 0xFFFFFFFF
        _combo = max(m["combo"] for m in miembros)
        _pd    = round(sum(m["pd"] for m in miembros) / _n)
        _star  = round(sum(m["star"] for m in miembros) / _n)
        _puesto = _puesto_eq.get(eq, 7) if _llegaron else 7
        if _r12 and _llegaron:
            _orden_m = sorted(miembros, key=lambda m: (-_propio[m["slot"]][0], -_propio[m["slot"]][1]))
            _puesto_m = {m["slot"]: _puesto + i for i, m in enumerate(_orden_m)}
        else:
            _puesto_m = {}
        for m in miembros:
            m["frame"] = _frame
            m["combo"] = min(_combo, 0xFFFF)
            m["pd"]    = min(_pd, 0xFF)
            m["star"]  = min(_star, 0xFF)
            m["puesto"] = _puesto_m.get(m["slot"], _puesto)
            # ★ El equipo entero comparte el destino: si alguno cruzó, NINGUNO es fallido — aunque
            #   su propio `FF28` haya venido con `frame = 0xFFFFFFFF`, que en relevo es la firma de
            #   *"cerré mi tramo, no me juzgues por tiempo"* y NO la de un abandono.
            m["fallo"] = not _llegaron
            # ★★★ Y LA EXP SE REHACE CON LOS VALORES DEL EQUIPO. El pedido del usuario fue
            #   *"según el desempeño del equipo junto"*, y tiene sentido: en relevo cada uno corre
            #   un tramo, así que su judgment individual mide un tercio de la canción y no la
            #   carrera. Recalculada acá, los tres cobran lo mismo y el número refleja lo que el
            #   cartel muestra.
            #   ⚠ Esto PISA la exp que se calculó arriba con el desempeño individual. Es a
            #     propósito y sólo en relevo; en equipo y en solo cada uno sigue con la suya.
            m["exp"] = m["pd"] * 10 + m["combo"] + m["star"]
    log("LOBBY", "  ★★★ CARTEL DE RELEVO: " + " · ".join(
        f"equipo {eq} ({len(ms)}) puesto {ms[0]['puesto']} frame={ms[0]['frame']} "
        f"combo={ms[0]['combo']} pd={ms[0]['pd']}" for eq, ms in sorted(equipos.items())))


def _cerrar_cartel_tarde(rid, magic=None, esperado=0.0):
    """★★★★★ EL RELOJ DEL CARTEL (2026-09-06). Saca el cartel aunque falte alguien por reportar.

    ⛔ EL BUG: `h_21_ff28` esperaba a que reportaran **todos**, sin límite de tiempo. Un cliente
      que no manda su `FF28` —colgado, crasheado, o una máquina lenta que no llega— dejaba a la
      SALA ENTERA clavada en la meta. Medido en producción (sala 8, carrera de las 14:26:48): el
      cartel salió **2 min 33 s** tarde, y no porque el que faltaba reportara sino porque **se le
      cayó la conexión**. Los otros dos se comieron esos dos minutos y medio mirando la pista.
      Aparece ahora y no antes porque recién ahora entraron máquinas modestas (ver
      `VIDEO_Y_RESOLUCIONES.md` §10): si una tarda de más en cerrar, arrastra a toda la sala.

    ★ CÓMO CIERRA, y por qué así: en vez de duplicar el armado del cartel, **le inventa a cada uno
      que falta el mismo `FF28` que manda un jugador que no llegó** (`frame = 0xFFFFFFFF`, todo lo
      demás en cero) y se lo pasa a `h_21_ff28` como si hubiera llegado por la red. Ventajas:
        · se reusa TODA la lógica que ya existe (orden, puestos, equipos, exp, rcoin, persistencia)
          en vez de escribir un segundo camino que después se desincroniza del primero;
        · el último inyectado encuentra `_faltan28` vacío y dispara el cartel por la vía normal;
        · el que no reportó queda con **puesto 7 = "no llegó"**, que es exactamente lo que el
          cliente ya sabe dibujar (medido en los 13 carteles del corpus).

    ⚠ Se llama desde un `threading.Timer`, o sea FUERA del hilo del jugador: por eso mira el estado
      bajo `_mesa_lock`, **suelta el candado** y recién después llama a `h_21_ff28` (que lo vuelve a
      tomar). Si se llamara con el candado puesto, se traba solo.

    ⚠ Si el cartel ya salió, `resultados` ya no está (se lo lleva el `pop` del pago) y esto no hace
      nada. Y si arranca una carrera nueva, el `FF24` reemplaza la entrada entera de `CARRERAS`,
      así que la bandera `reloj` no sobrevive de una corrida a la otra.
    """
    with _mesa_lock:
        _car = CARRERAS.get(rid) or {}
        _res = _car.get("resultados")
        if not _res:
            return                                   # el cartel ya salió (o no hay carrera)
        # ★★★ EL SELLO DE LA PARTIDA, y no es paranoia: lo encontró la propia prueba. Un reloj
        #   armado en la carrera A sigue vivo aunque la sala arranque la carrera B, y al saltar
        #   habría cerrado a B **12 s después de empezar**, dando por "no llegados" a todos.
        #   El `magic` lo pone el `FF24 START` al reemplazar la entrada de `CARRERAS`, así que
        #   compararlo distingue una corrida de la siguiente. Si no coincide, el reloj es viejo.
        if magic is not None and _car.get("magic") != magic:
            log("LOBBY", f"  ⏰ reloj VIEJO de la sala {rid} (magic {magic} != {_car.get('magic')})"
                         f" -> lo ignoro, ya es otra carrera")
            return
        _esp = {u for u in mesa_de(rid).values()
                if (CONEXIONES.get(u) is not None
                    and not getattr(CONEXIONES.get(u), "cerrado", False))}
        _falta = _esp - {r["usn"] for r in _res.values()}
        _crudos = dict(_car.get("crudos") or {})
        _reportaron_vivos = [(s, r) for s, r in _res.items()
                             if CONEXIONES.get(r.get("usn")) is not None
                             and not getattr(CONEXIONES.get(r.get("usn")), "cerrado", False)]
    if not _falta:
        # ★★★★★ EL SEGUNDO AGUJERO, y lo encontró producción el mismo día que el primero:
        #   cuando los que faltaban **se desconectaron** mientras el reloj corría, la lista de
        #   faltantes queda VACÍA... pero el cartel NUNCA se emitió, porque lo único que lo emite
        #   es un `FF28` entrando, y ya no va a entrar ninguno. La sala se queda igual de clavada.
        #   (Caso real: sala 1, corrida cooperativa de las 14:44:21 — 3 de 5 reportaron, los otros
        #   dos se cayeron, y la sala siguió "EN JUEGO" más de cinco minutos.)
        #   ⇒ Si el cartel sigue sin salir, se RE-DISPARA esta misma función con el paquete crudo
        #     de alguien que ya reportó Y sigue conectado. Al re-entrar, `_faltan28` ya da vacío y
        #     el cartel sale por la vía normal. Re-entrar no cobra dos veces: el pago va detrás del
        #     `pop` de `resultados`, que sólo puede ocurrir una vez.
        for _s, _r in _reportaron_vivos:
            _crudo = _crudos.get(_s)
            if _crudo is None:
                continue
            log("LOBBY", f"  ⏰ RELOJ DEL CARTEL: la sala {rid} sigue sin cartel y los que "
                         f"faltaban ya se fueron -> lo saco con los {len(_res)} que reportaron")
            try:
                h_21_ff28(CONEXIONES[_r["usn"]], 0x28, _crudo)
            except Exception as e:
                log("LOBBY", f"  ⚠ el reloj no pudo re-disparar el cartel: {e!r}")
            return
        return                                       # nadie vivo a quien re-disparar: se cierra solo
    log("LOBBY", f"  ⏰ RELOJ DEL CARTEL: pasaron {esperado:.0f}s y la sala {rid} sigue esperando a "
                 f"{sorted(_falta)} -> los doy por NO LLEGADOS y saco el cartel igual")
    _payload = struct.pack("<I", 0xFFFFFFFF) + bytes(58)     # el mismo FF28 de 62B de un fallido
    for _u in sorted(_falta):
        _c = CONEXIONES.get(_u)
        if _c is None or getattr(_c, "cerrado", False):
            continue
        # ★★ 17-oct (PROD, sala 2 de 12, anonimo03: «quedamos en la meta esperando a un jugador… desapareció de la pista,
        #   salió el cartel y la sala quedó en estado "jugando"»): usn=10294 se COLGÓ (último paquete 18:58:18, nunca
        #   reportó) y su conexión siguió abierta 1 min 45 s. El cartel salió bien, pero el server lo seguía contando
        #   EN CARRERA ⇒ la sala quedó «Jugando» en la lista y, cuando se fue el anfitrión, la herencia le dio el mando
        #   a ÉL y el aviso quedó esperando a que «volviera» — nadie podía arrancar.
        #   ⇒ el que el reloj da por no llegado queda COLGADO: no cuenta para `sala_en_carrera` ni para heredar el
        #   anfitrión. Su propio `en_carrera` NO se toca (los FF0E se le siguen guardando: si despierta en la pista no lo
        #   tumban). Lo borra su vuelta a la sala (FF13) o el próximo START.
        _c.carrera_colgada = True
        log("LOBBY", f"  ⏰ usn={_u} queda COLGADO en la carrera de la sala {rid}: no cuenta para «la sala está en "
                     f"carrera» ni para heredar el anfitrión")
        try:
            h_21_ff28(_c, 0x28, _payload)
        except Exception as e:
            log("LOBBY", f"  ⚠ el reloj no pudo cerrar por usn={_u}: {e!r}")


def h_21_ff28(st, cmd, data):
    # rama original:  cmd == 40
    # C->S FF28 (62B medidos): [frame:u32][combo:u16][pd:u8][star:u8][coin:u16][u16][md5 ascii 32B][cola]
    #   (los 32 chars ASCII son el hash anti-cheat del score; no lo validamos todavía).
    # Sin handler el cliente se QUEDA ATASCADO en la pista: nunca sale el cartel.
    #
    # S->C FF28 = el cartel. Layout SACADO DEL DISASM DEL 2013 (handler recv 0x5E9360 "CmdGameOver"),
    # NO calcado del CBT: se verificó y DIFIERE en dos puntos que lo habrían roto:
    #   prefijo:  [b0:u8][b1:u8][b2:u8][count:u8]      (el CBT tiene solo [winteam][count])
    #             ⚠ +2×u32 extra ANTES del count si roomtype==6 (couple); el nuestro es 7 -> no van.
    #             b0 -> vtable+0x20 de [[0x9314c8]+0xaf4] (equipo ganador: el cliente lo compara con
    #             el suyo -> GANASTE/PERDISTE). b1/b2: si alguno != 0 llama 0x4FDEC0 -> los dejamos en 0.
    #   fila por jugador = **41 B** (el CBT usa 23B). ⚠ Acá decía 34: mal contado. La cuenta real
    #   es 1+1+2+2+2+1+1+2+4+4+12+2+7 = 41, y cuadra con los 46 del cartel de 1 fila (4+41+1).
    #     [pos:u8][rank:u8][rank_bonus:u16][exp:u16][combo:u16][pd:u8][star:u8][coin:u16]
    #     [basecoin:u32][frame:u32][12 BYTES (sin mapear, en 0)][inner_count:u16=0]
    #     ★ el bloque de 12B (read 0xc @0x5E9503) es lo que el CBT no tiene; sin él el stream se
    #       desfasa 12B por fila. Con inner_count=0 se saltea el loop interno (u16+u16 por entrada).
    # ★ `.autoplay`: el que ya reportó terminó de correr — no pedirle más autoplays durante el
    #   cartel (el `en_carrera` sigue prendido hasta que vuelve a la sala). Ver `autoplay_gm.py`.
    st.autoplay_ya_corre = False
    if len(data) >= 10:
        frame = struct.unpack_from("<I", data, 0)[0]
        combo = struct.unpack_from("<H", data, 4)[0]
        pd, star = data[6], data[7]
        coin = struct.unpack_from("<H", data, 8)[0]
    else:
        frame = combo = pd = star = coin = 0
    # ★★★ LAS MILÉSIMAS DE LA PRECISIÓN — 2026-09-13, paso 1 (el cable).
    #   El cliente de fábrica NO las manda: manda `pd` como un byte y nada más. Esto lee el hueco
    #   donde las va a escribir el parche del cliente, y **hoy siempre da 0**.
    #   ★ MEDIDO sobre 16.624 paquetes reales de prod: los bytes 46..56 valen `00` en todos.
    #   ⚠ Leer un hueco que nadie llena no es inútil: es lo que hace que el día que el parche
    #     exista no haya que tocar el server. Y si algún cliente raro escribiera ahí, el log lo
    #     va a cantar en vez de que el número aparezca de la nada.
    #   ★★ Y LA PERILLA DE PRUEBA. Hay un huevo y gallina: el parche del cliente sólo se puede
    #     comprobar si el server manda milésimas, y el server sólo las manda si el cliente se las
    #     dio. `.pd N` en el chat rompe el círculo: inventa el número, una vez, para ver el cartel.
    #     ⚠ Es de PRUEBA: `PRECISION_MILESIMAS_FORZADAS` arranca en 0 y prod nunca lo toca.
    milesimas = 0
    _forz = getattr(st, "milesimas_forzadas", None)
    if _forz is None:
        _forz = PRECISION_MILESIMAS_FORZADAS
    if PRECISION_MILESIMAS and _forz:
        milesimas = max(0, min(int(_forz), 999))
        log("LOBBY", f"  🧪 FF28: milésimas FORZADAS a {milesimas} para usn="
                     f"{getattr(st, 'usn', None)} (perilla de prueba, no viene del cliente)")
    elif PRECISION_MILESIMAS and len(data) >= FF28_C2S_OFF_MILESIMAS + 2:
        milesimas = struct.unpack_from("<H", data, FF28_C2S_OFF_MILESIMAS)[0]
        if milesimas > 999:
            log("LOBBY", f"  ⚠ FF28: milésimas fuera de rango ({milesimas}) de usn="
                         f"{getattr(st, 'usn', None)} -> las ignoro. O el parche del cliente "
                         f"escribe mal, o ese byte NO era libre.")
            milesimas = 0
    # plausibilidad (guía CBT anti-cheat capa 1): pd y star son PORCENTAJES -> tope 100.
    if pd > 100:   pd = 100
    if star > 100: star = 100
    exp = pd * 10 + combo + star                      # fórmula del cartel del CBT
    # ★★★ ¿GANÓ O PERDIÓ? (2026-08-04). En el chase lo sabemos: lo calculó el handler del FF10F
    #   con la formula real del cliente. Fuera del chase no hay derrota, asi que se asume victoria.
    _es_chase = bool(getattr(st, "room_colab", False))
    _perdio   = _es_chase and not getattr(st, "chase_gano", False)
    # ★ El EXP y el RCOIN del cartel salen TAL CUAL de esta fila (`0x579E92` lee `struct+0x04` y lo
    #   muestra sin tocarlo; el Rcoin es `(u16)(coin + basecoin)`, `0x579E70`). O sea: **no hay
    #   ningún cálculo local del cliente**, lo que se ve es lo que mandamos. Por eso salía igual
    #   ganando que perdiendo. La exp ya varía con el desempeño (pd/combo/star); lo que faltaba era
    #   penalizar la derrota. ⚠ `CHASE_EXP_DERROTA` es una PERILLA DE DISEÑO, no un dato del juego.
    # ★ El cooperativo paga el DOBLE (medido: 2.02x en la captura, ver CHASE_EXP_MULT).
    #   Va ANTES de la penalización por derrota. Con los valores de hoy (2.0 y 0.5) eso deja
    #   al que pierde en coop cobrando EXACTAMENTE lo mismo que una canción suelta: se laburó
    #   el triple y no se cobra menos, pero tampoco se premia perder. Si algún día se quiere
    #   que perder en coop igual convenga, la perilla es `CHASE_EXP_DERROTA`, no ésta.
    if _es_chase:
        exp = int(exp * CHASE_EXP_MULT)
    if _perdio:
        exp = int(exp * CHASE_EXP_DERROTA)
    # ⚠ El Rcoin del cartel se trunca a u16: con `coin + basecoin > 65535` muestra basura.
    # ★★★★ 2026-08-05 — EL CARTEL AHORA LLEVA UNA FILA POR JUGADOR.
    #   Antes cada uno recibía el suyo, de una sola fila, y no veía el resultado del otro. Se
    #   juntan los reportes de la sala y, cuando reportaron TODOS, se arma un cartel con todas las
    #   filas ordenadas por desempeño y se le manda EL MISMO a cada uno.
    #   ⚠ Si alguien abandona y no reporta nunca, los demás se quedarían esperando: por eso el
    #     corte también se da cuando ya no queda nadie más conectado en la sala.
    _mi_slot28 = getattr(st, "room_slot", None)
    if _mi_slot28 is None:
        _mi_slot28 = HOST_SLOT
    _rid28 = getattr(st, "room_id", None)
    # ★★★ ¿LLEGÓ O NO LLEGÓ? Hacen falta LAS DOS REGLAS (guía del server del CBT, que las tiene
    #   medidas). Con una sola se rompe:
    #     (a) judgment EN CERO (`combo=pd=star=0`) **con frame REAL** = se congeló en el contador-0.
    #         Es el fallo de toda la vida, en todos los modos. Mirando sólo el frame, éste contaría
    #         como llegada.
    #     (b) `frame == 0xFFFFFFFF` — el cliente lo emite por `0x4C2660(flag=0)` -> `0x4B84B3`
    #         (`or eax,-1`). ★ En RELEVO ésa es la rama del corredor que YA CERRÓ SU TRAMO: manda
    #         combo/pd/star REALES pero sin tiempo de meta. Mirando sólo el judgment, éste entraría
    #         al orden de llegada con 0xFFFFFFFF y se llevaría un puesto falso.
    #   ⚠ MEDIDO EN NUESTRO PROPIO LOG (2026-09-04, 11:43:04): el 2º jugador mandó
    #     `frame=8248 combo=0 pd=0 star=0` = caso (a). Antes lo contábamos como llegada.
    _fallo28 = (frame == 0xFFFFFFFF) or (combo == 0 and pd == 0 and star == 0)
    _res = {"slot": _mi_slot28, "frame": frame, "combo": combo, "pd": pd, "star": star,
            "coin": coin, "exp": exp, "perdio": _perdio, "usn": getattr(st, "usn", None),
            "fallo": _fallo28, "milesimas": milesimas,
            # ★ En qué ronda del gorila se lo atrapó (`None` = se escapó). Lo usa el medallón del
            #   cartel en cooperativo: ver `medallon_del_gorila`.
            "ronda_captura": getattr(st, "chase_ronda_captura", None) if _es_chase else None}
    # ★★ EL `coin` DEL REPORTE, AL LOG — 2026-09-05, pregunta del usuario: *"¿basecoin tiene
    #   alguna fórmula, o es un valor fijo?"*.
    #   Hoy el Rcoin del cartel es `coin` (lo que el JUGADOR juntó, viene acá) + `FF28_BASECOIN`
    #   (35, fijo nuestro). En las 17 filas capturadas del server de referencia el `basecoin`
    #   **varía por jugador entre 25 y 40** y no correlaciona con NADA (puesto, precisión, combo,
    #   exp, ranking: todos |r| < 0.3). Esa forma es la de "monedas juntadas en la pista".
    #   ⇒ HIPÓTESIS: ese server mete lo juntado en `basecoin` y deja `coin` en 0; nosotros hacemos
    #     lo contrario Y ADEMÁS sumamos 35, así que pagaríamos ~35 de más.
    #   ⇒ Se contesta con UNA carrera terminada: si acá llegan valores de 25..40, la hipótesis vale
    #     y hay que decidir si el 35 fijo se saca. Si llega 0 siempre, el 35 es lo único que hay.
    log("LOBBY", f"  🪙 RCOIN del reporte: coin={coin} (lo que juntó en la pista) "
                 f"+ basecoin={FF28_BASECOIN} (fijo nuestro) -> el cartel mostrará "
                 f"{(coin + FF28_BASECOIN) & 0xFFFF}")
    _armar_ff27 = False                  # sin sala no hay a quién avisarle: se define acá para que
                                         # el bloque de abajo no dependa de la rama que se tomó.
    _armar_reloj28 = False               # idem para el reloj del cartel (ver FF28_ESPERA_MAX)
    if _rid28 is None:
        _dest28, _todos = [st], [_res]
    else:
        with _mesa_lock:
            _car28 = CARRERAS.setdefault(_rid28, {"magic": 0, "cargados": set(), "jugadores": set()})
            _car28.setdefault("resultados", {})[_mi_slot28] = _res
            # ★ Y el paquete CRUDO de cada uno, que el reloj necesita para poder RE-DISPARAR esta
            #   misma función cuando el que falta ya no está para inyectarle nada (ver
            #   `_cerrar_cartel_tarde`). Re-entrar es gratis: el pago se hace UNA vez, con el `pop`
            #   de `resultados`.
            _car28.setdefault("crudos", {})[_mi_slot28] = bytes(data)
            _esperados = {u for u in mesa_de(_rid28).values()
                          if (CONEXIONES.get(u) is not None
                              and not getattr(CONEXIONES.get(u), "cerrado", False))}
            _reportaron = {r["usn"] for r in _car28["resultados"].values()}
            _faltan28 = _esperados - _reportaron
            _todos = list(_car28["resultados"].values())
            # ★ el contador se arma UNA sola vez por corrida, y adentro del candado para que dos
            #   llegadas simultáneas no lo disparen dos veces.
            _armar_ff27 = (FF27_AL_PRIMER_FINALISTA and not _fallo28
                           and not _car28.get("contador") and not getattr(st, "room_colab", False))
            if _armar_ff27:
                _car28["contador"] = True
            # ★★★★★ Y EL RELOJ, que también se arma UNA sola vez y dentro del candado.
            #   Ver `FF28_ESPERA_MAX`: sin esto, un cliente que no reporta deja a TODA la sala
            #   clavada en la meta para siempre.
            _armar_reloj28 = (FF28_ESPERA_MAX > 0 and bool(_faltan28)
                              and not _car28.get("reloj"))
            _magic28 = _car28.get("magic")     # el sello de ESTA corrida, para el reloj
            if _armar_reloj28:
                _car28["reloj"] = True
        # ★★★★★ EL PRIMERO QUE LLEGA ENCIENDE EL CONTADOR DE TODA LA SALA (ver FF27_AL_PRIMER_FINALISTA).
        #   Va ANTES del corte por `_faltan28`: justamente sirve para que los que faltan cierren.
        #   ⛔ A TODOS, sin filtrar por modo ni por "éste ya llegó": el que ya llegó lo ignora solo
        #     (el handler `0x5E3010` chequea `0x4EBDB0` y se saltea el `SetTimer`), y filtrarlo es
        #     lo que en el CBT dejó a 4 de 6 jugadores desconectados.
        #   ⚠ El cooperativo queda afuera a propósito: allá el `FF27` lo manda el cierre del gorila
        #     tras la 3ª ronda (`FF27_PEDIR_RESULTADO`), y mandarlo acá lo cortaría en la 1ª canción.
        if _armar_ff27:
            _n27 = 0
            # ★ Y a los que MIRAN también: el `FF27` es el contador de 4 s del final de la carrera.
            #   Si no les llega, su pantalla no arranca el cierre y el cartel los agarra fríos.
            _usn27 = list(mesa_de(_rid28).values()) + [getattr(c, "usn", None)
                                                       for c in espectadores_de(_rid28)]
            for _u27 in _usn27:
                _c27 = CONEXIONES.get(_u27)
                if _c27 is None or getattr(_c27, "cerrado", False):
                    continue
                try:
                    _c27.send_ff55(0x27, b"", name="FF27 TIMEOVER (contador de 4s + cerrá y reportá)")
                    _n27 += 1
                except Exception as e:
                    log("LOBBY", f"  ⚠ no pude mandar el FF27 a usn={_u27}: {e!r}")
            log("LOBBY", f"  ★★★ FF27: llegó primero el slot {_mi_slot28} (frame={frame}) -> "
                         f"TIMEOVER a {_n27} jugador(es) de la sala {_rid28}")
        if _armar_reloj28:
            _t28 = threading.Timer(FF28_ESPERA_MAX, _cerrar_cartel_tarde, (_rid28,),
                                   {"magic": _magic28, "esperado": FF28_ESPERA_MAX})
            _t28.daemon = True          # que un reloj pendiente no impida apagar el server
            _t28.start()
        if _faltan28:
            log("LOBBY", f"  ⏳ FF28 reportó slot={_mi_slot28}; faltan {sorted(_faltan28)} "
                         f"-> el cartel espera (reloj de {FF28_ESPERA_MAX:.0f}s en marcha)")
            return
        _dest28 = [CONEXIONES.get(u) for u in _esperados]
        _dest28 = [c for c in _dest28 if c is not None and not getattr(c, "cerrado", False)]
        # ★★★ Y EL CARTEL A LOS QUE MIRAN — 2026-09-08.
        #   ⛔ Reportado: *"los espectadores no corren, pero no recibieron el cartel de los
        #     corredores: quedaron estancados"*. Medido en el log de las 00:53:04:
        #         ★★ FF28 GAMEOVER -> cartel de 2 fila(s) a 2 jugador(es)
        #     …con DOS espectadores en la sala. El cartel es el único camino de vuelta desde la
        #     pista: sin él se quedan en la pantalla de carrera para siempre.
        #   ⚠ Reciben el cartel pero NO están en `_esperados`: siguen sin tener que reportar el
        #     `FF28` (esa lista es la que decide cuándo se cierra), y el cobro de exp/rcoin se
        #     hace sobre `resultados`, donde tampoco están. Miran el resultado, no lo protagonizan.
        _dest28 = _dest28 + [c for c in espectadores_de(_rid28) if c not in _dest28]
    # ★★★ EL PUESTO SALE DEL ORDEN DE LLEGADA (frame ascendente), no de la precisión.
    #   ⛔ Acá se ordenaba por `(pd, combo)`. Es una carrera: gana el que llega antes.
    #   Las tres patas:
    #     · El server del CBT ordena por `frame` ascendente, y una captura del **juego ORIGINAL**
    #       en 3v3 muestra al equipo ganador con **peor precisión y menos combo** que el perdedor.
    #     · La captura del 2013: en los modos de carrera el puesto sigue al frame en **4 de 5**
    #       carteles (el que falla es de 3 jugadores). Por `pd/combo`, 3 de 5.
    #     · En cooperativo no lo explica NINGUNA de las dos reglas (0 de 7) — el cartel de coop de
    #       ese server está roto, cosa que ya sabíamos.
    #   ⚠ NO es unánime: si en pantalla los puestos salen al revés, ésta es la línea.
    #   Y los que NO llegaron van al final, ordenados entre ellos por desempeño (el `fallo` los
    #   manda atrás sin importar su frame: un fallo trae frame REAL y podría colarse adelante).
    #   ★★★ Y EL DESEMPATE ES **COMBO ANTES QUE PRECISIÓN** (2026-09-06, pedido del usuario tras
    #     verlo en pantalla: *"tiempo - combo - precision"*). Antes iba `-pd` primero.
    #     El caso que lo destapó, medido en el log de producción (sala 1, 09:48, "Chica Espacio"):
    #         slot 3  cuenta_admin    frame 7398  combo 582  pd 91
    #         slot 1  jugador11   frame 7398  combo 481  pd 92
    #     Empataron en el frame EXACTO. Con `-pd` primero ganaba jugador11 por UN punto de
    #     precisión, y el combo —que estaba en la regla— nunca se llegaba a mirar.
    #     ⇒ Y cuenta_admin había hecho **all combo**: el catálogo declara `Combo="582"` para esa
    #       canción, o sea que no falló una sola nota. Perdía un all combo contra un punto de pd.
    #   ⚠ Sólo decide cuando el `frame` EMPATA. El puesto lo sigue mandando el orden de llegada:
    #     esto no le gana nunca a alguien que llegó antes.
    # ★★★★★ LOS NPC TAMBIÉN SALEN EN EL CARTEL — SOLO EN LOCAL (2026-09-10, pedido de anonimo03).
    #   Va atado a `R2_CONSOLA_GM`, que pone `startserver.bat` y que systemd **no pone nunca**:
    #   en prod esto no corre ni por accidente. Ver `CHASE_NPC_REALISTA` en `ajustes.py`.
    #
    #   POR QUÉ HACE FALTA: probando solo con `.npc full`, el cartel salía con UNA fila y la
    #   pantalla de premios con UNA columna. Y la columna de cada uno en esa pantalla es su
    #   POSICIÓN en la lista del cartel (`0x575E70`) ⇒ sin filas de NPC **no se puede mirar ni el
    #   orden ni el resaltado**, que es justo lo que hay que verificar.
    #
    #   ⚠ Los NPC van con `usn = None`: el pago de exp/rcoin saltea las filas sin `usn`, así que
    #     son decorado y no tocan ninguna cuenta.
    #   ⚠ Su exp NO se inventa: se copia la MEDIANA de la que cobraron los jugadores de verdad en
    #     ESTE mismo cartel, para que la columna se vea coherente con la partida recién jugada.
    if (CHASE_NPC_REALISTA and CHASE_NPC_CARTEL and _es_chase
            and _rid28 is not None and _todos):
        _ya28 = {r["slot"] for r in _todos}
        _ord28 = sorted(_todos, key=lambda r: r["exp"])
        _exp_ref = _ord28[len(_ord28) // 2]["exp"]
        _fr_ref = max((r["frame"] for r in _todos if not r.get("fallo")), default=6000)
        with _mesa_lock:
            _pnpc28 = dict((CARRERAS.get(_rid28) or {}).get("puntos_npc") or {})
        _puestos_npc = []
        for _sl_npc in npcs_de(_rid28):
            if _sl_npc in _ya28:
                continue
            _pd_npc = random.randint(*CHASE_NPC_PD)
            _todos.append({"slot": _sl_npc,
                           "frame": max(1, _fr_ref + random.randint(-120, 120)),
                           "combo": random.randint(*CHASE_NPC_COMBO),
                           "pd": _pd_npc,
                           "star": _todos[0].get("star", 0),
                           "coin": random.randint(20, 60),
                           "exp": max(1, int(_exp_ref * random.uniform(0.75, 1.15))),
                           "perdio": bool(_todos[0].get("perdio")),
                           "usn": None, "fallo": False,
                           "puntos": aporte_al_gorila(_sl_npc, None, _pnpc28)})
            _puestos_npc.append(f"slot {_sl_npc} (pd {_pd_npc}, aporte "
                                f"{aporte_al_gorila(_sl_npc, None, _pnpc28)})")
        if _puestos_npc:
            log("LOBBY", "  🧪 NPC en el cartel (SOLO LOCAL, CHASE_NPC_REALISTA): "
                         + " · ".join(_puestos_npc) + " — no cobran nada (usn=None)")
    # ★★ Y LOS NPC QUE JUGARON (10-oct, SÓLO LOCAL): fuera del cooperativo, si corrieron con el avance que les
    #   inventa `npc_carrera.py`, salen en el cartel con un tiempo, combo y precisión que cuadran con eso.
    if CHASE_NPC_REALISTA and not _es_chase and _rid28 is not None and _todos:
        try:
            from . import npc_carrera
            _ref28 = min(_todos, key=lambda r: r["frame"] if not r.get("fallo") else 1 << 40)
            _todos += npc_carrera.filas_del_cartel(_rid28, {r["slot"] for r in _todos}, _ref28)
        except Exception as e:
            log("LOBBY", f"  ⚠ las filas de los NPC: {e!r}")
    # ★★ 09-nov (anonimo03: «el desempate por precisión está fallando, está ganando quien sacó menos precisión»):
    #   el desempate miraba la precisión ENTERA (`pd`) y no las milésimas que el cartel MUESTRA. Medido en prod:
    #   tres all combo en el mismo frame con 97.079 / 97.030 / 97.855 salían en ESE orden (97 = 97 = 97 ⇒ quedaba
    #   el orden de llegada del paquete). ⇒ se compara `pd*1000 + milésimas`, lo mismo que se ve.
    _todos.sort(key=lambda r: (bool(r.get("fallo")),
                               r["frame"] if not r.get("fallo") else 0,
                               -r["combo"], -precision_fina(r)))
    # ★★★★★ EN EL COOPERATIVO EL ORDEN NO ES LA LLEGADA: ES QUIÉN ATRAPÓ AL GORILA (2026-09-10).
    #
    #   El cooperativo NO es una carrera contra los compañeros: se gana o se pierde JUNTOS, y lo
    #   único que decide la partida es el minijuego de la cuerda. Ordenarlo por `frame` —el orden
    #   de las carreras— es lo que tenía el cartel y los turnos de las cajas **en dos órdenes
    #   distintos**, y eso se ve en pantalla: el cliente dibuja la fila de premios sobre la
    #   columna que ocupa el jugador **en la lista del cartel** (`0x575E70` busca el slot dentro
    #   del vector `[padre+0x8c]`, elementos de 0xA8, y devuelve el ÍNDICE). Cartel en un orden +
    #   turnos en otro = el resaltado cae sobre el vecino. Es el *"premio corrido"*.
    #
    #   ★ Y explica un dato viejo que nos había quedado sin explicación: en el corpus del
    #     referente el cartel de cooperativo **no lo explicaba NINGUNA de las dos reglas** (ni
    #     `frame` ni `pd/combo`, 0 de 7). Lo dimos por "roto". No estaba roto: estaba ordenado
    #     por otra cosa, y esa otra cosa es el aporte al gorila.
    #
    #   ⇒ Con esto, el puesto 1 del cartel es **el que atrapó al gorila**, y como los turnos de
    #     las cajas salen del MISMO orden (`_orden_del_gorila`), elegir va 1º, 2º, 3º… de arriba
    #     hacia abajo. Que es exactamente lo que pidió anonimo03.
    #   ⚠ Los que NO llegaron siguen yendo al final, como en todos los modos.
    if _es_chase and _todos:
        _pts28 = {}
        for _u28 in (mesa_de(_rid28).values() if _rid28 is not None else []):
            _c28 = CONEXIONES.get(_u28)
            if _c28 is not None:
                # ★ El MISMO número que usa el orden de elección. Ver `aporte_al_gorila`: si estos
                #   dos se separan, la fila resaltada cae sobre la columna del vecino.
                _pts28[_slot_de(_c28)] = aporte_al_gorila(_slot_de(_c28), _c28)
        # ★★★ Y LA MISMA REGLA QUE EL ORDEN DE ELECCIÓN: primero el que lo atrapó.
        #   Tienen que salir iguales o la fila resaltada cae sobre la columna del vecino.
        _act28 = activador_del_gorila(_rid28)
        _todos.sort(key=lambda r: (bool(r.get("fallo")),
                                   r["slot"] != _act28,
                                   -_pts28.get(r["slot"], r.get("puntos", 0)),
                                   r["frame"] if not r.get("fallo") else 0))
        # ⚠ ESTA LÍNEA MENTÍA (2026-09-10). Imprimía `_pts28.get(slot, 0)`, y `_pts28` sólo tiene
        #   a los jugadores de verdad ⇒ **todas las filas de NPC salían con aporte 0**, cuando el
        #   orden real las había usado bien. anonimo03 cruzó una foto de la pantalla contra el log y
        #   el log era el que no cerraba. ⇒ Se imprime el MISMO número con el que se ordenó.
        log("LOBBY", "  ★ cooperativo: el cartel se ordena por el APORTE AL GORILA "
                     + ", ".join(f"slot {r['slot']}={_pts28.get(r['slot'], r.get('puntos', 0))}"
                                 for r in _todos)
                     + (f" · ★ lo ATRAPÓ el slot {_act28} (iba adelante), va 1º"
                        if _act28 is not None else " · (sin activador: manda el esfuerzo)")
                     + " — mismo orden que los turnos de las cajas")
    # ★★★ RELEVO: el equipo puntúa como UNO SOLO. Va DESPUÉS del orden (necesita saber quién llegó
    #   primero para elegir el equipo ganador) y ANTES de las filas (reescribe frame/combo/pd/star
    #   y fija el `puesto` a mano). Ver `unificar_cartel_de_relevo`.
    _es_relevo28 = (bool(getattr(st, "room_mode", 0) & MODE_RELEVO)
                    and _rid28 is not None and not getattr(st, "room_colab", False))
    if _es_relevo28 and _todos:
        unificar_cartel_de_relevo(_todos, _rid28)
    # ★ EL BONO INVISIBLE POR SALA LLENA, para TODOS los modos (ver BONO_POR_JUGADORES).
    #   Va acá y no donde se calcula la exp de cada uno: recién en este punto se sabe
    #   CUÁNTOS reportaron. Se cuenta a los que reportaron, no los asientos ocupados —
    #   si alguien se fue a mitad de partida, la sala no estaba llena de verdad.
    # ★ EL EQUIPO GANADOR SE CALCULA ACÁ ARRIBA porque ahora lo necesitan DOS cosas: los puntos
    #   de ranking de cada fila (abajo) y el `b0` del cartel. Antes se calculaba después de armar
    #   las filas, y con el cambio de los puntos habría llegado tarde.
    _es_jefe28 = bool(getattr(st, "room_boss", False))
    _es_equipo28 = ((bool(getattr(st, "room_mode", 0) & (MODE_EQUIPO | MODE_RELEVO)) or _es_jefe28)
                    and not getattr(st, "room_colab", False))
    _winteam28 = 0
    # ⚠ Si NO LLEGÓ NADIE no hay equipo ganador: el orden pone a los fallidos al final, así que
    #   `_todos[0]` sería un fallido y le estaríamos regalando la victoria a su equipo.
    if _es_equipo28 and _todos and _rid28 is not None and not _todos[0].get("fallo"):
        _winteam28 = equipo_de(_rid28, _todos[0]["slot"])
    # ★★★ 14-oct · LA SALA DE 12 POR EQUIPOS: gana el PRIMER equipo que mete 3 en la meta (`DOCE_GANA_CON`, anonimo03).
    #   No el del 1.º: «sería injusto sin tomar en cuenta el esfuerzo de los demás». El jefe sigue con la suya (abajo).
    if (_es_equipo28 and DOCE_GANA_CON and _rid28 is not None and _todos and grande_de(_rid28) == 12
            and not _es_jefe28 and not (getattr(st, "room_mode", 0) & MODE_RELEVO)):
        _g3, _en3, _meta3 = ganador_por_llegada(_todos, lambda s: equipo_de(_rid28, s), DOCE_GANA_CON)
        _nom3 = {1: "ROJO", 2: "AZUL", 3: "VERDE", 4: "NARANJA"}     # ★ 15-oct: y los 4 equipos
        _lleg3 = " ".join({1: "R", 2: "A", 3: "V", 4: "N"}.get(equipo_de(_rid28, _r["slot"]), "?") + str(_r["slot"])
                          for _r in _todos if not _r.get("fallo"))
        log("LOBBY", f"  ★★★ 12 POR EQUIPOS — la llegada (equipo+asiento): {_lleg3}")
        for _e3 in sorted({equipo_de(_rid28, _r["slot"]) for _r in _todos}):   # todos los que llegaron (asiento + 1 «P»)
            _sl3 = [_r["slot"] for _r in _todos if not _r.get("fallo") and equipo_de(_rid28, _r["slot"]) == _e3]
            log("LOBBY", f"  ★★★   team {_nom3[_e3]} slots {' '.join(str(x) for x in _sl3)} "
                         f"(cartel {' '.join(f'{x + 1}P' for x in _sl3)}) {'WIN' if _e3 == _g3 else 'LOSS'}")
        log("LOBBY", f"  ★★★   gana {_nom3.get(_g3, 'nadie')}"
                     + (f": metió su {DOCE_GANA_CON}.º en el puesto {_en3}" if _en3 else " (ninguno juntó "
                        f"{DOCE_GANA_CON}: el que metió más)") + f" · antes habría ganado el del 1.º: {_nom3.get(_winteam28, 'nadie')}")
        _winteam28 = _g3
    # ★★★★★ EN EL MODO JEFE NO GANA EL PUESTO 1: GANA EL CAPITÁN QUE CRUZA PRIMERO (2026-09-07).
    #   Es la regla del modo, y el cliente la tiene de su lado: en `0x4FA6A0`, dentro del mismo
    #   init de la carrera, si `CalcGameFlags & 0x2000` guarda `[cGame+0xC78] = 0x4F65A0` —una
    #   función que compara el avance de los DOS capitanes (`fld [jugador+0x18]`) y deja 1 ó 2—.
    #   Los demás modos guardan otra. O sea que la barra de progreso del jefe ya mira capitanes.
    #   ⇒ Para el cartel no hace falta ningún paquete nuevo: el `b0` del `FF28` sigue siendo "el
    #     equipo ganador, 1-based". Lo único que cambia es de dónde sale el número.
    #   ⚠ Si NINGÚN capitán llegó, se cae al criterio normal (el puesto 1) en vez de dar 0, que en
    #     el cliente se lee como "perdieron todos" — el mismo síntoma que ya tuvimos con
    #     `FF28_WINTEAM = 0`.
    if _es_jefe28 and _rid28 is not None:
        _caps28 = capitanes_de(_rid28)
        if _caps28:
            _slots_cap28 = set(_caps28.values())
            _prim28 = next((_r for _r in _todos
                            if _r["slot"] in _slots_cap28 and not _r.get("fallo")), None)
            if _prim28 is not None:
                _winteam28 = equipo_de(_rid28, _prim28["slot"])
                log("LOBBY", f"  ★★★ JEFE: gana el equipo {_winteam28} — su capitán (slot "
                             f"{_prim28['slot']}) cruzó primero de los dos. Capitanes: {_caps28}")
            else:
                log("LOBBY", f"  ⚠ JEFE: ningún capitán terminó ({_caps28}) -> el cartel usa el "
                             f"puesto 1 como en equipo normal (b0={_winteam28})")
        else:
            log("LOBBY", "  ⚠ JEFE: la sala no tiene capitanes registrados -> cartel de equipo normal")

    # ★★★ Y EN LOS MODOS POR EQUIPOS, LA EXP TAMBIÉN LA DECIDE EL RESULTADO.
    #   Sin esto pasaba lo que el usuario vio: el que MÁS cobraba era del equipo que PERDIÓ,
    #   porque había tocado mejor. Ver `EXP_MULT_GANADOR` en `ajustes.py` para la calibración.
    if _winteam28:
        for _r in _todos:
            _r["exp"] = int(_r["exp"] * (EXP_MULT_GANADOR
                                         if equipo_de(_rid28, _r["slot"]) == _winteam28
                                         else EXP_MULT_PERDEDOR))
        log("LOBBY", f"  ★ exp por resultado: gana el equipo {_winteam28} "
                     f"(x{EXP_MULT_GANADOR} / x{EXP_MULT_PERDEDOR})")
    # ★ COOPERATIVO: achicar la brecha entre el que más aportó y el que menos. Va ANTES del bono
    #   de sala y del descuento, sobre la exp ya multiplicada por el modo. Ver
    #   `CHASE_EXP_ACERCA_AL_MEJOR` en `ajustes.py`.
    if _es_chase and _todos and CHASE_EXP_ACERCA_AL_MEJOR:
        _mejor28 = max(_r["exp"] for _r in _todos)
        for _r in _todos:
            _r["exp"] = int(_r["exp"] + (_mejor28 - _r["exp"]) * CHASE_EXP_ACERCA_AL_MEJOR)
        log("LOBBY", f"  ★ cooperativo: brecha achicada un {CHASE_EXP_ACERCA_AL_MEJOR:.0%} "
                     f"hacia el mejor ({_mejor28})")
    _bono28 = BONO_POR_JUGADORES.get(len(_todos), max(BONO_POR_JUGADORES.values()))
    if _bono28:
        for _r in _todos:
            _r["exp"] = int(_r["exp"] * (1.0 + _bono28))
        log("LOBBY", f"  ★ bono de sala: {len(_todos)} jugadores -> exp x{1 + _bono28:.2f}")
    # ★ Y AL FINAL DE TODO, el descuento del cooperativo. Va último a propósito: así lo que se
    #   resta es exactamente lo que baja en pantalla, sin que ningún multiplicador lo amplifique.
    if _es_chase:
        _desc = CHASE_EXP_DESCUENTO.get(len(_todos), max(CHASE_EXP_DESCUENTO.values()))
        for _r in _todos:
            _r["exp"] = max(0, _r["exp"] - _desc)
        log("LOBBY", f"  ★ cooperativo: -{_desc} de exp ({len(_todos)} jugadores)")
    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★ LOS RATES DE EVENTO — el `.rate exp 2.0` de un GM (2026-09-14)
    # ═══════════════════════════════════════════════════════════════════════════════════════════
    #   ⚠⚠ VAN ACÁ Y NO EN EL COBRO, Y ES LA PARTE IMPORTANTE. Estos diccionarios son LOS MISMOS
    #     objetos que después se cobran (`_todos = list(CARRERAS[rid]["resultados"].values())`),
    #     así que tocarlos acá mueve **el número de la pantalla y el del saldo a la vez**.
    #     Si el rate se aplicara en el cobro, el cartel diría una cosa y la base guardaría otra —
    #     que es EXACTAMENTE el bug que este archivo ya se comió dos veces (la exp el 03-sep y el
    #     rcoin el 05-sep, los dos "se veían bien en pantalla, por eso nadie lo notó").
    #
    #   ★ Y van AL FINAL de toda la cadena, después del bono de sala y del descuento del
    #     cooperativo: un rate de evento multiplica **lo que el jugador iba a cobrar**, no un
    #     número intermedio. Si fuera antes, el bono de sala amplificaría el rate y el número
    #     dejaría de ser "el doble".
    # ★ La mascota va ANTES del rate de evento, y el orden importa: el bono de la mascota es del
    #   jugador (se lo ganó comprándola) y el rate es del server. Si un GM pone `.rate exp 2.0`,
    #   lo justo es que el doble caiga sobre lo que el jugador ya tenía derecho a cobrar — o sea
    #   que el rate multiplique a la mascota, no al revés. Es la misma lógica con la que el rate
    #   va después del bono de sala.
    aplicar_bono_de_mascota(_todos)
    aplicar_rates_de_evento(_todos, _rid28)
    # ★ EL PUESTO 7 ES "NO LLEGÓ" (medido: en los 13 carteles del referente, las filas con puesto 7
    #   traen `frame = 0xFFFFFFFF`). Los que llegaron van 1..6.
    # ★★★★★ LOS PUNTOS DE RANKING SON DOS ESCALERAS DISTINTAS (2026-09-05, de dos capturas del
    #   juego ORIGINAL). En SOLO bajan de 100 en 100 con el puesto (600·500·400·300·200·100).
    #   Por EQUIPOS no hay escalera: **700 a los del equipo ganador y 300 a los del perdedor**,
    #   plano, sin importar quién tocó mejor.
    #   ★ La captura del 3v3 lo deja clarísimo: los perdedores tenían MÁS combo (236 contra 137) y
    #     mejor estrella (100 % contra 90 %), y perdieron sólo por TIEMPO. Esta columna premia el
    #     RESULTADO, no el desempeño — que es lo que uno espera de una carrera de postas.
    _por_equipos = _es_equipo28
    # ★★★★★ EL QUE SE FUE NO VA EN EL CARTEL — Y SI VA, MATA A TODA LA SALA (2026-09-10).
    #
    #   ⛔⛔ MEDIDO EN PROD, con su control, sobre 909 carteles de una corrida de 5 h:
    #
    #        filas  jugadores   veces   muertes en <=4 s   por vez
    #            2          2     114                  2      0.02
    #            3          3     105                  1      0.01
    #            4          4     133                  2      0.02
    #            5          5     143                  5      0.03
    #            6          6     391                 11      0.03
    #            6          7      12                  1      0.08     (12 con espectadores: inocuo)
    #        ─────────────────────────────────────────────────────
    #            5          4       1                  4      4.00  ← LA SALA ENTERA
    #            6          5       1                  5      5.00  ← LA SALA ENTERA
    #
    #   Dos casos de `filas > destinatarios` en toda la corrida y los dos se llevaron puesta a la
    #   sala COMPLETA, en menos de dos segundos, contra un fondo de 0,02 muertes por cartel. No hay
    #   que discutirlo: 9 de las 96 desconexiones del día salieron de estas dos líneas.
    #
    #   ★ Los dos son el MISMO jugador (usn 7371) y el MISMO asiento (slot 5): se le cortó la
    #     conexión justo DESPUÉS de reportar su `FF28` y ANTES de que cerrara el cartel.
    #     A las 20:18:14 en la sala 1 y a las 22:36:20 en la sala 10. Cuatro y cinco muertos.
    #
    #   ★★ CÓMO LLEGA A SER LETAL. Son dos listas distintas y nadie las cruzaba:
    #        · `_dest28`  sale de `_esperados`, que YA descarta al que no tiene conexión viva.
    #        · `_todos`   sale de `resultados`, que guarda lo que cada uno reportó DURANTE la
    #                     carrera y no se entera de que uno se cayó después.
    #      Entremedio, al soltarse la conexión, se difundió el `FF0E quitar ocupante` (está en el
    #      log, dos segundos antes en los dos casos). O sea: al cliente le sacamos el ocupante del
    #      asiento y acto seguido le mandamos un cartel con una fila que apunta a ese asiento.
    #      Muere sin excepción y sin crashdump, igual que el desborde del chart.
    #
    #   ⚠ NO se toca el cobro: la exp y el rcoin salen de `CARRERAS[rid]["resultados"]` por otro
    #     camino (`_pagar`, más abajo), así que el que se cayó COBRA IGUAL lo que hizo. Esto sólo
    #     decide qué se DIBUJA. Y por eso el filtro va acá y no sobre `_todos`: arriba se aplican el
    #     bono de sala y el descuento del cooperativo, y esos tienen que seguir viéndolo a él.
    #
    #   ⚠ Se conserva el PUESTO real: si el 2º se fue, los demás siguen siendo 1º, 3º, 4º… Quedar
    #     con un hueco en la numeración es cosmético; renumerar sería mentirle al que salió 3º.
    _vivos28 = None
    if _rid28 is not None:
        _vivos28 = {_s for _s, _u in mesa_de(_rid28).items()
                    if (CONEXIONES.get(_u) is not None
                        and not getattr(CONEXIONES.get(_u), "cerrado", False))}
        # ★ (11-oct) UN NPC NO TIENE CONEXIÓN y nunca se le mandó el `FF0E` que vacía su asiento: su fila es
        #   segura. Sin esto las filas de los NPC que juegan (`npc_carrera`) salían todas «⛔SACADA (se
        #   desconectó)» y el cartel quedaba con una sola fila. Sólo hay NPC en LOCAL.
        if CHASE_NPC_REALISTA:
            _vivos28 |= set(npcs_de(_rid28) or ())
    _mostrar28 = [r for r in _todos if _vivos28 is None or r["slot"] in _vivos28]
    _sacadas28 = [r["slot"] for r in _todos if _vivos28 is not None and r["slot"] not in _vivos28]
    if _sacadas28:
        log("LOBBY", f"  ⛔⛔ CARTEL: saco la(s) fila(s) del/de los slot(s) {_sacadas28} — se "
                     f"soltó/soltaron la conexión después de reportar. Al cliente ya le mandamos "
                     f"el FF0E de ese asiento; una fila que lo apunte MATA a toda la sala "
                     f"(medido 2026-09-10). Cobran igual: el pago no pasa por acá.")
    # ★★★★★ EL SORTEO DE LA CAMPANA SE HACE ACÁ, UNA VEZ, ANTES DE ARMAR LAS FILAS — 2026-09-15.
    #   El **premio gordo es de UNO SOLO** (dictado por anonimo03: *"sólo la plata+ lleva el premio
    #   gordo"*), y para elegirlo hace falta saber quiénes jugaron. Si cada fila se sorteara sola
    #   no habría forma de que exactamente una se lo lleve.
    if _rid28 is not None:
        try:
            from .lobby_campana import preparar_campana
            preparar_campana(_rid28, [r.get("usn") for r in _mostrar28 if r.get("usn")])
        except Exception as _e_prep:                                 # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude sortear el bono de la campana: {_e_prep!r}")
    # ★ Lo que las PROFECÍAS necesitan saber de la carrera, una sola vez: cuántos corrieron (con
    #   cuenta: los NPC no son rivales) y qué canción (la de la SALA, igual que el `FF25`).
    _ctx_prof = {"coop": _es_chase, "equipo": _es_equipo28,
                 "jugadores": len({r["usn"] for r in _todos if r.get("usn") is not None}),
                 "cancion": ((seleccion_de(_rid28)["cancion"] if _rid28 is not None else 0)
                             or getattr(st, "room_song", DEFAULT_ROOM_SONG))}
    # ★ EL PUESTO DE CADA ASIENTO, con la MISMA regla que la fila del cartel (abajo), para el récord
    #   del cobro (`medallas.contar_carrera`): el pago recorre otra lista y no ve `_puesto`.
    _puestos28 = {r["slot"]: (r["puesto"] if r.get("puesto")
                              else (7 if r.get("fallo") else min(6, i + 1)))
                  for i, r in enumerate(_todos)}
    _filas = []
    _c12 = []                                   # (fila, puesto real, puntos de ranking) para el cartel de 12
    for i, r in enumerate(_todos):
        if _vivos28 is not None and r["slot"] not in _vivos28:
            continue
        _puesto = (r["puesto"] if r.get("puesto")
                   else (7 if r.get("fallo") else min(6, i + 1)))
        _rb = None
        # ★ El que NO LLEGÓ cobra el mínimo de la escalera, no los puntos de su equipo. Sin esto,
        #   en modo equipo el que abandonaba se llevaba los mismos 300 que sus compañeros, que sí
        #   terminaron la canción.
        if r.get("fallo"):
            pass
        elif _por_equipos and _rid28 is not None and _winteam28:
            _rb = (RANK_BONUS_GANADOR if equipo_de(_rid28, r["slot"]) == _winteam28
                   else RANK_BONUS_PERDEDOR)
        # ★ Las tres columnas del cooperativo salen de lo que contamos durante la carrera.
        #   Fuera del cooperativo va `None` y la fila queda como siempre (todo en cero).
        _cuentas = (cuentas_del_cartel(_rid28, r["slot"])
                    if (_es_chase and _rid28 is not None) else None)
        # ★★★ EL BONO DE PAREJA. Se calcula acá y se guarda en la propia fila de resultados, para
        #   que el PAGO de más abajo use exactamente el mismo número que el cartel. Si se
        #   recalculara allá, cualquier diferencia dejaría la pantalla y el saldo en desacuerdo —
        #   que es el bug que ya tuvimos con la exp y con el rcoin.
        # ★★ Los dos bonos se SUMAN en la misma fila: son renglones distintos del cartel y no se
        #   pisan. Un jugador puede correr con su pareja **y** con un amigo del alma a la vez.
        # ★★★★★ Y LA CAMPANA ES OTRO RENGLÓN MÁS — 2026-09-15. anonimo03: *"es un bonus como el de
        #   pareja, o como el de joya de amistad, pero ligado a la presencia del ítem en la
        #   sala"*. Exacto: `bonus.xml` lo tiene con nombre (`bonustype 67 = 플래티넘벨`).
        #   ⚠ Los tres se SUMAN en la misma fila: son renglones distintos y no se pisan.
        _bono_camp = []
        if _rid28 is not None:
            try:
                from .lobby_campana import bono_de_campana
                _bono_camp = bono_de_campana(_rid28, r)
            except Exception as _e_bc:                               # noqa: BLE001
                log("LOBBY", f"  ⚠ no pude armar el renglón de la campana: {_e_bc!r}")
        r["bono_pareja"] = _bono = (_bono_de_pareja(r, _mostrar28)
                                    + _bono_del_alma(r, _mostrar28) + _bono_camp
                                    + _bono_heroe(r) + _bono_profecia(r, _puesto, _ctx_prof)
                                    + _bono_cupon(r, _ctx_prof) + _bono_circulo(r))
        _filas.append(build_ff28_fila(0xFFFFFFFF if r.get("fallo") else r["frame"],
                                      r["combo"], r["pd"], r["star"], r["coin"], r["exp"],
                                      r["perdio"], slot=r["slot"], puesto=_puesto,
                                      rank_bonus=_rb, cuentas=_cuentas, bonus=_bono,
                                      # ★ Las milésimas son DE ESE JUGADOR, no del que pide el
                                      #   cartel: cada fila lleva las suyas y así todos ven los
                                      #   decimales de todos. `r` es la fila de él.
                                      milesimas=r.get("milesimas", 0),
                                      # ★ El medallón del cooperativo sale de la captura, no de
                                      #   la precisión. Cada fila lleva SU ronda: si algún día se
                                      #   quiere premiar distinto al que lo atrapó, el dato ya está.
                                      ronda_captura=r.get("ronda_captura"),
                                      es_coop=bool(getattr(st, "room_colab", False))))
        _c12.append((r, 0 if r.get("fallo") else (r.get("puesto") or i + 1),
                     _rb if _rb is not None else RANK_BONUS_POR_PUESTO.get(_puesto, 100)))
    # ★ El grado sale de la PRIMERA FILA QUE SE DIBUJA, no del primero de `_todos`: si el que ganó
    #   se cayó, su fila ya no está y el encabezado tiene que hablar del que sí quedó arriba.
    _grado = (grado_de(_mostrar28[0]["pd"], _mostrar28[0]["perdio"]) if _mostrar28
              else (grado_de(_todos[0]["pd"], _todos[0]["perdio"]) if _todos else 0x46))
    # ★★★★★ EL EQUIPO GANADOR — byte0 del cartel. ANTES ERA LA CONSTANTE `FF28_WINTEAM = 0`, y
    #   como nuestros equipos son **1 y 2**, el 0 no era el de nadie ⇒ el cliente comparaba y a
    #   TODOS les salía "perdiste". Síntoma exacto que reportó el usuario, y determinista.
    #   MEDIDO sobre los 13 carteles del referente: los 3 de modo equipo traen `b0` = el equipo del
    #   puesto 1 (ganó slot 4 -> b0=2 · ganó slot 0 -> b0=1, dos veces). 3 de 3, y con NUESTRO
    #   reparto por asiento. El server del CBT hace la misma cuenta en una línea
    #   (`1 if ranked[0]["pos"] < 3 else 2`), que es idéntica a `equipo_por_defecto`.
    #   En solo/cooperativo va 0, como el referente (10 de 13 carteles con la cabecera en ceros).
    # ★★★★★ `b1` y `b2` = EL MARCADOR DE LA SERIE: victorias del equipo 1 y del equipo 2, que el
    #   cliente dibuja como **"b1 - b2"**. Lo cazó el usuario en pantalla (2026-09-04): *"existe un
    #   contador de wins de cada equipo... salió como 0 - 1"* — y salió así porque yo estaba
    #   mandando `b1=0, b2=1` FIJOS, creyendo que `b2` era una bandera de "modo equipo".
    #   ⛔ Mi lectura anterior era doblemente equivocada: dije que `b2` era la bandera del overlay y
    #      que `b1` "parecía una racha". Con el marcador, el corpus se explica ENTERO y sin sobras:
    #        (b0=2, b1=0, b2=1)  ganó el equipo 2  ->  0 - 1
    #        (b0=1, b1=1, b2=1)  ganó el equipo 1  ->  1 - 1
    #        (b0=1, b1=2, b2=1)  ganó el equipo 1  ->  2 - 1
    #      Son tres partidas seguidas de la misma sala: es el marcador acumulado, y por eso el `0x4FD620`
    #      del handler corre "si b1 O b2 != 0" — o sea, en cuanto hay algo que mostrar.
    #   ★ Se incrementa ANTES de armar el cartel: en el corpus, la partida que ganó el equipo 2 YA
    #     mostraba `0 - 1`, con esa victoria contada.
    # ★ El RELEVO cuenta como equipo acá: se juega 2v2 o 3v3, tiene equipo ganador y tiene
    #   marcador de serie. Y NO trae el bit `MODE_EQUIPO` puesto — el decoder del cliente
    #   (`0x46BBF0`) mira el relevo ANTES que el equipo y le da `CooperationMode = 2`, así que el
    #   bit de equipo ni aparece. Sin este `or`, el cartel de relevo salía con `b0 = 0` = "perdiste
    #   a todos", que es exactamente el bug que ya arreglamos para el modo equipo.
    _m1 = _m2 = 0
    _cuatro = None                                   # ★ 14-oct: el marcador de los 4 equipos del relevo de 12
    if _es_equipo28 and _rid28 is not None:
        from .salas import es_cuatro12
        with _mesa_lock:
            _marc = MARCADOR.setdefault(_rid28, {1: 0, 2: 0})
            for _e4 in (3, 4):
                _marc.setdefault(_e4, 0)
            if _winteam28 in (1, 2, 3, 4):
                _marc[_winteam28] = min(0xFF, _marc[_winteam28] + 1)
            _m1, _m2 = _marc[1], _marc[2]
            if es_cuatro12(_rid28):                  # ★ 15-oct: también el equipo de 4
                _cuatro = [_marc[1], _marc[2], _marc[3], _marc[4]]
    body = build_ff28_multi(_filas, _grado, winteam=_winteam28, b1=_m1, b2=_m2)
    # ★★ EL CARTEL DE 12 (11-oct): sus datos van PEGADOS detrás del grado (lo último que lee el juego) y los
    #   dibuja la dll encima del de fábrica, que es de 6. Contrato y porqué: `cartel12.py`.
    if _rid28 is not None and asientos_de_la_sala(_rid28) == 12 and _c12:
        try:
            from . import cartel12
            with _mesa_lock:
                _car12 = dict(CARRERAS.get(_rid28) or {})
            _cn12 = int(_car12.get("cancion") or _ctx_prof.get("cancion") or 0)
            _npc12 = list(npcs_de(_rid28) or ())
            _f12 = []
            # ★ 15-oct · EL EQUIPO DE 4 (EQUIPOS_4.md): el cartel de 4 equipos (cartel12.c, con la cola E4) agrupa los
            #   puestos de a 3 por equipo — 1-2-3 el ganador, 4-5-6 el 2.º… — como el relevo de 12. El orden de los
            #   equipos: el ganador (el 1.º que metió a sus 3), después los que metieron más y, empatados, el que
            #   completó antes; adentro, por llegada. Sólo el cartel: el pago y el récord siguen con el puesto real.
            _pu4 = {}
            if _cuatro is not None and not (getattr(st, "room_mode", 0) & MODE_RELEVO):
                _lleg4 = {}
                for _k4, _r4 in enumerate(_todos):
                    if not _r4.get("fallo"):
                        _lleg4.setdefault(equipo_de(_rid28, _r4["slot"]), []).append((_k4, _r4["slot"]))
                _ord4 = sorted(_lleg4, key=lambda e: (e != _winteam28, -len(_lleg4[e]), _lleg4[e][-1][0]))
                for _rk4, _e4 in enumerate(_ord4):
                    for _j4, (_k4, _sl4) in enumerate(_lleg4[_e4]):
                        _pu4[_sl4] = 3 * _rk4 + _j4 + 1
                log("LOBBY", "  ★ EQUIPO DE 4 — el cartel por equipos: " + " · ".join(
                    f"{_e4}:{[_s for _, _s in _lleg4[_e4]]}" for _e4 in _ord4))
            for _r, _pu, _rk in _c12:
                if _pu and _r["slot"] in _pu4:
                    _pu = _pu4[_r["slot"]]
                _ap = (f"NPC{_npc12.index(_r['slot']) + 1}" if _r.get("usn") is None and _r["slot"] in _npc12
                       else (db_get_char(int(_r["usn"])) or {}).get("nick", "") if _r.get("usn") else "?")
                _f12.append(cartel12.fila(
                    _r["slot"], _pu, (equipo_de(_rid28, _r["slot"]) or 0) if _es_equipo28 else 0, _ap,
                    0xFFFFFFFF if _r.get("fallo") else _r["frame"], _r["exp"], _rk,
                    int(_r["pd"]) * 1000 + int(_r.get("milesimas", 0) or 0), _r["star"], _r["combo"],
                    int(_r.get("coin") or 0) + FF28_BASECOIN))
            body += cartel12.cola(_es_equipo28, _winteam28 or 0, _m1, _m2, _cn12, notas.nivel_de(_cn12, 0),
                                  int(_car12.get("pista") or 0), notas.titulo_de(_cn12), _f12, cuatro=_cuatro)
            log("LOBBY", f"  ★ cartel de 12: cola C2 de {len(_f12)} filas pegada al FF28 ({len(body)} B en total)")
        except Exception as _e12:                                     # noqa: BLE001
            log("LOBBY", f"  ⚠ el cartel de 12 (la cola C2): {_e12!r}")
    if _es_equipo28:
        log("LOBBY", f"  ★★★ CARTEL DE EQUIPO: gana el equipo {_winteam28 or '(nadie llegó)'} "
                     f"(puesto 1 = slot {_todos[0]['slot']}) -> b0={_winteam28} · "
                     f"MARCADOR de la sala {_rid28}: {_m1} - {_m2}" + (f" (los 4: {_cuatro})" if _cuatro else ""))
    # ★ EL CARTEL SALE EN HEX AL LOG. Cuesta una línea y ahorra corridas enteras: con las
    #   centinelas prendidas, poder cruzar la FOTO contra los BYTES exactos es la diferencia entre
    #   mapear una columna y quedarse discutiendo si un "245" era "2" + "45". (2026-09-05: pasó.)
    # ★★★ EL RECUENTO DE EFECTOS DE LA CARRERA, al log. Es lo único que falta para llenar las
    #   tres columnas del cartel de cooperativo: saber QUÉ id es el impulsor y cuáles son los
    #   ítems de grupo. Con esto, UNA partida usando el impulsor a propósito lo resuelve.
    #   Ver `EFECTOS_COOP` en `carrera.py` para el porqué entero.
    if _es_chase and _rid28 is not None:
        _ef = efectos_de(_rid28)
        for _sl_ef in sorted(_ef):
            _d = _ef[_sl_ef]
            def _nom(k):
                _e = COOP_NOMBRES_EFECTO.get(k)
                if _e:
                    return f"id {k} = {_e}"
                if k in COOP_EFECTOS_AYUDA:
                    return f"id {k} = AYUDA"
                return f"id {k} = ⚠ SIN IDENTIFICAR"
            _ids = ", ".join(f"{_nom(k)}×{v}" for k, v in sorted(_d["ids"].items(),
                                                                 key=lambda kv: -kv[1]))
            log("LOBBY", f"  ★★ EFECTOS del slot {_sl_ef}: {_d['total']} en total · "
                         f"{_d['a_otros']} apuntados a OTRO jugador · [{_ids}]")
            # ★★ LA SECUENCIA, NUMERADA. Es lo único que hace falta cuando el usuario no puede
            #   elegir qué ítem le toca (salen al azar) pero sí puede anotar el ORDEN en que los
            #   usó. Se numera 1, 2, 3… a propósito: así su lista y ésta se cruzan renglón a
            #   renglón, sin contar con el dedo. Ver `COOP_ITEMS_Y_CONTADORES.md` §5.
            _orden = _d.get("orden") or []
            if _orden:
                log("LOBBY", f"     ★ SECUENCIA de {len(_orden)}, en orden de uso "
                             f"— cruzá esto contra tu lista:")
                for _n_ef, _ev in enumerate(_orden, 1):
                    # compat: antes se guardaba sólo el id
                    _kid, _dst = _ev if isinstance(_ev, tuple) else (_ev, None)
                    _a_otro = ("" if _dst is None or _dst == _sl_ef
                               else f"   → apuntado al slot {_dst}")
                    log("LOBBY", f"        {_n_ef:>2}) {_nom(_kid)}{_a_otro}")
        if not _ef:
            log("LOBBY", "  ★★ EFECTOS: no llegó ninguno en esta carrera.")
        olvidar_efectos(_rid28)
    log("LOBBY", "  ★ FF28 body: " + " ".join(f"{b:02x}" for b in body))
    # ⛔⛔ EL CINTURÓN, además del tirante. El filtro de arriba trabaja con la mesa y las conexiones
    #   leídas en ESE instante; si alguien se suelta entre aquella lectura y este envío, la fila de
    #   más vuelve a colarse. Acá ya no hay nada que recalcular, así que lo único honesto es NO
    #   mandar el paquete: un cartel que no llega deja a la sala clavada 12 s hasta el reloj, y un
    #   cartel con una fila de más la mata entera. Entre las dos, la primera se arregla sola.
    if _rid28 is not None and _mostrar28:
        _ahora28 = {_s for _s, _u in mesa_de(_rid28).items()
                    if (CONEXIONES.get(_u) is not None
                        and not getattr(CONEXIONES.get(_u), "cerrado", False))}
        if CHASE_NPC_REALISTA:                     # (11-oct) el NPC tampoco tiene conexión acá: ver `_vivos28`
            _ahora28 |= set(npcs_de(_rid28) or ())
        _tarde28 = [r["slot"] for r in _mostrar28 if r["slot"] not in _ahora28]
        if _tarde28:
            log("LOBBY", f"  ⛔⛔⛔ NO MANDO EL CARTEL: el/los slot(s) {_tarde28} se soltó/soltaron "
                         f"ENTRE el filtro y el envío, y su fila ya está adentro del paquete. "
                         f"Mandarlo mata a la sala entera (medido 2026-09-10: dos salas, nueve "
                         f"muertos). Se cae el cartel; el cobro de exp/rcoin sigue igual.")
            _dest28 = []
    for _c in _dest28:
        try:
            _c.send_ff55(0x28, body, name=f"FF28 CARTEL {len(_filas)} fila(s) ({len(body)}B)")
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandar el cartel a usn={getattr(_c,'usn','?')}: {e!r}")
    # ★★★ PERSISTIR LA EXPERIENCIA (2026-09-03) — esto FALTABA.
    #   El cartel calculaba la exp con el multiplicador del cooperativo y el bono de sala,
    #   la mandaba, y nunca tocaba la base: `db_add_exp` tenía UN solo llamador y era
    #   `misiones.py`. O sea que jugar no daba experiencia; al reloguear, la partida no
    #   había existido. Se veía bien en pantalla, que es por lo que nadie lo notó.
    #
    #   Se guarda EXACTAMENTE lo que se muestra, y por eso va acá: después del bono de
    #   sala y del castigo por derrota, con la misma lista que arma las filas.
    #
    #   ⚠ SE COBRA UNA SOLA VEZ. El `pop` del diccionario de resultados está dentro del
    #     candado, así que si dos jugadores completan el cartel a la vez sólo uno se lleva
    #     el diccionario y sólo él paga. El cliente reintenta el `FF28` (lo hace), y sin
    #     esto cobraría de nuevo en cada reintento.
    if _rid28 is not None:
        with _mesa_lock:
            _pagar = CARRERAS.get(_rid28, {}).pop("resultados", None) or {}
        _pagar = list(_pagar.values())
    else:
        # Un solo jugador: no hay estado de sala donde apoyarse, así que el candado es la
        # propia conexión. `frame` identifica la corrida y cambia con cada partida.
        _pagar = [] if getattr(st, "exp_cobrada", None) == frame else _todos
        st.exp_cobrada = frame
    # ★★★ Y EL RCOIN TAMBIÉN (2026-09-05) — le faltaba la mitad a esto.
    #   El 03-sep se arregló que la exp se guardara; el **rcoin del cartel seguía sin persistir**,
    #   así que jugar mostraba un premio en pantalla y al reloguear no había existido. Mismo bug
    #   que la exp, misma función, y quedó vivo dos días más porque nadie mira el saldo.
    #   ⚠ Se guarda EXACTAMENTE lo que dice el cartel: `coin` (lo que juntó en la pista) +
    #     `FF28_BASECOIN` (el fijo nuestro). Si acá se guardara otra cosa, el número de la pantalla
    #     y el de la DB se separarían y no habría forma de saber cuál está bien.
    for _r in _pagar:
        if _r.get("usn") is None:
            continue
        # ★★ El bono de pareja se PAGA además de dibujarse. Sale de la MISMA lista que se metió
        #   en la fila del cartel, no de un recálculo: así el número de la pantalla y el del saldo
        #   no se pueden separar. Es la lección de la exp y del rcoin, que ya nos mordió dos veces.
        _bp = dict(_r.get("bono_pareja") or ())
        # ★★★★★ La campana de PLATA paga EXPERIENCIA, y va en la misma suma que todo lo demás.
        #   ⛔ Estuvo yendo a `db_add_rpoint` —la columna que no lee nadie— exactamente como le
        #     pasó a la exp de las cajas del gorila el 2026-09-10. Lo cazó anonimo03 de una línea:
        #     *"rpoint es EXP corazón, lo pagamos en el modo gorila"*.
        _xp_camp = sum(int(_v) for _t, _v in (_r.get("bono_pareja") or ())
                       if int(_t) in _BONUSTYPES_CAMPANA)
        # ★ Y los del MODO HÉROE (EXP, `bonustype` 41/42/43/53): de la MISMA lista que se dibujó.
        from .ajustes import BONO_HEROE
        _tipos_heroe = {t for t, _v in BONO_HEROE.values()}
        _xp_heroe = sum(int(_v) for _t, _v in (_r.get("bono_pareja") or ()) if int(_t) in _tipos_heroe)
        # ★ Y las PROFECÍAS: EXP (59/61/63) acá y Rcoin (60/62/64) abajo, de la MISMA lista.
        from .ajustes import PROFECIAS
        _tipos_prof_xp = {te for _q, te, _tr in PROFECIAS.values()}
        _tipos_prof_rc = {tr for _q, _te, tr in PROFECIAS.values()}
        _xp_prof = sum(int(_v) for _t, _v in (_r.get("bono_pareja") or ()) if int(_t) in _tipos_prof_xp)
        # ★ Y los CUPONES DE PREMIO: EXP Up (9) y derrota (58) acá, Coin Up (10) abajo, de la MISMA lista.
        from .ajustes import BONO_DERROTA, CUPONES_PREMIO
        _tipos_cup_xp = ({t for q, t in CUPONES_PREMIO.values() if q == "exp"}
                         | {t for t, _v in BONO_DERROTA.values()})
        _tipos_cup_rc = {t for q, t in CUPONES_PREMIO.values() if q == "rcoin"}
        _xp_cup = sum(int(_v) for _t, _v in (_r.get("bono_pareja") or ()) if int(_t) in _tipos_cup_xp)
        # ★ Y el BONO DE CÍRCULO (EXP, `bonustype` 70), de la MISMA lista.
        from .ajustes import CIRCULO_BONO_TIPO_EXP
        _xp_circ = int(_bp.get(CIRCULO_BONO_TIPO_EXP, 0))
        _xp28 = (int(_r.get("exp") or 0) + int(_bp.get(PAREJA_BONO_TIPO_EXP, 0)) + _xp_camp
                 + _xp_heroe + _xp_prof + _xp_cup + _xp_circ)
        if _xp28:
            _saldo = db_add_exp(_r["usn"], _xp28)
            # ⚠ El renglón dice de DÓNDE sale cada parte. Antes decía sólo el total y anonimo03 creyó
            #   que el bono no se había sumado — estaba sumado, lo que faltaba era decirlo.
            log("LOBBY", f"  ★ exp guardada: usn={_r['usn']} slot={_r['slot']} +{_xp28} "
                         f"(carrera {_r.get('exp')}"
                         + (f" + BONO PAREJA {_bp[PAREJA_BONO_TIPO_EXP]}"
                            if _bp.get(PAREJA_BONO_TIPO_EXP) else "")
                         + (f" + CAMPANA DE PLATA {_xp_camp}" if _xp_camp else "")
                         + (f" + MODO HÉROE {_xp_heroe}" if _xp_heroe else "")
                         + (f" + PROFECÍA {_xp_prof}" if _xp_prof else "")
                         + (f" + CUPÓN EXP UP / DERROTA {_xp_cup}" if _xp_cup else "")
                         + (f" + BONO DE CÍRCULO {_xp_circ}" if _xp_circ else "")
                         + f") -> {_saldo}")
        # ★★★★★ EL BONO DEL ALMA TAMBIÉN SE PAGA — 2026-09-15, y **lo cazó anonimo03 preguntando**:
        #   *"revisá el log para confirmar que se pagó"*. No se estaba pagando.
        #
        #   ⛔ El síntoma es el de manual: el renglón salía en el cartel y el log del pago decía
        #        `+600 (coin 0 + base 400 + BONO PAREJA 200)`
        #      …sin el `+100` del alma. **Se dibujaba y no se acreditaba** — exactamente
        #      [[dibujar-no-es-acreditar]], que este repo ya tiene anotado con esas palabras.
        #   ★★ La causa: esta suma tomaba **un solo bonustype** (el 5, el de pareja), y el del
        #      alma usa 132..136. Agregar el bono al cartel no lo agrega al bolsillo: son dos
        #      funciones distintas, y ésa es justo la trampa.
        #
        #   ⚠ Se suma **desde la misma lista que se dibujó**, igual que el de pareja: si acá se
        #     recalculara, el número de la pantalla y el del saldo podrían separarse y no habría
        #     forma de saber cuál está bien.
        _rc_alma = sum(int(_v) for _t, _v in (_r.get("bono_pareja") or ())
                       if ALMA_BONO_TIPO_BASE < int(_t) <= ALMA_BONO_TIPO_BASE + ALMA_BONO_NIVEL_MAX)
        # ★★ El bono de la campana de ORO también es Rcoin, y sale del MISMO renglón que se
        #   dibujó (bonustype 55 = 골든벨, `type="1"` = 알코인).
        _rc_camp = sum(int(_v) for _t, _v in (_r.get("bono_pareja") or ())
                       if int(_t) in _BONUSTYPES_CAMPANA_RCOIN)
        _rc_prof = sum(int(_v) for _t, _v in (_r.get("bono_pareja") or ()) if int(_t) in _tipos_prof_rc)
        _rc_cup = sum(int(_v) for _t, _v in (_r.get("bono_pareja") or ()) if int(_t) in _tipos_cup_rc)
        _rc28 = (int(_r.get("coin") or 0) + FF28_BASECOIN
                 + int(_bp.get(PAREJA_BONO_TIPO_RCOIN, 0)) + _rc_alma + _rc_camp + _rc_prof + _rc_cup)
        if _rc28:
            _rsaldo = db_add_rcoin(_r["usn"], _rc28)
            log("LOBBY", f"  🪙 rcoin guardado: usn={_r['usn']} slot={_r['slot']} +{_rc28} "
                         f"(coin {_r.get('coin')} + base {FF28_BASECOIN}"
                         + (f" + BONO PAREJA {_bp[PAREJA_BONO_TIPO_RCOIN]}"
                            if _bp.get(PAREJA_BONO_TIPO_RCOIN) else "")
                         # ★ El renglón dice de DÓNDE sale cada parte. Ese detalle es lo que
                         #   permitió ver que el bono del alma NO se estaba pagando: el total
                         #   solo no lo habría delatado. Un log que desglosa es un log que caza.
                         + (f" + BONO ALMA {_rc_alma}" if _rc_alma else "")
                         + (f" + CAMPANA DE ORO {_rc_camp}" if _rc_camp else "")
                         + (f" + PROFECÍA {_rc_prof}" if _rc_prof else "")
                         + (f" + CUPÓN COIN UP {_rc_cup}" if _rc_cup else "")
                         + f") -> {_rsaldo}")
        # ★ La carga del Coin Up se gasta ACÁ, donde se cobra (una vez), no donde se dibuja.
        try:
            _gastar_cupones(_r["usn"], _r.get("bono_pareja"))
        except Exception as _e_cup:                                  # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude gastar la carga del cupón de usn={_r['usn']}: {_e_cup!r}")
        # ★★ EL RÉCORD Y LAS MEDALLAS (24-sep): la carrera se suma al récord ACÁ, donde se cobra (una
        #   vez), con la EXP y los Rcoin TOTALES que se acaban de acreditar (la escalera 1 y 2 son «en
        #   una partida», y con bonos se llega: anonimo03 24-sep). Si cruza un escalón, el cartel `FFD1`.
        try:
            from . import medallas
            from .ajustes import MEDALLA_AVISO
            _ctx_rec = dict(_ctx_prof)
            _ctx_rec["gano_equipo"] = ((equipo_de(_rid28, _r["slot"]) == _winteam28)
                                      if (_es_equipo28 and _rid28 is not None and _winteam28) else None)
            _tot_c = notas.combo_total_de(_ctx_prof.get("cancion")) if _ctx_prof.get("cancion") else None
            _nuevas = medallas.contar_carrera(
                _r["usn"], _r, _puestos28.get(_r["slot"], 7), _ctx_rec, _xp28, _rc28, _tot_c)
            # ★ 15-oct: la MISIÓN DE HOY (2001…2010: jugar / ganar, equipo / solo, velocidad / ítem). No el cooperativo.
            try:
                if not _ctx_prof.get("coop"):
                    from . import mision_hoy
                    from .ajustes import MODE_VELOCIDAD
                    mision_hoy.fin_de_carrera(_r["usn"], bool(_es_equipo28),
                                              bool(getattr(st, "room_mode", 0) & MODE_VELOCIDAD),
                                              bool(_ctx_rec.get("gano_equipo")), _puestos28.get(_r["slot"], 7))
            except Exception as _e_mh:                               # noqa: BLE001
                log("LOBBY", f"  ⚠ misión de hoy (carrera) usn={_r['usn']}: {_e_mh!r}")
            # ★ 15-oct: las MISIONES PUZZLE verifican su FFB2 contra ESTA carrera (no le creen al cliente). `puzzle.py`.
            try:
                from . import puzzle
                from .ajustes import MODE_VELOCIDAD as _MV_PZ   # ⛔ con alias: un import local con el nombre
                #   de afuera lo vuelve LOCAL en toda h_21_ff28 (UnboundLocalError arriba). MODE_RELEVO ya es del módulo.
                with _mesa_lock:
                    _car_pz = dict(CARRERAS.get(_rid28) or {}) if _rid28 is not None else {}
                _modo_pz = getattr(st, "room_mode", 0)
                puzzle.fin_de_carrera(_r["usn"], {
                    "cancion": int(_car_pz.get("cancion") or _ctx_prof.get("cancion") or 0),
                    "pista": int(_car_pz.get("pista") or 0),
                    "velocidad": bool(_modo_pz & _MV_PZ),
                    "coop": ("C" if _ctx_prof.get("coop") else "R" if _modo_pz & MODE_RELEVO
                             else "T" if _es_equipo28 else "S"),
                    "jugadores": len(_todos), "puesto": _puestos28.get(_r["slot"], 7),
                    "gano_equipo": bool(_ctx_rec.get("gano_equipo")),
                    "pd": int(_r.get("pd") or 0), "star": int(_r.get("star") or 0), "combo": int(_r.get("combo") or 0),
                    "combo_total": _tot_c, "fallo": bool(_r.get("fallo"))})
            except Exception as _e_pz:                               # noqa: BLE001
                log("LOBBY", f"  ⚠ misión puzzle (carrera) usn={_r['usn']}: {_e_pz!r}")
            # ★ «MI RECORD» del picker (29-sep): la canción de la sala, una vez, acá donde se cobra.
            try:
                from .picker import contar_carrera as _contar_cancion
                _contar_cancion(_r["usn"], _ctx_prof.get("cancion"), _r, _tot_c)
            except Exception as _e_rc:                               # noqa: BLE001
                log("LOBBY", f"  ⚠ no pude anotar el récord de la canción de usn={_r['usn']}: {_e_rc!r}")
            _cx_med = CONEXIONES.get(_r["usn"])
            if _nuevas and MEDALLA_AVISO and _cx_med is not None and not getattr(_cx_med, "cerrado", False):
                _cx_med.send_ff55(0xD1, medallas.armar_ffd1(_nuevas),
                                  name=f"FFD1 ¡MEDALLA ADQUIRIDA! {_nuevas}")
            # ★ Y EL AVISO A TODO EL SERVER (`FF40` 0x36), sólo las que se anuncian (`MEDALLA_AVISO_GLOBAL`).
            _anun = [m for m in _nuevas if medallas.se_anuncia(m)]
            if _anun:
                _apodo = (db_get_char(int(_r["usn"])) or {}).get("nick", "")
                _n_avisos = 0
                for _cx_todos in list(CONEXIONES.values()):
                    if _cx_todos is None or getattr(_cx_todos, "cerrado", False):
                        continue
                    for _m in _anun:
                        _cx_todos.send_ff55(0x40, medallas.armar_ff40_36(_m, _apodo),
                                            name=f"FF40/0x36 AVISO GLOBAL: {_apodo} ganó la medalla {_m}")
                    _n_avisos += 1
                log("LOBBY", f"  📣 MEDALLA ANUNCIADA a {_n_avisos} conectado(s): {_apodo} -> {_anun}")
        except Exception as _e_rec:                                  # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude sumar el récord de usn={_r['usn']}: {_e_rec!r}")

    # ★★★★★ Y EL BONO DE LA CAMPANA SE CIERRA ACÁ — 2026-09-15, lo corrigió anonimo03 mirando la
    #   pantalla: *"el cartel de quién recibió el bono salió antes; éste recién debe salir al
    #   final de la partida"*. Y la descripción del ítem lo dice igual: «Si hace sonar la campana
    #   de plata **y comienza el juego**, todos reciben bonus…».
    #   ⚠⚠ El Rpoint ya se acreditó ARRIBA, desde el renglón del cartel, en el mismo bucle que la
    #     exp y el rcoin. Acá sólo sale el aviso y se borra la campana pendiente. Acreditar en
    #     dos lugares es exactamente cómo se separan la pantalla y el saldo — ya nos pasó dos
    #     veces (la exp y el rcoin del cartel).
    if _rid28 is not None and _pagar:
        try:
            from .lobby_campana import cerrar_campana
            cerrar_campana(_rid28, [r.get("usn") for r in _pagar if r.get("usn") is not None])
        except Exception as _e_camp:                                 # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude cerrar el bono de la campana: {_e_camp!r}")
    # ★ LOCAL: la carrera terminó ⇒ los NPC que juegan se paran (su reloj seguía mandando avances a un juego cerrado,
    #   3.ª prueba del relevo, 11-oct). Ver npc_carrera.olvidar.
    if CHASE_NPC_REALISTA and _rid28 is not None:
        try:
            from . import npc_carrera
            npc_carrera.olvidar(_rid28)
        except Exception as _e_npc:                                  # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude parar a los NPC: {_e_npc!r}")
    # ★ Este renglón es el que permitió medir el bug: trae filas Y destinatarios, y cruzándolos
    #   sobre toda una corrida saltó que `filas > destinatarios` era 100 % letal. Que siga saliendo
    #   así, y que las filas sacadas queden marcadas, para poder repetir la medición cuando haga falta.
    log("LOBBY", "  ★★ FF28 GAMEOVER -> cartel de %d fila(s) a %d jugador(es): %s"
                 % (len(_filas), len(_dest28),
                    ", ".join(f"#{i+1} slot {r['slot']} pd={r['pd']}"
                              # ★ Las milésimas SÓLO se nombran si llegaron. Un `.000` en cada
                              #   renglón de cada cartel, durante meses y sin parche de cliente,
                              #   es ruido; el día que aparezcan tienen que SALTAR.
                              + (f".{r['milesimas']:03d}" if r.get("milesimas") else "")
                              + f" combo={r['combo']}"
                              + (" ⛔SACADA (se desconectó)" if (_vivos28 is not None
                                                                and r['slot'] not in _vivos28)
                                 else "")
                              for i, r in enumerate(_todos))))
    # ⛔⛔⛔ ACÁ NO VA NADA MÁS. NO REPINTAR LA SALA AL CERRAR LA CARRERA (2026-09-04).
    #
    #   Estaban acá un `difundir_roominfo` y un `restaurar_musica` por ocupante, puestos para
    #   que el cartel de la música sobreviviera a la partida. **Se sacaron**, y el motivo es
    #   el que explica la intermitencia que se vio jugando (una carrera lo recuperaban casi
    #   todos, la siguiente algunos, la siguiente uno solo):
    #
    #   ★★ EL `FF13` DEL CLIENTE NO ES UN POLL: ES UN AVISO. Al salir a la carrera,
    #      `cRoom::Leave` (`0x540110`) **destruye** el mapa de ocupantes —no lo resetea:
    #      llama al destructor de cada uno—. Al volver, `cRoom::Enter` (`0x53A520`) emite el
    #      `FF13` que nos llega. O sea que ese pedido significa **"ya reconstruí la escena de
    #      la sala"**. Todo lo que mandemos ANTES aterriza en una sala que el cliente todavía
    #      no rearmó.
    #
    #   ⛔ Y no es que "no tenga efecto": el CBT lo dejó anotado con sangre, medido en vivo —
    #      *"el cliente está en la PANTALLA DE RESULTADO y recibir un `FF9B`/`FF13` ahí lo
    #      CRASHEA (capturado: la VM crasheó justo tras el cartel + FF9B)"*. Por eso allá el
    #      liderazgo diferido espera al `FF13` del cliente en vez de empujarlo.
    #      ⛔ (Se citó acá un `c0000005` de nuestro log del cliente como corroboración. NO
    #        vale: aparece en los SIETE clientes dentro de los mismos 6 segundos, o sea al
    #        CERRAR la sesión. Es un fallo de salida. La evidencia buena es sólo la del CBT.)
    #
    #   ★ El server de referencia hace lo mismo: entre el `FF28` y el `FF13` que pide el
    #     cliente **no manda un solo `FF13`** — y el cliente puede tardar 39 s en pedirlo
    #     (medido en `mitm_20260903_214324`).
    #
    #   ★★ POR QUÉ ERA INTERMITENTE, que es lo que lo confirma: en el camino de vuelta el
    #      cliente manda su propio `FF1C type 5` = `SetMusic(0)`, que le BORRA la canción. Si
    #      nuestro empujón llegaba antes de ese type 5, el type 5 lo borraba; si llegaba
    #      después, quedaba. Y cada jugador sale de la pantalla de resultado en un instante
    #      distinto ⇒ una carrera lo ganan casi todos, la siguiente algunos, la siguiente uno.
    #      Contenido correcto, carrera perdida contra el propio cliente.
    #
    #   ⇒ El camino bueno ya está implementado y es el de siempre: `h_19_ff13` responde el
    #     `FF13` cuando el cliente lo pide, y `h_20_ff0c` repone la música después. **El
    #     cliente pidió, nosotros contestamos** — no repintamos por las dudas.


def h_23_ff23(st, cmd, data):
    # rama original:  cmd == 35
    # C->S, MEDIDO, siempre 12 B. Ejemplos capturados:
    #     00 |00 00 84 c2| |00 00 04 c3| 00 00 00      -> x=-66   y=-132
    #     04 |00 00 46 43| |00 00 84 c2| 01 00 00      -> x=198   y=-66
    #     0a |00 00 00 00| |00 00 46 c3| 01 00 00      -> x=0     y=-198
    # ⇒ [kind:u8][x:f32][y:f32][3 bytes más]. Las coordenadas son múltiplos de 66 (una grilla) y
    #   el byte0 toma 00/02/04/08/0a = la dirección.
    # ★ NO viaja ningún slot: el emisor es implícito ("soy yo"). Para que el OTRO mueva el avatar
    #   correcto hay que decirle QUIÉN se movió, y eso lo agrega el server.
    # ⚠⚠ EL FORMATO DE VUELTA (S->C) ESTÁ SIN CONFIRMAR. En el CBT el S->C es el C->S con el
    #   **slot antepuesto**, pero allá el C->S mide 11 y acá mide 12, así que la analogía NO cierra
    #   sola — hay un agente desensamblando el handler RX del 0x23 en NUESTRO cliente. Mientras
    #   tanto se releva con la hipótesis del slot al frente, que es lo único que tiene sentido.
    _rid23 = getattr(st, "room_id", None)
    # ★★ LA SALA DE CONVERSACIÓN (24-sep): ahí no hay `room_id`; el movimiento va a los de la estancia.
    if _rid23 is None and getattr(st, "lugar_clave", None) is not None:
        from . import charla
        charla.reenviar_ff23(st, data)
        return
    # ★★★★ EL QUE MIRA NO MUEVE A NADIE — 2026-09-08.
    #   ⛔ El bug del avatar que camina: un espectador que se movía se relevaba como jugador y le
    #     movía el avatar a otro (su asiento viejo, o `HOST_SLOT` = el anfitrión). Se corta acá, en
    #     el emisor, que es el único lugar donde vale para todos los destinos.
    #   ⚠ El `st.room_slot = None` de la rama de espectador del `FF11` ya saca la causa de raíz;
    #     esto es el cinturón: aunque mañana alguien vuelva a dejar un asiento colgado, el que mira
    #     sigue sin poder mover nada. **Los espectadores RECIBEN movimiento, no lo EMITEN.**
    if getattr(st, "slot_espectador", None) is not None:
        log("LOBBY", f"  · FF23 de un ESPECTADOR (casillero {st.slot_espectador}): NO se releva "
                     f"(mira la sala, no camina en ella)")
        return
    if _rid23 is not None and len(data) >= 9:
        _mi = getattr(st, "room_slot", None)
        if _mi is None:
            _mi = HOST_SLOT
        _out = bytes([_mi & 0xFF]) + data if FF23_SLOT_AL_FRENTE else data
        _n = 0
        # ★ Y a los ESPECTADORES el movimiento: es LITERALMENTE lo que fueron a ver.
        #   Reportado: *"los espectadores no recibieron el sync de los que estan corriendo"*.
        # ⛔⛔ ACÁ IBA `data` EN VEZ DE `_out` — corregido 2026-09-08. `data` es el C->S CRUDO, que
        #   **no lleva el slot del que se movió** (el emisor es implícito, "soy yo"): el slot lo
        #   antepone el server, y es justo lo único que le dice al cliente A QUIÉN animar. Al
        #   espectador le llegaba el paquete un byte corto ⇒ leía el byte de dirección como si
        #   fuera el slot y las coordenadas corridas. Movimiento recibido, avatar equivocado.
        for _ce23 in espectadores_de(_rid23):
            try:
                _ce23.send_ff55(0x23, _out, name=RESUMIR)          # ★ alta frecuencia: resumido
            except Exception:
                pass
        for _usn in mesa_de(_rid23).values():
            # ★ NO se le devuelve al emisor: su avatar ya se movió local, y si el handler no tiene
            #   guard de "soy yo" (en el CBT NO lo tiene) se animaría a sí mismo como remoto.
            if _usn == getattr(st, "usn", None):
                continue
            _c = CONEXIONES.get(_usn)
            if _c is None or getattr(_c, "cerrado", False):
                continue
            try:
                _c.send_ff55(0x23, _out, name=RESUMIR)             # ★ alta frecuencia: resumido
                _n += 1
            except Exception as e:
                log("LOBBY", f"  ⚠ no pude relevar el FF23 a usn={_usn}: {e!r}")
        if _n:
            _x, _y = struct.unpack("<ff", data[1:9])
            log("LOBBY", f"  ★ FF23 slot={_mi} kind={data[0]} x={_x:.0f} y={_y:.0f}"
                         f" -> relevado a {_n}")


def h_24_ff59(st, cmd, data):
    # rama original:  cmd == 89
    # cada asset que no pudo cargar, en texto plano:
    #   [len:u16][ "USN:0 TIME:2026-7-30-2-58 SERVER:<canal>\n<clase>::<metodo> - <path>" ]
    # p.ej. "c2DImage::LoadImage - rnr_bg/back11/logo_lt.tga".
    # ★ VALE ORO PARA DIAGNOSTICAR: si mandamos un indice de pista equivocado, el FF59 nos dice el
    #   PATH EXACTO que falto -> se verifica la pista del chase sin adivinar ni parchear nada.
    txt = data[2:].decode("cp1252", "replace") if len(data) > 2 else data.decode("cp1252", "replace")
    # ★ 17-oct: la dll avisa que saca de la pista al que abandona en la de 12 (grande.c, gr_abandono) ⇒ a ése el
    #   FF0E en carrera le va en el momento (salas.difundir_salida). Por usn: sobrevive al cambio de canal.
    # ★ 06-nov (161): la misma línea dice también si el chart del FF57 puede pasar de 4096 (chart_grande.c):
    #   «R2DLL abandono12=1 chart64k=1» (cada cosa, si la trae). A la que no lo dice, el chart le va recortado.
    #   (Se busca en cualquier parte del texto, como antes: el exe le antepone «USN:… TIME:…» a lo que reporta.)
    _r2dll = re.search(r"R2DLL((?: \w+=\w+)+)", txt)
    if _r2dll and getattr(st, "usn", None):
        _trae = set(_r2dll.group(1).split())
        if "abandono12=1" in _trae:
            from .salas import DLL_ABANDONO
            DLL_ABANDONO.add(st.usn)
            log("LOBBY", f"  ★ usn={st.usn} trae la dll que saca al que abandona en la de 12: el FF0E en carrera le va en el momento")
        if "chart64k=1" in _trae:
            from .salas import DLL_CHART64K
            DLL_CHART64K.add(st.usn)
            log("LOBBY", f"  ★ usn={st.usn} trae la dll que recibe charts de más de 4096 B (chart_grande.c)")
        return
    for linea in txt.replace("\r", "").split("\n"):
        if linea.strip():
            log("LOBBY", f"  ⚠ FF59 CLIENTE REPORTA: {linea.strip()}")


def h_27_ff139(st, cmd, data):
    # rama original:  cmd == 313
    # El server debe RESPONDER un FF139 "PlayData" (handler recv 0x5DCD70 = "[MUSIC] PlayData Cmd") que fija la
    # canción de la sala y destraba el cartel "elija una música". Wire de la RESPUESTA = 7 campos (19B) leídos por
    # el cursor 0x67cfe0 en orden: [A:u16][B:u8][C:u16][D:u16][E:u32][F:u32][G:u32]. El aplicador 0x5BA510 tiene un
    # GATE: word[[0x9314ec]+4 deref]+0x594] == A1 (uno de estos campos) o NO aplica (this->0 no pasa a 2).
    # ★ PASO 1 (DIAGNOSTICO): mando CENTINELAS distintos por campo + Frida (trace_ff139.py) para mapear cada
    #   arg a1..a7 -> campo y leer el valor que el gate espera. Tras mapear, se pone el layout real.
    song = struct.unpack("<H", data[0:2])[0] if len(data) >= 2 else 0
    # ⚠ El FF139 es una CONSULTA (el cursor quieto ~1,5 s sobre una canción, `0x5BFC30`), no una
    #   elección. Esta línea queda porque el START cae a `room_song` si la sala no tiene canción.
    st.room_song = song
    if FF139_SENTINEL:
        pd  = struct.pack("<H", 0x1101)       # A u16 centinela
        pd += bytes([0x22])                    # B u8  centinela
        pd += struct.pack("<H", 0x3303)       # C u16 centinela
        pd += struct.pack("<H", 0x4404)       # D u16 centinela
        pd += struct.pack("<I", 0x55555555)   # E u32 centinela
        pd += struct.pack("<I", 0x66666666)   # F u32 centinela
        pd += struct.pack("<I", 0x77777777)   # G u32 centinela
    else:
        # ★ MAPEADO EN VIVO (trace_ff139, 2026-07-12): A (1er u16) = songid = LLAVE del gate 0x5BA510
        #   (gate exige A == songid que el cliente guardó local en [[0x9314ec]+4]+0x594). Al pasar -> this->0=2
        #   = "canción lista" -> destraba "elija una música". C/D/E/F/G = params de play (map/dif/mode) -> 0 por
        #   ahora (canción carga de la DB del cliente por A); refinar si la carga sale mal. B(u8) -> bool a5.
        # ★★ 29-sep: C/D/E/F/G NO son «params de play»: son «MI RECORD» de esa canción (mejor combo,
        #   precisión, veces) y su puesto de popularidad (`0x5B9C50`). Iban en 0. Ver `picker.playdata`.
        from .picker import playdata_con_top5          # ★ 09-oct: + el TOP 5 RANK de la canción (top5.c)
        pd = playdata_con_top5(int(getattr(st, "usn", 0) or 0), song)
    st.send_ff55(0x139, pd, name=f"FF139 PlayData reply song={song} sentinel={FF139_SENTINEL}")
    log("LOBBY", f"  ★ FF139 ROOM MUSIC pick song={song} -> PlayData reply {len(pd)}B (sentinel={FF139_SENTINEL})")


def h_28_ff1b(st, cmd, data):
    """`FF1B` CmdEditStage — el host eligió otra pista. `[u16 pista]`.

    ★★★ EL ECO DEL `FF1B` NO PUEDE FUNCIONAR, Y NUNCA PUDO (2026-09-04). El handler del
    cliente (`0x5C5400`) es, entero:

        mov ecx,[esp+0xc]   ; el lector (3er arg, la convención de todos los handlers)
        push 1 / lea eax,[esp+0x10] / push eax
        call 0x67d200       ; lee UN byte...
        ret 0xc             ; ...y lo tira. Fin.

    Es un **stub**: el cliente ignora el `FF1B` que recibe. No es que lo mandáramos mal —
    no hay forma de que sirva, aunque salga perfecto. Y el server de referencia lo confirma
    del otro lado: en `mitm_20260904_102312` recibe **4 `FF1B` y no contesta ni uno**.

    ⇒ La pista viaja en el **`FF13`, en el `@14`** (medido: `FF1B 63/0b/09` → el `FF13` de
      al lado sale con `@14 = 0x63/0x0b/0x09`, tres valores en el mismo orden). Era el plan
      del CBT que estaba anotado acá desde siempre —*"guardar room_map + reenviar FF13"*—
      y que quedó sin hacer porque faltaba justamente ese offset.

    ★ Y la pista se guarda EN LA SALA, no en `st`: era una copia por jugador, así que el
      host la cambiaba y el invitado seguía con la suya. Mismo error que ya se pagó con los
      NPC (ver `NPCS_SALA`).
    """
    stage = struct.unpack("<H", data[0:2])[0] if len(data) >= 2 else DEFAULT_ROOM_MAP
    _rid = getattr(st, "room_id", None)
    _usn = getattr(st, "usn", None)
    # ⛔⛔ SIN SALA (la PRÁCTICA) NO SE CONTESTA NADA (08-oct, 1ª prueba de la etapa 4). La práctica corre en el
    #   cliente (FF3A, sin FF25) y no es una sala: le mandábamos un FF13 de sala —con el modo de la última sala a la
    #   que había entrado, «equipo»— y el cliente se creía en una sala por equipos y NO ARRANCABA la práctica. Lo que
    #   se elige ahí lo resuelve la d3d9 (pista_propia.c / panel_sala.c); acá sólo se anota, como antes.
    if _rid is None:
        if not stage & 0x8000:
            st.room_map = stage
        log("LOBBY", f"  ★ FF1B sin sala (práctica) usn={_usn}: {stage:#06x} — nada que contestar (lo resuelve el cliente)")
        return
    # ★★★ LA PISTA PROPIA DEL INVITADO (2026-10-08). Hasta hoy sólo el anfitrión podía mandar esto (el exe le
    #   cerraba la ventana al invitado); desde la d3d9 `pista_propia.c` también lo manda el invitado. anonimo03:
    #   *"si el invitado no elige la suya, la que ponga el anfitrión sigue mandando, hasta que el invitado elija"*.
    #   ⇒ Lo del invitado es SUYO: se anota sólo para él, y el FF13 se le reemite SÓLO a él (con su pista en el
    #     @14). La sala no se entera. ⛔ NO se toca `st.room_map`: el FF25 lo lee de la conexión del que aprieta
    #     START, y un invitado que después pasa a anfitrión arrastraría su pista a toda la sala.
    # ★★★ LOS OBSTÁCULOS POR LA VENTANA (08-oct, etapa 4): la d3d9 (`panel_sala.c`) abre la misma ventana de
    #   pistas desde el recuadro «Obstáculos», y al confirmar manda el FF1B con el bit 0x8000. Es una elección
    #   PARA SÍ (anfitrión o invitado): lo del anfitrión es además lo que ven los que no eligieron, así que si
    #   lo cambia él se le reemite el FF13 a toda la sala; si lo cambia un invitado, sólo a él. La pista de la
    #   sala NO se toca (la ventana se quedó mostrando la de los obstáculos: el FF13 se la devuelve).
    if stage & 0x8000:
        _ob = stage & 0x7FFF
        from .ajustes import OBSTACULOS_2013
        if _ob != 0 and _ob not in OBSTACULOS_2013:
            log("LOBBY", f"  ⚠ FF1B obstáculos de usn={_usn}: la pista {_ob} no trae backNNN.txt -> ignorado")
            enviar_roominfo(st, motivo=" (obstáculos rechazados)")
            return
        poner_eleccion(_rid, _usn, "obstaculos", _ob)
        if _usn is not None and _usn == anfitrion_de(_rid):
            difundir_roominfo(_rid, motivo=" (OBSTÁCULOS del anfitrión)")
        else:
            enviar_roominfo(st, motivo=" (sus OBSTÁCULOS)")
        log("LOBBY", f"  ★★ FF1B OBSTÁCULOS usn={_usn}: {'aleatorios' if _ob == 0 else f'los de la pista {_ob}'} "
                     f"(sala {_rid})")
        return
    # ★★★ EL COOPERATIVO (09-oct): la pista que se elige en su mini-panel (la d3d9 abre la ventana NORMAL de
    #   pistas) va a `pista_coop`, aparte de la normal: así la de una carrera normal no le pisa la fija al chase, ni
    #   la del chase a la normal. Mismas reglas: el anfitrión la de la sala (y pisa el `.oscuro`), el invitado la suya.
    if getattr(st, "room_colab", False):
        if _usn is not None and _usn == anfitrion_de(_rid):
            poner_seleccion(_rid, pista_coop=stage)
            poner_eleccion(_rid, _usn, "pista_coop", None)
            if mapa_de_sala(_rid) is not None:
                poner_mapa_sala(_rid, None)
            difundir_roominfo(_rid, motivo=" (PISTA del cooperativo)")
        else:
            poner_eleccion(_rid, _usn, "pista_coop", stage)
            enviar_roominfo(st, motivo=" (su PISTA del cooperativo)")
        log("LOBBY", f"  ★★ FF1B COOPERATIVO usn={_usn}: pista {stage} "
                     f"({'de la sala' if _usn == anfitrion_de(_rid) else 'la suya'}, sala {_rid})")
        return
    if _rid is not None and _usn is not None and _usn != anfitrion_de(_rid):
        poner_eleccion(_rid, _usn, "pista", stage)
        enviar_roominfo(st, motivo=" (su PISTA PROPIA)")
        log("LOBBY", f"  ★★ FF1B del INVITADO usn={_usn}: su pista propia -> {stage} (sala {_rid}); "
                     f"FF13 sólo a él, la sala sigue con la suya")
        return
    st.room_map = stage                       # se deja por compatibilidad: lo lee el FF25
    poner_seleccion(_rid, pista=stage)
    # ★ Lo que elige el anfitrión ES la de la sala: si traía una propia de cuando era invitado, se le borra.
    poner_eleccion(_rid, _usn, "pista", None)
    # ★ ELEGIR PISTA EN PANTALLA PISA AL `.oscuro` (2026-09-07). Lo reportó el usuario: *"si el
    #   master usa el picker de mapas y cambia a otro = mapa oscuro debe ser pisado"*. Manda la
    #   ÚLTIMA acción del anfitrión, que es lo que uno espera: si el comando sobreviviera, elegir
    #   una pista en el menú no haría nada y parecería que el picker está roto.
    #   ⚠ Se limpia acá y no en el START: así el `FF13` que sale abajo ya lleva la pista de verdad
    #     y todos la ven en la sala, no recién al arrancar.
    _osc_previo = mapa_de_sala(_rid)
    if _osc_previo is not None:
        poner_mapa_sala(_rid, None)
    difundir_roominfo(_rid, motivo=" (cambio de PISTA)")
    log("LOBBY", f"  ★★ FF1B cambiar pista -> {stage}, y FF13 reemitido a la sala {_rid} "
                 f"({len(mesa_de(_rid)) if _rid else 0} ocupante/s). "
                 f"⛔ Sin eco del FF1B: su handler en el cliente es un stub."
                 + (f" · ★ el .oscuro ({_osc_previo}) queda PISADO por el picker"
                    if _osc_previo is not None else ""))


def rate_efectivo(que, rid=None):
    """El multiplicador que se le aplica de verdad a una carrera de la sala `rid`.

    ★★ Son DOS perillas y se MULTIPLICAN:
         · el global  (`.rate exp 2.0`)      -> todo el server
         · el de sala (`.rate sala exp 2.0`) -> sólo esa sala

      Multiplicar es lo que uno espera cuando pide "un extra encima del evento": con el evento en
      x2 y la sala en x2, esa sala paga x4.

    ⚠⚠ EL TOPE SE APLICA AL PRODUCTO, no a cada perilla. Si se acotara sólo por separado, dos
      x10 darían x100 y el tope no serviría para nada — que es justo lo que el tope tiene que
      impedir. Acotar al final es lo único que garantiza que NINGÚN camino pase de `RATE_MAX`.
    """
    return max(RATE_MIN, min(rate_de(que) * rate_sala_de(rid, que), RATE_MAX))


def aplicar_bono_de_mascota(filas):
    """El +% de exp y rcoin de la **mascota Gorila equipada**. Modifica las filas en el lugar.

    ★★★ NO ES UN NÚMERO NUESTRO: lo dice el propio juego, en la descripción del ítem
      (`string_lt/item.csv`, vía el `ItemEffect` de `shop_lt.txt`), palabra por palabra:

          600164 «Gorila Verde»    ItemEffect 1443 -> *"Recibe **15%** adicional en Exp y Rcoins
                                                       equipando este ítem."*
          600178 «Gorila Rosado»   ItemEffect 1450 -> *"Recibe **30%** adicional…"*

    ⛔⛔ Y NO SE PAGABA. Lo preguntó anonimo03: *"si podemos canjear la mascota de la moneda gorila
      pero no comprobé si su bono se está pagando"*. Estaba bien la sospecha: en todo el server
      había **una sola** mención a esos dos ids, y era la del canje en la tienda. El jugador
      gastaba sus monedas, se ponía la mascota y no cobraba un peso de más.

    ★★ SE APLICA A LA FILA, no al cobro. Es la misma razón que tiene escrita `aplicar_rates_de_evento`
      arriba: estos dicts son los MISMOS objetos que después se cobran, así que tocarlos acá mueve
      **el número de la pantalla y el del saldo a la vez**. Aplicarlo sólo al pagar sería el bug que
      este archivo ya se comió dos veces (la exp el 03-sep, el rcoin el 05-sep).

    ⚠ **EQUIPADA, no en el inventario.** El texto dice *"equipando este ítem"*: tenerla guardada no
      paga. Por eso se mira `parts` (lo que lleva puesto) y no el inventario.
    ⚠ Si alguien tuviera las dos puestas, se toma **la mejor** y no se suman: son la misma mascota
      en dos colores, y sumarlas sería pagar 45 % por un caso que el juego no contempla.
    """
    if not MASCOTA_GORILA_BONO:
        return filas
    for r in filas:
        _usn = r.get("usn")
        if not _usn:
            continue
        try:
            _puestas = set(int(p) for p in ((db_get_char(int(_usn)) or {}).get("parts") or []) if p)
        except Exception:                                        # noqa: BLE001
            continue
        _pct = max((p for i, p in MASCOTA_GORILA_BONO.items() if i in _puestas), default=0.0)
        if _pct <= 0:
            continue
        _xp0, _cn0 = int(r.get("exp") or 0), int(r.get("coin") or 0)
        r["exp"] = max(0, int(_xp0 * (1 + _pct)))
        # ⚠ Sobre `coin + FF28_BASECOIN`, que es lo que el jugador cobra de verdad — la misma
        #   corrección que ya pagaron caro el rate de monedas y el bono de pareja. Después se
        #   resta la base, porque la fila guarda `coin` SIN ella.
        r["coin"] = max(0, int((_cn0 + FF28_BASECOIN) * (1 + _pct)) - FF28_BASECOIN)
        log("LOBBY", f"  🦍 MASCOTA GORILA: usn={_usn} +{_pct:.0%} -> "
                     f"exp {_xp0}->{r['exp']} · coin {_cn0}->{r['coin']}")
    return filas


def aplicar_rates_de_evento(filas, rid=None):
    """Multiplica exp y monedas de cada fila por el rate vigente. **Modifica las filas en el lugar.**

    ⚠⚠ QUE MODIFIQUE EN EL LUGAR NO ES PEREZA: ES EL PUNTO. Estos diccionarios son LOS MISMOS
      objetos que después se cobran (`_todos = list(CARRERAS[rid]["resultados"].values())`), así
      que tocarlos acá mueve **el número de la pantalla y el del saldo a la vez**. Si el rate se
      aplicara en el cobro, el cartel diría una cosa y la base guardaría otra — que es EXACTAMENTE
      el bug que este archivo ya se comió dos veces (la exp el 03-sep y el rcoin el 05-sep, los
      dos *"se veían bien en pantalla, por eso nadie lo notó"*).

    ★ Se llama AL FINAL de toda la cadena, después del bono de sala y del descuento del
      cooperativo: un rate de evento multiplica **lo que el jugador iba a cobrar**, no un número
      intermedio. Si fuera antes, el bono de sala amplificaría el rate y ya no sería "el doble".

    ★ Y es una función con nombre, en vez de estar suelta en el medio del cartel, para que el
      banco de pruebas corra ESTO y no una copia de la cuenta. Ver `pruebas/probar_gm_y_rates.py`.
    """
    rexp = rate_efectivo("exp", rid)
    if rexp != 1.0:
        for r in filas:
            r["exp"] = max(0, int(int(r.get("exp") or 0) * rexp))
        log("LOBBY", f"  🎉 RATE: exp x{rexp:g}  (server x{rate_de('exp'):g}"
                     f" · sala x{rate_sala_de(rid, 'exp'):g})")
    rcoin = rate_efectivo("coin", rid)
    if rcoin != 1.0:
        # ⚠ El rate se aplica sobre lo que el jugador COBRA DE VERDAD, que es `coin + basecoin`
        #   (así lo arma el cartel y así lo guarda el cobro). Si multiplicáramos sólo `coin`, un
        #   `.rate coin 2.0` no daría el doble y nadie entendería por qué.
        # ⚠ Con un rate MENOR a 1 el resultado se acota en 0, o sea que **lo mínimo que se paga es
        #   el fijo** (`FF28_BASECOIN`). Es una limitación real, no un descuido: está acá dicha
        #   para que el día que alguien pruebe `.rate coin 0.1` y vea 35, sepa por qué.
        for r in filas:
            total = int(r.get("coin") or 0) + FF28_BASECOIN
            r["coin"] = max(0, int(total * rcoin) - FF28_BASECOIN)
        log("LOBBY", f"  🎉 RATE: monedas x{rcoin:g}  (server x{rate_de('coin'):g}"
                     f" · sala x{rate_sala_de(rid, 'coin'):g})")
    return filas


def aviso_sistema(st, texto):
    """Una línea de chat firmada SERVER. Sirve para lo que la tabla del cliente no dice."""
    _rb = texto.encode("cp1252", "replace")[:0xFF]
    _nk = b"SERVER"
    st.send_ff55(0x08, bytes([len(_nk)]) + _nk + bytes([len(_rb)]) + _rb + bytes([2, 0]),
                 name=f"FF08 aviso del sistema {texto!r}")


def rechazar_arranque(st, codigo):
    """★★★ "No se puede empezar": `FF36 [codigo]`. Es LA respuesta al botón START.

    Hace las dos cosas que hay que hacer, y la segunda es la importante:

    ```asm
    005ce7f0  read(1) -> codigo
    005ce800  cmp al,1 -> texto  73   "El juego comenzará cuando todos estén listos."
    005ce811  cmp al,2 -> texto  74   "…cuando hayan suficientes usuarios."
    005ce81e  cmp al,3 -> texto  75   "No puede iniciar el juego solo en Multi juego"
    005ce83b  cmp al,5 -> texto 254   ★ "No puede competir 1:1 Batalla de Relevos."
    005ce879  call 0x4233A0                 ; el cartel, de un botón
    005ce897  mov byte [cRoom+0x93F0], 0    ; ★★ DESBLOQUEA EL BOTÓN START
    ```

    ⚠⚠ **Sin el `FF36`, el host queda TRABADO.** `0x59AE9F` pone `[cRoom+0x93F0] = 1` justo antes
    de mandar el `FF24`, y nada más lo baja. Rechazar por chat —como se hacía hasta el 2026-09-05—
    dejaba el cartel bien escrito y al jugador sin poder hacer nada. Lo reportó el usuario en la
    primera prueba: *"luego de eso el host quedó bloqueado sin poder hacer acciones"*.

    ★ Y de paso resuelve lo otro: el `FF36` llega a textos que el `FF68` no alcanza. El 254 —que es
      literalmente nuestra regla, escrita por los autores del juego— está **por debajo** de la base
      255 del `FF68`. Por un número.
    """
    st.send_ff55(0x36, bytes([codigo & 0xFF]),
                 name=f"FF36 no se puede arrancar (codigo {codigo}) + desbloquea el START")


def popup_cliente(st, string_id):
    """★★★ Saca un CARTEL del cliente, con SU texto ya traducido. `FF68 [string_id - 255]`.

    El handler `0x5D0DC0` son tres líneas y es la palanca:

        005d0dc0  read(1) -> n
        005d0dd5  add eax, 0xFF          ; ★ el número de texto es n + 255
        005d0ddb  call 0x433380          ; la tabla de textos (objeto 0x9D50C0)
        005d0df4  call 0x4946D0          ; -> el popup

    ⇒ el server puede sacar cualquier cartel del **255 al 510** sin inventar texto ni parchear el
    ejecutable. Los números se consultan con `taller/re2013/strings_cliente.py`.
    """
    _n = string_id - FF68_BASE
    if not 0 <= _n <= 0xFF:
        log("LOBBY", f"  ⚠ el texto {string_id} está fuera del alcance del FF68 "
                     f"({FF68_BASE}..{FF68_BASE + 0xFF}) -> no se manda")
        return
    st.send_ff55(0x68, bytes([_n]), name=f"FF68 cartel del cliente nº {string_id}")


def relevo_puede_arrancar(st):
    """¿La sala puede correr un RELEVO? Devuelve `(motivo, nº_de_cartel)`, o `None` si se puede.

    ★★★★★ POR QUÉ EXISTE — medido en vivo el 2026-09-05.
    Se jugó un relevo **1 contra 1** y el cartel salió al revés: el que llegó primero vio *"perdiste"*
    y la que no jugó vio *"ganó"* y sin tiempo. El servidor había calculado bien (el log dice
    `puesto 1 frame=8710` para el que corrió), así que la incoherencia es del cliente — y tiene
    sentido: **en relevo los tramos van por POSICIÓN dentro del equipo** (0 vs 3, después 1 vs 4, al
    final 2 vs 5), y en esa partida los dos jugadores habían quedado en los asientos **2 y 3** ⇒ el
    equipo rojo tenía a su único corredor en el TERCER tramo, sin nadie en el primero ni el segundo.
    Una carrera así no está prevista por el cliente.

    ⚠⚠ **Y EL CLIENTE NO LO IMPIDE.** Su propio guard de arranque es `0x592B50`, lo primero que
    corre al apretar START (`0x59AE30`), y pide **tres** cosas — ninguna de ellas ésta:

    | # | qué pide | dónde | ¿la cumplía el 1v1? |
    |---|---|---|---|
    | 1 | al menos **2 ocupantes en total** | `[cRoom+0xB8] - 0x591020() >= 2` | sí (eran 2) |
    | 2 | que estén **todos listos** | `[ocupante+0x167] != 0` | sí |
    | 3 | **equipos parejos** | `0x58BFF0` → CoopMode 0 (equipo), **2 (relevo)** o GameMode 5 (jefe) | sí: 1 y 1 |

    ⇒ No es que el guard esté "apagado": **el mínimo por equipo no existe en esta build.** Se pone
    server-side, que además no cuesta ningún parche.

    ★ De paso queda medido algo que la doc del CBT dejó como pregunta abierta (*"si el relevo exige
      equipos armados para arrancar"*): **sí, los exige** — `0x58BFF0` mete al relevo en el mismo
      saco que el modo equipo y el jefe. La dirección que aquella nota citaba (`0x4FB43B`) es de
      otro build y en éste cae en medio de otra función.

    ⏳ **Lo que NO se bloquea (todavía)**: que los asientos de un equipo dejen un hueco adelante
       (p. ej. 2v2 en los asientos 1,2 contra 4,5, con el primer tramo vacío). Es el sospechoso
       número uno de lo que se vio, pero que el cliente corra los tramos por número de asiento y no
       "los ocupados en orden" **no está medido**. Se avisa en el log y no se corta.
    """
    rid = getattr(st, "room_id", None)
    if rid is None:
        return None
    if not (getattr(st, "room_mode", 0) & MODE_RELEVO) or getattr(st, "room_colab", False):
        return None
    _mesa = set(mesa_de(rid))
    # ★ LOCAL (11-oct, anonimo03: «no detecta a los NPC como jugadores»): los NPC que juegan también corren su tramo
    #   (npc_carrera.py, la posta). En prod no hay NPC que jueguen: ahí cuentan sólo los de verdad, como siempre.
    if CHASE_NPC_REALISTA:
        _mesa |= set(npcs_de(rid) or ())
    _por_equipo = {1: [], 2: []}
    for _s in sorted(_mesa):
        _por_equipo.setdefault(equipo_de(rid, _s), []).append(_s)
    # ★ 14-oct · EL RELEVO DE 12 (RELEVO_12.md): 4 equipos de 3. anonimo03: «cada equipo debe tener sus 3 jugadores
    #   completos para empezar» y «la partida empieza con al menos 3 o 4 equipos».
    from .salas import es_relevo12
    if es_relevo12(rid):
        return _cuatro_equipos_listos(rid, _por_equipo, "Relevo de 12")
    _e1, _e2 = _por_equipo.get(1, []), _por_equipo.get(2, [])
    if len(_e1) < RELEVO_MIN_POR_EQUIPO or len(_e2) < RELEVO_MIN_POR_EQUIPO:
        # ★ Código 5 = texto 254, *"No puede competir 1:1 Batalla de Relevos."* — literalmente esta
        #   regla, escrita por los autores del juego. La línea de chat va aparte porque el cartel
        #   no dice cuántos hay de cada lado.
        return (f"El relevo necesita al menos {RELEVO_MIN_POR_EQUIPO} corredores por equipo "
                f"({RELEVO_MIN_POR_EQUIPO * 2} en total). Ahora hay {len(_e1)} y {len(_e2)}.",
                FF36_RELEVO_1V1)
    if len(_e1) != len(_e2):
        # Código 2 = texto 74, el MISMO que usa el guard interno del cliente para los equipos
        # disparejos (`0x592B50` devuelve 3 -> `push 0x4A`). Cortamos acá igual, para poder decir
        # además los números.
        return (f"Los equipos tienen que estar parejos: {len(_e1)} contra {len(_e2)}.",
                FF36_FALTAN_USUARIOS)
    for _eq, _slots in ((1, _e1), (2, _e2)):
        _esperados = list(range(0 if _eq == 1 else 3, (0 if _eq == 1 else 3) + len(_slots)))
        if _slots != _esperados:
            log("LOBBY", f"  ⚠⚠ RELEVO: el equipo {_eq} ocupa los asientos {_slots} y no los "
                         f"{_esperados} — queda un TRAMO VACÍO adelante. Es el sospechoso del "
                         f"cartel roto del 1v1; no lo corto porque no está medido.")
    return None


def _cuatro_equipos_listos(rid, por_equipo, que):
    """★ 14-oct (relevo de 12) · ★ 15-oct (y el equipo de 4, EQUIPOS_4.md): 4 equipos de 3. anonimo03: «cada equipo debe
    tener sus 3 jugadores completos para empezar» y «la partida empieza con al menos 3 o 4 equipos». `None` = se puede."""
    from .ajustes import RELEVO12_EQUIPOS, RELEVO12_POR_EQUIPO, RELEVO12_MIN_EQUIPOS
    _nom = {1: "rojo", 2: "azul", 3: "verde", 4: "naranja"}
    _cuantos = {e: len(por_equipo.get(e, [])) for e in range(1, RELEVO12_EQUIPOS + 1)}
    _incompletos = [e for e, n in _cuantos.items() if 0 < n < RELEVO12_POR_EQUIPO]
    _completos = [e for e, n in _cuantos.items() if n == RELEVO12_POR_EQUIPO]
    _estado = " · ".join(f"{_nom[e]} {n}/{RELEVO12_POR_EQUIPO}" for e, n in _cuantos.items())
    if _incompletos:
        return (f"{que}: cada equipo tiene que estar completo ({RELEVO12_POR_EQUIPO}). Ahora: {_estado}.",
                FF36_FALTAN_USUARIOS)
    if len(_completos) < RELEVO12_MIN_EQUIPOS:
        return (f"{que}: hacen falta al menos {RELEVO12_MIN_EQUIPOS} equipos completos. Ahora: {_estado}.",
                FF36_FALTAN_USUARIOS)
    log("LOBBY", f"  ★ {que.upper()}: arranca con {len(_completos)} equipos — {_estado} (sala {rid})")
    return None


def cuatro_puede_arrancar(st):
    """★ 15-oct · ¿la sala de 12 de 4 EQUIPOS en batalla en equipo (velocidad o ítem) puede arrancar? Las mismas reglas
    que el relevo de 12 (anonimo03: «la sala de 4 equipos, igual a la del relevo»). `(motivo, cartel)` o `None`."""
    rid = getattr(st, "room_id", None)
    if rid is None or (getattr(st, "room_mode", 0) & MODE_RELEVO) or getattr(st, "room_colab", False):
        return None
    from .salas import es_cuatro12
    if not es_cuatro12(rid):
        return None
    _mesa = set(mesa_de(rid))
    if CHASE_NPC_REALISTA:
        _mesa |= set(npcs_de(rid) or ())
    _por_equipo = {}
    for _s in sorted(_mesa):
        _por_equipo.setdefault(equipo_de(rid, _s), []).append(_s)
    return _cuatro_equipos_listos(rid, _por_equipo, "Equipo de 4")


def jefe_puede_arrancar(st):
    """¿La sala puede correr una BATALLA DE JEFES? `(motivo, nº de cartel)` o `None` si se puede.

    ★★★★★ POR QUÉ EXISTE — y acá no es cosmético como en el relevo: **es lo que evita el crash.**

    El init de la escena de carrera (`0x4F9D50`) tiene un bloque que abre **sólo** el jefe
    (`test word [cGame+0x0c], 0x2000`; el jefe es el único modo cuyo `CalcGameFlags` trae ese bit —
    vale `0x2017`). Ese bloque pide los dos capitanes y usa la respuesta **como índice crudo**:

        004fabb2  call 0x4EBBF0        ; FindCaptain(equipo) -> 0xFF cuando NO HAY capitán
        004fabbf  movzx esi, bl        ; esi = 255
        004fabd5  cmp esi, ecx         ; ecx = cantidad de jugadores (6)
        004fabd7  jb  0x4fabde         ; 255 < 6 ? NO -> no salta
        004fabd9  call 0x74FF1F        ; _invalid_parameter_noinfo
        004fabe4  mov ecx,[edx+esi*4]  ; vector[255] = 1020 B pasado el final -> BASURA
        004fabe9  call 0x502CF0        ; método sobre un `this` basura -> c0000005

    Y para que `FindCaptain` NO devuelva `0xFF` hacen falta **las dos cosas a la vez** en el padrón
    (`[0x931660]`): `sRoomUser+0x4A == equipo` **y** `+0x4B != 0`. Hasta hoy no mandábamos ninguna
    de las dos: el equipo iba en cero en el `FF0C` (`rel12`) y la bandera no la prendía nadie.
    ⇒ El `0xFF` era **seguro**, no probable. Eso explica "el modo crashea siempre".

    ⚠⚠ **LEÍDO, NO MEDIDO.** El disasm dice qué hace esa línea; no me consta que el proceso muera
       ahí. Si con capitanes designados igual se cae, el sospechoso siguiente es `0x4F3FA0` (el
       apuntado de ítems, misma compuerta `0x2000`) y hay que ir con Frida.

    ⚠ El cliente **no** pide nada de esto: su guard (`0x592B50`) sólo mira 2 ocupantes, todos
      listos y equipos parejos (`0x58BFF0`, que mete al jefe en el mismo saco que equipo y relevo).
      Recorridos los ocho sitios donde pregunta `GameMode == 5`: ninguno es un guard de arranque.
      Va server-side, que además no cuesta ningún parche.
    """
    rid = getattr(st, "room_id", None)
    if rid is None or not getattr(st, "room_boss", False):
        return None
    _mesa = mesa_de(rid)
    _por_equipo = {1: [], 2: []}
    for _s in sorted(_mesa):
        _por_equipo.setdefault(equipo_de(rid, _s), []).append(_s)
    _e1, _e2 = _por_equipo.get(1, []), _por_equipo.get(2, [])
    # ★ Código 4 = texto 207, *"No puede iniciar el juego con la composición actual"* — verificado
    #   en el disasm (`0x5CE82B cmp al,4 / push 0xCF`). Es el más honesto de los siete que hay: en
    #   la tabla del cliente no existe ningún texto con la palabra "capitán" (en este juego el
    #   capitán se comunica por ÍCONO). El detalle con los números va por chat, aparte.
    if len(_e1) < JEFE_MIN_POR_EQUIPO or len(_e2) < JEFE_MIN_POR_EQUIPO:
        return (f"La Batalla de Jefes necesita al menos {JEFE_MIN_POR_EQUIPO} por equipo "
                f"({JEFE_MIN_POR_EQUIPO * 2} en total). Ahora hay {len(_e1)} y {len(_e2)}.",
                FF36_COMPOSICION)
    if len(_e1) != len(_e2):
        return (f"Los equipos tienen que estar parejos: {len(_e1)} contra {len(_e2)}.",
                FF36_COMPOSICION)
    return None


def coop_puede_arrancar(st):
    """¿La sala puede correr un COOPERATIVO? `(motivo, nº de cartel)` o `None` si se puede.

    ★★★★★ POR QUÉ EXISTE — 2026-09-08. Es el tercero de la familia (`relevo` 4, `jefe` 4), pero
    por un motivo distinto: acá **no es por equipos, es porque no hay datos**.

    | | qué dice | dónde |
    |---|---|---|
    | el cliente **exige** | 2 ocupantes, todos listos, y equipos parejos **sólo si la sala usa equipos** | `0x592B50` |
    | …y el cooperativo **no usa equipos** | `0x58BFF0` deja pasar CooperationMode 0 y 2, y GameMode 5. El 4 no está | `0x58BFF0` |
    | el modo **supone** | de **3 a 6** | `0x568118` |

    La lógica del gorila se indexa por cantidad de jugadores y sólo existe para 6/5/4/3:

        00568118  mov eax,[0x931660]     ; el padrón
        0056811d  mov eax,[eax+0x1c]     ; cuántos jugadores
        00568126  cmp eax, 2
        00568129  jbe 0x568175           ; ⛔ 2 o menos -> NO CARGA NINGUNA FILA
        0056812b  cmp al,6 -> fila 0 · 5 -> 1 · 4 -> 2 · 3 -> 3 · otra cosa -> tampoco

    ★ Y los archivos del propio juego lo confirman **4 de 4**: la fila que arma ese código es la
      de `npcitemtable.txt`, que trae los comentarios de los devs al lado —`//0(6명)`, `//1(5명)`,
      `//2(4명)`, `//3(3명)`— e `itemappear.txt` encabeza con `//플레이어수(6~3)`, o sea
      "cantidad de jugadores (6~3)". El disasm y los datos dicen lo mismo por separado.

    ⚠⚠ **RIESGO LEÍDO, NO MEDIDO.** En `0x56836D` hay un `div` por el tamaño de una lista de
       candidatos. Si la que queda vacía con ≤2 jugadores es ésa, eso es división por cero **en
       el master**. Hay varias listas en esa función y no comprobé cuál. No se afirma; se anota.

    ⚠ Por eso el corte es **3** y no 4: con 3 hay datos y con 2 no. Y `COOP_MIN_SOLO_AVISAR`
      existe para no bloquear las pruebas de a uno.
    """
    rid = getattr(st, "room_id", None)
    if rid is None or not getattr(st, "room_colab", False):
        return None
    # ★ Los NPC de `.npc` CUENTAN. No es una comodidad: el cliente cuenta lo que ve
    #   (`[padrón+0x1c]`, que incluye a los fantasmas), así que contar sólo a los humanos daría
    #   un número distinto del que usa el juego para elegir su fila de `npcitemtable.txt`.
    _reales = mesa_de(rid)
    _fantasmas = [s for s in (npcs_de(rid) or []) if s not in _reales]
    _n = len(_reales) + len(_fantasmas)
    if _n >= COOP_MIN_JUGADORES:
        return None
    if COOP_MIN_SOLO_AVISAR:
        log("LOBBY", f"  ⚠⚠ COOPERATIVO con {_n} ocupante(s) ({len(_reales)} de verdad + "
                     f"{len(_fantasmas)} NPC): el modo sólo tiene datos para "
                     f"{COOP_MIN_JUGADORES}..6 (`0x568118`), así que la lógica del gorila arranca "
                     f"sin ninguna fila cargada. NO se corta porque COOP_MIN_SOLO_AVISAR está "
                     f"prendido. ⚠ Y ojo con el `div` de `0x56836D`, que podría ser por cero.")
        return None
    # ★ Mismo cartel que el jefe: código 4 = texto 207, *"No puede iniciar el juego con la
    #   composición actual"*. Es el más honesto de los siete que hay — no existe ninguno que
    #   hable de "mínimo de jugadores" para este modo. El número va por chat, aparte.
    return (f"El modo cooperativo necesita al menos {COOP_MIN_JUGADORES} ocupantes "
            f"(el juego sólo trae datos para {COOP_MIN_JUGADORES} a 6). Ahora hay {_n}. "
            f"Los NPC de `.npc` cuentan.",
            FF36_COMPOSICION)


def h_30_ff24(st, cmd, data):
    # rama original:  cmd == 36
    # ★★★ GUARD DEL RELEVO, antes de nada. Ver `relevo_puede_arrancar`: el cliente NO impide
    #   arrancar un 1v1, y una partida así rompe el cartel (medido el 2026-09-05).
    _no24 = (relevo_puede_arrancar(st) or cuatro_puede_arrancar(st) or jefe_puede_arrancar(st)
             or coop_puede_arrancar(st))
    if _no24:
        _txt24, _cod24 = _no24
        # ★★ EL `FF36` VA SÍ O SÍ: además del cartel, es lo único que baja `[cRoom+0x93F0]` y le
        #    devuelve el botón al host. Rechazar sólo por chat lo dejaba trabado.
        rechazar_arranque(st, _cod24)
        aviso_sistema(st, _txt24)         # y el detalle con los números, que el cartel no da
        log("LOBBY", f"  ⛔ FF24 START RECHAZADO: {_txt24} "
                     f"[FF36 codigo {_cod24} + desbloqueo del START]")
        return
    # ★★★★★ LOS CAPITANES DEL MODO JEFE, ANTES DE MANDAR EL LOADGAME (2026-09-07).
    #   Sin esto el cliente entra a la carrera, pregunta quién es el capitán, le contestan "nadie"
    #   (`0xFF`) y usa ese 255 como índice de un vector de 6 -> `c0000005`. Ver
    #   `jefe_puede_arrancar` para el disasm entero.
    #
    # ⛔⛔ ACÁ SE SORTEABA, Y ESO PISABA LA CESIÓN — corregido el 2026-09-08 a pedido del usuario:
    #     *"el sorteo sólo debe ocurrir al regresar a sala, no al presionar start … si el jugador 3
    #       le cedió al 1, al empezar partida está ocurriendo sorteo: ceder jefe perdió el sentido"*.
    #   El `FF175` (ceder el puesto) es la mecánica del modo, y un sorteo en el START la borraba
    #   **justo cuando iba a servir**. Cambiar o crear la sala en modo jefe sí sortea (`h_25_ff4b`
    #   y la entrada del `FF11`): eso está bien y no se toca.
    #   ⇒ Acá sólo se REPARA (que no mueve al capitán que sigue sentado y sigue siendo de su equipo)
    #     y se DIFUNDE, que es lo que evita el `0xFF`. El sorteo nuevo se hace **al volver de la
    #     carrera**: se anota abajo con `marcar_sorteo_al_volver` y lo ejecuta el `FF13` del regreso
    #     (`lobby_salas.h_19_ff13`). Así entre carrera y carrera los capitanes cambian, y desde ahí
    #     hasta el START mandan las cesiones.
    if getattr(st, "room_boss", False) and JEFE_SORTEAR_CAPITAN:
        _rid_cap = getattr(st, "room_id", None)
        if _rid_cap is not None:
            reparar_capitanes(_rid_cap)
            _caps24 = capitanes_de(_rid_cap)
            if len(_caps24) < 2:
                # No debería pasar (el guard de arriba ya pidió gente en los dos equipos), pero si
                # pasa NO se arranca: un equipo sin capitán es exactamente el 0xFF que crashea.
                rechazar_arranque(st, FF36_COMPOSICION)
                aviso_sistema(st, "No se pudo designar un capitán en cada equipo.")
                log("LOBBY", f"  ⛔ FF24 START RECHAZADO (jefe): capitanes = {_caps24} "
                             f"— falta al menos un equipo. NO se manda el LOADGAME (crashearía).")
                return
            difundir_capitanes(_rid_cap, _caps24, " (los vigentes, al apretar START)")
            # ★ Y queda anotado el sorteo para CUANDO VUELVAN. No se hace acá (pisaría la cesión)
            #   ni al terminar la carrera: se hace en el `FF13` del regreso, con la sala ya armada
            #   y toda la gente de vuelta. Ver `salas.SORTEO_AL_VOLVER`.
            marcar_sorteo_al_volver(_rid_cap)
            # ★ Y el espejo del impulsor arranca en cero: la barra del cliente también nace en 0
            #   en cada carrera, y si el nuestro quedara con lo de la anterior le mandaríamos de
            #   menos (o nada) y la barra no subiría. Ver `JEFE_IMPULSOR` en `ajustes.py`.
            reiniciar_impulsor(_rid_cap, " (al arrancar la carrera)")
    # [magic:u32][map:u16][flag:u8][song:u16...]. magic = clave XOR de scores/FF4E. El cliente carga y luego
    # manda C->S FF25 (cargue) -> respondemos FF24 GO. songcount lo saca el cliente de un contenedor propio;
    # si sale mal -> "[cGame] music size n error". Frida (trace_loadgame.py) mide songcount para calibrar.
    st.game_magic = struct.unpack("<I", os.urandom(4))[0]
    # ★ La pista y la canción salen de LA SALA, no de la conexión del que apretó START. Es lo
    #   mismo mientras sólo el host elija, pero deja de depender de que la copia del host esté
    #   al día — que es justo lo que fallaba cuando cambiaba la pista (ver `h_28_ff1b`).
    _sel24 = seleccion_de(getattr(st, "room_id", None))
    # ★ «Aleatoria» (0) se sortea acá, una vez por carrera para la sala (08-oct; antes corría siempre la 11)
    mp   = pista_de_carrera(_sel24["pista"])
    if not _sel24["pista"]:
        log("LOBBY", f"  ★ pista ALEATORIA: sorteada la {mp}")
    song = _sel24["cancion"] or getattr(st, "room_song", DEFAULT_ROOM_SONG)
    # ★ RED DE SEGURIDAD: un songid 0 en el LOADGAME MATA al cliente en la pantalla de carga (carga una
    #   cancion que no existe). Nunca dejarlo salir: si por lo que sea quedo en 0, va el default.
    # ★★★ LAS MANERAS DE LISTA AL AZAR (29-sep): Aleatorio / TOP 20 / NUEVOS 20 las sortea el SERVER
    #   (el cliente manda canción 0 y no tiene código de sorteo). Hasta hoy arrancaba la última elegida:
    #   en prod «Aleatorio» se pidió 5.157 veces en una semana sin sortear nunca. Ver `picker.sortear`.
    #   El cooperativo tiene su propio sorteo (abajo) y no pasa por acá.
    from .ajustes import PICKER_MODOS
    _modo24 = _sel24.get("modo")
    if PICKER_MODOS and not getattr(st, "room_colab", False) and _modo24 in ("aleatorio", "top20", "nuevos20"):
        from .picker import sortear
        _s24 = sortear(_modo24, banda=dificultad_de(getattr(st, "room_id", None)))
        if _s24:
            log("LOBBY", f"  ♪ START en «{_modo24}»: sorteada la {_s24} (la de la sala era {song})")
            song = _s24
    if getattr(st, "song_override", None):
        # ★ 13-oct: `.tema N` (dev, el QA automático): la canción la fija el anfitrión por encima del picker
        log("LOBBY", f"  ♪ START con tema forzado {st.song_override} (la de la sala era {song})")
        song = st.song_override
    if not song:
        song = DEFAULT_ROOM_SONG
        log("LOBBY", f"  ⚠ room_song estaba en 0 -> se manda el default {song} (un 0 crashea la carga)")
    if FF25_SENTINEL:
        ld = struct.pack("<I", 0xAABBCCDD) + struct.pack("<H", 0x1234) + bytes([0x55]) + struct.pack("<H", song)
    else:
        # ★ el byte tras el map = SONGCOUNT (no un flag): con 0 -> "music size n error" + crash. =1 -> una cancion.
        # ★★ COOPERATIVO (chase): el modo consume VARIAS canciones (3) que se van rotando, asi que
        #    va songcount=3 + los 3 songids seguidos. El handler del FF25 (0x5EB030) es el que
        #    alimenta `cGameMusicBlock` (llama a 0x56E590), o sea que los bloques de musica del
        #    chase salen de ACA. Con songcount=1 la partida arrancaba con una sola cancion.
        # ★★★★★ EL SORTEO DE LAS 3 CANCIONES SE HACE ACÁ, EN CADA START (2026-09-05).
        #   ⛔ Antes vivía SÓLO en el handler del `FF4B` (cambio de modo) y en `st.chase_songs`.
        #      Eso rompía dos cosas, las dos reportadas por el usuario:
        #        1. creando la sala YA en cooperativo, el `FF4B` nunca corre ⇒ no había sorteo y
        #           el `FF25` caía al `[song]` de UNA sola canción, siempre la misma. (Por eso
        #           andaba si cambiabas a otro modo y volvías: ahí sí pasaba por el `FF4B`.)
        #        2. volviendo a la sala para otra partida, sin cambio de modo nadie volvía a
        #           sortear ⇒ se repetían las 3 anteriores.
        #   ⇒ Sortear en el START arregla las dos de una: siempre hay canciones y siempre son
        #     nuevas. Y va a la SALA, para que los 6 vean lo mismo (ver `CANCIONES_CHASE`).
        canciones = None
        if getattr(st, "room_colab", False):
            _prev = list(getattr(st, "chase_songs", None) or [])
            canciones = asegurar_canciones_chase(
                st, "★ SORTEO DE CADA START (no del cambio de modo)", resortear=True)
            if _prev and _prev != canciones:
                log("LOBBY", f"  ★★ CHASE: la partida anterior fue {_prev} y ésta es {canciones}"
                             f" — el sorteo se rehace en cada arranque")
            song = canciones[0]
        if not canciones:
            canciones = [song]
        elif CHASE_EXPERIMENTAL and CHASE_MAP is not None:
            mp = CHASE_MAP        # ★ la pista FIJA del chase (ver CHASE_MAP arriba)
        # ★ SONDA DE LA PISTA DEL CHASE (independiente de CHASE_EXPERIMENTAL, para mover UNA sola
        #   variable): en cooperativo el cliente ya conmuto su stage-select al de chase y lo forzo
        #   a 15000; mandarle un map fuera de 15000..16383 es incoherente con lo que el tiene.
        if getattr(st, "room_colab", False) and CHASE_USAR_MAP_FIJO:
            mp = CHASE_MAP_FIJO
            log("LOBBY", f"  ★★ CHASE: map fijo {mp} en vez de {DEFAULT_ROOM_MAP}")
        # ★★ la que eligió el anfitrión en el mini-panel del cooperativo (09-oct) le gana a la fija
        if getattr(st, "room_colab", False) and seleccion_de(getattr(st, "room_id", None)).get("pista_coop") is not None:
            mp = pista_de_carrera(seleccion_de(getattr(st, "room_id", None))["pista_coop"])
            log("LOBBY", f"  ★★ CHASE: la pista que eligió el anfitrión -> {mp}")
        # ★★ `.oscuro` — el mapa que forzó EL ANFITRIÓN para toda la sala. Pisa el modo (incluido
        #   el fijo del cooperativo) porque para eso existe: *"un master quiere elegir ese mapa en
        #   cualquier modo de juego"*. Es de la SALA, así que sale igual para todos y no hace falta
        #   armar el LOADGAME por destinatario. Ver `salas.MAPA_SALA`.
        _osc = mapa_de_sala(getattr(st, "room_id", None))
        if _osc is not None:
            mp = _osc
            log("LOBBY", f"  ★★ .oscuro: mapa {mp} forzado por el anfitrión para TODA la sala")
        # ★ `.map N` del chat pisa TODO (sonda de pista sin relanzar). Va al final a proposito.
        if getattr(st, "map_override", None) is not None:
            mp = st.map_override
            log("LOBBY", f"  ★★ map OVERRIDE por chat = {mp}")
        # ★ ¿se puede usar la pista propia de cada uno? No en el cooperativo con su pista fija (el cliente ya
        #   conmutó su selector al del chase), ni con el `.map` de prueba, que pisa todo a propósito.
        # ★ 09-oct: también en el cooperativo, con SU pista del mini-panel (`pista_coop`, aparte de la normal)
        _propia_ok = getattr(st, "map_override", None) is None
        _coop25 = bool(getattr(st, "room_colab", False))
        ld = (struct.pack("<I", st.game_magic) + struct.pack("<H", mp & 0xFFFF)
              + bytes([len(canciones) & 0xFF])
              + b"".join(struct.pack("<H", s & 0xFFFF) for s in canciones))
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★ ACÁ EMPIEZAN LOS CAMPOS NUESTROS — ⛔ LEER `documentacion/FF25_LOADGAME_BYTES.md`
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   ⛔⛔ REGLA, Y NO ES UNA SUGERENCIA: **un campo nuevo va SIEMPRE AL FINAL**, después
        #     del último que ya esté. Nunca en el medio, nunca reordenado, nunca cambiándole el
        #     tipo a uno existente.
        #     El cliente NO lee por offset: lee el flujo EN ORDEN, pidiendo "el byte que sigue".
        #     Meter un campo antes de otro hace que el cave del segundo lea el primero, y **nada
        #     avisa**: anda "casi bien", que es lo peor que puede pasar.
        #   ⚠ Y el offset de todo esto es VARIABLE (`7 + 2×canciones`): con 1 canción cae en el
        #     byte 9 y en cooperativo (3 canciones) en el 13. Por eso se lee en orden y no por
        #     posición — un cave con offset fijo pasa todas las pruebas y se rompe en el chase.
        #   ⇒ El registro de qué está tomado y qué está libre vive en
        #     `documentacion/FF25_LOADGAME_BYTES.md`. Si agregás un campo, anotalo AHÍ TAMBIÉN.
        #     Es el lugar natural para los modificadores de partida que vienen (rate de exp, rate
        #     de rcoin, bonos), y sin registro el segundo que llegue elige el byte a ojo.
        #
        # ── campo 1 · «PD VALOFE» (2026-09-14) ─────────────────────────────────────────────────
        #   Con qué tabla de puntaje juega ESTA sala: 0 = la del 2013, 1 = la del cliente moderno.
        #   La elige el anfitrión con `.pd on/off`, y sale igual para todos los de la sala —
        #   incluidos los espectadores, que reciben el mismo `ld` unas líneas más abajo.
        #
        #   ★★ POR QUE PEGADO AL FINAL Y NO COMO UN CAMPO NUEVO: porque así **esto puede subir a
        #     prod SIN el cliente**, y sin romper a nadie. Está leído del binario, no supuesto:
        #     el handler del FF25 (`0x5EA910`) pide al flujo exactamente magic + mapa + cuántas +
        #     las canciones, y **nunca pregunta si sobró algo** ⇒ un cliente viejo ni lo mira.
        #     Y al revés también: el lector (`0x67D200`) devuelve 0 y **no toca el destino** si
        #     no alcanzan los bytes, así que un cliente NUEVO contra un server VIEJO lee el cero
        #     que su propio cave puso antes = apagado. Es la misma propiedad que los decimales.
        #
        #   ⚠ Va DESPUÉS de las canciones a propósito: el flujo se lee en orden, y el cave del
        #     cliente pide su byte una vez que el handler terminó de leer los suyos. Meterlo en el
        #     medio obligaría a tocar el orden y rompería a los clientes viejos.
        _pdv = pd_valofe_de(getattr(st, "room_id", None))
        ld += bytes([1 if _pdv else 0])
        log("LOBBY", f"  ★★ PD: la sala juega con {'PD Valofe' if _pdv else 'PD Normal'} "
                     f"(byte {1 if _pdv else 0} al final del LOADGAME)")
        # ── campo 2 · «OBSTÁCULOS» (2026-10-08) — ⚠ EL PRIMERO QUE ES DE CADA JUGADOR ──────────────────
        #   No se pega acá: va en `cola_ff25_jugador`, al mandarle el LOADGAME a cada uno (abajo). Hasta hoy el
        #   `ld` era uno solo para toda la sala; desde éste, a cada destinatario le va `ld + SU cola`. Lo que
        #   va en `ld` sigue siendo de la sala, y la cola va siempre DESPUÉS (la regla del registro no cambia).
        #   Ver `salas.cola_ff25_jugador` y `documentacion/FF25_LOADGAME_BYTES.md`.
    # ★★★★ 2026-08-05 — EL START ARRANCA A TODA LA SALA, no sólo al que apretó.
    #   Antes el FF25 LOADGAME salía por `st` y nada más: el host entraba a la carrera y el
    #   invitado se quedaba en la sala mirando.
    #   ★★ Y el `magic` TIENE que ser EL MISMO para todos: es la clave XOR con la que se cifran
    #      los scores y los paquetes de juego. Con una clave por jugador, lo que manda uno es
    #      ilegible para el otro. Por eso vive en la CARRERA (la sala), no en la conexión.
    _rid24 = getattr(st, "room_id", None)
    _jug24 = [CONEXIONES.get(u) for u in mesa_de(_rid24).values()] if _rid24 else []
    _jug24 = [c for c in _jug24 if c is not None and not getattr(c, "cerrado", False)] or [st]
    # ★★ LOS ESPECTADORES TAMBIEN RECIBEN EL LOADGAME (2026-09-08). Sin esto se quedaban en la
    #   sala mientras los demas corrian — que es justo lo contrario de para lo que entraron.
    #   ⚠ Van SOLO al `FF25`: NO entran en `CARRERAS[rid]["jugadores"]`, porque esa lista es la de
    #     quienes tienen que reportar su `FF28` al final. Un espectador que nunca reporta dejaria
    #     el cartel esperando para siempre — el mismo cuelgue que ya se pago con el que entraba a
    #     mitad de partida. Miran la carrera, no la juegan.
    _esp24 = [c for c in espectadores_de(_rid24) if c not in _jug24] if _rid24 else []
    if _rid24 is not None:
        with _mesa_lock:
            CARRERAS[_rid24] = {"magic": st.game_magic, "cargados": set(),
                                "jugadores": {getattr(c, "usn", None) for c in _jug24},
                                # ★ (12-oct) los que miran: el GO los espera, con tope (`GO_ESPERA_ESPECTADOR_S`)
                                "espectadores": {getattr(c, "usn", None) for c in _esp24},
                                # ★ (11-oct) la pista que SE CORRIÓ (la «Aleatoria» ya sorteada) y la canción: las
                                #   lee el cartel de 12 (`cartel12.py`)
                                "pista": mp, "cancion": song}
    # ★★★★★ EL CONTADOR DE RONDAS DEL GORILA SE PONE EN CERO PARA TODOS — 2026-09-06.
    #   ⛔ EL BUG QUE ESTO ARREGLA, visto en vivo (sala 9, corrida de las 15:35:19): `chase_token`
    #     vivía en CADA CONEXIÓN y **no se reiniciaba nunca**. La sala ya había jugado un
    #     cooperativo (rondas 0·1·2·3, la última a las 15:32:45), así que los que estaban ahí
    #     quedaron con el contador en **4**. A las 15:34:11 entró alguien nuevo, con el contador
    #     en **0**. Y el guard que resuelve cada ronda del minijuego exige que TODOS tengan el
    #     mismo número:
    #         if any(getattr(c, "chase_token", 0) != token for c in vivos): -> descartar
    #     Con uno en 0 y los otros en 4 esa condición **nunca se cumple** ⇒ el minijuego no se
    #     resuelve JAMÁS y la sala entera queda con el cartelito de "Captura a Gorila" abierto.
    #     En el log queda como `· GORILA: disparo descartado (...): la ronda 4 ya se resolvió`
    #     seguido de silencio.
    #   ★ Por qué se repetía tanto: le pasa a CUALQUIER sala donde ya se jugó un cooperativo y
    #     después entra alguien. O sea, lo más normal del mundo.
    #   ⇒ El arranque de la carrera es el único momento en que se sabe quiénes van a jugar, así
    #     que es acá donde se los sincroniza. Va también `chase_ronda`, que cuenta las 3 canciones
    #     de la corrida y arrastraba el mismo problema (es lo que decide el `FF27` del cierre).
    #   ⚠ Se hace para TODOS los modos, no sólo el cooperativo: si la sala cambia de modo, el
    #     contador viejo no tiene por qué sobrevivir.
    # ★★★★★ 2026-09-06, MISMA TARDE, SEGUNDA VUELTA: no eran dos contadores, eran CUATRO.
    #   El usuario reportó el *"premio corrido"* y que su grupo **quedaba trabado en el cartel de
    #   premios**, y el log lo explica entero. Los otros dos arrastrados:
    #
    #   · `chase_puntos` — el aporte de cada uno al minijuego. **Sólo se suma, nunca se
    #     reiniciaba**, y con él se decide QUIÉN ELIGE PRIMERO (`_slot_del_que_mas_aporto`) y EL
    #     ORDEN DE LOS TURNOS (`_pendientes.sort(key=-chase_puntos)`). Después de la 1ª partida ya
    #     no es "el que más aportó" sino "el que más acumuló desde que se conectó" ⇒ el orden se
    #     despega de la realidad **más en cada partida**, que es tal cual como lo describió:
    #     *"ese grupo lleva más de una partida... la lista aún más corrida"*.
    #
    #   · `chase_premios` — el tablero de 6 cajas de ESA corrida. ⛔ Es el peor de los cuatro:
    #     `h_39_ff10e` usa "¿ya tiene premios?" para distinguir el pedido inicial del reintento
    #     por timeout (`elif _gano and st.chase_premios: -> IGNORADO`). Con el valor viejo colgado,
    #     el pedido del tablero de la partida NUEVA se toma por repetido y **ese jugador nunca
    #     recibe el tablero**: no puede abrir caja, y como el revelado espera a que abran TODOS,
    #     la sala entera se queda en el cartel. Medido: en la partida de las 18:05 pidieron los 6,
    #     **3 recibieron tablero y 3 fueron ignorados**, y no se abrió ni una caja.
    #     Y además `_premios = st.chase_premios` en el `sub=4` ⇒ al abrir, el premio se busca en el
    #     TABLERO DE LA PARTIDA ANTERIOR: literalmente el "premio corrido".
    #     (`chase_abiertas` va con él: son pareja, se arman juntos en el mismo punto.)
    #
    #   ⇒ Regla que queda: **todo lo que describe UNA corrida se reinicia en el START**. Lo que es
    #     preferencia del jugador NO: `chase_n` (cuántas canciones, se pone por chat) se respeta.
    for _c in _jug24:
        # ★ El listo se consume al arrancar: al volver del cartel nadie sigue listo. Sin esto,
        #   `enviar_listos` repintaria el LISTO de la carrera ANTERIOR al rearmarse la sala.
        _c.ready = False
        _c.chase_token = 0
        _c.chase_ronda = 0
        _c.chase_puntos = 0
        _c.chase_premios = None
        _c.chase_abiertas = set()
        # ★ 2026-09-10: el tablero y las cajas abiertas viven ahora en la SALA, y la entrada de
        #   `CARRERAS` se reemplaza entera unas líneas más arriba, así que se limpian solas. Éste
        #   es el residuo del camino "sin sala" (un jugador suelto), que sí hay que borrar.
        _c.chase_abiertas_solo = None
    # ★ Y el AVANCE en la pista: describe UNA corrida, así que se reinicia en el START como
    #   todo lo demás. Vive fuera de `CARRERAS` (en `carrera.AVANCE_COOP`), así que el
    #   reemplazo de la entrada de la sala NO se lo lleva puesto — hay que borrarlo a mano.
    olvidar_avance(getattr(st, "room_id", None))
    # ★★ Y LA CAMPANA SE REHABILITA — 2026-09-15. El texto 639 del cliente dice *«intente
    #   nuevamente luego de JUGAR UN JUEGO»*, no «luego de N minutos». O sea que el candado no es
    #   un reloj: se abre acá, en el START, que es el único momento en que la sala juega.
    #   ⚠ Va en el START y no en el final de la carrera a propósito: una partida abandonada a
    #     mitad de camino dejaría la campana trabada para siempre.
    try:
        from .lobby_campana import liberar_campana
        liberar_campana(getattr(st, "room_id", None), "START")
    except Exception as _e_camp:                                     # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude rehabilitar la campana de la sala: {_e_camp!r}")
    # ★★★ LOS CUPONES DE LA PARTIDA (`FF80`), justo antes del `FF25`: sin esto cada cliente sólo ve
    #   SUS cupones (el Grito del Héroe lo veía únicamente el que lo tenía). Ver
    #   `FF80_CUPONES_DE_PARTIDA` en `ajustes.py`.
    _ff80 = None
    if FF80_CUPONES_DE_PARTIDA:
        try:
            from .catalogo import cupones_de_partida
            from .paquetes import build_ff80_cupones
            _cup = [(getattr(_c, "room_slot", None),
                     cupones_de_partida((db_get_char(getattr(_c, "usn", 0)) or {}).get("parts")))
                    for _c in _jug24]
            _cup = [(s, its) for s, its in _cup if s is not None]
            _ff80 = build_ff80_cupones(_cup)
            for _c in list(_jug24) + list(_esp24):
                _c.send_ff55(0x80, _ff80, name=f"FF80 cupones de la partida {_cup}")
            if any(its for _s, its in _cup):
                log("LOBBY", f"  ★★ FF80 CUPONES DE LA PARTIDA: {_cup}")
        except Exception as _e80:                                      # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude mandar el FF80 de cupones: {_e80!r}")
    for _c in _jug24:
        _c.game_magic = st.game_magic       # la MISMA clave para todos
        # ★ "está adentro de la carrera". Lo apaga el `FF13` que el cliente pide al VOLVER a la
        #   sala (`h_19_ff13`), así que también cubre el rato del cartel de resultado. Único uso:
        #   no mandarle el aviso de traspaso de anfitrión ahí, que es lo que tumbaba al CBT.
        _c.en_carrera = True
        _c.carrera_colgada = False          # ★ 17-oct: ver `_reloj_del_cartel` (el colgado de la carrera anterior)
        try:
            # ★ `ld` (lo de la sala) + la cola de ESTE jugador (sus obstáculos). Con el centinela, nada nuestro.
            _cola = b"" if FF25_SENTINEL else cola_ff25_jugador(_rid24, getattr(_c, "usn", None))
            # ★★ LA PISTA PROPIA (2026-10-08): el mapa (@4, u16) de ESTE jugador, si eligió uno para sí.
            _ld_c, _mp_c = ld, mp
            _pp = None if (FF25_SENTINEL or not _propia_ok) else pista_propia_de(_rid24, getattr(_c, "usn", None),
                                                                                    coop=_coop25)
            if _pp is not None:
                _mp_c = pista_de_carrera(_pp)          # ★ su «Aleatoria» propia tiene su propio sorteo
                _ld_c = ld[:4] + struct.pack("<H", _mp_c & 0xFFFF) + ld[6:]
            _c.send_ff55(0x25, _ld_c + _cola, name=f"FF25 LOADGAME magic=0x{st.game_magic:08X} map={_mp_c}"
                                                   f"{' (la suya)' if _pp is not None else ''} song={song}"
                                                   f"{' cola=' + _cola.hex() if _cola else ''}")
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandar el LOADGAME a usn={getattr(_c,'usn','?')}: {e!r}")
    for _ce in _esp24:                       # ★ los que MIRAN: mismo LOADGAME, sin entrar al padrón
        # ★ Y LA MISMA CLAVE. Al espectador le mandamos el `magic` de la carrera adentro del `FF25`,
        #   así que su cliente va a ofuscar con ÉSE lo que mande: si no lo anotamos, sus `FF4E`
        #   entrarían ilegibles. Hoy los descartamos igual (el que mira no juega), pero la clave
        #   tiene que decir la verdad — una copia desincronizada es de las que se cobran en tres
        #   meses. ⚠ Para lo que SALE no cambia nada: el `send_ff4e` va en claro.
        _ce.game_magic = st.game_magic
        try:
            # ★ el que mira no corre: le va la cola de la SALA (lo del anfitrión), que es lo que verá de fondo
            _cola_e = b"" if FF25_SENTINEL else cola_ff25_jugador(_rid24, None)
            _ce.send_ff55(0x25, ld + _cola_e, name=f"FF25 LOADGAME (ESPECTADOR) map={mp} song={song}")
        except Exception as _e:
            log("LOBBY", f"  ⚠ no pude mandarle el LOADGAME al espectador: {_e!r}")
    # ★ Y la sala pasa a "Jugando" en la lista del lobby: es lo que evita que alguien la
    #   clickee en el medio. El rechazo del FF11 es la red; esto es no llegar a necesitarla.
    if _rid24 is not None:
        marcar_en_juego(_rid24, True)
        # ★★★★★ Y SE ARMA EL RELOJ DEL ARRANQUE — 2026-09-08. Ver `arrancar_tarde`: si alguien no
        #   manda su `FF25` (cerró el juego cargando, crasheó, o su máquina no llega), sin esto la
        #   sala entera se queda **mirando la pista sin que empiece nunca**. Pasó en producción.
        #   ⚠ Va acá, en el START, y no en el primer `FF25`: el que se cuelga puede ser el PRIMERO,
        #     y entonces no habría ningún `FF25` que armara el reloj. El tiempo se cuenta desde que
        #     mandamos el `LOADGAME`, que es cuando empieza la espera de verdad.
        if FF25_ESPERA_MAX > 0:
            _t25 = threading.Timer(FF25_ESPERA_MAX, arrancar_tarde, (_rid24,),
                                   {"magic": st.game_magic, "esperado": FF25_ESPERA_MAX})
            _t25.daemon = True          # que un reloj pendiente no impida apagar el server
            _t25.start()
    _cs = getattr(st, "chase_songs", None) if getattr(st, "room_colab", False) else None
    log("LOBBY", f"  ★ FF24 START -> FF25 LOADGAME a {len(_jug24)} jugador(es) "
                 f"magic=0x{st.game_magic:08X} map={mp} "
                 + (f"★CHASE songcount={len(_cs)} canciones={_cs}" if _cs else f"song={song}")
                 + f" (sentinel={FF25_SENTINEL}) sala={getattr(st, 'room_id', None)} anfitrión usn={getattr(st, 'usn', None)}")


def dar_el_go(rid, motivo=""):
    """Manda el `FF24 GO` a la sala. **Una sola vez por carrera**, pase por donde pase.

    ★ Existe para que el arranque tenga UN solo camino. Antes vivía suelto adentro de `h_31_ff25`,
      y al agregarle el reloj del arranque habrían quedado dos copias — que es exactamente cómo se
      desincronizan (ver el `FF28`, donde el reloj **reusa** el handler en vez de duplicarlo).

    ⚠ El `arrancada` no es un lujo: sin él, el reloj y el último `FF25` pueden mandar el `GO` dos
      veces, y un segundo arranque en pleno juego reinicia la pista de todos.
    """
    with _mesa_lock:
        _car = CARRERAS.get(rid)
        if _car is None or _car.get("arrancada"):
            return 0
        _car["arrancada"] = True
        _jug = set(_car.get("jugadores") or ())
        _cargados = set(_car.get("cargados") or ())
    _esp_go = espectadores_de(rid) if rid is not None else []
    # ★ 14-oct · LA SALA DE 12 CON ESPECTADORES (ESPECTADOR_12.md): el corredor transmite (FF98, globo, calculadora)
    #   sólo si sabe que alguien mira ([cGame+0xC1C], lo prende el FFBB). En la de 6 se entera por el FF0C de los que
    #   miran (lugares 6..11); en la de 12 ese FF0C no le va (sus 12 lugares) ⇒ el FFBB al GO, ya en carrera: el juego
    #   la apaga al terminar (0x4F27E0 → 0x563100), así que no queda prendida en la sala (el cartel «no puede iniciar
    #   solo» que daba mandarlo en la sala, ver salas.difundir_espectadores).
    # ⛔⛔ 16-oct · Y VA ANTES DEL GO, no después: `0x4F0A80` (el arranque, al procesar el GO) arma el reloj del FF98
    #   UNA sola vez, si `[+0xC1C]` ya está. Mandado después, casi nadie transmitía en toda la carrera (1–3 de 12,
    #   medido en prod con Frida) y el que miraba veía breaks falsos y saltos. Mismo flujo TCP ⇒ llega primero.
    #   Ver documentacion/ESPECTADOR_12_SIN_TRANSMISION.md.
    from .ajustes import FFBB_12_ANTES_DEL_GO

    def _ffbb12(cuando):
        if not (_esp_go and rid is not None):
            return
        try:
            from .salas import asientos_de_la_sala
            if asientos_de_la_sala(rid) == 12:
                for _u in _jug:
                    _c = CONEXIONES.get(_u)
                    if _c is not None and not getattr(_c, "cerrado", False):
                        _c.send_ff55(0xBB, struct.pack("<I", len(_esp_go)),
                                     name=f"FFBB {cuando} del GO (sala de 12, {len(_esp_go)} miran)")
        except Exception as e:                                              # noqa: BLE001
            log("LOBBY", f"  ⚠ el FFBB {cuando} del GO de la sala de 12: {e!r}")
    if FFBB_12_ANTES_DEL_GO:
        _ffbb12("antes")
    _n = 0
    for _u in _jug:
        _c = CONEXIONES.get(_u)
        if _c is None or getattr(_c, "cerrado", False):
            continue
        try:
            _c.send_ff55(0x24, bytes([0, 0]), name="FF24 GO count=0 (arranca carrera)")
            _n += 1
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandar el GO a usn={_u}: {e!r}")
    # ★★ Y EL "GO" A LOS ESPECTADORES (2026-09-08). Reportado: *"la partida cargó para todos, pero
    #   para los espectadores no empezó, se quedaron esperando el arranque"*. El GO salía sólo para
    #   `jugadores`, y el espectador NO está ahí a propósito (esa lista es la de quienes deben
    #   reportar el `FF28`, ver `h_30_ff24`). Pero el arranque sí tiene que llegarle.
    for _ce in _esp_go:
        try:
            _ce.send_ff55(0x24, bytes([0, 0]), name="FF24 GO (ESPECTADOR)")
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandar el GO al espectador: {e!r}")
    if not FFBB_12_ANTES_DEL_GO:
        _ffbb12("después")                                                  # el orden viejo (control al revés)
    # ★ LOCAL: los NPC que juegan arrancan con el GO (el que espera su tramo de relevo no avisa nada). Ver npc_carrera.
    if CHASE_NPC_REALISTA and rid is not None:
        try:
            from . import npc_carrera
            _cs_go = [CONEXIONES.get(_u) for _u in _jug]
            _cs_go = [c for c in _cs_go if c is not None and not getattr(c, "cerrado", False)]
            npc_carrera.al_arrancar(rid, _cs_go[0] if _cs_go else None, _cs_go + list(_esp_go))
        except Exception as e:
            log("LOBBY", f"  ⚠ el arranque de los NPC: {e!r}")
    _falt = sorted(_jug - _cargados)
    log("LOBBY", f"  ★★ FF24 GO a {_n} jugador(es)"
                 + (f" + {len(_esp_go)} espectador(es)" if _esp_go else "")
                 + (f" ⚠ SIN esperar a {_falt} (no cargaron)" if _falt else "")
                 + motivo)
    return _n


def arrancar_tarde(rid, magic=None, esperado=0.0):
    r"""★★★★★ EL RELOJ DEL ARRANQUE (2026-09-08). Arranca la carrera aunque falte alguien por cargar.

    ⛔ EL BUG, reportado por el usuario desde adentro de la partida y confirmado en el log de
      PRODUCCIÓN de ese mismo rato:

          14:33:38  ⏳ FF25 cargó usn=9117; faltan [10026]
          (y nada más — el `GO` nunca salió)
          14:35:19  ★ conexión usn=10026 dada de baja     ← cerró el juego mientras cargaba

      `h_31_ff25` esperaba a que cargaran **todos**, sin límite. El que nunca reporta deja a la
      sala entera **mirando la pista sin que empiece**. Tal cual lo describió: *"cargó pero no
      empezó… los demás cerraron alt+F4 para crear otra sala"*.

    ★ Es el MISMO modo de falla que `_cerrar_cartel_tarde` ya arreglaba en la otra punta (allá se
      esperaba el reporte del final; acá, la carga del principio), y el CBT ya tenía este guard.
      Por eso está escrito igual: mismo sello de partida, mismo `daemon`, y **reusa** `dar_el_go`
      en vez de escribir un segundo arranque.

    ⚠ EL SELLO (`magic`) NO ES PARANOIA: un reloj armado en la carrera A sigue vivo si la sala
      arranca la B, y al saltar mandaría un `GO` en el medio. El `magic` lo pone el `FF24 START`
      al reemplazar la entrada de `CARRERAS`, así que distingue una corrida de la siguiente.
    """
    with _mesa_lock:
        _car = CARRERAS.get(rid) or {}
        if not _car or _car.get("arrancada"):
            return                                    # ya arrancó por la vía normal
        if magic is not None and _car.get("magic") != magic:
            log("LOBBY", f"  ⏰ reloj de ARRANQUE viejo de la sala {rid} "
                         f"(magic {magic} != {_car.get('magic')}) -> lo ignoro, ya es otra carrera")
            return
        _faltan = set(_car.get("jugadores") or ()) - set(_car.get("cargados") or ())
    if not _faltan:
        return
    _vivos = [u for u in _faltan
              if CONEXIONES.get(u) is not None and not getattr(CONEXIONES.get(u), "cerrado", False)]
    log("LOBBY", f"  ⏰⏰ RELOJ DE ARRANQUE: la sala {rid} lleva {esperado:.0f} s esperando a "
                 f"{sorted(_faltan)} y no arranca. De ésos siguen conectados {sorted(_vivos)} "
                 f"-> ARRANCO IGUAL, que la sala no se quede clavada en la pista.")
    dar_el_go(rid, motivo=f"  ⏰ (por el reloj de {esperado:.0f} s)")


def revisar_arranque(rid):
    """¿Se puede arrancar ya? Se llama cuando alguien SE VA de una sala que está cargando.

    ⛔ EL SEGUNDO AGUJERO, y es el que se vio en producción: el que faltaba por cargar **se
      desconectó**, así que su `FF25` no iba a llegar nunca… y nadie volvía a mirar si los demás
      podían empezar. El reloj lo hubiera destrabado igual, pero tarde: acá se arranca en el acto.
    ⚠ Sólo si YA cargaron todos los que quedan vivos. Si todavía falta alguien conectado, se le
      sigue esperando (para eso está el reloj).
    """
    if rid is None:
        return
    with _mesa_lock:
        _car = CARRERAS.get(rid) or {}
        if not _car or _car.get("arrancada"):
            return
        _faltan = set(_car.get("jugadores") or ()) - set(_car.get("cargados") or ())
    _vivos = [u for u in _faltan
              if CONEXIONES.get(u) is not None and not getattr(CONEXIONES.get(u), "cerrado", False)]
    if _faltan and not _vivos:
        log("LOBBY", f"  ⏰ los que faltaban por cargar en la sala {rid} ya no están "
                     f"({sorted(_faltan)}) -> arranco con los que quedan")
        dar_el_go(rid, motivo="  (se fueron los que faltaban por cargar)")


def _go_sin_el_que_mira(rid, magic):
    """El reloj de `GO_ESPERA_ESPECTADOR_S`: si el que mira no terminó de cargar, arrancan los que corren igual.
    ⚠ Con el SELLO de la carrera (como `arrancar_tarde`): un reloj de la carrera anterior no arranca la nueva."""
    from .ajustes import GO_ESPERA_ESPECTADOR_S
    _car = CARRERAS.get(rid)
    if _car is None or _car.get("magic") != magic:
        return 0
    return dar_el_go(rid, motivo=f"  (el que mira no terminó de cargar en {GO_ESPERA_ESPECTADOR_S:.0f} s)")


def h_31_ff25(st, cmd, data):
    # rama original:  cmd == 37
    # FF24 GO recv 0x5CE930: lee count; si count>0 loop de entradas por-jugador [u8][16B]; luego [final:u8] y
    # dispara el arranque (vtable [[0x9314cc]+0xaffc]+0x58). count=0 = arranque directo (sin posiciones iniciales).
    # ★★★ EL "GO" SE ESPERA A QUE CARGUEN TODOS. Si se le manda a cada uno apenas termina de
    #   cargar, el que cargó primero arranca solo y corre contra un rival congelado. La VM tarda
    #   bastante más que el host, así que el desfase no es teórico.
    _rid25 = getattr(st, "room_id", None)
    _car = CARRERAS.get(_rid25) if _rid25 is not None else None
    if _car is None:
        st.send_ff55(0x24, bytes([0, 0]), name="FF24 GO count=0 (arranca carrera)")
        log("LOBBY", "  ★ FF25 (cargado) -> FF24 GO count=0 (sin carrera registrada: solo)")
    elif _car.get("arrancada") and set(_car.get("jugadores") or ()) == {getattr(st, "usn", None)}:
        # ★★ «REPETIR» DE LA PAUSA (04-oct, `documentacion/PAUSA_REPETIR.md`). La d3d9 pone el botón SÓLO
        #   si el jugador corre solo; al apretarlo, el cliente vuelve a cargar la carrera (0x413760) y manda
        #   OTRO `FF25`. `dar_el_go` no lo contesta (una sola vez por carrera, a propósito: en grupo, un
        #   segundo GO reinicia la pista de TODOS) ⇒ sin esto se quedaría mirando la pista sin arrancar.
        #   Acá no hay nadie más a quien reiniciar: el GO va sólo a él.
        st.send_ff55(0x24, bytes([0, 0]), name="FF24 GO count=0 (REPETIR, solo)")
        log("LOBBY", f"  ↻ FF25 de nuevo en una carrera ya arrancada, corre SOLO (usn={getattr(st, 'usn', '?')}): "
                     f"«Repetir» de la Pausa -> FF24 GO otra vez")
    else:
        from .ajustes import GO_ESPERA_ESPECTADOR_S
        with _mesa_lock:
            _car["cargados"].add(getattr(st, "usn", None))
            _faltan = _car["jugadores"] - _car["cargados"]
            _vivos = {u for u in (_car.get("espectadores") or ())
                      if CONEXIONES.get(u) is not None and not getattr(CONEXIONES.get(u), "cerrado", False)}
            _faltan_esp = (_vivos - _car["cargados"]) if GO_ESPERA_ESPECTADOR_S > 0 else set()
            _primera_espera = not _faltan and _faltan_esp and not _car.get("esperando_espectador")
            if _primera_espera:
                _car["esperando_espectador"] = True
        if _faltan:
            log("LOBBY", f"  ⏳ FF25 cargó usn={getattr(st,'usn','?')}; faltan {sorted(_faltan)}"
                         + (f" (el reloj arranca igual en {FF25_ESPERA_MAX:.0f} s)"
                            if FF25_ESPERA_MAX > 0 else ""))
        elif _faltan_esp:
            # ★★ (12-oct) los corredores ya cargaron y falta alguien que MIRA: se lo espera, pero con tope. El GO es
            #   de una sola vez (`dar_el_go`), así que el reloj y el último FF25 no pueden mandarlo dos veces.
            if _primera_espera:
                _te = threading.Timer(GO_ESPERA_ESPECTADOR_S, _go_sin_el_que_mira, (_rid25, _car.get("magic")))
                _te.daemon = True
                _te.start()
            log("LOBBY", f"  ⏳ FF25 cargaron los corredores; falta(n) cargar {sorted(_faltan_esp)} que mira(n) "
                         f"-> el GO espera hasta {GO_ESPERA_ESPECTADOR_S:.0f} s")
        else:
            # ★ El arranque tiene UN solo camino (ver `dar_el_go`): el reloj usa el mismo.
            dar_el_go(_rid25, motivo="  (cargaron todos)" + (" y los que miran" if _car.get("espectadores") else ""))


def h_38_ff10f(st, cmd, data):
    # rama original:  cmd == 271
    # El cartel "Captua a Gorila": una CUERDA y la cara del gorila se mueven sobre una barra y hay
    # que apretar Ctrl cuando se cruzan. El cliente manda su resultado y **SE QUEDA ESPERANDO**.
    #
    # C->S = **1 byte = el PUNTAJE CRUDO 0..100** (sender `0x5DFC20`, llamador `0x570C00`).
    #   ⚠ NO es el grado: el propio cliente lo umbraliza despues (>=0x5A=90 -> grado 1,
    #     >=0x46=70 -> grado 2, menos -> grado 3). Si no apretas nada, un timeout manda 0.
    # S->C = **2 bytes** (handler `0x5DFD90` -> `0x56BAD0(A,B)`), y el primero decide la rama:
    #   A != 6 -> `[slot][score]` = "el jugador del slot tal saco tanto". Se INSERTA en un
    #             `std::map<slot,score>` del minijuego (`0x571540`); insert **no pisa** una clave
    #             que ya este.
    #   A == 6 -> ★ el DISPARADOR: `cBossNPC::Command(0x86)` pone el deadline de resolucion
    #             (`[gorila+0x1ac] = contador + 60`). **Sin esto no se resuelve NUNCA**: ese campo
    #             nace en `0xFFFFFF` (`0x56A274`) y el update `0x56CC70` no hace nada mientras
    #             `+0x1ac > +0x1a8`. El 2º byte se ignora en esta rama.
    #
    # ★★ CONDICION DE VICTORIA (`0x570E30`): gana si **`aciertos*2 >= cantidad de resultados`**,
    #   contando acierto = `score >= 70` (`0x56FD80`). Se evalua sobre el TAMAÑO DEL MAP, no sobre
    #   la cantidad de jugadores de la sala.
    #   ⚠⚠ POR ESO HAY QUE MANDAR SIEMPRE EL `[slot][score]`: con el map VACIO da `0 >= 0` =
    #      **VICTORIA REGALADA**. Mandar solo el `[06][00]` seria hacer trampa a favor del jugador.
    # ⚠ Multijugador: el `[06][xx]` solo surte efecto en el cliente **MASTER** (guard `0x569C60`:
    #   `mi_slot == master_slot`). Los demas se enteran por el broadcast `cmd 0x26` que emite el
    #   master, asi que cuando haya varios jugadores el server va a tener que retransmitirlo.
    # ⛔ Ninguna de las dos ramas (exito `0x56C910` / fracaso `0x56C140`) manda un paquete: el
    #   resultado es LOCAL del cliente. El premio se comunica aparte (FF119 monedas / FF10E cajas).
    _score = data[0] if data else 0
    _grado = 1 if _score >= 90 else (2 if _score >= 70 else 3)
    # ★★ VICTORIA SERVER-SIDE (2026-08-04). El cliente resuelve el minijuego LOCALMENTE y **no
    #   avisa el resultado por red** (ni la rama de éxito `0x56C910` ni la de fracaso `0x56C140`
    #   mandan nada) ⇒ el server tiene que sacar la misma cuenta por su lado.
    #   Regla del cliente (`0x570E30`): gana si **aciertos*2 >= resultados recibidos**, con
    #   acierto = `score >= 70` (`0x56FD80`). Con UN solo jugador se reduce a `score >= 70`.
    #   ⚠ Cuando haya varios habrá que acumular los scores de todos y aplicar la fórmula entera.
    # (el `chase_gano` lo calcula _disparar_gorila con TODOS los puntajes)
    # ★★★★ 2026-09-01 — ORDEN CORREGIDO CONTRA EL WIRE REAL (7 rondas capturadas).
    #   El server que anda difunde PRIMERO todos los `[slot][score]` y manda el `[06][00]`
    #   **AL FINAL**, cuando ya reportaron todos. Nosotros lo mandábamos pegado al score del
    #   propio jugador ⇒ con varios jugadores el minijuego se resolvía con el map casi vacío.
    #   Confirmado además: el real **nunca te devuelve tu propio slot** (vos ya te insertaste).
    #   ⛔ CORREGIDO 2026-09-02: acá decía que "los scores sólo valen 0 / 80 / 100 (el cliente
    #      manda su grado ya umbralizado)". **Es falso.** En 14 rondas capturadas aparecen 43
    #      valores continuos entre 0 y 99 (48, 55, 61, 87, 95, 99…). El byte es el PUNTAJE
    #      CRUDO, como ya dice el comentario del C->S de más arriba, y este handler lo reenvía
    #      tal cual — o sea que el código estaba bien y la nota estaba mal.
    #   ⚠ Con UN solo jugador SÍ hay que mandarle el suyo: si no, el map queda vacío y
    #     `0>=0` le regala la victoria (ver la nota de arriba).
    st.chase_score = _score
    _rid10f = getattr(st, "room_id", None)
    _dest10f = [CONEXIONES.get(u) for u in mesa_de(_rid10f).values()] if _rid10f is not None else []
    _dest10f = [c for c in _dest10f if c is not None and not getattr(c, "cerrado", False)] or [st]
    _mislot = getattr(st, "room_slot", None)
    if _mislot is None:
        _mislot = HOST_SLOT
    # ★★★ EL PUNTAJE VA A TODOS, TAMBIÉN AL QUE LO MANDÓ (corregido 2026-09-02).
    #   ⛔ Acá se salteaba al emisor, por una nota que decía "el real nunca te devuelve tu
    #      propio slot (vos ya te insertaste)". **Es falsa.** Medido en la captura: el
    #      server de referencia difundió el slot 4 —el del jugador capturado— 14 veces.
    #   El daño era exacto y explicaba dos síntomas a la vez: cada cliente armaba un mapa
    #   DISTINTO, así que sacaban resultados distintos del mismo minijuego.
    #      el que sacó 80 recibía sólo {otro:0}  -> 0 de 1 -> FALLA  -> sigue corriendo
    #      el que sacó  0 recibía sólo {otro:80} -> 1 de 1 -> captura -> termina
    #   Reportado tal cual: "completé el minijuego pero salió como si hubiera fallado, y
    #   seguí corriendo; la otra instancia dejó de correr pero no recibió cartel" — el
    #   cartel esperaba al que nunca terminaba.
    for _c in _dest10f:
        _c.send_ff55(0x10F, bytes([_mislot & 0xFF, _score & 0xFF]),
                     name=f"FF10F slot={_mislot} score={_score}")
    # ★★★ EL TOKEN DE RONDA — arreglo del 2026-09-02.
    #   ⛔ El guard de antes (`any(chase_disparado)`) NO servía para nada: la misma función
    #      ponía la bandera en True y la volvía a False tres líneas después, así que cuando
    #      vencía el temporizador de respaldo la encontraba SIEMPRE apagada y disparaba un
    #      SEGUNDO `[06][00]`.
    #   Medido en el log del 17:32:50 — dos disparos, uno "ya reportaron todos" y otro
    #   "venció la espera" 6 s más tarde. Consecuencias, las dos reportadas por el usuario:
    #     · la ronda siguiente se resolvía sola, sin dejar apretar (“se skipeó”)
    #     · y se resolvía con el map VACÍO ⇒ `0*2 >= 0` ⇒ **victoria regalada** en pantalla,
    #       mientras el server la contaba como derrota y mandaba “No hay premio”.
    #   Ahora cada ronda lleva un número: el temporizador guarda el suyo y sólo dispara si
    #   la ronda sigue siendo esa. Resuelta la ronda, el token cambia y el timer viejo muere.
    _token = getattr(st, "chase_token", 0)

    def _disparar_gorila(dest, motivo, token):
        """Manda el `[06][00]` UNA sola vez por ronda y cierra la ronda."""
        vivos = [c for c in dest if not getattr(c, "cerrado", False)]
        _desfasados = [c for c in vivos if getattr(c, "chase_token", 0) != token]
        if not vivos or _desfasados:
            # ⚠ 2026-09-06 — ANTES ESTE LOG NO DECÍA QUIÉN, y por eso un desfasaje permanente
            #   (ver el bloque del `chase_token` en el FF24) se leía como un descarte normal:
            #   la sala quedaba muerta y el log parecía tranquilo. Ahora nombra a los que no
            #   coinciden, así se ve de una si es "llegó tarde" o "están desfasados".
            log("LOBBY", f"  · GORILA: disparo descartado ({motivo}): la ronda {token} ya "
                         f"se resolvió"
                         + (f" ⚠ DESFASADOS: "
                            + ", ".join(f"usn={getattr(c, 'usn', '?')} en la ronda "
                                        f"{getattr(c, 'chase_token', 0)}" for c in _desfasados)
                            if _desfasados else " (sin nadie vivo)"))
            return
        # ★★★★★ RELLENO DE LOS QUE NO REPORTARON (2026-09-08). Ver el bloque de
        #   `CHASE_RELLENO` en `ajustes.py`, que explica el porqué entero.
        #   En dos palabras: el divisor de la regla es **el tamaño del map de cada cliente**,
        #   así que un jugador que no manda su `FF10F` no baja el promedio: BAJA EL LISTÓN
        #   para todos los demás. Se lo completa con 0 —que es lo mismo que manda el propio
        #   cliente cuando se le vence el temporizador— y así los seis maps quedan iguales.
        #   ⚠ Va ANTES del `[06][00]`, si no llega tarde: el `[06]` arma el deadline de
        #     resolución y lo que entre después ya no cuenta.
        _reportados_npc = []               # los puntajes inventados de los asientos de NPC
        if CHASE_RELLENO:
            # (1) QUIÉNES hay que completar. Dos familias, y la segunda es fácil de olvidar:
            #   (a) conexiones de verdad que no reportaron;
            #   (b) ★ los asientos de NPC de `.npc`, que **no tienen conexión** y por lo tanto
            #       no están en `vivos` — pero el CLIENTE sí los cuenta como ocupantes. Sin
            #       esto, 1 humano + 5 NPC deja el map con UNA entrada y gana solo: el mismo
            #       síntoma que se quiere reproducir, provocado por el banco de pruebas.
            _faltan = []                                   # [(slot, conexión o None)]
            for c in vivos:
                if getattr(c, "chase_score", None) is None:
                    _faltan.append((_slot_de(c), c))
            _ocupados = {getattr(c, "room_slot", None) for c in vivos}
            for _sl in (npcs_de(getattr(vivos[0], "room_id", None)) or []):
                if _sl not in _ocupados:
                    _faltan.append((_sl, None))
            # (2) QUÉ puntaje le toca a cada uno. Tres formas, de la más específica a la más
            #   general — y la del medio existe por un error medido.
            #
            #   ⛔⛔ 2026-09-08, EL BANCO DE PRUEBAS SE ENGAÑÓ A SÍ MISMO. El preset del caso 2
            #      era `CHASE_RELLENO_SLOTS = {1:95, 2:88, 3:0, 4:0, 5:0}`, o sea "que acierten
            #      los asientos 1 y 2". Pero **el humano se sienta en el 2** (medido: `.npc
            #      full` ocupó [3,1,4,0,5]), así que el 88 se tiraba a la basura y el slot 0
            #      —que no estaba en el dict— caía al 0 por omisión. Resultado: 1 acierto de
            #      NPC en vez de 2, total 2 de 6, y el gorila se escapaba cuando la prueba
            #      esperaba que lo atraparan. El servidor y el cliente estuvieron BIEN los dos:
            #      el que estaba mal era el experimento.
            #      ⇒ Por eso `CHASE_RELLENO_ACIERTOS` cuenta **cuántos**, no **cuáles**: da
            #        igual dónde se siente el humano.
            _n_ok = CHASE_RELLENO_ACIERTOS
            _hechos = 0
            _rellenados = []
            for _sl, _c in _faltan:
                if _sl in CHASE_RELLENO_SLOTS:                 # (a) a dedo, por asiento
                    _pt = CHASE_RELLENO_SLOTS[_sl]
                elif _n_ok is not None:                        # (b) ★ por CANTIDAD
                    _pt = CHASE_RELLENO_PUNTAJE_OK if _hechos < _n_ok else CHASE_RELLENO_PUNTAJE
                    _hechos += 1 if _hechos < _n_ok else 0
                elif CHASE_NPC_REALISTA:                       # (b-bis) ★★ COMO EN PROD
                    #   Sólo en local (va atado a `R2_CONSOLA_GM`). Sin esto todos los NPC sacan
                    #   el mismo número y el gorila se escapa SIEMPRE: no se puede probar la
                    #   captura. Ver `CHASE_NPC_PUNTAJES` en `ajustes.py`.
                    _pt = puntaje_npc_realista()
                else:                                          # (c) todos igual
                    _pt = CHASE_RELLENO_PUNTAJE
                _pt &= 0xFF
                for _d in vivos:
                    _d.send_ff55(0x10F, bytes([_sl & 0xFF, _pt]),
                                 name=f"FF10F slot={_sl} score={_pt} (RELLENO)")
                if _c is not None:
                    _c.chase_score = _pt
                else:
                    # ⚠ Los puntajes de NPC son INVENTADOS. Entran igual en la cuenta del
                    #   server, porque si no el server contaría sobre 1 y el cliente sobre 6.
                    _reportados_npc.append(_pt)
                    # ★ Y se ACUMULAN por sala, igual que `chase_puntos` de los jugadores: es lo
                    #   que después ordena su fila en el cartel (`CHASE_NPC_CARTEL`).
                    _rid_npc = getattr(vivos[0], "room_id", None)
                    if _rid_npc is not None:
                        with _mesa_lock:
                            _acum = CARRERAS.setdefault(_rid_npc, {}).setdefault("puntos_npc", {})
                            _acum[_sl] = _acum.get(_sl, 0) + _pt
                _rellenados.append((_sl, _pt, "NPC" if _c is None else "no reportó"))
            if _rellenados:
                _ok = sum(1 for _s, _p, _q in _rellenados if _p >= 70)
                log("LOBBY", "  ★★ GORILA: relleno " + ", ".join(
                    f"slot {s}={p} ({q})" for s, p, q in _rellenados)
                    + f"  ⇒ {_ok} acierto(s) puestos por el relleno. Sin esto el map quedaba "
                      f"corto (y el listón más bajo para todos). Se apaga con CHASE_RELLENO.")
        # ★ La MISMA cuenta que hace el cliente (`0x5708C0` / `0x56FA30`, releídas del exe el
        #   2026-09-08): gana si `aciertos*2 >= cuántos puntajes tiene el map`, con acierto =
        #   score >= 70. Antes se miraba SÓLO el puntaje del último que reportó
        #   (`_score >= 70`), así que con varios jugadores el server y el cliente podían
        #   decidir cosas distintas — y decidían.
        _reportados = [getattr(c, "chase_score", None) for c in vivos]
        _reportados = [s for s in _reportados if s is not None]
        # ★ Los asientos de NPC entran en la MISMA cuenta. Si no, el server contaría sobre 1 y
        #   el cliente sobre 6, y volveríamos a tener dos veredictos distintos para lo mismo —
        #   que es el error que ya se pagó el 2026-09-02.
        _reportados += _reportados_npc
        _aciertos = sum(1 for s in _reportados if s >= 70)
        _gano = bool(_reportados) and _aciertos * 2 >= len(_reportados)
        # ★★★★★ QUIÉN ACTIVÓ EL MINIJUEGO — se congela ACÁ (2026-09-10).
        #   Es el que iba MÁS ADELANTE en la pista, o sea el que tenía al gorila más cerca.
        #   Se decide al resolverse la ronda y no después, porque durante la cuerda los corredores
        #   dejan de mandar avance: el último valor que llegó es el de cuando arrancó el minijuego.
        #   ⚠ Sólo con `_gano`: si el gorila se escapó no hubo captura y no hay a quién poner
        #     primero. Y si nadie mandó avance, no se toca nada y manda el esfuerzo.
        _rid_act = getattr(vivos[0], "room_id", None)
        if _gano and CHASE_PRIMERO_EL_QUE_ACTIVA and _rid_act is not None:
            _av = avance_de(_rid_act)
            # ⛔⛔ LOS NPC NO EXISTEN PARA EL SERVER, Y SÍ ACTIVAN EL MINIJUEGO (2026-09-10).
            #   anonimo03: *"los NPC han estado activando el minijuego — ellos no corren pero tampoco
            #   chocan, y uno se acerca tanto que lo activa; así ha estado funcionando del lado
            #   del cliente"*.
            #   ⇒ Un NPC **no manda `FF4E`**: se mueve sólo dentro de cada cliente. El server no
            #     ve su avance NUNCA, así que `_av` sólo tiene a los humanos y el activador
            #     siempre saldría "el jugador" — justo al revés de lo que pasa en pantalla.
            #     No es un fallo de la regla: el server es ciego a los NPC, y punto.
            #   ⇒ En LOCAL se les inventa un avance para que la prueba se parezca a lo que se ve
            #     (van parejos con el humano y a veces lo pasan, porque no chocan). En prod no hay
            #     NPC en cooperativo y este bloque no corre.
            #   ⚠ Lo que se inventa NO es el activador: es el avance. Quién activó lo sigue
            #     decidiendo el mismo `max()` para todos.
            if CHASE_NPC_REALISTA and _av:
                _base_av = max(_av.values())
                _ocup_av = {getattr(c, "room_slot", None) for c in vivos}
                for _sl_av in (npcs_de(_rid_act) or []):
                    if _sl_av in _ocup_av or _sl_av in _av:
                        continue
                    _av[_sl_av] = _base_av * random.uniform(*CHASE_NPC_AVANCE)
                    anotar_avance(_rid_act, _sl_av, _av[_sl_av])
            if _av:
                _quien = max(_av, key=lambda s: _av[s])
                with _mesa_lock:
                    CARRERAS.setdefault(_rid_act, {})["gorila_activo"] = _quien
                log("LOBBY", f"  ★★★ GORILA: lo ATRAPÓ el slot {_quien} — iba adelante "
                             f"({_av[_quien]:.0f} de pista) " +
                             " · ".join(f"slot {s}={_av[s]:.0f}" for s in sorted(_av)) +
                             ". Elige cofre PRIMERO; el resto va por esfuerzo.")
            else:
                log("LOBBY", "  ⚠ GORILA: nadie mandó avance en esta ronda -> no hay activador, "
                             "el orden lo decide el esfuerzo (ver CHASE_PRIMERO_EL_QUE_ACTIVA)")
        for c in vivos:
            c.chase_token = token + 1              # cierra la ronda: los timers viejos mueren
            c.chase_gano = _gano
            # ★★★★★ EN QUÉ RONDA SE ATRAPÓ — 2026-09-15, lo pidió anonimo03: *"si lo atrapan durante
            #   la primera canción es un S, durante la segunda un B, durante la tercera un D"*.
            #   Es el dato que le faltaba al cartel para dar el medallón bien. Se guarda SÓLO en
            #   la captura: si el gorila se escapa, queda en `None` y el cartel da 'F'.
            #   ⚠ Y se anota ACÁ, no al cerrar: al cerrar el `chase_token` ya avanzó.
            if _gano and getattr(c, "chase_ronda_captura", None) is None:
                c.chase_ronda_captura = token
            c.send_ff55(0x10F, bytes([6, 0]),
                        name=f"FF10F [06][00] = resolver (ÚLTIMO, {motivo})")
            c.chase_ronda = getattr(c, "chase_ronda", 0) + 1
        log("LOBBY", f"  ★★ GORILA ronda {token}: scores {_reportados} -> {_aciertos} "
                     f"acierto(s) de {len(_reportados)} ⇒ {'CAPTURA' if _gano else 'se escapó'} "
                     f"(la misma cuenta que hace el cliente)")
        for c in vivos:
            # ★ Se ACUMULA lo que aportó cada uno en el minijuego, ronda a ronda. Es la
            #   medida de "quién atrapó al gorila": con eso se ordena el cartel y, por lo
            #   tanto, el turno para elegir caja (que sale del mismo orden).
            c.chase_puntos = getattr(c, "chase_puntos", 0) + (getattr(c, "chase_score", 0) or 0)
            c.chase_score = None
            c.chase_disparado = False
        log("LOBBY", f"  ★★ GORILA: disparo la resolución ({motivo})")
        if FF27_PEDIR_RESULTADO and getattr(vivos[0], "chase_ronda", 0) >= CHASE_RONDAS:
            for c in vivos:
                c.chase_ronda = 0
                c.send_ff55(0x27, b"", name="FF27 = mandame tu resultado (cierra la corrida)")
            log("LOBBY", f"  ★★ FF27 a {len(vivos)} jugador(es): se cumplieron las "
                         f"{CHASE_RONDAS} rondas -> que manden su FF28 y sale el cartel")

    if all(getattr(_c, "chase_score", None) is not None for _c in _dest10f):
        _disparar_gorila(_dest10f, "ya reportaron todos", _token)
    else:
        # ⚠ RED DE SEGURIDAD: si uno se cuelga o se va sin reportar, sin esto el minijuego no
        #   se resuelve NUNCA y el cliente queda esperando (el modo de falla clásico de este
        #   proyecto). A los `FF10F_ESPERA` segundos se dispara igual con lo que haya.
        threading.Timer(FF10F_ESPERA, _disparar_gorila,
                        args=(_dest10f, f"venció la espera de {FF10F_ESPERA}s",
                              _token)).start()
    log("LOBBY", f"  ★★★ GORILA: el jugador saco {_score}/100 (grado {_grado}, "
                 f"{'ACIERTO' if _score >= 70 else 'fallo'}) -> se difunde "
                 f"[slot={_mislot}][{_score}] a los {len(_dest10f)} de la sala (INCLUÍDO él) "
                 f"y despues [06][00] para que resuelva "
                 f"(~60 frames). Gana si aciertos*2 >= resultados recibidos.")


def _slot_de(c, por_defecto=HOST_SLOT):
    """El asiento de una conexión, **respetando el slot 0**.

    ⛔⛔ EL BUG QUE ESTA FUNCIÓN VIENE A MATAR (2026-09-06). En todo el camino de los premios del
      gorila se escribía `getattr(c, "room_slot", None) or HOST_SLOT`, y **en Python `0 or X` da
      `X`**: el asiento 0 se convertía en el 2 en OCHO lugares distintos. Consecuencias medidas:

        · `_slot_del_que_mas_aporto` — si el que más aportó estaba en el slot 0, el turno se le
          daba al slot 2. El premio le aparecía **al que no era**: el *"premio corrido"*.
        · el `sub=4` — si el del slot 0 abría una caja, se anotaba como abierta **por el slot 2**.
          El slot 0 seguía figurando entre los pendientes ⇒ el revelado, que espera a que abran
          TODOS, **esperaba para siempre a alguien que ya había abierto**. La sala trabada en el
          cartel de premios.

      ★ Y la prueba está en producción: de los 7 tableros repartidos hoy, el ÚNICO que se completó
        fue el de las 16:11 — y en ese abrieron los slots **[1, 2, 3, 4, 5]**, o sea que **no había
        nadie en el slot 0**. Todos los que tenían un jugador ahí se colgaron.

    ⚠ El `por_defecto` sólo entra si NO hay asiento (None). Un 0 es un asiento perfectamente
      válido y tiene que sobrevivir.
    """
    s = getattr(c, "room_slot", None)
    return por_defecto if s is None else s


def _slot_del_que_mas_aporto(rid, yo):
    """El slot del que más aportó al minijuego del gorila en la sala.

    Es "el que atrapó al gorila": el minijuego es colectivo, así que el aporte se mide con
    el puntaje acumulado de las rondas (`chase_puntos`). Si no hay datos —o la sala no
    existe— cae al slot del que preguntó, que es lo que hacíamos siempre.
    """
    if rid is None:
        return _slot_de(yo)
    conns = [CONEXIONES.get(u) for u in mesa_de(rid).values()]
    conns = [c for c in conns if c is not None and not getattr(c, "cerrado", False)]
    if not conns:
        return _slot_de(yo)
    mejor = max(conns, key=lambda c: (getattr(c, "chase_puntos", 0),
                                      -_slot_de(c, 99)))
    return _slot_de(mejor)


def aporte_al_gorila(slot, conn, puntos_npc=None):
    """Cuánto aportó ese asiento a atrapar al gorila. **UNA sola definición, para los dos usos.**

    ★★★★★ POR QUÉ ESTÁ SUELTA (2026-09-10, pregunta de anonimo03: *"¿que se sienten según su aporte,
      empezando por el que capturó al gorila — lo tenemos contemplado?"*).

      El aporte se usa en DOS lugares que tienen que dar EXACTAMENTE lo mismo:

        · el ORDEN DEL CARTEL (`h_21_ff28`) — que es el que decide **en qué columna se sienta
          cada uno** en la pantalla de premios, porque el cliente resuelve la posición con
          `0x575E70`, que devuelve el **ÍNDICE dentro de la lista del cartel**;
        · el ORDEN DE ELECCIÓN (`_orden_de_la_sala`).

      Si los dos no salen del mismo número, la fila resaltada cae sobre la columna del vecino:
      es literalmente el *"premio corrido"*.

      ⛔ Y ya se había vuelto a abrir la grieta el mismo día: el orden de elección respetaba
        `CHASE_NPC_APORTES` (el pisado a dedo de las pruebas) y **el cartel no**, así que en local
        con el preset puesto los dos órdenes discrepaban — justo en la prueba hecha para
        comprobar que NO discrepan.
      ⇒ Un solo lugar donde se define, y los dos lo llaman.
    """
    if conn is not None:
        return getattr(conn, "chase_puntos", 0) or 0
    # ⚠ El pisado a dedo SÓLO vale en local: `CHASE_NPC_REALISTA` va atado a `R2_CONSOLA_GM`.
    if CHASE_NPC_REALISTA and slot in CHASE_NPC_APORTES:
        return CHASE_NPC_APORTES[slot]
    return (puntos_npc or {}).get(slot, 0)


def activador_del_gorila(rid):
    """El slot que ATRAPÓ al gorila: el que iba más adelante cuando se resolvió la ronda.

    `None` = no se supo (nadie mandó avance, o el interruptor está apagado), y entonces el orden
    lo decide el esfuerzo, que es como venía. Ver `CHASE_PRIMERO_EL_QUE_ACTIVA` en `ajustes.py`.
    """
    if rid is None or not CHASE_PRIMERO_EL_QUE_ACTIVA:
        return None
    with _mesa_lock:
        return (CARRERAS.get(rid) or {}).get("gorila_activo")


def _orden_de_la_sala(rid, dest):
    """TODOS los asientos que juegan la ronda de cajas, en orden de aporte al gorila.

    Devuelve `[(slot, conexión o None)]`. Un `None` es un **asiento de NPC**: ese turno lo juega
    el server.

    ⛔⛔ EL BUG QUE VIENE A MATAR (2026-09-10). Los NPC no estaban en esta fila: abrían **todos de
      golpe** apenas elegía el primer humano, y **en el orden en que estaban sentados**. O sea que
      el orden por aporte —que es la regla del modo— sólo se respetaba entre los jugadores de
      carne y hueso. anonimo03 lo pidió al revés de como suele aparecer un bug: *"no puedo ver el
      orden"*, y al ir a hacerlo visible resultó que además estaba mal.

    ⚠ El aporte de un NPC se acumula en `CARRERAS[rid]["puntos_npc"]` (lo llena el relleno del
      minijuego). `CHASE_NPC_APORTES` lo pisa a dedo, para poder fijar el orden en una prueba.
    """
    _porslot = {}
    for c in dest:
        if c is not None and not getattr(c, "cerrado", False):
            _porslot[_slot_de(c)] = c
    _npc_pts = {}
    if rid is not None:
        with _mesa_lock:
            _npc_pts = dict((CARRERAS.get(rid) or {}).get("puntos_npc") or {})
    asientos = list(_porslot.items())
    for _sl in (npcs_de(rid) if rid is not None else []):
        if _sl not in _porslot:
            asientos.append((_sl, None))

    # ★★★ PRIMERO EL QUE ATRAPÓ AL GORILA (el que iba adelante), y recién después el
    #   ESFUERZO. Si no hay activador, `_act` es None y la primera clave da True para todos:
    #   el orden queda como venía, por esfuerzo solo.
    _act = activador_del_gorila(rid)
    asientos.sort(key=lambda par: (par[0] != _act,
                                   -aporte_al_gorila(par[0], par[1], _npc_pts),
                                   par[0]))
    return asientos


def _revelar_las_cajas(rid, dest, premios, abiertas):
    """El `sub 6` FINAL: arranca el revelado **y acredita**. Ver `_paquete_del_revelado`."""
    _rev = _paquete_del_revelado(premios, abiertas)
    # ⛔⛔ UNA SOLA VEZ POR JUGADOR: `0x57D140` acredita cada vez que le llega, sin memoria.
    if rid is not None:
        with _mesa_lock:
            _car = CARRERAS.setdefault(rid, {})
            _car["cajas_revelado"] = True
            _car.setdefault("cajas_revelado_a", set()).update(
                getattr(_c, "usn", None) for _c in dest)
    for _c in dest:
        _c.send_ff55(0x10E, _rev,
                     name=f"FF10E sub=6 REVELADO {len(set(abiertas.values()))} caja(s) con premio "
                          f"-> acredita y cierra")
    # ★★★ Y EL SALDO NUEVO DE MONEDAS, PEGADO AL REVELADO. Así lo hace el referente, medido en
    #   `mitm_20260902_144457.txt` (mismo segundo, el `FF69` justo detrás del `sub 6`):
    #       14:53:00  FF10E sub 6, 164 B      ← el revelado
    #       14:53:00  FF69  01 | 540 | 03     ← el saldo nuevo
    #   ⛔ HACE FALTA: el `type 5` del revelado **NO incrementa ningún contador**. Lo único que
    #     hace es prender un flag (`0x57D209` -> `0x5ABF80` pone `[cRoom+0x2560C] = 1`, un byte) y
    #     dibujar el icono. El número de la pantalla sale del INVENTARIO, y al inventario lo
    #     escribe el `FF69`. Sin esto, ganás una moneda, se ve el icono, y el contador no se mueve
    #     hasta el próximo login — que es tal cual lo que reportó anonimo03.
    #   ⚠ A cada uno el SUYO: `enviar_ff69_moneda_gorila` lee el saldo de la base por `usn`.
    for _c in dest:
        try:
            enviar_ff69_moneda_gorila(_c)
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandar el FF69 de monedas a usn={getattr(_c,'usn','?')}: {e!r}")
    log("LOBBY", f"  ★★★ GORILA: abrieron todos {sorted(abiertas)} -> revelado con premio "
                 f"({len(_rev)} B) a los {len(dest)} de la sala. Cierran solos en ~8 s.")


def _avanzar_turno(rid, dest, premios, abiertas):
    """Le da el turno al siguiente de la fila; si es un NPC lo juega; si no queda nadie, REVELA.

    ★ Es el corazón de la ronda de cajas y **hay uno solo**: lo llaman el `sub 2` (para arrancar)
      y el `sub 4` (cada vez que alguien abre). Antes esta lógica estaba escrita dos veces y media
      —una para el primer turno, otra para los siguientes, y el bloque suelto de los NPC— que es
      exactamente cómo se llega a que los NPC no respeten el orden.
    ⚠ Con `CHASE_NPC_RITMO > 0` el turno del NPC se parte en dos: primero se resalta su columna
      (`sub 3`), y su cofre se abre un segundo después. Sirve para **ver** el orden; en prod va en
      0 y todo pasa en el mismo instante, como venía.
    """
    vivos = [c for c in dest if c is not None and not getattr(c, "cerrado", False)]
    if not vivos:
        return
    for _sl, _c in _orden_de_la_sala(rid, vivos):
        if _sl in abiertas:
            continue
        if rid is not None:
            with _mesa_lock:
                CARRERAS.setdefault(rid, {})["turno_caja"] = _sl
        for _d in vivos:
            _d.send_ff55(0x10E, bytes([3, _sl & 0xFF]),
                         name=f"FF10E sub=3 turno del {'slot' if _c is not None else 'NPC slot'} {_sl}")
        if _c is not None:                       # ★ humano: se le da el turno y se ESPERA
            log("LOBBY", f"  ★ GORILA: abrieron {sorted(abiertas)}; le toca al slot {_sl} "
                         f"(tope {GORILA_TOPE_APERTURA}s).")
            _tope_apertura(rid, _sl, _c)
            return
        # ★ NPC: el turno lo juega el server. La pantalla espera a que abran TODOS los ocupantes,
        #   y un NPC nunca manda su `[04][caja]`.
        _libres = [i for i in range(len(premios)) if i not in abiertas.values()]
        if not _libres:
            break
        _bnpc = CHASE_NPC_CAJAS.get(_sl) if CHASE_NPC_REALISTA else None
        if _bnpc is None:
            _bnpc = _libres[0]
        elif _bnpc not in _libres:
            log("LOBBY", f"  ⚠ GORILA: el NPC del slot {_sl} tenía pedido el cofre {_bnpc} "
                         f"(CHASE_NPC_CAJAS) pero ya lo agarraron -> le doy el {_libres[0]}")
            _bnpc = _libres[0]
        abiertas[_sl] = _bnpc                    # se reserva YA, aunque el `sub 5` salga después

        def _abrir(sl=_sl, bnpc=_bnpc):
            _v = [c for c in vivos if not getattr(c, "cerrado", False)]
            for _d in _v:
                _d.send_ff55(0x10E, bytes([5, sl & 0xFF, bnpc & 0xFF]),
                             name=f"FF10E sub=5 el NPC {sl} abre la caja {bnpc}")
            log("LOBBY", f"  ★ GORILA: el NPC del slot {sl} abre la caja {bnpc}")
            _avanzar_turno(rid, _v, premios, abiertas)

        if CHASE_NPC_RITMO and CHASE_NPC_RITMO > 0:
            _t = threading.Timer(CHASE_NPC_RITMO, _abrir)
            _t.daemon = True                     # que no impida cerrar el server
            _t.start()
        else:
            _abrir()
        return
    _revelar_las_cajas(rid, vivos, premios, abiertas)


def _tope_apertura(rid, slot, conn):
    """Si a los `GORILA_TOPE_APERTURA` segundos ese slot no abrió su caja, se la abrimos nosotros.

    ★★★★★ POR QUÉ EXISTE — EL CUELGUE DEL CARTEL DE PREMIOS, 2026-09-09.

      Reportado por un jugador: *«se buguea cuando reciben recompensas: el primero llega a elegir
      pero se pasa al último y ya no deja escoger a nadie más»*, y las partidas terminaban con la
      gente yendose de a una.

      ⛔ LA CAUSA: el `else` que arranca el revelado **sólo se evalúa cuando llega un `sub=4`**.
        Si el último que falta se desconecta —o su paquete no descifra— **nadie vuelve a entrar a
        esta función jamás**, y la sala se queda en el cartel para siempre. No mandamos nada mal:
        dependíamos de una respuesta que puede no llegar.

    ★ LO QUE HACE EL REFERENTE, medido en 5 capturas (`GORILA_ESCENARIO_PARA_LA_CAPTURA.md`):
      da el turno igual que nosotros, pero **no depende del `04`**. Entre turno y revelado le pasan
      **0 a 3 s**, y en las capturas viejas hay **39 pares en el MISMO segundo**. Lo que nunca hace
      es quedarse colgado.

    ★★ Y QUE SE PUEDE, lo confirmó un agente leyendo **los dos clientes** (2013 `0x5F33C0` y 2019):
      para aceptar un `sub=5` el cliente sólo pide **que la caja exista y que ese slot no tenga ya
      una**. **No mira el turno ni si el jugador eligió.** Revelar la caja de alguien que no abrió
      **no crashea**.

    ⚠ NO se duplica el camino del revelado: se **simula el paquete del cliente** y se reusa el
      handler entero (premios, acreditación, revelado, turno siguiente). El propio handler ya sabe
      reasignar una caja inválida a la primera libre, así que el índice que le pasemos da igual.
    ⚠ El cliente **se auto-elige solo a los 6 s** (`0x57CEE0`), así que este tope casi nunca debería
      dispararse: cubre el caso en que ese paquete **no llega**. Por eso el default va un poco por
      encima de esos 6 s — primero que conteste él; esto es la red.
    """
    if not GORILA_TOPE_APERTURA or rid is None or conn is None:
        return

    def _vencio():
        try:
            with _mesa_lock:
                _ab = (CARRERAS.get(rid) or {}).get("cajas_abiertas") or {}
            if slot in _ab:
                return                      # abrió solo: todo bien, no hay nada que hacer
            log("LOBBY", f"  ★★ GORILA: el slot {slot} no abrió en {GORILA_TOPE_APERTURA}s "
                         f"-> le abro yo y sigo. Sin esto la sala se queda en el cartel "
                         f"PARA SIEMPRE (el revelado sólo avanza cuando llega un sub=4).")
            h_39_ff10e(conn, 0x10E, bytes([4, 0]))
        except Exception as e:
            log("LOBBY", f"  ⚠ GORILA: el tope del slot {slot} reventó: {e!r}")

    _t = threading.Timer(GORILA_TOPE_APERTURA, _vencio)
    _t.daemon = True                        # que no impida cerrar el server
    _t.start()


def _tablero_de_la_sala(car):
    """El tablero de 6 cajas de ESTA corrida. Se sortea UNA vez y lo comparten todos.

    ⚠ Llamar SIEMPRE con `_mesa_lock` tomado: `car` es la entrada viva de `CARRERAS`.

    ⛔⛔ EL BUG QUE ESTA FUNCIÓN VIENE A MATAR (medido en prod el 2026-09-10, 13:05:42):
        `⚠ FF10E sub=4 caja=1: no queda ninguna caja libre de 0 (abiertas={2: 2})`
      El tablero se guardaba en `CARRERAS[rid]["cajas"]` **y también** en `st.chase_premios`, y el
      `sub=4` leía el de la CONEXIÓN. Pero `st.chase_premios` sólo se llenaba en la conexión que
      pasaba por la rama del tablero: al que pedía tarde —o al que le contestábamos "repetido"— le
      quedaba vacío, y su `sub=4` caía en «no queda ninguna caja libre de 0».
      ⇒ Una sola fuente de verdad: la SALA. La conexión ya no guarda el tablero.
    """
    _prem = car.get("cajas")
    if _prem:
        return _prem
    _pares = list(CHASE_CAJA_PREMIOS)
    random.shuffle(_pares)
    _cuantas = random.randint(*CHASE_GORILA_CAJAS)
    _con = set(random.sample(range(len(_pares)), min(_cuantas, len(_pares))))
    _prem = [(_rc, _xp, 1 if _i in _con else 0)
             for _i, (_rc, _xp) in enumerate(_pares)]
    car["cajas"] = _prem
    return _prem


def puntaje_npc_realista():
    """Un puntaje de minijuego con la FORMA que tienen los de producción.

    Ver `CHASE_NPC_PUNTAJES` en `ajustes.py`: los tramos salen de 56 rondas reales del 10-sep,
    no de una campana inventada. Se sortea el tramo con su peso y después un número adentro.
    ⇒ 44 % de aciertos y ~46 % de rondas ganadas, que es lo que da prod.
    """
    _total = sum(p for _a, _b, p in CHASE_NPC_PUNTAJES) or 1
    _r = random.randrange(_total)
    for _a, _b, _p in CHASE_NPC_PUNTAJES:
        if _r < _p:
            return random.randint(_a, _b)
        _r -= _p
    return CHASE_NPC_PUNTAJES[-1][1]


def _orden_del_gorila(dest):
    """El orden para elegir caja: PRIMERO EL QUE MÁS APORTÓ A ATRAPAR AL GORILA.

    Es el mismo criterio con el que se ordena el cartel del cooperativo (`h_21_ff28`), y eso
    **es a propósito**: el cliente dibuja la fila de premios sobre la columna que ocupa el
    jugador en la LISTA DEL CARTEL (`0x575E70` busca el slot dentro del vector `[padre+0x8c]`,
    elementos de 0xA8, y devuelve el ÍNDICE). Si el cartel va en un orden y los turnos en otro,
    el resaltado cae sobre la columna equivocada: el *"premio corrido"* que reportó anonimo03.
    ⇒ Un solo orden para las dos cosas, y así elegir caja va 1º, 2º, 3º… de arriba hacia abajo.
    """
    return sorted(dest, key=lambda c: (-(getattr(c, "chase_puntos", 0) or 0), _slot_de(c, 99)))


def _paquete_del_revelado(premios, abiertas):
    """El `sub 6` FINAL: SÓLO las cajas que se abrieron, con su contenido.

    ★★★★★ ACÁ ESTÁ LA RECOMPENSA QUE NO SE PAGABA (2026-09-10, leído del exe).

      El aplicador de premios del cliente es `0x57D140(caja, premio)`, y antes de sumar nada
      pregunta `0x57ABD0(caja)`:

          vec  = [pantalla+0x6c .. +0x70]      (elementos de 0x68 = LAS 6 CAJAS)
          if caja >= cantidad: return false
          return vec[caja].dueño == MI slot          (dueño = byte +0x1c)

      Y el **único** que escribe ese dueño es el `sub 5` (`0x57B530`: `vec[caja].dueño = slot`).
      Mientras nadie la haya abierto, el dueño vale **0xFF** (lo confirma `0x57CEE0`, que busca
      cajas libres comparando contra 0xFF).

      ⇒ Nosotros mandábamos el tablero ENTERO en un `sub 6` **al principio**, antes de cualquier
        `sub 5`. En ese momento las 6 cajas tienen dueño 0xFF ⇒ `0x57ABD0` da falso para todas ⇒
        **no se le suma un solo RCoin, ni una sola exp, ni una moneda a nadie**. Los iconos sí se
        dibujan (eso va por otro camino, `vec[caja]+0x50`), y por eso "se veía" que pagaba.
        Y el `sub 6` con `count=0` del cierre no puede pagar nada: la lista viene vacía.

      ★ El REFERENTE manda la lista **AL FINAL**, después de todos los `sub 5`, y sólo con las
        cajas abiertas. Capturado el 2026-09-09 (`mitm_20260909_181537.txt`, línea 22767):
            06 03  | 00 00 02 [1,50,0][2,1000,0] | 03 00 02 [...] | 04 01 02 [...]
        3 jugadores → 3 cajas (0, 3 y 4, las mismas de sus `sub 5`), 50 RCoin + 1000 del `type 2`
        cada una, y la caja 4 además con `coin=1` (Moneda Gorila).

    Layout, del parser `0x5F4033`:
        [06][N] + N x { [caja:u8][coin:u8][M:u8] + M x [type:u32][value:u32][extra:u32] }
      `coin`: 0 nada · 1 = +1 Moneda Gorila · 2 = +1 Moneda Zombie (el cliente lo sintetiza).
      `type`: 1 = RCoin (`[jugador+0x2D8]`) · **2 = EXPERIENCIA** (`[jugador+0x2D0]`) ·
              5/6 = monedas · cualquier otro = ITEM y `value` es el itemId.
      ⚠⚠ Un itemId inexistente CRASHEA al cliente (`0x57C038` usa FindItem sin chequear NULL).
    """
    _cajas = sorted(set(abiertas.values()))
    p = bytes([6, len(_cajas) & 0xFF])
    for _b in _cajas:
        if _b >= len(premios):
            continue
        _rc, _xp, _mg = premios[_b]
        _lista = ([(1, _rc)] if _rc else []) + ([(2, _xp)] if _xp else [])
        p += bytes([_b & 0xFF, _mg & 0xFF, len(_lista) & 0xFF])
        for _t, _v in _lista:
            p += struct.pack("<III", _t, _v & 0xFFFFFFFF, 0)
    return p


def h_39_ff10e(st, cmd, data):
    # rama original:  cmd == 270
    # Al terminar la persecucion el cliente pide elegir una caja y SE QUEDA ESPERANDO: sin respuesta
    # la pantalla de resultado no se cierra y no se vuelve al lobby (medido en vivo 2026-07-30).
    # ⚠ ACÁ DECÍA `0x5F3F70` Y NO ES UNA FUNCIÓN — corregido el 2026-09-09. Cae en el medio de
    #   `0x5F3F30`. El handler de verdad del `FF10E` es **`0x5F33C0`**, extraído con `tabla_rx.py`.
    #   ★ Regla: una dirección se comprueba con `fn_start`; si no coincide consigo misma, miente.
    # Sub-comandos que acepta la RESPUESTA (del disasm de 0x5F33C0):
    #     3 -> cResultGroupTeam::0x57B5E0(v)            (lee 1 byte mas)
    #     5 -> [a][b]; si a==0xFF "Su estado no le permite ser seleccionado", si no
    #          0x57BF30(a,b) = "es la caja elegida: slot %d box %d"
    #     6 -> la LISTA de resultados (contador + entradas de 12B)  ← el premio de verdad
    #     7 -> "No es el turno para elegir la caja"
    #     8 -> popup de la tabla 0x9d50c0
    #     9 -> "No hay premio"                          ← ★ 1 SOLO BYTE, no lee nada mas
    #   otro -> popup "Error: %d"   ⚠ por eso NO se puede ecoar el sub que manda el cliente (2).
    # ★ Politica actual (pedida por el usuario): la caja de premio SOLO corresponde si se GANA
    #   (se atrapa al gorila). Como todavia no hay condicion de victoria server-side, se contesta
    #   siempre "no hay premio" -> el cartel se cierra y se vuelve al lobby.
    # ★ MEDIDO 2026-07-30: el sub 9 SOLO muestra el cartelito — no hace avanzar el estado, y el
    #   jugador quedaba igual de trabado en la pantalla de resultado. El que AVANZA es el sub 6:
    #   su layout es [6][count:u8][...], y con count=0 el handler toma el atajo de 0x5F4210, que
    #   llama a 0x57DD80(cResultGroupTeam) + 0x5EE9D0 y cierra, sin leer un solo campo mas.
    #   ⇒ se manda el 9 (avisa "no hay premio") y enseguida el 6 con lista VACIA (cierra).
    # ★★★ 2026-08-04: YA HAY VICTORIA SERVER-SIDE (la calcula el handler del FF10F), asi que la
    #   caja de premio SE ENTREGA cuando corresponde. Layout del sub 6, sacado del parser 0x5F4033:
    #       [06][N] + N x { [boxIdx:u8][coin:u8][M:u8] + M x [type:u32][value:u32][extra:u32] }
    #     `coin`: 0 nada · 1 = +1 Moneda Gorila · 2 = +1 Moneda Zombie (el cliente lo sintetiza).
    #     `type`: 1 RCoin · 2 RPoint · 5 Moneda Gorila · 6 Moneda Zombie · **cualquier otro = ITEM,
    #             y ahi `value` es el itemId**.
    #     ⚠⚠ UN itemId QUE NO EXISTA EN LA TABLA DEL CLIENTE LO CRASHEA AL INSTANTE
    #        (`0x57C038 call FindItem` y usa el resultado **sin chequear NULL**). Por eso aca solo
    #        se reparten RCoin y monedas: cero riesgo. Para dar ropa habria que validar contra
    #        el shop_lt primero.
    #   Secuencia obligatoria (el orden importa): **sub 6 (tablero) -> sub 3 (turno) -> el cliente
    #   contesta [04][caja] -> sub 5 (revelar)**. El contenido viaja en el 6; el 5 solo dice quien
    #   se quedo con cual.
    #   ⚠ Si el sub 5 rebota (caja fuera de rango, o ese slot ya abrio una), el cliente **no vuelve
    #     a pedir nada y queda colgado** -> validar server-side ANTES de mandarlo.
    sub = data[0] if data else 0xFF
    _gano = bool(getattr(st, "chase_gano", False))
    if sub == 0x04:                      # el jugador ELIGIO una caja
        # ★★★ EL REPARTO ES DE TODA LA SALA, no del que eligió (2026-09-02).
        #   ⛔ Antes esta rama mandaba TODO sólo a `st`: el que elegía veía el revelado y
        #      **los demás se quedaban en la pantalla de premios para siempre** (reportado:
        #      "jugador41 sigue en la sección de premios, no regresó a la sala"). Además usaba
        #      `HOST_SLOT` como si el que elige fuera siempre el anfitrión, y el estado de
        #      "quién ya abrió" vivía en la conexión en vez de en la sala.
        #   Ahora: se difunde a todos, el turno rota por orden de aporte al gorila, y recién
        #   cuando abrieron TODOS se manda el `op 6` que arranca el revelado.
        _caja = data[1] if len(data) > 1 else 0xFF
        _rid04 = getattr(st, "room_id", None)
        _mislot04 = _slot_de(st)
        _dest04 = [CONEXIONES.get(u) for u in mesa_de(_rid04).values()] if _rid04 is not None else []
        _dest04 = [c for c in _dest04 if c is not None and not getattr(c, "cerrado", False)] or [st]
        # ★★★ EL TABLERO SALE DE LA SALA, NUNCA DE LA CONEXIÓN — ver `_tablero_de_la_sala`, que
        #   explica el «no queda ninguna caja libre de 0» medido en prod.
        with _mesa_lock:
            if _rid04 is not None:
                _car04 = CARRERAS.setdefault(_rid04, {})
                _premios = _tablero_de_la_sala(_car04)
                _abiertas = _car04.setdefault("cajas_abiertas", {})
            else:
                # Sin sala (un jugador suelto) el estado vive en la conexión, que acá SÍ es la
                # única que hay. No es el camino normal del cooperativo.
                _car04 = {}
                _premios = getattr(st, "chase_premios", None) or []
                _abiertas = getattr(st, "chase_abiertas_solo", None)
                if _abiertas is None:
                    _abiertas = st.chase_abiertas_solo = {}
        # ★★★ EL CLIENTE PUEDE ELEGIR UNA CAJA QUE NO ESTÁ EN EL TABLERO (2026-09-02, en vivo).
        #   Medido, partida de 2: mandamos `sub 6 TABLERO 2 cajas` (índices 0 y 1), la pantalla
        #   igual dibuja SEIS cofres, el 2º jugador hizo clic en el 3 y llegó `[04][03]`.
        #   Como 3 >= 2 caía en el `else`, que NO contesta nada "para no colgarlo"... y eso es
        #   justamente lo que lo colgó: la máquina de estados de la pantalla no tiene
        #   temporizador, así que sin respuesta se queda mirando para siempre.
        #     18:58:41  sub=5 revelar caja 0 del slot 2   -> jugador41 OK
        #     18:58:41  sub=3 turno del slot 3            -> le toca a jugador20
        #     18:58:43  ⚠ sub=4 caja=3 INVALIDA (premios=2) -> silencio -> ATASCO
        #   ⇒ REGLA: al `sub 4` SIEMPRE se le contesta. Si el índice no existe (o ya lo abrió
        #   otro), se le da la primera caja LIBRE y se sigue el flujo normal. El revelado abre
        #   la caja que le asignamos, no la que tocó — puede no coincidir con el dibujo, pero
        #   nadie queda trabado. (Lo prolijo sería que el tablero tenga tantas cajas como
        #   dibuja la pantalla; eso pide RE de cuántas celdas arma, y hasta saberlo esto es la
        #   red de seguridad.)
        if _mislot04 not in _abiertas:
            _libres04 = [i for i in range(len(_premios)) if i not in _abiertas.values()]
            if _libres04 and (_caja >= len(_premios) or _caja in _abiertas.values()):
                log("LOBBY", f"  ⚠ FF10E sub=4: el slot {_mislot04} eligió la caja {_caja}, que no "
                             f"está en el tablero de {len(_premios)} (o ya la abrieron) -> se le "
                             f"asigna la primera libre ({_libres04[0]}) en vez de dejarlo colgado")
                _caja = _libres04[0]
        if _caja < len(_premios) and _mislot04 not in _abiertas:
            _abiertas[_mislot04] = _caja
            _rc, _xp, _mg = _premios[_caja]
            # ★ El cliente sólo lo SUMA EN PANTALLA (`0x57D174` hace `[player+0x2D8] = ((v^0x1FEF)
            #   + value) ^ 0x1FEF`). Persistirlo es NUESTRO, o al relogear no existió.
            _saldo = db_add_rcoin(getattr(st, "usn", 0), _rc) if _rc else db_get_rcoin(getattr(st, "usn", 0))
            # ★★★★★ EL `type 2` DE LA CAJA ES **EXPERIENCIA**, NO UN "RPoint" (2026-09-10).
            #   anonimo03 preguntó *"los rpoint ¿es exp?"* y la respuesta es SÍ, leída del exe:
            #     · `0x57D140` con `type==2` hace  get(0x485590) + value -> set(0x485570)
            #     · `0x485590/70` leen y escriben **`[jugador+0x2D0]`** (ofuscado con `^0x1FEF`)
            #     · y ese mismo campo lo escribe el handler del **`FFB9`**, que en el cliente 2019
            #       —el que trae los nombres de los devs— se llama **`CmdSyncExp`** (`0x5D7E20`:
            #       lee un u32 y llama a `0x485570`). El `FF92` es `CmdEditExp` y toca el mismo.
            #     · y quien lo CONSUME es la barra de nivel (`0x58D670`): divide ese valor por
            #       `tabla_exp[nivel]` (`0x882118`) para sacar el porcentaje.
            #   ⇒ Lo estábamos guardando en la columna `rpoint`, que **no se le manda al cliente
            #     en ningún paquete**: la exp de la caja se perdía entera. Ahora se paga como exp.
            #   ⚠ La columna `rpoint` queda en la base con lo cobrado hasta hoy; no se borra.
            _saldo_xp = db_add_exp(getattr(st, "usn", 0), _xp) if _xp else 0
            if _mg:
                # ⛔ Esto acreditaba la moneda al personaje "0" fijo, no al que abrió la caja.
                # ★ 2026-09-05: era `db_load()` = los 4806 para sumarle una moneda a uno.
                _kusn = getattr(st, "usn", 0)
                _chg = db_get_char(_kusn)
                if _chg:
                    _chg["monedas_gorila"] = int(_chg.get("monedas_gorila", 0) or 0) + _mg
                    db_save_uno(_kusn, _chg)
            for _c in _dest04:                       # ★ el revelado lo ve TODA la sala
                _c.send_ff55(0x10E, bytes([5, _mislot04 & 0xFF, _caja & 0xFF]),
                             name=f"FF10E sub=5 revelar caja {_caja} del slot {_mislot04}")
            _que = " + ".join(([f"{_rc} RCoin (saldo {_saldo})"] if _rc else [])
                              + ([f"{_xp} exp (saldo {_saldo_xp})"] if _xp else [])
                              + (["1 Moneda Gorila"] if _mg else [])) or "VACIA"
            log("LOBBY", f"  ★★★ GORILA: abrio la caja {_caja} -> {_que}")
            # ★★ LOS NPC TAMBIEN TIENEN QUE ELEGIR. La pantalla espera a que **todos** los
            #   ocupantes abran su caja; como el NPC no es un cliente real, nunca manda su
            #   `[04][caja]` y el jugador queda esperando para siempre.
            #   ⇒ Eso lo hace `_avanzar_turno`, que los mete en la MISMA fila que los jugadores.
            #     Antes había acá un bloque suelto que los abría TODOS de golpe y en el orden en
            #     que estaban sentados: el orden por aporte se lo saltaba entero.
            # ★★★ EL DISPARADOR DEL REVELADO: un SEGUNDO `op 6` con **count = 0** (2026-08-04).
            #   La pantalla es una maquina de estados en `[cChaseStageSelect+0x5C]` con 5 ramas
            #   (jump table `0x57DFC8`):
            #       0 = mirando como elige otro   ·  1 = te toca elegir
            #       2 = fade-in del revelado      ·  3 = las cajas VUELAN a su dueño + roll-up
            #       4 = cierre (480 frames = 8 s) -> `[padre+0x1E4]=1` -> se cierra SOLA
            #   ⚠ **Nada la saca del 0 ni del 1 por su cuenta**: no hay temporizador. El unico que
            #     pone el 2 es `0x57DD8D`, y a esa funcion se llega SOLO por el `op 6` — incluso
            #     con `count=0`, porque el handler saltea el loop pero igual la llama (`0x5F4210`).
            #   ⇒ nuestro ultimo `op 3` (el turno del ultimo NPC, que no es el jugador) dejaba el
            #     estado en 0 = "mirando", y ahi se quedaba para siempre.
            #   ⛔ NO mandar un 2º `op 6` CON premios: es un `push_back` puro, duplicaria los
            #      iconos y **volveria a acreditar el RCoin**.
            #   ⛔ NO mandar ningun `op 3` despues de esto: vuelve a poner el estado en 0/1 y
            #      CANCELA el revelado.
            #   ⛔ Los `op 7/8/9` no sirven: son solo popups, no tocan la maquina de estados. El
            #      `op 9` que mandabamos antes era ruido; lo que cerraba era este `op 6` vacio.
            #   ★ El cierre y la vuelta a la sala **no llevan paquete**: son 8 segundos locales.
            # ★ ¿Falta alguien por abrir? Entonces le toca al siguiente —jugador o NPC, en la
            #   misma fila— y el revelado NO arranca todavía. Si no queda nadie, `_avanzar_turno`
            #   manda el `sub 6` con los premios, que es DONDE SE PAGA.
            #   ⚠ NO se borra el tablero al revelar: el que pida su `sub 2` tarde tiene que poder
            #     recibir ese mismo revelado y cerrar. El `FF24 START` reemplaza la entrada entera
            #     de `CARRERAS`, así que no se arrastra a la corrida siguiente.
            _avanzar_turno(_rid04, _dest04, _premios, _abiertas)
        elif _mislot04 in _abiertas:
            # clic repetido del mismo slot (el cliente reintenta por timeout): ya se le contestó.
            log("LOBBY", f"  · FF10E sub=4 caja={_caja}: el slot {_mislot04} ya abrió la "
                         f"{_abiertas[_mislot04]} -> ignorado (reintento)")
        else:
            # ★ Único caso que queda: NO hay ninguna caja libre y él todavía no abrió (pasa si los
            #   NPC se llevaron todas). Antes acá se cortaba en silencio = pantalla congelada.
            #   Se le devuelve el turno para que al menos la pantalla siga viva y pueda reintentar.
            log("LOBBY", f"  ⚠ FF10E sub=4 caja={_caja}: no queda ninguna caja libre de "
                         f"{len(_premios)} (abiertas={_abiertas}) -> le devuelvo el turno al slot "
                         f"{_mislot04} en vez de dejarlo congelado")
            for _c in _dest04:
                _c.send_ff55(0x10E, bytes([3, _mislot04 & 0xFF]),
                             name=f"FF10E sub=3 turno (reintento) del slot {_mislot04}")
    elif _gano:                          # ★ atrapó al gorila: le toca su turno
        # ★★★ EL TABLERO ES SIEMPRE DE 6 Y NINGUNA CAJA VA VACIA (2026-09-02, regla del usuario).
        #   El minijuego es una LOTERIA por turnos: elige primero el que mas aporto al gorila,
        #   despues el siguiente, y asi; cada uno se lleva UNA de las que quedan. Al final se
        #   revela el contenido de TODAS (por eso las que nadie eligio tambien tienen que tener
        #   premio: se ven igual).
        #   ⛔ Dos cosas que estaban mal y se midieron en vivo el mismo dia:
        #     · el tablero se armaba con `len(jugadores)` cajas — 2 en una partida de 2 — pero la
        #       pantalla dibuja SEIS. El 2º jugador eligio el cofre 5, que no existia.
        #     · dos de las seis filas eran `(0,0)` = VACIAS, asi que al reasignarle la caja 0 le
        #       toco nada. Reportado tal cual: "selecciona la sexta caja, pero salio vacia".
        #   ⇒ 6 filas siempre, todas con RCOIN + RPOINT (cantidades distintas, barajadas), y
        #     entre 1 y 3 de ellas con la Moneda Gorila encima.
        #   ★★ Y el TAMAÑO del corpus lo respalda: las filas del server de referencia medían
        #      **27 B**, que es exactamente `3 de cabecera + 2 × 12` ⇒ **DOS premios por caja**.
        #      Con una sola (solo RCoin) darían 15 B. O sea que el original repartía dos cosas
        #      por caja, igual que ahora: RCoin (`type=1`) + RPoint (`type=2`).
        #   ⚠ La otra mitad de esa medición decía que el `count` igualaba la cantidad de
        #      JUGADORES, y eso **sí está medido**: la partida de 5 jugadores trajo un tablero
        #      de 5 cajas y la de 6 uno de 6. O sea que el server de referencia manda una por
        #      jugador, no seis fijas — el corpus sí distingue las dos hipótesis.
        #   ⇒ Acá se manda SIEMPRE 6 **a propósito**, por DECISIÓN DE DISEÑO del usuario
        #     ("aunque no sean 6 jugadores, las cajas siempre deben tener recompensa"), no
        #     porque el original lo haga. Además la pantalla dibuja 6 cofres y deja clickear
        #     todos: con menos cajas que cofres, tocar uno inexistente colgaba la pantalla.
        #     Eso último ya está cubierto aparte (el `sub=4` SIEMPRE contesta), así que si
        #     algún día se quiere fidelidad al original, se puede volver a una por jugador.
        #   El MISMO sorteo para toda la sala (se guarda en `CARRERAS[rid]["cajas"]`): si cada
        #   cliente barajara por su lado, la misma caja daria premios distintos a cada uno.
        #
        # ★★★★★ 2026-09-10 — ACÁ YA NO SE MANDA EL TABLERO. Es el cambio grande de esta tanda.
        #   El `sub 6` con las 6 cajas se mandaba ACÁ, ANTES de cualquier `sub 5`, y por eso el
        #   cliente **no acreditaba un solo premio**: `0x57ABD0` sólo paga la caja cuyo dueño ya
        #   es tu slot, y el dueño lo escribe el `sub 5`. Ver `_paquete_del_revelado`.
        #   ⇒ Ahora el tablero se SORTEA acá (para que todos compartan el mismo) y se MANDA
        #     al final, con las cajas abiertas. Igual que el referente, que en la captura del
        #     09-sep arranca con `03 03` (turno) y recién cierra con `06 03 …`.
        #   ★ Y de paso desaparece la rama del "pedido repetido": ya no hay nada que duplicar.
        #     Antes se distinguía por `st.chase_premios`, y ese atributo era la mitad del
        #     «premio corrido». El estado ahora vive todo en la sala.
        _rid10e = getattr(st, "room_id", None)
        with _mesa_lock:
            _car10e = CARRERAS.setdefault(_rid10e, {}) if _rid10e is not None else {}
            _premios = _tablero_de_la_sala(_car10e) if _rid10e is not None else None
            if _premios is None:                      # sin sala: el tablero vive en la conexión
                _premios = getattr(st, "chase_premios", None)
                if not _premios:
                    _premios = _tablero_de_la_sala({})
                    st.chase_premios = _premios
            _ya = dict(_car10e.get("cajas_abiertas") or {})
            _revelado = bool(_car10e.get("cajas_revelado"))
            _ya_cobro = getattr(st, "usn", None) in (_car10e.get("cajas_revelado_a") or set())
        # ⛔⛔ SI YA LE MANDAMOS EL REVELADO, NO SE LE MANDA DE NUEVO. `0x57D140` acredita cada
        #   vez que le llega: repetirlo **le paga dos veces**. Este pedido es el reintento por
        #   timeout del cliente (`0x5779E0`), y su pantalla ya está cerrando sola.
        if _revelado and _ya_cobro:
            log("LOBBY", f"  · FF10E sub={sub}: al slot {_slot_de(st)} ya se le mandó el revelado "
                         f"-> IGNORADO (mandarlo otra vez le pagaría dos veces)")
            return
        # ★ EL QUE LLEGA TARDE. Si la sala ya reveló, mandarle un `sub 3` lo dejaría "mirando"
        #   para siempre (`0x57AB30` con un slot ajeno pone `[pantalla+0x5c]=0`, y nada la saca
        #   de ahí sola). Se le manda el revelado y cierra con los demás.
        if _revelado:
            # ⛔⛔ Y EL `sub 3` VA PRIMERO, SIEMPRE. Es el único que llama a `0x578420(1)`, que
            #   **instala el Update de la pantalla** (`[padre+8] = 0x575B20`). Sin él, el `sub 6`
            #   pone el estado en 2 y **nadie corre la máquina**: se queda mirando para siempre.
            #   Es el mismo cuadro que ya nos costó el cuelgue de la derrota en agosto.
            #   ★ Lo cazó el banco (`simular_premios_con_gente.py`, escena E-bis): el rezagado
            #     recibía el revelado y no cerraba.
            #   ⚠ Con un slot AJENO, no el suyo: `0x57AB30` con el propio pone el estado en 1 y
            #     arranca el temporizador de auto-elección de 6 s. El `sub 6` de la línea siguiente
            #     lo pisa igual, pero no hace falta correr ese riesgo.
            _ajeno_rez = next((s for s in _ya if s != _slot_de(st)), (_slot_de(st) + 1) & 0x0F)
            st.send_ff55(0x10E, bytes([3, _ajeno_rez & 0xFF]),
                         name=f"FF10E sub=3 slot ajeno {_ajeno_rez} (instala el FSM del rezagado)")
            for _sl_ya, _cj_ya in sorted(_ya.items(), key=lambda kv: kv[1]):
                st.send_ff55(0x10E, bytes([5, _sl_ya & 0xFF, _cj_ya & 0xFF]),
                             name=f"FF10E sub=5 (al rezagado) caja {_cj_ya} del slot {_sl_ya}")
            st.send_ff55(0x10E, _paquete_del_revelado(_premios, _ya),
                         name="FF10E sub=6 REVELADO (al rezagado)")
            if _rid10e is not None:
                with _mesa_lock:
                    (CARRERAS.setdefault(_rid10e, {})
                     .setdefault("cajas_revelado_a", set()).add(getattr(st, "usn", None)))
            log("LOBBY", f"  · GORILA: el slot {_slot_de(st)} pidió el tablero DESPUÉS del "
                         f"revelado -> se le manda el resultado para que cierre, no un turno.")
            return
        # ★ Si ya hay cajas abiertas, este que pide tarde tiene que ver lo que se perdió: los
        #   `sub 5` que ya viajaron. Si no, su pantalla no dibuja de quién es cada cofre.
        for _sl_ya, _cj_ya in sorted(_ya.items(), key=lambda kv: kv[1]):
            st.send_ff55(0x10E, bytes([5, _sl_ya & 0xFF, _cj_ya & 0xFF]),
                         name=f"FF10E sub=5 (repaso) caja {_cj_ya} del slot {_sl_ya}")
        # ★★★ LA FILA ARRANCA UNA SOLA VEZ POR SALA.
        #   ⚠ Cada jugador manda SU `sub 2`, así que esto corre 6 veces. Antes daba igual porque lo
        #     único que hacía era mandarle el turno al que preguntaba. Ahora la fila puede **jugar
        #     turnos de NPC**, y arrancarla seis veces serían seis cadenas de NPC pisándose.
        #   ⇒ El PRIMERO que pregunta arranca la fila (a toda la sala). Los que preguntan después
        #     reciben el turno vigente **sólo ellos**: alcanza para instalarles el FSM de la
        #     pantalla (`0x578420(1)`, ver el rezagado) sin tocar a nadie más.
        _dest10e = [c for c in (CONEXIONES.get(u) for u in mesa_de(_rid10e).values())
                    if c is not None and not getattr(c, "cerrado", False)] if _rid10e is not None else []
        _dest10e = _dest10e or [st]
        _arranco = False
        if _rid10e is not None:
            with _mesa_lock:
                _car_t = CARRERAS.setdefault(_rid10e, {})
                _arranco = bool(_car_t.get("turno_arrancado"))
                _car_t["turno_arrancado"] = True
        if not _arranco:
            # ★ EL ORDEN ESPERADO, AL LOG, ANTES DE EMPEZAR. Es lo que se cruza contra la pantalla
            #   para saber si el orden salió bien (pedido de anonimo03: *"no puedo ver el orden"*).
            _fila = _orden_de_la_sala(_rid10e, _dest10e)
            _txt = " → ".join(
                f"{n}º slot {_sl}{'' if _c is not None else ' (NPC)'}"
                for n, (_sl, _c) in enumerate(_fila, 1))
            log("LOBBY", f"  ★★★ GORILA ATRAPADO -> tablero de la sala {_premios} "
                         f"(se manda AL FINAL, con el revelado).")
            log("LOBBY", f"  ★★★ ORDEN ESPERADO de elección (por aporte al gorila): {_txt}")
            _abiertas10e = None
            if _rid10e is not None:
                with _mesa_lock:
                    _abiertas10e = CARRERAS.setdefault(_rid10e, {}).setdefault("cajas_abiertas", {})
            else:
                _abiertas10e = getattr(st, "chase_abiertas_solo", None)
                if _abiertas10e is None:
                    _abiertas10e = st.chase_abiertas_solo = {}
            _avanzar_turno(_rid10e, _dest10e, _premios, _abiertas10e)
        else:
            with _mesa_lock:
                _tv = (CARRERAS.get(_rid10e) or {}).get("turno_caja") if _rid10e is not None else None
            if _tv is None:
                _tv = _slot_del_que_mas_aporto(_rid10e, st)
            st.send_ff55(0x10E, bytes([3, _tv & 0xFF]),
                         name=f"FF10E sub=3 turno vigente del slot {_tv} (sólo a él, para su FSM)")
            log("LOBBY", f"  · GORILA: el slot {_slot_de(st)} pidió el tablero con la fila ya en "
                         f"marcha -> se le manda el turno vigente ({_tv}), sin re-arrancar nada.")
    else:
        # ★★★ DERROTA — el gorila se escapó. Sin caja, pero HAY QUE CERRAR LA PANTALLA.
        #   ⚠⚠ CAUSA DEL CUELGUE (hallada 2026-08-04): faltaba el **`op 3`**. Es el ÚNICO caller de
        #   `0x578EF0` en todo el binario (`0x57B616`), y `0x578EF0` es quien **instala** el
        #   `Update` de la pantalla (`[this+8] = 0x57DF70` = la máquina de estados de `[0x5C]`).
        #   Sin `op 3`, `[this+8]` sigue siendo el update por defecto (`0x578CF0`, cajas flotando y
        #   nada más) ⇒ aunque nuestro `op 6` ponga `[0x5C]=2`, **nadie corre la máquina**, nunca se
        #   llega al estado 4, nunca se ejecuta `0x57CD7A mov byte [padre+0x1E4],1` (el único
        #   "terminé" del binario) y la pantalla **no cierra jamás**. Ganando funcionaba de casualidad
        #   porque ahí sí mandábamos el `op 3` (para darle el turno al jugador).
        #   ★ En derrota el `op 3` va con un **slot AJENO**: cae en `0x57B665` -> `[0x5C]=0`
        #     ("mirando") + input OFF. Con el slot del jugador (`0x57B63A`) pondría `[0x5C]=1`,
        #     input ON y un timer de 6 s = le habilitaríamos elegir caja donde no hay premio.
        #   ⛔ Nada después del `op 6 00`: cualquier `op 3` posterior vuelve a pisar `[0x5C]`.
        #   · El `op 9` es INOCENTE del cuelgue (es sólo un popup, `0x5F4276`), pero se saca porque
        #     tapa la pantalla con un modal justo cuando arranca la animación de cierre.
        #   ★ ORDEN (pedido del usuario): primero el cartelito "No hay premio", y recién después
        #     la secuencia de cierre. Así el jugador ve POR QUÉ no hay cofres, en vez de que le
        #     aparezca un tablero vacío sin explicación. El `op 9` va PRIMERO justamente para que
        #     no tape la animación de cierre (fue el error de la versión anterior).
        # ★★★★★ 2026-09-05 — ESTE `op3` ES EL "PREMIOS CORRIDO 1 SLOT A LA DERECHA".
        #   Lo cazó el usuario en pantalla y el log de esa misma partida lo dice:
        #       01:43:24  FF10E sub=3 slot ajeno 3   (el jugador estaba en el slot 2)
        #   Le decimos al cliente que el turno es del slot 3 ⇒ dibuja la fila de premios sobre
        #   la columna 3 en vez de la 2. **Un slot a la derecha, exactamente.**
        #   ⚠ Y no es un descuido: el slot ajeno está a propósito, para que el cliente entre en
        #     modo "mirando" en vez de habilitarle elegir caja donde no hay premio. El problema
        #     es que ese slot ajeno **también es el que resalta**.
        #   ⇒ `FF10E_DERROTA_OP3` permite probar las tres salidas sin tocar código:
        #       "ajeno" (default, lo de hoy) · "yo" (tu slot: ¿se endereza?) · un número suelto
        #   ⚠⚠ CUIDADO con mandar un slot que NO EXISTA (6, 0xFF): si el cliente lo usa como
        #     índice de su vector de 6 jugadores, es el mismo cuadro que crasheaba el modo jefe.
        #     No está comprobado que no lo use. Por eso no es el default.
        #   ⛔ Y ojo: las direcciones que cita el comentario de abajo (`0x57B616`, `0x57B63A`,
        #     `0x57B665`) **no son de este build** — `0x57B616` cae en medio de otra función que
        #     ni siquiera tiene un `call` ahí. Es la trampa de siempre; no las sigas sin
        #     re-verificarlas con `taller/re2013/disasm.py`.
        st.send_ff55(0x10E, bytes([9]), name="FF10E sub=9 'No hay premio'")
        _mio10e = getattr(st, "room_slot", None)
        if _mio10e is None:
            _mio10e = HOST_SLOT
        if FF10E_DERROTA_OP3 == "yo":
            _ajeno = _mio10e
        elif isinstance(FF10E_DERROTA_OP3, int):
            _ajeno = FF10E_DERROTA_OP3
        else:
            _ajeno = next((s for s in slots_npc(st) if s != _mio10e), (_mio10e + 1) & 0x0F)
        st.send_ff55(0x10E, bytes([3, _ajeno & 0xFF]),
                     name=f"FF10E sub=3 slot ajeno {_ajeno} (instala el FSM de la pantalla)")
        st.send_ff55(0x10E, bytes([6, 0]), name="FF10E sub=6 count=0 -> cierra el resultado")
        log("LOBBY", f"  ★★ FF10E (pidio sub={sub}) -> DERROTA: op3 slot ajeno {_ajeno} (instala el "
                     f"FSM) + op6 count=0. Sin el op3 la pantalla NO cerraba nunca.")


def h_40_ff57(st, cmd, data):
    # rama original:  cmd == 87
    sid  = struct.unpack("<H", data[0:2])[0] if len(data) >= 2 else getattr(st, "last_song", 0)
    blob = notas.chart_de(sid)
    via  = notas.origen_de(sid)                   # de qué .bin salió (None = no está en el mapa)
    src  = f"{via}.bin" if via is not None else f"{sid}.bin (SIN MAPA -> puede ser otra canción)"
    que  = notas.titulo_de(sid)
    if blob is None:
        # ⚠⚠ EN CHASE UN result=0 MATA AL CLIENTE, con retardo. Medido en el disasm: el applier
        #   `0x56FC60` sólo llena los vectores de `cGameMusicBlock` cuando ok==1, pero el contador
        #   de FF57 pendientes (`[[0x9314D0]+0x21B50]`) baja IGUAL. Cuando llega a 0 corre
        #   `0x56E5F0`, que aborta si esos vectores estan vacios -> `_invalid_parameter` (0x74FBBF)
        #   = el proceso se AUTO-MATA, sin excepcion, sin log y sin crashdump.
        #   ⇒ en cooperativo hay que gritarlo bien fuerte: la canción sin chart es un bug de datos.
        st.send_ff55(0x57, b"\x00", name=f"FF57 SIN notas song={sid}")
        log("LOBBY", f"  ★ FF57 song={sid} '{que}' -> SIN NOTAS (result=0; buscado {src})")
        if getattr(st, "room_colab", False):
            log("LOBBY", "  ⛔⛔ result=0 EN COOPERATIVO: el cliente se va a AUTO-MATAR al terminar "
                         "de pedir notas (0x56E5F0 aborta con los vectores vacios). "
                         "La cancion del chase TIENE que tener chart.")
    else:
        # ★★ 06-nov (161): un chart de más de 4096 MATA a la dll vieja (la caja de la pila del 0x5D01F0). A quien no
        #   avisó «chart64k=1» le va recortado (notas de menos al final): juega sin el final, pero no se cae.
        if len(blob) > notas.TECHO_FF57_VIEJO:
            from .salas import DLL_CHART64K
            if getattr(st, "usn", None) not in DLL_CHART64K:
                entero = len(blob)
                blob, _antes, _despues = notas.recortar_al_techo(blob)
                if blob is None:
                    st.send_ff55(0x57, b"\x00", name=f"FF57 SIN notas song={sid} (no entra en 4096)")
                    log("LOBBY", f"  ⛔ FF57 song={sid} '{que}' -> {entero}B y no se pudo recortar al techo de 4096: "
                                 f"result=0 (dll vieja, usn={getattr(st, 'usn', None)})")
                    return
                log("LOBBY", f"  ⚠ FF57 song={sid} '{que}': {entero}B no entra en la dll vieja (usn="
                             f"{getattr(st, 'usn', None)}) -> RECORTADO a {len(blob)}B, {_despues} de {_antes} notas")
        resp = b"\x01" + struct.pack("<H", sid) + struct.pack("<H", len(blob)) + blob
        st.send_ff55(0x57, resp, name=f"FF57 {len(blob)}B notas song={sid}")
        aviso = "  ⚠ revisión distinta del chart -> puede salir el popup del combo" \
                if notas.es_otra_revision(sid) else ""
        log("LOBBY", f"  ★ FF57 song={sid} '{que}' -> {len(blob)}B notas servidas ✓ (chart {src}){aviso}")


def h_43_ff63(st, cmd, data):
    # rama original:  cmd == 99
    _q = leer_ff63_pedido(data)
    log("LOBBY", f"  ★★★ FF63 FIN DE CANCIÓN: raw={hx(data)} -> canción={_q['cancion']} "
                 f"b0={_q['b0']} u32@1={_q['u32_1']} u32@7={_q['u32_7']} "
                 f"u16@11={_q['u16_11']} u32@13={_q['u32_13']}")
    if not FF63_RESPONDER:
        log("LOBBY", "  ⛔ FF63_RESPONDER=False -> NO se contesta (el cliente se va a colgar)")
    elif not _q["b0"]:
        # ★★★ MEDIDO 2026-07-31, a costa de una corrida: el `FF63` se manda en DOS momentos y
        #   contestar el de ARRANQUE hace salir el CARTEL DE RESULTADO apenas empezás la misión
        #   (el cliente aplica el pago y da la canción por terminada). Discriminador:
        #       arranque -> b0=0, canción=0, todo el resto en 0
        #       final    -> b0=1, canción=<Music= del script>, con puntaje
        #   Estaba a la vista en las dos capturas (17:53 vs 17:55) y no se separaron.
        log("LOBBY", "  ○ FF63 de ARRANQUE (b0=0, canción=0) -> NO se contesta: contestarlo "
                     "dispara el cartel de resultado al empezar la misión")
    else:
        if FF63_PROBE:
            _exp, _rc = int(FF63_PROBE[0]), int(FF63_PROBE[1])
            log("LOBBY", f"  🔬 FF63_PROBE ACTIVA: mando exp={_exp} rcoin={_rc} — son valores "
                         f"DISTINTIVOS para leer en pantalla, no un pago real. Si el cliente "
                         f"muestra esos dos números, el layout queda MEDIDO y se apaga la sonda.")
        else:
            _exp, _rc = 0, 0
        st.send_ff55(0x63, build_ff63(exp=_exp, rcoin=_rc),
                     name=f"FF63 fin de canción: exp={_exp} rcoin={_rc}")

