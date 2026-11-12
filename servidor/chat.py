# -*- coding: utf-8 -*-
"""chat — los comandos que se escriben en el chat de la sala.

Son las herramientas de prueba del proyecto: sentar NPCs, forzar el modo de sala, tirar
el cartel de resultado, cambiar el mapa. No son parte del juego original — el cliente
manda texto y acá se lo interpreta antes de repartirlo como mensaje.

Vive aparte de `lobby_menu.py` (que atiende el `FFxx` del chat) porque es una consola de
desarrollo y crece sola; el handler sólo la llama.
"""
import struct
import threading
import time

from . import gm
from .ajustes import (
    COMANDOS_GM,
    COMANDOS_STREAMER,
    CONSOLA_GM_TODOS,
    CONSOLA_GM_USNS,
    CONSOLA_SIN_GM,
    RATE_MAX,
    RATE_MIN,
    RATE_NOMBRES,
    FF28_BASECOIN,
    poner_rate,
    rates,
    CHASE_EXP_DERROTA,
    CHASE_MAP_FIJO,
    CHASE_NUM_CANCIONES,
    DEFAULT_ROOM_MAP,
    FF6E_SALAS_POR_PAGINA,
    HOST_SLOT,
    LIBRE_TIER_BYTE,
    MAPA_OSCURO,
    OWNED_STAGES_2013,
    OBSTACULOS_2013,
    ORDEN_ASIENTOS,
)
from .carrera import build_ff28_cartel
from .lobby_carrera import rate_efectivo
from .progresion import licencia_actual
from .basedatos import db_get_char
from .registro import log
from .paquetes import grupo_de_licencia, mision_para_icono
from .salas import (
    CONEXIONES,
    avisar_a_la_sala,
    avisar_a_uno,
    SONDA_FF0C,
    anfitrion_de,
    mapa_de_sala,
    limpiar_rate_sala,
    marcador_de,
    reiniciar_marcador,
    sala_por_equipos,
    pd_valofe_de,
    poner_pd_valofe,
    poner_rate_sala,
    rate_sala_de,
    poner_mapa_sala,
    poner_eleccion,
    obstaculos_para,
    actualizar_ocupantes_sala,
    difundir_roomlist,
    difundir_userlist,
    enviar_ready_npcs,
    enviar_userlist,
    mesa_de,
    n_salas_falsas,
    poner_npcs,
    poner_salas_falsas,
    grande_de,
    poner_grande,
    asientos_de_la_sala,
    orden_asientos,
    slots_npc,
)

# ★ Estado del `.pulso` (el latido de prueba). Es un dict y no un bool suelto a propósito: el hilo
#   tiene que ver el cambio que hace `.pulso off` desde otro hilo, y rebindear un global desde
#   adentro de una función anidada no se ve afuera — el clásico que ya nos mordió con
#   `SALAS_FALSAS_N` (por eso existe `n_salas_falsas()` en vez de importar la variable).
_PULSO = {"vivo": False}


def avisar_a_todos(texto):
    """Una línea firmada SERVER a TODOS los conectados. Devuelve a cuántos llegó.

    ★ Lo de devolver el número no es adorno: es lo que pedía la guía del CBT
      (`taller/estudio/J-operacion/06-comandos-gm.md`). *"Un anuncio que no confirma destinatarios te
      deja sin saber si el problema fue tuyo o de la difusión"* — y eso importa justo en el
      minuto anterior a algo grande, que es cuando se usa.
    """
    return sum(bool(avisar_a_uno(_c, texto)) for _c in list(CONEXIONES.values()))


def puede_usar_consola(st, comando):
    r"""¿Este jugador puede correr `.comando`?

    ⛔ ANTES NO SE PREGUNTABA. Cualquiera que escribiera un mensaje empezado con `.` tenía la
      consola de desarrollo entera, **en producción y desde siempre**. Ver `CONSOLA_GM_*` en
      `ajustes.py`, que es donde está el porqué completo.

    ★★★ TRES PUERTAS, no dos (2026-09-14). Ver `COMANDOS_GM` en `ajustes.py` para el porqué.

      1. `CONSOLA_SIN_GM`  — del JUEGO (`.oscuro`, `.pd`, `.ayuda`). Pasa cualquiera; cada uno
                             se controla solo por dentro ("solo el anfitrion").
      2. `COMANDOS_GM`     — de OPERACIÓN (`.rate`). Pide estar en `gm.txt`.
                             ★ (04-oct) los de `COMANDOS_STREAMER` (`.gm1`, `.anuncio`) los abre
                             TAMBIÉN `streamers.txt`.
      3. todo lo demás     — de DESARROLLO. Pide `R2_CONSOLA_GM`, que prod no define.

    ★★ Los ejes 2 y 3 son distintos a propósito: `gm.txt` dice **quién**, `R2_CONSOLA_GM` dice
      **qué está construido**. Ser GM NO abre los de desarrollo, y eso no es un olvido: un
      comando de desarrollo no tiene que existir en producción, ni siquiera para un GM.
    """
    c = str(comando).lower()
    if c in CONSOLA_SIN_GM:
        return True
    if c in COMANDOS_GM:
        return gm.es_gm(st) or (c in COMANDOS_STREAMER and es_streamer(st))
    if CONSOLA_GM_TODOS:
        return True
    return int(getattr(st, "usn", 0) or 0) in CONSOLA_GM_USNS


def es_streamer(st):
    """¿Está en `streamers.txt` (al lado de `gm.txt`)? Mismo formato que `gm.txt`.
    ⚠ Si no se puede leer, NO: una puerta que falla tiene que fallar cerrada."""
    try:
        from .gm import streamers
        _u = int(getattr(st, "usn", 0) or 0)
        return _u > 0 and _u in streamers()
    except Exception as e:                                   # noqa: BLE001
        log("LOBBY", f"  ⚠ consola: no pude leer streamers.txt ({e}) -> se lo trata como jugador")
        return False


# ★★ LO QUE VA AL CHAT, EN ASCII (24-sep, visto en pantalla con los círculos). El chat del cliente
#   NO dibuja lo que no es ASCII: «¡te aceptaron en el círculo!» salió «¶e aceptaron en el c?culo»
#   (la «¡» se volvió otro signo y la «í» se comió la letra de al lado). Las tildes se sacan, unos
#   pocos signos se cambian por uno parecido y el resto de lo que no sea ASCII se descarta.
_A_ASCII = {"¡": "", "¿": "", "·": "-", "—": "-", "–": "-", "→": "->", "★": "*", "☆": "*",
            "⚠": "!", "⛔": "!", "✅": "", "«": '"', "»": '"', "“": '"', "”": '"', "…": "..."}


def a_ascii(texto):
    import unicodedata
    t = "".join(_A_ASCII.get(ch, ch) for ch in str(texto))
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")


def comando_chat(st, texto):
    """Comandos de GM tecleados en el chat de la sala. Devuelve las lineas a responder.
       Equivalente 2013 del `.gm1/2/3` del CBT.

    ⚠ Devuelve **`None`** si el que escribe no tiene permiso. No es lo mismo que una lista vacía:
      con `None`, `lobby_menu` manda el texto como **chat normal**. Así la consola no se delata —
      y de paso se arregla algo que molestaba: hasta hoy, escribir "...bueno" en el chat te
      contestaba *"comando desconocido"* en vez de decirlo.
    """
    part = texto[1:].split()
    if not part:
        return ["comando vacio - probá .ayuda"] if puede_usar_consola(st, "ayuda") else None
    c, args = part[0].lower(), part[1:]
    if not puede_usar_consola(st, c):
        # ⛔⛔ ESTE MENSAJE DECÍA SIEMPRE «NO es GM», Y PARA DOS DE LAS TRES PUERTAS ERA FALSO
        #   — 2026-09-16, y costó una caza. anonimo03 avisó *"comandos gm no funcionando"*: lo que le
        #   había fallado era `.npc`, que **no tiene nada que ver con ser GM** (es de DESARROLLO y
        #   pide `R2_CONSOLA_GM`). Los de GM le andaban perfecto. El log decía «NO es GM» y mandó
        #   a buscar el problema al lado equivocado.
        #   ⇒ Ahora dice QUÉ PUERTA lo paró y qué habría hecho falta. Un rechazo que no dice el
        #     motivo obliga a leer el código para interpretarlo.
        if c in COMANDOS_STREAMER:
            _por = "es de GM o streamer y el usn no está ni en `gm.txt` ni en `streamers.txt`"
        elif c in COMANDOS_GM:
            _por = "es de GM y el usn no está en `gm.txt`"
        else:
            _por = ("es de DESARROLLO y la consola está cerrada (falta `R2_CONSOLA_GM`; en local "
                    "se abre arrancando con `startserver.bat`). ⚠ Ser GM NO alcanza para éstos")
        log("LOBBY", f"  · consola: usn={getattr(st, 'usn', None)} escribió '.{c}' y se rechazó: "
                     f"{_por} -> va como chat normal")
        return None

    if c in ("libre", "todos", "all"):
        # ★★ CANAL LIBRE EN VIVO: el FFC9 con un byte FUERA de 1..8 -> `0x58CEF0` devuelve la
        #    categoría 13 = LIBRE (el mismo tier1 del `cat 0x09`). Un byte, sin tocar el exe.
        apagar = args and args[0].lower() in ("off", "no", "salir")
        st.libre = not apagar
        if st.libre:
            st.send_ff55(0xC9, bytes([LIBRE_TIER_BYTE & 0xFF]),
                         name=f"FFC9 CANAL LIBRE (byte={LIBRE_TIER_BYTE} -> categoria 13)")
            return [f"canal LIBRE activado (FFC9 byte={LIBRE_TIER_BYTE} -> categoria 13)"]
        _cl, _ti, _li = licencia_actual(getattr(st, "usn", 0))
        st.send_ff55(0xC9, bytes([_ti & 0xFF]), name=f"FFC9 licencia/tier byte={_ti} (vuelta a {_cl!r})")
        return [f"canal libre APAGADO - vuelta a la licencia del nivel ({_cl}, byte={_ti})"]

    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★ LAS DOS HERRAMIENTAS PARA PROBAR EL GORILA — 2026-09-15, pedidas por anonimo03
    # ═══════════════════════════════════════════════════════════════════════════════════════════
    if c == "carga":
        # `.carga charla N` — NPCs de la base LOCAL que entran, caminan, hablan y se van en la sala de
        #   conversación: la PRUEBA DE CARGA (25-sep). Es de DESARROLLO (no está en las listas de GM:
        #   pide `R2_CONSOLA_GM`, que prod no define) y además `npc_charla.permitido`. ⚠ No se llama
        #   `.npc`: ése es el de los NPC de las salas de CARRERA (más abajo).
        return ["la prueba de carga de la charla no viene en la versión abierta"]

    if c == "autoplay":
        # `.autoplay [on|off]` — tu personaje juega SOLO, con el autoplay escondido del cliente
        #   (el ítem de carrera «오토»: corre solo y da 99 por nota). El server se lo prende cada 6 s.
        #   Para probar los bonos que piden precisión. Ver `autoplay_gm.py`.
        from . import autoplay_gm
        _on = not (args and args[0].lower() in ("off", "no", "0", "apagar"))
        if not args and getattr(st, "autoplay_gm", False):
            _on = False                                  # `.autoplay` a secas alterna
        log("LOBBY", f"  🤖 .autoplay {'on' if _on else 'off'}: usn={getattr(st, 'usn', None)}")
        return autoplay_gm.activar(st, _on)

    if c == "record":
        # `.record` — el récord de las medallas (24-sep, pedido de anonimo03: *"mapearlo con comandos o
        #   editando el valor + prueba de unas partidas"*). Ver `medallas.py`.
        #     .record                  ver el tuyo y qué medallas tenés
        #     .record ganadas 199      EDITAR un contador (queda en la base)
        #     .record reset            todo a cero
        #     .record sonda            la próxima «Ver perfil» tuya trae números de prueba
        from . import medallas
        from .basedatos import db_record_de, db_sumar_record
        _usn = int(getattr(st, "usn", 0) or 0)
        _alias = {"exp": "exp_max", "rcoin": "rcoin_max", "97": "pd97", "ac": "allcombo",
                  "g": "ganadas", "p": "perdidas", "e": "empates"}
        if args and args[0].lower() == "sonda":
            st.record_sonda = True
            log("LOBBY", f"  🔬 .record sonda: usn={_usn}")
            return ["sonda armada: abrí «Ver perfil» (el tuyo) y la pestaña «Mis Medallas»",
                    f"columnas: @9={medallas.SONDA_COLUMNAS[9]} @17={medallas.SONDA_COLUMNAS[17]} "
                    f"@13={medallas.SONDA_COLUMNAS[13]} · ranking {medallas.SONDA_RANKING}",
                    "sacales captura: dicen qué columna es cuál (se usa una sola vez)"]
        if args and args[0].lower() == "anuncio":
            # Prueba el aviso global de medalla (`FF40` 0x36) mandándotelo SÓLO a vos.
            _mid = int(args[1]) if len(args) > 1 and args[1].isdigit() else 103
            from .basedatos import db_get_char as _gc_an
            _ap = (_gc_an(_usn) or {}).get("nick", "")
            st.send_ff55(0x40, medallas.armar_ff40_36(_mid, _ap), name=f"FF40/0x36 PRUEBA aviso medalla {_mid}")
            log("LOBBY", f"  🔬 .record anuncio {_mid}: usn={_usn}")
            return [f"aviso de la medalla {_mid} mandado SOLO a vos - mirá el chat"]
        if args and args[0].lower() == "cabeza":
            # SONDA de la bandera `cola[28]` del FF0C (la medalla arriba de la cabeza). El id ya
            #   viaja en `cola[29..32]`; esto sólo barre el valor de la bandera. No toca la base.
            _v = args[1].lower() if len(args) > 1 else ""
            if _v in ("off", "no", ""):
                medallas.CABEZA["bandera"] = None
            else:
                try:
                    medallas.CABEZA["bandera"] = int(_v, 0) & 0xFF
                except ValueError:
                    return ["uso: .record cabeza 0 | 1 | 0xff | off"]
            _rid = getattr(st, "room_id", None)
            difundir_userlist(_rid) if _rid else enviar_userlist(st)
            log("LOBBY", f"  🔬 .record cabeza: bandera cola[28] = {medallas.CABEZA['bandera']}")
            return [f"bandera de la medalla (cola[28]) = {medallas.CABEZA['bandera']} - lista re-emitida",
                    "mirá arriba de la cabeza del que tiene medalla puesta"]
        if args and args[0].lower() == "reset":
            db_sumar_record(_usn, poner={k: 0 for k in ("ganadas", "perdidas", "empates", "pd97",
                                                        "allcombo", "exp_max", "rcoin_max", "medalla")})
            log("LOBBY", f"  🏅 .record reset: usn={_usn}")
            return ["récord en cero (reabrí «Ver perfil» para verlo)"]
        if len(args) >= 2:
            _campo = _alias.get(args[0].lower(), args[0].lower())
            try:
                _val = int(args[1])
                db_sumar_record(_usn, poner={_campo: _val})
            except ValueError:
                return [f"no entiendo '{args[0]} {args[1]}' - campos: ganadas perdidas empates "
                        f"97 ac exp rcoin medalla"]
            log("LOBBY", f"  🏅 .record: usn={_usn} {_campo} = {_val}")
            return [f"{_campo} = {_val} (reabrí «Ver perfil» para verlo)"]
        _rec = db_record_de(_usn)
        _t = medallas.tabla()
        _tiene = medallas.ganadas_por(_rec, _t)
        return [f"G {_rec['ganadas']} · P {_rec['perdidas']} · E {_rec['empates']} · 97%: {_rec['pd97']}"
                f" · AC: {_rec['allcombo']} · EXP máx {_rec['exp_max']} · RC máx {_rec['rcoin_max']}",
                f"puesta: {_rec['medalla'] or 'ninguna'} · tenés {len(_tiene)}: "
                + (", ".join(str(m) for m in _tiene) or "ninguna")]

    if c in ("circulo", "círculo"):
        # `.circulo …` — el CÍRCULO (24-sep). Reemplaza a la web de Softnyx, que era donde se creaba,
        #   se pedía entrar, se echaba y se pasaba el mando (el cliente no tiene pantalla para eso).
        #   Es del JUEGO (`CONSOLA_SIN_GM`): las reglas de quién puede qué están en `circulos.py`.
        #   ★ `.circulo sonda` sí es de GM: manda un GuildInfo INVENTADO para mapear la pestaña.
        from . import circulos, gm as _gm_ci
        _usn = int(getattr(st, "usn", 0) or 0)
        _sub = args[0].lower() if args else ""
        _resto = " ".join(args[1:])
        if _sub in ("sonda", "off"):
            if not _gm_ci.es_gm(st):
                return ["la sonda es sólo para GM"]
            if _sub == "off":
                circulos.enviar_guildinfo(st, " (fin de la sonda)")
                return ["GuildInfo de verdad re-mandado (se terminó la sonda)"]
            from .basedatos import db_get_char as _gc_ci
            _ap = (_gc_ci(_usn) or {}).get("nick", "")
            _nom = args[1] if len(args) > 1 else "Prueba"
            try:
                _a, _b, _c = (int(x, 0) for x in (list(args[2:5]) + ["0", "1", "0"][len(args[2:5]):]))
            except ValueError:
                return ["uso: .circulo sonda [nombre] [a] [b] [c]   (a b c son números)"]
            _pq = circulos.armar_ff40_21(_nom, [(_usn, _a, _b, _c, _ap)], aviso="Aviso de prueba")
            st.send_ff55(0x40, _pq, name=f"FF40/0x21 SONDA círculo {_nom!r} a={_a} b={_b} c={_c}")
            log("LOBBY", f"  🔬 .circulo sonda: usn={_usn} {_nom!r} a={_a} b={_b} c={_c} -> {_pq.hex(' ')}")
            return [f"GuildInfo de PRUEBA (sólo a vos): círculo {_nom!r}, a={_a} b={_b} c={_c}",
                    "abrí Mensajería -> Círculo · .circulo off vuelve al de verdad"]
        if _sub == "eco":
            # `.circulo eco [nivel|exp|dinero|marca N]` (GM) — ver/EDITAR la economía de TU círculo y
            #   re-mandarle el FFD4 a los conectados. Para probar el nivel, la barra y el dinero.
            if not _gm_ci.es_gm(st):
                return ["la economia del circulo se edita solo siendo GM"]
            from .basedatos import db_circulo_de as _cd, db_economia_circulo as _ec, db_poner_economia_circulo as _pe
            _k = _cd(_usn)
            if not _k:
                return ["no estas en ningun circulo"]
            if len(args) >= 3:
                try:
                    _pe(_k["id"], **{args[1].lower(): int(args[2], 0)})
                except ValueError as _ev:
                    return [f"no entiendo: {_ev} - campos: nivel exp dinero marca"]
                _n = circulos.reenviar_ffd4(_k["id"])
                log("LOBBY", f"  🔬 .circulo eco {args[1]}={args[2]}: circulo {_k['nombre']!r} -> FFD4 a {_n}")
            _e = _ec(_k["id"])
            return [f"{_k['nombre']}: nivel {_e['nivel']} (tope {circulos.tope_de(_e['nivel'])}) - exp {_e['exp']}"
                    f" - dinero {_e['dinero']} - marca 0x{_e['marca']:08X}"]
        _gm_salta = _gm_ci.es_gm(st)             # un GM no necesita el nivel (para probar)
        if _sub in ("", "ver", "info"):
            return circulos.ver(_usn)
        if _sub in ("ayuda", "help", "?"):
            return circulos.AYUDA
        if _sub == "crear":
            return circulos.crear(_usn, _resto, saltear_nivel=_gm_salta) if _resto else ["uso: .circulo crear <nombre>"]
        if _sub in ("unirme", "unirse", "pedir", "entrar"):
            return circulos.pedir(_usn, _resto, saltear_nivel=_gm_salta) if _resto else ["uso: .circulo unirme <nombre del círculo>"]
        if _sub == "cancelar":
            return circulos.cancelar(_usn)
        if _sub in ("solicitudes", "pedidos"):
            return circulos.solicitudes(_usn)
        if _sub in ("miembros", "lista"):
            return circulos.lista_miembros(_usn)
        if _sub == "salir":
            return circulos.salir(_usn)
        if _sub == "aviso":
            return circulos.poner_aviso(_usn, _resto)
        if _sub == "cerrar":
            return circulos.cerrar(_usn, _resto)
        _con_apodo = {"aceptar": circulos.aceptar, "rechazar": circulos.rechazar,
                      "echar": circulos.echar, "expulsar": circulos.echar,
                      "jefe": circulos.poner_jefe,
                      "quitarjefe": lambda u, a: circulos.poner_jefe(u, a, si=False),
                      "lider": circulos.pasar_mando, "líder": circulos.pasar_mando}
        if _sub in _con_apodo:
            return _con_apodo[_sub](_usn, _resto) if _resto else [f"uso: .circulo {_sub} <apodo>"]
        return [f"no conozco '.circulo {_sub}'"] + circulos.AYUDA

    if c in ("monedas", "moneda", "monedasgorila"):
        # `.monedas N` — le pone N Monedas Gorila a quien lo escribe (o a un apodo).
        #   ⚠ **ASIGNA, no suma**: el `FF69` es un "fijá este contador", no un incremento. Con el
        #     mismo criterio, `.monedas 0` deja la cuenta limpia para probar desde cero.
        from .basedatos import db_get_char, db_save_uno, db_uids_por_nick
        from .myrecord import enviar_ff69_moneda_gorila
        if not args or not args[0].lstrip("-").isdigit():
            return ["uso: .monedas N  [apodo]   (asigna, no suma)"]
        _n = max(0, min(int(args[0]), 9999))
        _dest_usn = int(getattr(st, "usn", 0) or 0)
        _dest_con = st
        if len(args) > 1:
            _uids = [int(u) for u in (db_uids_por_nick(args[1]) or [])]
            _con = next((CONEXIONES.get(u) for u in _uids if CONEXIONES.get(u) is not None), None)
            if not _uids:
                return [f"no encuentro a {args[1]!r}"]
            _dest_usn = next((u for u in _uids if CONEXIONES.get(u) is not None), _uids[0])
            _dest_con = _con
        _ch = db_get_char(_dest_usn) or {}
        if not _ch:
            return [f"uid {_dest_usn} no tiene personaje"]
        _antes = int(_ch.get("monedas_gorila") or 0)
        _ch["monedas_gorila"] = _n
        db_save_uno(_dest_usn, _ch)
        # ★ Y se lo avisamos al cliente en el acto: sin el `FF69` el número de la tienda sigue
        #   mostrando el viejo hasta el próximo login, y parecería que el comando no hizo nada.
        if _dest_con is not None and not getattr(_dest_con, "cerrado", False):
            enviar_ff69_moneda_gorila(_dest_con)
        log("LOBBY", f"  🪙 .monedas: usn={_dest_usn} ({_ch.get('nick')!r}) {_antes} -> {_n}")
        return [f"Monedas Gorila de {_ch.get('nick')}: {_antes} -> {_n}"]

    if c in ("gorila", "capturar"):
        # `.gorila [ronda]` — da el gorila por ATRAPADO en esa ronda, para TODA la sala.
        #
        #   ⛔ NO ARRANCA EL MINIJUEGO, y no es por falta de ganas: **el minijuego nace dentro del
        #     cliente y el server no manda nada para abrirlo** (medido en `mitm_20260909_181537`:
        #     el `FF10F` del cliente aparece sin que el server haya dicho una palabra). Está
        #     escrito en `carrera.anotar_avance`.
        #   ⇒ Lo que SÍ se puede, y es lo que hace falta para probar: **marcar el resultado**. Con
        #     eso el cartel sale como si lo hubieran atrapado en la ronda que se pida, y se puede
        #     ver el medallón (S/B/D/F) sin tener que alcanzarlo de verdad.
        _rid = getattr(st, "room_id", None)
        if _rid is None:
            return ["no estas en una sala"]
        _ronda = int(args[0]) if (args and args[0].isdigit()) else 1
        _off = bool(args and args[0].lower() in ("off", "no", "escapo", "escapa"))
        _n = 0
        for _u in mesa_de(_rid).values():
            _c = CONEXIONES.get(int(_u))
            if _c is None or getattr(_c, "cerrado", False):
                continue
            _c.chase_gano = not _off
            _c.chase_ronda_captura = None if _off else _ronda
            _n += 1
        log("LOBBY", f"  🦍 .gorila: sala {_rid} -> "
                     + (f"se ESCAPÓ (medallón F)" if _off
                        else f"ATRAPADO en la ronda {_ronda}") + f", a {_n} jugador(es)")
        if _off:
            return ["gorila: se ESCAPO -> el cartel dara F"]
        from .carrera import medallon_del_gorila
        return [f"gorila ATRAPADO en la ronda {_ronda} -> medallon "
                f"{chr(medallon_del_gorila(_ronda))} ({_n} jugador/es)"]

    if c == "grupo":
        # ★ LA CARRERA EN GRUPO (10-oct, paso A1): desde la sala de charla o el lobby, el server arma la sala de 12 y
        #   te LLEVA sin que lo pidas (FF11 sin pedido) — ver servidor/grupo.py y documentacion/MODO_6VS6.md §10
        from . import grupo
        return grupo.llevar(st, alto=bool(args) and args[0].lower() == "alto")

    if c == "grande":
        # ★ LA CARRERA GRANDE (6vs6, 10-oct): `.grande 12` = la próxima carrera de ESTA sala arma 12 corredores
        #   (el campo 3 del FF25 → grande.c). Los asientos 6..11 se llenan con `.npc full` / `.npc slots 6 7`.
        _rid = getattr(st, "room_id", None)
        if _rid is None:
            return ["hay que estar en una sala"]
        if not args:
            n = grande_de(_rid)
            return [f"carrera grande: {n or 'apagada (6)'} - uso: .grande 12 | .grande off"]
        a = args[0].lower()
        n = poner_grande(_rid, 0 if a in ("off", "no", "0") else (int(a) if a.isdigit() else 12))
        return [f"carrera grande -> {n} corredores (la próxima carrera)" if n else "carrera grande APAGADA (6)"]

    if c in ("npc", "npcs"):
        actual = slots_npc(st)
        if not args:
            return [f"NPC: {len(actual)} en slots {actual} - uso: .npc N | .npc full | .npc off"]
        a = args[0].lower()
        # ★ Los slots que quedan: los que NO tiene un JUGADOR DE VERDAD. `.npc full` llena eso, no
        #   una lista fija — si no, el NPC se sentaría encima de alguien.
        _rid = getattr(st, "room_id", None)
        _tomados = set(mesa_de(_rid)) if _rid is not None else {HOST_SLOT}
        # ★ carrera grande (6vs6): los asientos 6..N-1 también son de corredor, en el orden de la sala de 12
        _n_as = asientos_de_la_sala(_rid)
        libres = [s for s in (orden_asientos(_rid) if _rid is not None else ORDEN_ASIENTOS) if s not in _tomados]
        if a in ("full", "lleno", "max"):
            nuevos = list(libres)
        elif a in ("off", "no", "ninguno", "clear"):
            nuevos = []
        elif a.isdigit():
            nuevos = libres[:max(0, min(int(a), len(libres)))]
        elif a in ("slot", "slots"):
            nuevos = [int(x) for x in args[1:]
                      if x.isdigit() and 0 <= int(x) < _n_as and int(x) not in _tomados]
        else:
            return [f"no entiendo '{a}' - uso: .npc N | .npc full | .npc off | .npc slots 3 4"]
        if _rid is not None:
            poner_npcs(_rid, nuevos)          # ★ de la SALA: los ven todos los que estén adentro
        st.ghost_slots = nuevos
        st.ghost = True                       # el FF0C ahora lo maneja `ghost_slots` (puede quedar vacio)
        # ★ re-emitir la lista EN VIVO a TODA la sala, no solo a quien escribió el comando.
        if _rid is not None and mesa_de(_rid):
            difundir_userlist(_rid)
            actualizar_ocupantes_sala(_rid)
        else:
            enviar_userlist(st)
            enviar_ready_npcs(st, " (.npc)")
        return [f"NPC -> {len(nuevos)} en slots {nuevos}" +
                ("" if nuevos else " (sala sin NPC)")]

    if c in ("map", "mapa", "pista"):
        # ★ Cambia el `map` del FF25 LOADGAME SIN relanzar el server. Pisa todo (el DEFAULT_ROOM_MAP,
        #   el FF1B y el CHASE_MAP_FIJO), asi la sonda de pista es un solo click en el chat.
        actual = getattr(st, "map_override", None)
        if not args:
            return [f"map override = {actual if actual is not None else 'off'} "
                    f"(default {DEFAULT_ROOM_MAP}, chase {CHASE_MAP_FIJO}) - uso: .map N | .map off"]
        a = args[0].lower()
        if a in ("off", "no", "auto", "default"):
            st.map_override = None
            return ["map override APAGADO (vuelve al automatico)"]
        if not a.isdigit():
            return [f"'{a}' no es un numero - uso: .map N | .map off"]
        st.map_override = int(a) & 0xFFFF
        return [f"map override = {st.map_override} (aplica en el proximo START; "
                f"si el escenario no existe el FF59 lo dice)"]

    if c in ("tema", "song"):
        # ★ 13-oct (el QA automático): fija la CANCIÓN del próximo START de esta sala, por encima del picker y del
        #   sorteo. Los corredores del QA juegan solos con el plan de la sesión Piloto, que es de UNA canción
        #   (Lavie, 7603). Mismo molde que `.map`. Sólo dev (no existe en prod).
        actual = getattr(st, "song_override", None)
        if not args:
            return [f"tema forzado = {actual if actual is not None else 'off'} - uso: .tema N | .tema off"]
        a = args[0].lower()
        if a in ("off", "no", "auto", "default"):
            st.song_override = None
            return ["tema forzado APAGADO (vuelve el de la sala / el sorteo)"]
        if not a.isdigit():
            return [f"'{a}' no es un numero - uso: .tema N | .tema off"]
        st.song_override = int(a) & 0xFFFF
        return [f"tema forzado = {st.song_override} (aplica en el proximo START de esta sala)"]

    if c in ("chase", "canciones", "temas"):
        # ★ Cuantas canciones consume el chase. El modo trae 3 por diseño, pero para PROBAR es larguisimo:
        #   con 1 la partida dura una sola cancion y se llega al gorila y al cartel en un minuto.
        #   ⚠ Es un acortador de PRUEBA, no un cambio de diseño: el valor real del modo es 3.
        #   ⚠ Cada cancion del FF25 tiene que tener chart servible (el cliente pide un FF57 por cada
        #     una y un result=0 lo AUTO-MATA), por eso se eligen con `elegir_canciones_chase`.
        actual = getattr(st, "chase_n", CHASE_NUM_CANCIONES)
        if not args:
            return [f"chase = {actual} cancion/es (el modo real usa {CHASE_NUM_CANCIONES}) - "
                    f"uso: .chase 1 | .chase off"]
        a = args[0].lower()
        if a in ("off", "no", "auto", "default"):
            st.chase_n = None
            return [f"chase vuelve al default ({CHASE_NUM_CANCIONES} canciones)"]
        if not a.isdigit() or not (1 <= int(a) <= 9):
            return [f"'{a}' no sirve - uso: .chase 1..9 | .chase off"]
        st.chase_n = int(a)
        return [f"chase = {st.chase_n} cancion/es (aplica al proximo cambio de modo o START)"]

    if c in ("cartel", "fin", "resultado"):
        # ★ Manda el CARTEL DE RESULTADO ya, sin esperar a que termine la carrera. Es EXACTAMENTE el
        #   mismo paquete que contestamos al FF28, sólo que sin pedido previo: sirve para probar el
        #   cartel (medalla, exp, rcoin) sin jugarse 3 canciones enteras.
        #   Uso: `.cartel`  = como si hubieras GANADO con precisión 100
        #        `.cartel F`= como si hubieras PERDIDO   ·  `.cartel 85` = con esa precisión
        #   ⚠ Es un atajo de PRUEBA: en una partida real el cartel lo dispara el FF28 del cliente.
        a = (args[0].upper() if args else "")
        perdio = (a == "F")
        pd = 100 if not a or perdio else (int(a) if a.isdigit() and int(a) <= 100 else 100)
        exp = pd * 10 + 300 + 90
        if perdio:
            exp = int(exp * CHASE_EXP_DERROTA)
        grado, body = build_ff28_cartel(0, 300, pd, 90, 0, exp, perdio)
        st.send_ff55(0x28, body, name=f"FF28 CARTEL forzado por chat ({len(body)}B)")
        return [f"cartel mandado: medalla '{chr(grado)}', precision {pd}, exp {exp}, "
                f"{'DERROTA' if perdio else 'victoria'}"]

    if c in ("salas", "paginas"):
        # ★★ SALAS DE MENTIRA PARA PROBAR LAS PESTAÑAS DE PÁGINA. Con `FF6E_SALAS_POR_PAGINA=12`,
        #   `.salas 30` = 3 páginas. Se listan como cualquier otra sala (mismo layout), pero NO se
        #   puede entrar: no existen en `SALAS_VIVAS`, así que el `FF11` contesta "inexistente".
        #   ⚠ Se ven en TODOS los canales a propósito (no tienen canal): así se prueba la
        #     paginación sin tener que crear salas de verdad en cada canal.
        if not args:
            return [f"salas de mentira: {n_salas_falsas()} - uso: .salas N | .salas off",
                    f"(entran {FF6E_SALAS_POR_PAGINA} por pagina)"]
        n = 0 if args[0].lower() in ("off", "no", "0") else int(args[0]) if args[0].isdigit() else 0
        n = poner_salas_falsas(n)
        difundir_roomlist()          # que la lista se refresque sola, sin salir y entrar al canal
        _pag = (n + FF6E_SALAS_POR_PAGINA - 1) // FF6E_SALAS_POR_PAGINA
        return [f"{n} sala(s) de mentira -> {_pag} pagina(s) de {FF6E_SALAS_POR_PAGINA}",
                "salí al lobby y mirá la lista (con 2+ paginas aparecen las pestañas)"]

    if c == "campana":
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★ SONDA DE LA CAMPANA — el cartel del bono, sin gastar campanas ni reiniciar
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   ⛔⛔ DOS INTENTOS FALLIDOS, Y LOS DOS POR EL MISMO MOTIVO:
        #     1. `FF40` sub `0x3A` -> salió «Círculo <cuenta_admin> llegó al nivel 1».
        #     2. `FF40` sub `0x12` (el del megáfono) con el itemcode de la campana -> **el cartel
        #        correcto, pero con los datos mal**: el número de sala. Dibujaba porque el `u32`
        #        cae en la misma tabla de `notice.xml`, pero ése no es el paquete de la campana.
        #
        #   ★★★★★ La respuesta la tenía el CLIENTE 2019, que trae su tabla RX con los NOMBRES
        #     (`taller/_analisis/reg19b.json`). Las campanas tienen sus propios comandos:
        #         0xA8 CmdUse   <- el que recibimos
        #         0xA9/0xC3 Cmd{Golden,Platinum}Bell          plantar
        #         0xAA/0xC4 Cmd{Golden,Platinum}BellNotifer   el cartel (lleva la SALA)
        #         0xB4/0xC5 Cmd{Golden,Platinum}BellHit       «fulano cobró N Rcoin»
        #   ⇒ Esta sonda los manda sueltos, a quien la escribe, para barrir los campos que
        #     quedan sin medir sin gastar campanas ni reiniciar.
        from .lobby_campana import (CMDS_POR_METAL, s2c_cartel_campana, s2c_cobro_campana,
                                    s2c_spawn_campana)
        # ⚠ ALIAS A PROPÓSITO: más abajo, dentro de ESTA MISMA función, hay un
        #   `from .basedatos import db_get_char`, y eso convierte a `db_get_char` en **local de
        #   toda `comando_chat`** — el import de arriba del archivo deja de verse y sale
        #   `UnboundLocalError`. Ya mordió tres veces; por eso cada bloque trae el suyo.
        from .basedatos import db_get_char as _gc_camp
        _yo = str((_gc_camp(getattr(st, "usn", 0)) or {}).get("nick", "") or "GM")
        _rid_c = int(getattr(st, "room_id", 0) or 0)
        _que = (args[0].lower() if args else "")
        _num = [int(a) for a in args[1:] if a.isdigit()]
        if _que not in ("todo", "spawn", "cartel", "cobro"):
            return ["uso: .campana todo|spawn|cartel|cobro [numeros]",
                    "  .campana todo   [item] [rcoin]      los tres, como al tocarla de verdad",
                    "  .campana spawn  [item] [slot] [extra]   planta la campana (FFA9/FFC3)",
                    "  .campana cartel [item] [sala]       el cartel (FFAA/FFC4)",
                    "  .campana cobro  [rcoin]             «cobraste N» (FFB4/FFC5)",
                    "items: 181 oro · 183 oro+ · 297 plata · 304 plata+",
                    "⏳ sin medir: el `extra` del spawn (va a un global del cliente)"]
        _item = next((n for n in _num if n in (181, 183, 297, 304)), 304)
        _metal = "oro" if _item in (181, 183) else "plata"
        _spawn, _cartel, _cobro = CMDS_POR_METAL[_metal]
        _resto = [n for n in _num if n != _item]
        _fuera = []
        if _que in ("todo", "spawn"):
            _slot = _resto[0] if len(_resto) > 0 and _que == "spawn" else 0
            _extra = _resto[1] if len(_resto) > 1 and _que == "spawn" else 0
            _pk = s2c_spawn_campana(_item, _slot, 0.0, 0.0, 0.0, _extra)
            st.send_ff55(_spawn, _pk, name=f"SONDA CAMPANA FF{_spawn:02X} plantar")
            _fuera.append(f"FF{_spawn:02X} plantar  item={_item} slot={_slot} extra={_extra}"
                          f"  hex: {_pk.hex(' ')}")
        if _que in ("todo", "cartel"):
            _sala = _resto[0] if (_resto and _que == "cartel") else _rid_c
            _pk = s2c_cartel_campana(_item, _yo, _sala)
            st.send_ff55(_cartel, _pk, name=f"SONDA CAMPANA FF{_cartel:02X} cartel")
            _fuera.append(f"FF{_cartel:02X} cartel   item={_item} sala={_sala} quien={_yo!r}"
                          f"  hex: {_pk.hex(' ')}")
        if _que in ("todo", "cobro"):
            _rc = (_resto[0] if _resto else 200) if _que == "cobro" else (
                _resto[0] if _resto else 200)
            _pk = s2c_cobro_campana(_yo, _rc)
            st.send_ff55(_cobro, _pk, name=f"SONDA CAMPANA FF{_cobro:02X} cobro")
            _fuera.append(f"FF{_cobro:02X} cobro    {_yo!r} +{_rc} Rcoin  hex: {_pk.hex(' ')}")
        for _l in _fuera:
            log("LOBBY", f"  ★★★ SONDA CAMPANA: {_l}")
        return _fuera

    if c == "tira":
        # ★ LA TIRA DE ANUNCIOS de arriba del lobby (29-sep, `tira.py`, el FFBF). Cada cambio se DIFUNDE a
        #   todos: el cliente reemplaza la tira entera, así que un anuncio se pone y se saca EN VIVO.
        import time as _t
        from . import tira as _tira
        from .basedatos import db_agregar_tira, db_quitar_tira, db_tira_anuncios
        _sub = args[0].lower() if args else ""
        if not args:
            _ls = db_tira_anuncios()
            if not _ls:
                return ["la tira está vacía · .tira <texto> | .tira 2h <texto> | .tira quitar <id> | .tira vaciar"]
            _ahora = _t.time()
            return [f"tira ({len(_ls)}):"] + [
                f"  #{a['id']}  {a['texto'][:70]}"
                + (f"   (vence en {max(0, int(a['hasta'] - _ahora)) // 60} min)" if a["hasta"] else "")
                for a in _ls]
        if _sub in ("quitar", "borrar", "sacar"):
            if len(args) < 2 or not args[1].lstrip("#").isdigit():
                return ["uso: .tira quitar <id>   (el id sale en .tira)"]
            _n = db_quitar_tira(int(args[1].lstrip("#")))
            return [f"quitado ({_n}) · tira difundida a {_tira.difundir_tira()} conectado(s)"]
        if _sub in ("vaciar", "off", "limpiar"):
            _n = db_quitar_tira(None)
            return [f"tira vaciada ({_n}) · difundida a {_tira.difundir_tira()} conectado(s)"]
        # `.tira [30m|2h|1d] <texto>`: con duración vence sola; sin duración queda hasta que se quite
        _dur = 0
        _m = args[0].lower()
        if len(args) > 1 and _m[:-1].isdigit() and _m[-1] in "mhd":
            _dur = int(_m[:-1]) * {"m": 60, "h": 3600, "d": 86400}[_m[-1]]
            args = args[1:]
        _txt = " ".join(args).strip()
        _vis = _tira.texto_para_la_tira(_txt)
        if not _vis:
            return ["uso: .tira <texto>   (sin tildes: el cliente sólo dibuja ASCII)"]
        _ahora = _t.time()
        _id = db_agregar_tira(_txt, int(_ahora + _dur) if _dur else 0,
                              getattr(st, "nick", "") or str(getattr(st, "usn", "")), int(_ahora))
        _n = _tira.difundir_tira()
        log("LOBBY", f"  📰 TIRA #{_id} de usn={getattr(st, 'usn', None)}: {_vis!r} -> {_n}")
        return [f"anuncio #{_id} en la tira" + (f" por {_dur // 60} min" if _dur else "")
                + f" · difundida a {_n} conectado(s)", f"   se ve: {_vis}"]

    if c in ("aviso", "anuncio", "gm1", "gm2", "gm3", "horn", "notice", "cartelgm", "csonda"):
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★★★ LOS ANUNCIOS DE GM — el `.gm1/.gm2/.gm3` del CBT, traído al 2013 (2026-09-15)
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   Pedido de anonimo03: *"en el CBT usaba .gm1 .gm2 .gm3 para enviar mensajes globales,
        #   buscar en nuestro cliente 2013, cablearlo como comando para GM"*.
        #
        # ★ QUÉ ERAN ALLÁ (`taller/estudio/J-operacion/06-comandos-gm.md`):
        #     `.gm1` / `.gm2` / `.gm3`  -> banner GM verde / amarillo / rojo
        #     `.horn <valor> <texto>`   -> probar cualquier estilo a mano
        #
        # ★★★ Y ACÁ EXISTE, MEDIDO EN NUESTRO CLIENTE. El camino fue el de siempre: **leer al
        #   consumidor**. `rnr_script/notice.xml` tiene la tabla de carteles, y ahí está la fila:
        #
        #       <type noticedtype="D" itemcode="10000002" imgindex="20" flag="64" name="GM 공지">
        #                                                             ↑ img 20 = gm_megaphone.spr
        #
        #   («GM 공지» = *aviso de GM*.) De ahí, quién dibuja: la función del notice es `0x596570`,
        #   y tiene **3 llamadores**. Uno es el cartel de pareja (que ya usábamos) y los otros dos
        #   son handlers de paquete — `FF46` (`0x5CF140`) y `FF48` (`0x5CF360`).
        #
        # ★★ EL `FF46`, DESENSAMBLADO — tres subtipos según el primer byte:
        #       A == 0  ->  call 0x593b30(str2)                       texto simple
        #       A == 1  ->  call 0x593f40(1) + call 0x596570(...)     ★ EL NOTICE
        #       A == 2  ->  call 0x593f40(0)                          apagar
        #   Y el `u32` del itemcode **sólo se lee si A == 1** (`cmp byte[esp+5],1 / jne`), que es
        #   la confirmación de que ése es el que consulta `notice.xml`.
        #
        #       FF46  [u8 A=1][u32 itemcode][u8 len][str1][u8 len][str2]
        #
        # ⛔⛔⛔ Y LO PROBAMOS, Y **NO ES** — 2026-09-15, lo cazó anonimo03 en pantalla:
        #   *"los horn que me pusiste son de «ha nacido una pareja»"*. Probó los itemcodes
        #   **0, 1 y 10000002** y los TRES dibujaron el mismo cartel de pareja.
        #   ⇒ El `u32` **no elige el cartel**: el texto es fijo, así que este camino está mal.
        #     (El paquete sí dibuja algo, o sea que el `A=1` como subtipo del notice está bien;
        #      lo que falla es de dónde saca el TEXTO.)
        #
        #   ★★ El error de método, y es uno viejo: leí el disasm y **no busqué al productor**.
        #     `0x596570` tiene 3 llamadores y uno es el cartel de pareja — que era justamente la
        #     pista de que esa función **es la de pareja**, no la del notice genérico.
        #
        #   ★★★★★ LO QUE SÍ QUEDÓ MEDIDO, y es la pista buena: **el itemcode del `notice.xml` es
        #     el id del ÍTEM MEGÁFONO**, no un código aparte. Cruzado contra `shop_lt.txt`:
        #         Index 1   «Megafono pequeño»  <->  notice.xml itemcode 1   (작은 확성기)
        #         Index 2   «Megafono grande»   <->  notice.xml itemcode 2   (큰 확성기)
        #         Index 200 «Megáfono agregar amigos» <-> itemcode 200       (친구 추가)
        #     Los tres coinciden, y el `Index` es el id real (verificado con el Gorila Verde,
        #     `Index="600164"` = el 600164 que ya usábamos).
        #     Y el texto del ítem lo dice todo: *"Puedes anunciar tu mensaje a todos los usuarios"*.
        #
        #   ⇒ EL PRÓXIMO PASO ES MEDIR, NO DEDUCIR: se le puso el megáfono en la mochila a las
        #     cuentas de GM (item 1, 2 y 200). Cuando alguien lo USE, el paquete de verdad cae en
        #     el log — y ése es el que hay que cablear. `.horn` se queda como sonda mientras tanto.
        #
        # ⚠⚠ POR QUÉ ARRANCA MANDÁNDOSE **SÓLO A QUIEN LO ESCRIBE**: el layout está leído del
        #   disasm pero **no está visto en pantalla todavía**, y en este cliente un paquete mal
        #   armado no se queja: **mata al que lo recibe** (el `Ani` de 16 bytes ya nos tiró
        #   clientes). Hacer broadcast de algo sin confirmar sería tirar a TODO el server de una.
        #   ⇒ `GM_AVISO_A_TODOS = False` hasta que anonimo03 lo vea en pantalla. Con la perilla en
        #     `True`, va a todos. El `.aviso` de abajo NO tiene ese riesgo: es chat común.
        from .ajustes import GM_AVISO_A_TODOS, GM_NOTICE_ITEMCODE, GM_CARTEL_FF46
        _txt = " ".join(args).strip()

        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★★★ EL CARTEL DE VERDAD: `FF40 [0x12]` CON EL u32 EN `0xFFFFFFFF` — 2026-09-15
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   ⛔ Y LO TUVE DELANTE TODO EL TIEMPO: es **el mismo paquete del cartel de pareja**
        #     (`lobby_pareja._s2c_cartel_global`), que ya mandábamos desde hace días.
        #
        #   ★ La idea de dónde mirar fue de anonimo03: *"en las capturas mitm, al llegar al lobby,
        #     ellos ya tienen un anuncio de sistema, que debe estar en el mismo lugar que los de
        #     GM"*. Y ahí estaba, en `mitm_20260902_140426`:
        #
        #       12 ff ff ff ff 15 "¡Bienvenido/a a Rbit!" 64 "Sitio web spacewander.lat\n…"
        #       ↑sub  ↑u32       ↑len1  ↑titulo           ↑len2 ↑cuerpo
        #
        #   ★★★ LA LLAVE ES EL `u32` EN **`0xFFFFFFFF`**. Con un id de anillo el cliente dibuja
        #     *"Ha nacido una pareja"*; con `0xFFFFFFFF` **no hay anillo que buscar** y sale el
        #     cartel con LOS DOS TEXTOS QUE MANDES. Por eso todos mis intentos daban pareja: le
        #     estaba dando ids válidos.
        #   ⚠ Y va **SIN el byte de flag final**: el paquete del corpus mide 128 = 1+4+1+21+1+100,
        #     exacto. Nuestro builder de pareja sí lo manda, pero para este camino no va.
        #
        #   ⚠⚠ El corpus se usa acá **para ubicar el paquete**, que es su uso válido — no para
        #     decidir nada. Lo que mande esto se comprueba en pantalla antes de darlo por bueno.
        # ★★★★★ LA COSECHA DE SUBTIPOS — 2026-09-15, pedido de anonimo03: *"no copies por si acaso,
        #   investiga y mira si puedes cosechar los comandos de carteles de gm"*.
        #   Se enumeró la tabla de saltos del `FF40` (índices en `0x5F3194`, destinos en
        #   `0x5F30B4`) y se miró, rama por rama, cuáles llaman a los pintores que ya teníamos
        #   medidos. **TRES** llaman al que AGREGA UN CARTEL (`0x4325E0`) — y el CBT tenía
        #   justamente tres comandos (`.gm1/.gm2/.gm3`):
        #
        #       tabla 0x39  ->  rama 0x5EE68B     (la que anonimo03 probó: salió cartel de premio)
        #       tabla 0x3C  ->  rama 0x5EE650     ⏳ sin probar
        #       tabla 0x3D  ->  rama 0x5EE5ED     ⏳ sin probar
        #
        #   ⚠⚠ Y HAY UNA CONTRADICCIÓN SIN RESOLVER, que por eso esto sigue siendo una SONDA:
        #     la tabla dice que el **`0x11`** lleva al cartel de pareja (`0x5F15F4`) y que el
        #     `0x12` cae en la rama de descarte — pero nosotros mandamos `0x12` **y funciona**
        #     (visto con frida). O sea que hay un corrimiento de 1 en alguna parte, y hasta
        #     saber dónde, los números de arriba **no están confirmados**.
        #   ⇒ `.cartelgm <sub> <texto>` los prueba uno por uno. Se confirma EN PANTALLA.
        if c in ("cartelgm", "csonda"):
            if not args or not args[0].lower().startswith("0x") and not args[0].isdigit():
                return ["uso: .cartelgm <sub> [u32] <texto>    (sonda del cartel)",
                        "★ CONFIRMADO: el sub 0x12 con u32=FFFFFFFF dibuja tu texto",
                        "   .cartelgm 0x12 reinicio en 10 minutos",
                        "⏳ buscando los 3 estilos del CBT — probá cambiando el u32:",
                        "   .cartelgm 0x12 0 hola   ·   0x12 1 hola   ·   0x12 2 hola"]
            _sub = int(args[0], 16) if args[0].lower().startswith("0x") else int(args[0])
            # ★★★★★ CONFIRMADO EN PANTALLA (anonimo03, 19:36): de los cinco candidatos **sólo el
            #   `0x12` dibujó**, y dibujó lo que le mandamos:
            #        ┌ SERVIDOR ┐
            #        │ hola      │
            #   ⚠ (en la captura salía un "5000" al lado y lo anoté como el campo del estilo:
            #      era el SALDO DE RCOIN de anonimo03. El aviso se dibuja encima de ese contador.)
            #   ⇒ `FF40 [0x12][u32][u8 len]<título>[u8 len]<texto>` con el `u32` en `0xFFFFFFFF`
            #     ES el aviso de sistema con TEXTO LIBRE. La llave era el `u32`: con un id de
            #     anillo el cliente busca el dibujo y sale «Ha nacido una pareja»; con
            #     `0xFFFFFFFF` no hay nada que buscar y se queda con los dos textos.
            #   ★ Y de paso queda resuelta la contradicción de la tabla de saltos: el subtipo real
            #     es el `0x12`, así que **el índice que leí estaba corrido en 1** — los "0x39 /
            #     0x3C / 0x3D" cosechados son en realidad 0x3A / 0x3D / 0x3E. No se tocan hasta
            #     probarlos, pero queda anotado por qué no coincidían.
            #
            # ⏳ LOS TRES ESTILOS del CBT no aparecen: en este paquete lo único que varía es el
            #   `u32`, y ya sabemos qué hace. O el estilo viene por otro lado, o el 2013 tiene uno
            #   solo. El `u32` queda como argumento para poder rastrearlo sin inventar nada.
            _u32 = 0xFFFFFFFF
            _resto = args[1:]
            if _resto and (_resto[0].lower().startswith("0x") or _resto[0].isdigit()):
                _u32 = (int(_resto[0], 16) if _resto[0].lower().startswith("0x")
                        else int(_resto[0]))
                _resto = _resto[1:]
            _cu = " ".join(_resto).encode("cp1252", "replace")[:200] or b"prueba"
            _ti = b"SERVIDOR"
            _pk = (bytes([_sub & 0xFF]) + struct.pack("<I", _u32 & 0xFFFFFFFF)
                   + bytes([len(_ti)]) + _ti + bytes([len(_cu)]) + _cu)
            st.send_ff55(0x40, _pk, name=f"SONDA CARTEL FF40 sub 0x{_sub:02X}")
            log("LOBBY", f"  ★★★ SONDA CARTEL: FF40 sub 0x{_sub:02X} u32=FFFFFFFF "
                         f"titulo={_ti!r} texto={_cu[:40]!r} -> {_pk.hex(' ')}")
            return [f"sonda mandada: FF40 sub 0x{_sub:02X}  u32=0x{_u32:08X}",
                    f"   hex: {_pk.hex(' ')}",
                    "★ el 0x12 ya está CONFIRMADO. Ahora buscamos qué cambia el estilo:",
                    "   .cartelgm 0x12 0 hola  ·  0x12 1 hola  ·  0x12 2 hola  ·  0x12 3 hola"]

        if c in ("gm1", "gm2", "gm3", "cartel_gm"):
            if not _txt:
                return [f"uso: .{c} <texto>   (cartel a todo el server)"]
            _tit = {"gm1": "SERVIDOR", "gm2": "AVISO", "gm3": "ATENCIÓN"}.get(c, "SERVIDOR")
            _t1 = _tit.encode("cp1252", "replace")[:60]
            _t2 = _txt.encode("cp1252", "replace")[:200]
            _pk = (bytes([0x12]) + struct.pack("<I", 0xFFFFFFFF)
                   + bytes([len(_t1)]) + _t1 + bytes([len(_t2)]) + _t2)
            _dst = ([st] if not GM_AVISO_A_TODOS
                    else [x for x in list(CONEXIONES.values())
                          if x is not None and not getattr(x, "cerrado", False)])
            for _cc in _dst:
                _cc.send_ff55(0x40, _pk, name=f"FF40/0x12 CARTEL GM {_tit!r}: {_txt[:40]!r}")
            log("LOBBY", f"  ★★★ CARTEL DE GM {_tit!r} de usn={getattr(st, 'usn', None)}"
                         f"{' (streamer)' if not gm.es_gm(st) else ''}: {_txt!r} -> {len(_dst)} jugador(es)"
                         + ("  ⚠ SOLO al que lo escribió (GM_AVISO_A_TODOS)"
                            if not GM_AVISO_A_TODOS else ""))
            return [f"cartel mandado a {len(_dst)} jugador(es)"
                    + ("  ⚠ solo a vos hasta verlo en pantalla" if not GM_AVISO_A_TODOS else ""),
                    f"   hex: {_pk[:24].hex(' ')}…"]

        if c in ("aviso", "anuncio"):
            # ★ EL SEGURO: texto por el chat, firmado SERVER. No dibuja cartel, pero **no puede
            #   romper nada** y llega a todos. Es el que sirve hoy para "reinicio en 10 minutos".
            if not _txt:
                return [f"uso: .{c} <texto>   (va a TODOS, por el chat)"]
            _n = avisar_a_todos(_txt)
            log("LOBBY", f"  ★★★ AVISO de usn={getattr(st, 'usn', None)}: {_txt!r} -> {_n}")
            return [f"aviso mandado a {_n} jugador(es)"]

        # — los que dibujan el CARTEL —
        # ⛔⛔⛔ MEDIDO CON FRIDA, Y EL CAMINO ESTA CERRADO — 2026-09-15, 19:03.
        #   anonimo03 mando `.horn medir 1 hola` con el enganche puesto:
        #       0x596570   arg0="GM"       arg1="hola"      arg2=1       arg3=NULL
        #       (pareja)   arg0="cuenta_admin"  arg1="jugador1"  arg2=30478   arg3=NULL
        #   ★★★ EL ITEMCODE LLEGO PERFECTO (`arg2 = 1`, lo que mandamos). El paquete estaba bien
        #     armado — y aun asi el cliente dibujo **"ha nacido una pareja"**.
        #   ⇒ `0x596570` **NO es el notice generico: ES el cartel de pareja**. El itemcode solo
        #     elige el DIBUJO del anillo, no el texto. Probar mas itemcodes da siempre lo mismo.
        #
        #   ⚠⚠ Y ACA ME CORRIJO POR SEGUNDA VEZ EN EL MISMO ASUNTO: escribi que la causa del
        #     crash era "un byte que falta al final". **No era eso.** El paquete estaba bien; lo
        #     que estaba mal era la funcion elegida — el error de la PRIMERA vez, no una
        #     consecuencia suya. Anotar una causa plausible sin medirla es adivinar, aunque
        #     suene tecnica y venga con un disasm al lado.
        #
        #   ⏳ Queda sin probar el **FF48** (`0x5CF360`), el tercer llamador del mismo dibujante.
        #     Pero `.aviso` ya cubre el caso de uso real ("reinicio en 10 minutos"), asi que
        #     seguir o no es una decision, no una obligacion.
        # ★★ LA EXCEPCIÓN PARA MEDIR: `.horn medir <itemcode> <texto>` pasa el freno **una vez**.
        #   Existe porque para saber el layout hay que **mandar el paquete** con Frida enganchado
        #   (ver `taller/re2013/frida_notice.py`), y obligar a editar `ajustes.py` + reiniciar el server
        #   para cada intento hace que medir cueste más que adivinar — que es justo el error que
        #   nos trajo hasta acá. La palabra `medir` es el "sé lo que estoy haciendo".
        #   ⚠ Sigue yendo SÓLO al que lo escribe, y sigue pudiendo matarle el cliente.
        _medir = bool(args) and args[0].lower() == "medir"
        if _medir:
            args = args[1:]
        if not GM_CARTEL_FF46 and not _medir:
            return ["⛔ el cartel está APAGADO: este paquete le tiró el cliente a anonimo03 el 15-sep",
                    "   (el layout está mal leído — la medición con Frida lo confirmó)",
                    "★ usá `.aviso <texto>`, que va por el chat y es seguro",
                    "⚠ para MEDIR con frida_notice.py enganchado, y sabiendo que puede matarte",
                    "   el cliente:   .horn medir <itemcode> <texto>"]
        if c in ("horn", "notice"):
            if len(args) < 2 or not args[0].lstrip("-").isdigit():
                return ["uso: .horn <itemcode> <texto>   (sonda: probá cualquier estilo)",
                        "itemcodes de notice.xml: 0=aviso · 1=megafono chico · 2=megafono grande",
                        "                         10000002=GM (gm_megaphone) · 10000001=otro",
                        "⚠ se manda SOLO A VOS hasta confirmar el layout en pantalla"]
            _item, _txt = int(args[0]), " ".join(args[1:])
        else:
            if not _txt:
                return [f"uso: .{c} <texto>   (cartel de GM a todo el server)"]
            _item = GM_NOTICE_ITEMCODE.get(c, 10000002)

        # ⚠ Import LOCAL a propósito, y no es redundante: el bloque de `.monedas` hace
        #   `from .basedatos import db_get_char` **dentro de esta misma función**, y eso convierte
        #   a `db_get_char` en variable local de TODA `comando_chat` — así que el import de arriba
        #   del módulo deja de verse acá y esto reventaba con `UnboundLocalError`. Lo cazó el banco.
        from .basedatos import db_get_char as _get_char
        _yo = str((_get_char(getattr(st, "usn", 0)) or {}).get("nick", "") or "GM")
        _p = (bytes([1]) + struct.pack("<I", _item & 0xFFFFFFFF)
              + bytes([len(_yo.encode("cp1252", "replace")[:30])])
              + _yo.encode("cp1252", "replace")[:30]
              + bytes([len(_txt.encode("cp1252", "replace")[:120])])
              + _txt.encode("cp1252", "replace")[:120])
        # ⚠ La sonda (`.horn`) va SIEMPRE sólo al que la escribe, diga lo que diga la perilla:
        #   es para experimentar con itemcodes que nadie midió.
        _solo_yo = (c in ("horn", "notice")) or not GM_AVISO_A_TODOS
        _dest = [st] if _solo_yo else [x for x in list(CONEXIONES.values())
                                       if x is not None and not getattr(x, "cerrado", False)]
        for _c46 in _dest:
            _c46.send_ff55(0x46, _p, name=f"FF46 NOTICE itemcode={_item} de {_yo!r}: {_txt[:40]!r}")
        log("LOBBY", f"  ★★★ FF46 NOTICE itemcode={_item} de {_yo!r}: {_txt!r} "
                     f"-> {len(_dest)} jugador(es)"
                     + ("  ⚠ SOLO AL QUE LO ESCRIBIÓ (ver GM_AVISO_A_TODOS)" if _solo_yo else ""))
        return [f"cartel mandado (itemcode {_item}) a {len(_dest)} jugador(es)"
                + ("  ⚠ solo a vos: el layout todavía no se vio en pantalla" if _solo_yo else ""),
                "si NO ves nada, probá otro itemcode con .horn <n> <texto>"]

    if c in ("avisogm", "sondagm"):
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★★★ LA SONDA DE LOS SEIS SOSPECHOSOS — 2026-09-15
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   `.avisogm <n> <texto>`  manda al candidato n el paquete **con el layout del 2019**:
        #
        #       [u8 tipo][u16 largo][texto]
        #
        #   que es el de `CNetwork::CmdSystemNotice`, leído del cliente 2019 (`0x00D304E0`).
        #   Ver `GM_CANDIDATOS` en `ajustes.py` y `documentacion/AVISO_DE_GM.md`.
        #
        # ★ UNO POR UNO Y NO TODOS DE UNA: si alguno mata el cliente, los siguientes no se
        #   probarían — y encima no se sabría cuál fue. Con Frida enganchado, cada intento dice
        #   qué leyó ese handler, y el que lea `[u8][u16][texto]` es el bueno.
        # ⚠ Va SÓLO a quien lo escribe. Puede cerrarle el juego: es una sonda, no una herramienta.
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★★★ ENCONTRADO: **`FF40` SUBTIPO `0x39`** — 2026-09-15, la última vuelta
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   El camino, esta vez completo y sin adivinar ni un paso:
        #     1. el cliente LOGUEA cada cartel (`Notice Append %s`, en `.\cNotice.cpp`) ⇒ la
        #        función que los agrega es `0x432390`;
        #     2. sus llamadores útiles son dos envoltorios, `0x4325E0` y `0x432630`;
        #     3. a `0x4325E0` lo llama **UNA sola** función: `0x5EE72D`…
        #     4. …que está DENTRO del `FF40` (`0x5EDF50`), el comando social de siempre;
        #     5. y la tabla de saltos del `FF40` (índices en `0x5F3194`, destinos en `0x5F30B4`)
        #        dice que a esa rama (`0x5EE68B`) se llega **sólo con el subtipo `0x39`**.
        #
        #   EL LAYOUT, normalizado con `campos13.py` (⚠ con `ebp=1`, que el sub-handler hereda
        #   del despachador — sin ese detalle los largos salen mal):
        #
        #       FF40 [0x39][u8 A][u16 B][u16 C][u8 len1][str1][u8 len2][str2]
        #
        #   ★★ DOS STRINGS LIBRES, y con buffers **grandes** (0x2dc y 0x12c). Eso es un aviso de
        #     verdad — justo lo que el `FF46` no podía llevar.
        #   ⏳ Qué son A, B y C **no está medido**: por eso esto es una SONDA con los tres a mano,
        #     y no un `.gm1` cableado. Ya me equivoqué tres veces hoy por dar por sabido un campo.
        if c in ("avisogm", "sondagm") and args and args[0].lower() == "n":
            if len(args) < 5:
                return ["uso: .avisogm n <A> <B> <C> <texto>    (sonda del FF40 sub 0x39)",
                        "   A = u8 · B = u16 · C = u16 · después el texto",
                        "   probá:  .avisogm n 0 0 0 hola   ·   .avisogm n 1 1 0 hola",
                        "⚠ enganchá antes:  python taller/re2013/frida_notice.py"]
            try:
                _a39, _b39, _c39 = int(args[1]), int(args[2]), int(args[3])
            except ValueError:
                return ["A, B y C tienen que ser números"]
            # ⚠ Import local, por lo mismo que en el bloque del `FF46`: el bloque de `.monedas`
            #   hace `from .basedatos import db_get_char` dentro de ESTA función, y eso vuelve
            #   `db_get_char` local a toda `comando_chat`. Ya me mordió dos veces.
            from .basedatos import db_get_char as _gc39
            _yo39 = str((_gc39(getattr(st, "usn", 0)) or {}).get("nick", "") or "GM")
            _tx39 = " ".join(args[4:]).encode("cp1252", "replace")[:200]
            _n39 = _yo39.encode("cp1252", "replace")[:30]
            _p39 = (bytes([0x39, _a39 & 0xFF]) + struct.pack("<HH", _b39 & 0xFFFF, _c39 & 0xFFFF)
                    + bytes([len(_n39)]) + _n39 + bytes([len(_tx39)]) + _tx39)
            st.send_ff55(0x40, _p39, name=f"SONDA FF40/0x39 A={_a39} B={_b39} C={_c39}")
            log("LOBBY", f"  ★★★ SONDA FF40 sub 0x39: A={_a39} B={_b39} C={_c39} "
                         f"nick={_yo39!r} texto={_tx39[:40]!r}  -> hex {_p39.hex(' ')}")
            return [f"sonda FF40/0x39 mandada: A={_a39} B={_b39} C={_c39}",
                    f"   hex: {_p39.hex(' ')}",
                    "¿salió algún cartel? si no, probá otros A/B/C"]

        from .ajustes import GM_CANDIDATOS
        if not args or not args[0].isdigit() or not (1 <= int(args[0]) <= len(GM_CANDIDATOS)):
            return [f"uso: .avisogm <1..{len(GM_CANDIDATOS)}> <texto>   (sonda del aviso de GM)"] + \
                   [f"   {i + 1}) FF{_cmd:02X}   handler 0x{_h:06X}"
                    for i, (_cmd, _h) in enumerate(GM_CANDIDATOS)] + \
                   ["⚠ enganchá primero:  python taller/re2013/frida_notice.py",
                    "⚠ puede cerrarte el juego. El que dibuje algo (o lea bien) es el bueno."]
        _i = int(args[0]) - 1
        _cmd_s, _h_s = GM_CANDIDATOS[_i]
        _t_s = (" ".join(args[1:]) or "prueba").encode("cp1252", "replace")[:200]
        # ★ El `tipo` va en 1: en el 2019 ese primer byte se lee antes que nada y el handler
        #   ramifica con él. 1 es el valor más probable para "mostrar"; si no sale nada, se
        #   prueban otros con `.avisogm <n> <texto>` cambiando esto — pero primero hay que saber
        #   QUÉ comando es, que es lo que esta sonda busca.
        _p_s = bytes([1]) + struct.pack("<H", len(_t_s)) + _t_s
        st.send_ff55(_cmd_s, _p_s, name=f"SONDA aviso GM: FF{_cmd_s:02X} [01][u16 {len(_t_s)}][{_t_s[:20]!r}]")
        log("LOBBY", f"  ★★★ SONDA AVISO GM #{_i + 1}: FF{_cmd_s:02X} (handler 0x{_h_s:06X}) "
                     f"<- [01][u16 largo={len(_t_s)}][texto] — mirá frida_notice y la pantalla")
        return [f"sonda {_i + 1}/{len(GM_CANDIDATOS)} mandada: FF{_cmd_s:02X} (handler 0x{_h_s:06X})",
                "mirá la PANTALLA (¿salió algún cartel?) y la ventana de frida (¿qué leyó?)",
                f"probá el siguiente con  .avisogm {_i + 2} {args[1] if len(args) > 1 else 'hola'}"
                if _i + 2 <= len(GM_CANDIDATOS) else "era el último de los seis"]

    if c in ("mesas", "fantasmas"):
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★★★ `.mesas` — VER LAS SALAS FANTASMA SIN LEER EL LOG (2026-09-15)
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   Nació de una pregunta de anonimo03 probando el arreglo: *"¿necesitamos emular el tráfico
        #   real de prod?"*. No hace falta —el bug es una secuencia de dos paquetes, no un tema de
        #   volumen— pero **sí** hacía falta poder MIRAR el estado: hasta ahora la única forma de
        #   saber si una mesa tenía un fantasma era leer el `servidor.log` a mano.
        #
        #   Muestra, por sala: quién está sentado, y si ese `usn` está **vivo** (tiene conexión y
        #   su `room_id` apunta acá), **colgado** (conectado pero cree estar en otra) o **muerto**
        #   (sin conexión = el fantasma del expediente).
        #
        #   ★ `.mesas barrer` fuerza una pasada del barrido AHORA, sin esperar los 60 s.
        #     ⚠ Corre las MISMAS reglas que el hilo, no una copia: si se probara con otra lógica,
        #       la prueba no diría nada del código que corre en prod.
        from .salas import (OCUPACION, SALAS_VIVAS, barrer_mesas_huerfanas, espectadores_de,
                            _mesa_lock, nuevo_roomid, registrar_sala)
        from .ajustes import BARRIDO_MESAS_SEG
        if args and args[0].lower() in ("fantasma", "fantasmas"):
            # ★★★★★ SEMBRAR UN FANTASMA A MANO — 2026-09-15.
            #   ⛔ POR QUÉ HACE FALTA: el fantasma **no se puede provocar a voluntad**. Nace de un
            #     `CREATEROOM` que el cliente no completa (ver `SALAS_FANTASMA.md` §2), y eso no
            #     depende de nosotros. anonimo03 intentó el doble clic muchas veces sin sacar ninguno.
            #   ⇒ Se arma el MISMO estado que dejaba el bug —un `usn` sentado en una mesa de la
            #     que nadie lo va a levantar— y así se puede ver a la red trabajar en vivo.
            #   ⚠ Usa un `usn` que NO tiene conexión (el 999999), o sea que cae en la regla (a)
            #     del barrido: la del fantasma MUERTO, que es el caso del 6671 de prod.
            _rid_f = nuevo_roomid()
            _usn_f = 999999
            with _mesa_lock:
                OCUPACION.setdefault(_rid_f, {})[HOST_SLOT] = _usn_f
            registrar_sala(type("_F", (), {
                "room_id": _rid_f, "room_name": "SALA FANTASMA (de prueba)", "room_mode": 0,
                "room_colab": False, "room_boss": False, "room_privada": False,
                "room_en_juego": False, "usn": _usn_f, "canal": getattr(st, "canal", None),
            })())
            return [f"sembrada la sala {_rid_f} con el usn {_usn_f} sentado y SIN conexión",
                    "es el mismo estado que dejaba el bug (el caso del 6671 de prod)",
                    "mirá la lista de salas: ahí está. Ahora `.mesas` y `.mesas barrer`",
                    f"(o esperá {BARRIDO_MESAS_SEG}s y se va sola)"]
        if args and args[0].lower() in ("barrer", "limpiar", "ya"):
            _lib, _bor = barrer_mesas_huerfanas()
            return [f"barrido a mano: {_lib} asiento(s) liberado(s), {len(_bor)} sala(s) borrada(s)"
                    + (f" -> {_bor}" if _bor else ""),
                    "(es la MISMA función del hilo de cada 60s, no una copia)"]
        _out = [f"mesas: {len(OCUPACION)} · salas publicadas: {len(SALAS_VIVAS)}"]
        _fant = 0
        for _rid in sorted(set(OCUPACION) | set(SALAS_VIVAS)):
            _m = mesa_de(_rid)
            _nom = (SALAS_VIVAS.get(_rid) or {}).get("nombre", "(sin publicar)")
            _quien = []
            for _sl, _u in sorted(_m.items()):
                _cx = CONEXIONES.get(_u)
                if _cx is None:
                    _est, _fant = "MUERTO", _fant + 1
                elif getattr(_cx, "room_id", None) != _rid:
                    _est, _fant = f"colgado(esta en {getattr(_cx, 'room_id', None)})", _fant + 1
                else:
                    _est = "vivo"
                _quien.append(f"s{_sl}=usn{_u}[{_est}]")
            _esp = len(espectadores_de(_rid))
            _out.append(f"  sala {_rid} {_nom!r}: " + (" ".join(_quien) if _quien else "VACIA")
                        + (f" +{_esp} mirando" if _esp else ""))
        _out.append(f"★ fantasmas detectados: {_fant}"
                    + ("  -> proba `.mesas barrer`" if _fant else "  (todo limpio)"))
        return _out

    if c in ("rate", "rates"):
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★ LOS RATES DE EVENTO — el primer comando de OPERACIÓN (2026-09-14)
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   `.rate exp 2.0` · `.rate coin 1.5` · `.rate` (ver) · `.rate off` (todo a 1.0)
        #
        #   Multiplican lo que paga UNA carrera, para TODO el server. Es la "happy hour".
        #   ⚠ Sólo pasan los que están en `gm.txt` — la puerta la abre `puede_usar_consola`,
        #     acá arriba, y no hace falta volver a preguntarlo.
        #
        #   ⚠⚠ ARRANCAN EN 1.0 Y NO SOBREVIVEN A UN REINICIO. A propósito: un multiplicador que
        #     sobrevive a un reinicio que nadie recuerda es como se termina pagando el triple una
        #     semana entera sin que nadie sepa por qué.
        _r = rates()
        _rid = getattr(st, "room_id", None)
        if not args:
            # ★ Se muestran las TRES columnas, y la que manda (el efectivo) al final. Mostrar
            #   sólo el global esconde el de sala, y así es como un GM jura que el evento está
            #   en x2 mientras una sala paga x4.
            _l = []
            for _k in _r:
                _l.append(f"{_k}: server x{_r[_k]:g} · sala x{rate_sala_de(_rid, _k):g}"
                          f" -> x{rate_efectivo(_k, _rid):g}")
            return _l + ["uso: .rate exp 2.0 (server) | .rate sala exp 2.0 | .rate off"]
        _q = args[0].lower()

        # ── la variante POR SALA ───────────────────────────────────────────────────────────
        if _q in ("sala", "room", "aqui", "aquí"):
            if not _rid:
                return ["no estas en una sala"]
            _a2 = args[1].lower() if len(args) > 1 else ""
            if _a2 in ("", "ver"):
                return [" · ".join(f"{k} x{rate_sala_de(_rid, k):g}" for k in _r),
                        "uso: .rate sala exp 2.0 | .rate sala off"]
            if _a2 in ("off", "no", "normal", "1"):
                limpiar_rate_sala(_rid)
                log("LOBBY", f"  🎉 RATE de la sala {_rid} a 1.0 "
                             f"(lo apagó usn={getattr(st, 'usn', None)})")
                avisar_a_la_sala(_rid, "Los rates de la sala vuelven a lo normal")
                return [f"la sala vuelve a x1 (el del server sigue: "
                        f"{' · '.join(f'{k} x{v:g}' for k, v in _r.items())})"]
            if _a2 not in _r:
                return [f"no conozco el rate '{_a2}' - hay: {', '.join(_r)}"]
            if len(args) < 3:
                return [f"sala {_a2} x{rate_sala_de(_rid, _a2):g}", f"uso: .rate sala {_a2} 2.0"]
            try:
                _v2 = float(args[2].replace(",", "."))
            except ValueError:
                return [f"'{args[2]}' no es un numero - uso: .rate sala {_a2} 2.0"]
            _v2 = max(RATE_MIN, min(_v2, RATE_MAX))
            poner_rate_sala(_rid, _a2, _v2)
            _ef = rate_efectivo(_a2, _rid)
            _nom2 = RATE_NOMBRES.get(_a2, _a2)
            log("LOBBY", f"  🎉 RATE de sala {_rid}: {_a2} x{_v2:g} -> efectivo x{_ef:g} "
                         f"(lo puso usn={getattr(st, 'usn', None)})")
            avisar_a_la_sala(_rid, f"Esta sala: {_nom2} x{_ef:g}" if _ef != 1.0
                             else f"{_nom2.capitalize()} normal en esta sala")
            # ⚠ Si el global y el de sala se multiplicaron, se DICE de dónde salió cada parte.
            #   Un GM que ve x4 y puso x2 tiene que poder entender el otro x2 sin ir al log.
            _extra = ([f"= server x{_r[_a2]:g} × sala x{_v2:g}"] if _r[_a2] != 1.0 else [])
            return [f"sala {_a2} x{_v2:g} -> se paga x{_ef:g}"] + _extra

        if _q in ("off", "no", "normal", "1"):
            for _k in _r:
                poner_rate(_k, 1.0)
            log("LOBBY", f"  🎉 RATES a 1.0 (los apagó usn={getattr(st, 'usn', None)})")
            _n = avisar_a_todos("Los rates vuelven a lo normal")
            return [f"rates a 1.0 — avisado a {_n} jugador(es)"]
        if _q not in _r:
            return [f"no conozco el rate '{_q}' - hay: {', '.join(_r)}"]
        if len(args) < 2:
            return [f"{_q} x{_r[_q]:g}", f"uso: .rate {_q} 2.0"]
        try:
            _v = float(args[1].replace(",", "."))
        except ValueError:
            return [f"'{args[1]}' no es un numero - uso: .rate {_q} 2.0"]
        _puesto = poner_rate(_q, _v)
        _nom = RATE_NOMBRES.get(_q, _q)
        log("LOBBY", f"  🎉 RATE {_q} = x{_puesto:g} (lo puso usn={getattr(st, 'usn', None)}, "
                     f"pidió x{_v:g})")
        # ⚠ Si se acotó, se DICE. Contestar "listo" tras haber guardado otra cosa es como se
        #   termina creyendo que el evento está en x200 cuando está en x10.
        _aviso = ([f"⚠ el maximo es x{RATE_MAX:g} y el minimo x{RATE_MIN:g}: quedo en x{_puesto:g}"]
                  if _puesto != _v else [])
        # ⚠ EL PISO DE LAS MONEDAS. El cartel paga `coin + FF28_BASECOIN` y `coin` no puede ser
        #   negativo (viaja como u16), así que por debajo de 1.0 el rate se topa: lo mínimo que
        #   se paga es el fijo. O sea que `.rate coin 0.5` paga MÁS de la mitad. Es una limitación
        #   real; se dice acá para que no la descubra mirando saldos.
        if _q == "coin" and 0 < _puesto < 1.0:
            _aviso.append(f"⚠ ojo: las monedas no bajan del fijo de {FF28_BASECOIN} por carrera, "
                          f"asi que se va a pagar mas de x{_puesto:g}")
        _n = avisar_a_todos(f"Evento: {_nom} x{_puesto:g}" if _puesto != 1.0
                            else f"{_nom.capitalize()} vuelve a lo normal")
        # ⚠ Si ESTA sala además tiene su propio rate, se avisa acá: el GM acaba de poner x2 y en
        #   la sala donde está parado se paga x4. Sin este renglón lo descubre mirando el log.
        _ef2 = rate_efectivo(_q, _rid)
        _mas = ([f"⚠ en ESTA sala se paga x{_ef2:g} (tiene su propio x{rate_sala_de(_rid, _q):g})"]
                if _ef2 != _puesto else [])
        return _aviso + [f"{_q} x{_puesto:g} en todo el server — avisado a {_n} jugador(es)"] + _mas

    if c == "gm":
        # ★ Para poder ver la puerta desde adentro del juego, sin entrar al server.
        #   ⚠ No muestra quiénes son: dice CUÁNTOS y de qué archivo. Listar los uid de los GM en
        #     el chat de una sala es regalar la lista de a quién apuntarle.
        if args and args[0].lower() in ("recargar", "reload"):
            _u = gm.recargar(" (a mano, por .gm recargar)")
            return [f"lista de GM releida: {len(_u)} GM(s)"]
        return [f"sos GM. hay {len(gm.uids())} en la lista ({gm.RUTA})",
                "uso: .gm recargar"]

    # ★ `.reset score` — 2026-09-14, pedido de anonimo03: *"en lugar de .score reset, que sea
    #   .reset score"*. Se normaliza acá arriba y cae en el MISMO handler: una sola
    #   implementación, dos formas de escribirlo. Si mañana hay `.reset otracosa`, se agrega
    #   al `if` de abajo y listo.
    if c == "reset" and args and args[0].lower() in ("score", "marcador"):
        c, args = "score", ["reset"] + args[1:]
    elif c == "reset":
        return ["uso: .reset score"]

    if c in ("score", "marcador"):
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★ EL MARCADOR DE LA SERIE — `.score reset` (2026-09-14)
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   ⛔ EL AGUJERO, reportado por anonimo03: *"hay un contador en modo equipo que actualmente
        #     no reiniciamos ni de forma auto ni de forma manual"*. Sube con cada partida de
        #     equipo y **sólo se borra cuando la sala muere** ⇒ una sala que se queda abierta toda
        #     la tarde termina mostrando `7 - 5` de partidas que ya nadie recuerda, y la única
        #     forma de empezar de cero era cerrar la sala y volver a armarla.
        #
        #   ⚠ SÓLO EN SALAS DE EQUIPO. El marcador no existe en solo ni en cooperativo
        #     (`lobby_carrera` lo toca únicamente con `_es_equipo28`), así que ofrecer el comando
        #     ahí sería ofrecer algo que no hace nada.
        #   ⚠ Y sólo el master, como `.pd`: es el marcador de TODA la sala.
        _rid = getattr(st, "room_id", None)
        if not _rid:
            return ["no estas en una sala"]
        if not sala_por_equipos(st):
            return ["el marcador es solo de las salas por equipos"]
        _m1, _m2 = marcador_de(_rid)
        from .salas import texto_marcador
        if not args:
            return [texto_marcador(_rid), "uso: .reset score"]
        if args[0].lower() not in ("reset", "0", "cero", "reiniciar"):
            return [texto_marcador(_rid), "uso: .reset score"]
        _duenio = anfitrion_de(_rid)
        if _duenio is not None and _duenio != getattr(st, "usn", None):
            return ["solo el master de sala"]
        reiniciar_marcador(_rid)
        log("LOBBY", f"  ★★ .score reset: la sala {_rid} vuelve a 0 - 0 (venía {_m1} - {_m2}, "
                     f"lo puso usn={getattr(st, 'usn', None)}, el master)")
        # ⚠ A TODA la sala: el marcador es de todos, y el que no se entere va a ver el 0-0 en el
        #   próximo cartel sin saber por qué.
        avisar_a_la_sala(_rid, texto_marcador(_rid))
        return []

    if c == "pd":
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★ «PD VALOFE» — LA TABLA DE PUNTAJE DE LA SALA (2026-09-14)
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   Pedido de anonimo03, textual: *"pd valofe por default al crear la sala, master de sala con
        #   comando prende o apaga pd valofe para todos los jugadores de la sala"*.
        #
        #   El R2Beat moderno puntúa cada nota un escalón más arriba que el de 2013 (el análisis
        #   completo, con la escala leída del binario, está en `TOOLBIT_PD_VALOFE.md`). Acá se
        #   elige con cuál de las dos juega la sala.
        #
        #   ⚠⚠ ESTO NO ES "MEDIR MEJOR", ES SUMAR MÁS: el número de precisión sube. Por eso lo
        #     decide el anfitrión para TODOS y no cada uno para sí: el cartel del final pone los
        #     números uno al lado del otro y el ranking los ordena. Dos escalas mezcladas en la
        #     misma sala serían peras y manzanas en la pantalla de todos.
        #
        #   ⚠ EL AVISO VA A TODA LA SALA, no sólo al que escribió. Es una regla que le cambia el
        #     puntaje a los demás: enterarse recién al ver el número raro sería feo.
        #   ⚠ Y LA RESPUESTA VA CORTA, como el `.oscuro`: es el chat del juego, no un manual.
        #
        #   ⛔ ANTES `.pd` ERA OTRA COSA: la perilla de GM que inventaba milésimas para probar el
        #     cartel. Sigue existiendo, ahora en `.milesimas` / `.decimales` (que ya eran alias
        #     suyos, así que no se perdió nada). `.pd` pasó a ser esto porque es lo que anonimo03
        #     escribe y lo que el anfitrión de una sala espera que haga.
        _rid = getattr(st, "room_id", None)
        if not _rid:
            return ["no estas en una sala"]
        if not args:
            return ["PD Valofe" if pd_valofe_de(_rid) else "PD Normal"]
        _a = args[0].lower()
        if _a not in ("on", "off", "si", "no", "1", "0"):
            return ["uso: .pd on | .pd off"]
        _duenio = anfitrion_de(_rid)
        if _duenio is not None and _duenio != getattr(st, "usn", None):
            return ["solo el anfitrion"]
        _on = _a in ("on", "si", "1")
        poner_pd_valofe(_rid, _on)
        _txt = "PD Valofe" if _on else "PD Normal"
        log("LOBBY", f"  ★★ .pd: la sala {_rid} juega con {_txt} "
                     f"(lo puso usn={getattr(st, 'usn', None)}, el anfitrion)")
        avisar_a_la_sala(_rid, _txt)
        return []                       # ★ ya lo dijo `avisar_a_la_sala`; no repetirlo al que escribió

    if c in ("milesimas", "decimales"):
        # ★★ LA PERILLA DE PRUEBA DE LAS MILÉSIMAS. Existe por un huevo y gallina: el parche del
        #   cliente (que dibuja `94532`) sólo se puede comprobar si el server manda milésimas, y
        #   el server sólo las manda si el cliente se las dio — y ese pedazo del parche todavía
        #   no está. Con esto el server las inventa **para el que lo escribe**, una sola vez.
        #   ⚠ No toca a nadie más: se guarda en la conexión, no en un global.
        if not args:
            _a = getattr(st, "milesimas_forzadas", None)
            return [f"milesimas forzadas: {_a if _a else 'no (las manda el cliente, o 0)'}",
                    "uso: .pd 532 | .pd off     (se ve al terminar la proxima cancion)"]
        if args[0].lower() in ("off", "no"):
            st.milesimas_forzadas = 0
            return ["milesimas forzadas APAGADAS"]
        _n = int(args[0]) if args[0].isdigit() else 0
        _n = max(0, min(_n, 999))
        st.milesimas_forzadas = _n
        return [f"milesimas forzadas a {_n} -> el cartel deberia decir <precision>{_n:03d}",
                "(con el parche del cliente puesto; sin el, el numero sale como siempre)"]

    if c in ("pulso", "latir"):
        # ★★★ EL LATIDO DE PROD, EN LOCAL. Reproduce el bug de "la lista se vuelve sola a la
        #   página 1" sin tener que probar en producción con 140 jugadores adentro.
        #
        #   POR QUÉ HACE FALTA: el empujón de lista no lo dispara nadie en particular — lo
        #   dispara que ALGUNA sala arranque o termine una canción (`marcar_sala_jugando`), y en
        #   prod eso pasa cada 3 segundos porque hay 25 salas. En local, con dos clientes, no pasa
        #   nunca. Sin este comando el bug es **irreproducible fuera de prod**, y probar ahí es
        #   justo lo que no queremos.
        #
        #   CÓMO SE USA, junto con `.salas`:
        #       .salas 30     -> 3 páginas (hacen falta >12 salas para que existan las pestañas)
        #       .pulso 40     -> 40 empujones, uno cada 2 s
        #       ...y ahora andá a la lista, tocá la pestaña 2 y NO toques nada.
        #
        #   ⚠ Es una herramienta de prueba: NO se sube a prod prendida. No hace falta apagarla a
        #     mano (se apaga sola al llegar a N), pero `.pulso off` la corta.
        if not args:
            return [f"pulso: {'ANDANDO' if _PULSO.get('vivo') else 'apagado'}"
                    f" - uso: .pulso N [segundos] | .pulso off",
                    "reproduce el empujon de lista de prod (que en local no pasa solo)"]
        if args[0].lower() in ("off", "no", "0"):
            _PULSO["vivo"] = False
            return ["pulso apagado"]
        _n   = int(args[0]) if args[0].isdigit() else 20
        _seg = float(args[1]) if len(args) > 1 else 2.0
        if _PULSO.get("vivo"):
            return ["ya hay un pulso andando - `.pulso off` primero"]

        def _latir(n, seg):
            # ⛔ El hilo comprueba la bandera ANTES de cada empujón, no sólo al principio: si no,
            #   `.pulso off` no lo cortaba hasta que terminara la cuenta y quedaba latiendo solo.
            _PULSO["vivo"] = True
            try:
                for i in range(n):
                    if not _PULSO.get("vivo"):
                        log("SALA", f"  ★ pulso cortado a mano en el {i} de {n}")
                        return
                    time.sleep(seg)
                    if not _PULSO.get("vivo"):
                        return
                    log("SALA", f"  ★ PULSO {i + 1}/{n}: empujo la lista sin que nadie la pida "
                                f"(esto es lo que en prod pasa cada ~3 s)")
                    difundir_roomlist()
            finally:
                _PULSO["vivo"] = False

        threading.Thread(target=_latir, args=(_n, _seg), daemon=True, name="pulso").start()
        return [f"pulso: {_n} empujones, uno cada {_seg:g}s ({_n * _seg:.0f}s en total)",
                "andá a la lista, tocá la pestaña 2 y NO toques nada"]

    if c in ("obs", "observar", "espectador"):
        # ★★★ SONDA DEL MODO ESPECTADOR (2026-09-07). Ver el bloque de investigación en
        #   `documentacion/` — acá sólo el banco de pruebas.
        #
        #   LO QUE SE SABE, y es lo que hace falta para probar:
        #     · el botón de la sala manda `FF99` con el cuerpo VACÍO (medido en el log del usuario)
        #     · `FF99` = `CmdChangeObserverMode` y `FFBB` = `CmdUpdateMassObservers`, leídos del
        #       cliente moderno, que está simbolizado
        #     · el `FF99` S→C ya lo usamos para pintar equipos, con 5 bytes:
        #           [tipo][slotA][slotB][aux][equipo]
        #       y usamos **tipo 0**. Los neutros son `slotA=0xFF` (no toca otro asiento) y
        #       `equipo=0xFF` (no asigna equipo). Ver `salas.enviar_equipos`.
        #
        #   ⇒ La apuesta es que OTRO valor de `tipo` sea "pasá a observador". No hay con qué
        #     saberlo desde el binario (el disasm de esta zona no alinea) ni desde las capturas
        #     (hay UNA sola muestra del FF99 en todo el corpus, y sin respuesta). Así que se prueba
        #     en pantalla, que es lo que resolvió el ícono de licencia.
        _rid = getattr(st, "room_id", None)
        _mi = getattr(st, "room_slot", None)
        if _mi is None:
            _mi = 0
        if not args:
            return ["★ .obs ir          <- LOS DOS PASOS DE UNA (lo mas probable)",
                    "  .obs bb [n]      solo la bandera de espectadores",
                    "  .obs N           FF99 tipo=N sobre tu asiento",
                    "  .obs N a b c d   los 5 bytes crudos",
                    f"tu asiento={_mi} · el tipo 0 es el que ya usamos para pintar equipos"]
        if args[0].lower() in ("bb", "lista"):
            # ★★★ `FFBB` = `CmdUpdateMassObservers`, handler REAL `0x5D7EC0` (sacado con
            #   `taller/re2013/tabla_rx.py`, NO de la tabla vieja, que está envenenada). Son 10
            #   instrucciones y no dejan lugar a dudas:
            #       push 4 ; call read        -> lee UN u32
            #       cmp dword, 0 / jbe salir  -> si es 0, no hace NADA
            #       mov byte [cRoom+0xC1C], 1 -> si es > 0, PRENDE la bandera de espectadores
            #   ⛔ La primera versión de esta sonda lo mandaba VACÍO. Por eso "no hacía nada":
            #     el paquete no traía el número que el handler exige.
            _n = 1
            if len(args) > 1:
                try:
                    _n = int(args[1], 0)
                except ValueError:
                    return ["uso: .obs bb [cuantos]   (por defecto 1)"]
            st.send_ff55(0xBB, struct.pack("<I", _n & 0xFFFFFFFF),
                         name=f"FFBB espectadores={_n}")
            return [f"FFBB con {_n} - mira si aparece la seccion de espectadores"]
        if args[0].lower() in ("ir", "ya", "todo"):
            # ★ LOS DOS PASOS DE UNA, que es lo que el usuario pidió: *"los comandos se me
            #   hicieron un poco dificiles"*. Primero el FF99 que lo saca del asiento (el tipo 1
            #   ya lo logró en pantalla) y después el FFBB que prende la sección.
            _c1 = bytes([1, 0xFF, _mi & 0xFF, 0, 0xFF])
            st.send_ff55(0x99, _c1, name=f"FF99 a espectador {_c1.hex()}")
            st.send_ff55(0xBB, struct.pack("<I", 1), name="FFBB espectadores=1")
            return [f"mandado: FF99 {_c1.hex(' ')} + FFBB 1",
                    "mira si ahora SI aparecés en la seccion de espectadores"]
        try:
            _n = [int(x, 0) & 0xFF for x in args]
        except ValueError:
            return ["los valores tienen que ser numeros - .obs 1 | .obs 1 255 2 255 255"]
        if len(_n) == 1:
            #   [tipo][slotA=FF neutro][slotB=mi asiento][aux=FF][equipo=FF neutro]
            cuerpo = bytes([_n[0], 0xFF, _mi & 0xFF, 0xFF, 0xFF])
        else:
            cuerpo = bytes((_n + [0xFF] * 5)[:5])
        st.send_ff55(0x99, cuerpo, name=f"FF99 sonda observador {cuerpo.hex()}")
        return [f"FF99 -> {cuerpo.hex(' ')}",
                "mirá la pantalla: ¿te movió a espectadores?"]

    if c in ("oscuro", "abismo"):
        # ★★ EL MAPA DE LA SALA, que elige el ANFITRIÓN y reciben TODOS (2026-09-07).
        #   Se distingue del `.map` en tres cosas, y por eso son dos comandos y no uno:
        #     · `.map`     = sonda de UNA conexión, para probar. Pisa hasta esto. No se comparte.
        #     · `.oscuro`  = decisión de LA SALA. La toma el dueño y la juegan todos.
        #   ⏳ Pendiente elegido por el usuario: que un invitado se lo ponga sólo para él. Hoy el
        #     `FF25` se arma una vez para toda la sala; hacerlo por jugador es otro cambio.
        #   ⚠ LA RESPUESTA VA CORTA — UNA LÍNEA. Es el chat del juego, no un manual: el usuario lo
        #     vio en pantalla y pidió *"seria algo 'Server: mapa oscuro' suficiente"*. Lo que hay
        #     que explicar se explica acá arriba, que es donde lo lee quien mantiene esto.
        _rid = getattr(st, "room_id", None)
        if not _rid:
            return ["no estas en una sala"]
        _duenio = anfitrion_de(_rid)
        if _duenio is not None and _duenio != getattr(st, "usn", None):
            return ["solo el anfitrion"]
        if args and args[0].lower() in ("off", "no", "auto", "quitar"):
            poner_mapa_sala(_rid, None)
            return ["mapa automatico"]
        _mp = MAPA_OSCURO
        if args:
            if not args[0].isdigit():
                return ["uso: .oscuro | .oscuro N | .oscuro off"]
            _mp = int(args[0])
        # ⚠ Se valida contra lo que el cliente TIENE. Mandarle un stage que no existe es el mismo
        #   error que con las canciones fantasma, y ése terminaba en crash. Ver OWNED_STAGES_2013.
        if _mp not in OWNED_STAGES_2013:
            return [f"mapa {_mp} no disponible"]
        poner_mapa_sala(_rid, _mp)
        return ["mapa oscuro" if _mp == MAPA_OSCURO else f"mapa {_mp}"]

    if c in ("obstaculos", "obstaculo"):
        # ★★ LOS OBSTÁCULOS DE CADA UNO (2026-10-08): corre la pista de la sala con los obstáculos de OTRA.
        #   Lo elige CADA jugador para sí (no el anfitrión para todos): anonimo03, 08-oct. Si no elige, corre con
        #   los del anfitrión; y lo que eligió vence cuando se va de la sala. Ver `salas.ELECCION_JUGADOR`.
        #   ⏳ Es la etapa 2 (para probar): después se elige en la sala, con su recuadro y su ventana.
        #   ⚠ RESPUESTA CORTA, como `.oscuro`: es el chat del juego.
        _rid = getattr(st, "room_id", None)
        _usn = getattr(st, "usn", None)
        if not _rid:
            return ["no estas en una sala"]
        if not args:
            _v = obstaculos_para(_rid, _usn)
            return [f"obstaculos de la pista {_v}" if _v else "obstaculos de la pista", "uso: .obstaculos N | .obstaculos off"]
        if args[0].lower() in ("off", "no", "auto", "quitar"):
            poner_eleccion(_rid, _usn, "obstaculos", None)
            _v = obstaculos_para(_rid, _usn)
            return [f"obstaculos del anfitrion ({_v})" if _v else "obstaculos de la pista"]
        if not args[0].isdigit():
            return ["uso: .obstaculos N | .obstaculos off"]
        _n = int(args[0])
        # ⚠ Sólo las pistas que traen su `backNNN.txt` en el cliente (contadas): un archivo que no existe es
        #   el mismo error que una canción fantasma.
        if _n not in OBSTACULOS_2013:
            return [f"la pista {_n} no tiene obstaculos"]
        poner_eleccion(_rid, _usn, "obstaculos", _n)
        log("LOBBY", f"  ★ .obstaculos: usn={_usn} corre con los obstáculos de la pista {_n} (sala {_rid})")
        return [f"obstaculos de la pista {_n}"]

    if c in ("lic", "licencia", "sonda"):
        # ★★★ BANCO DE PRUEBAS DEL ICONO DE LICENCIA (2026-09-07). Ver `salas.SONDA_FF0C`.
        #   No arregla nada: pisa un campo del FF0C y re-emite la lista para MIRAR LA PANTALLA.
        #   Existe porque ya se descartaron tres candidatos por calce de valores, y la lección fue
        #   que el calce no prueba nada: hay que ver el icono cambiar. Con esto cada intento cuesta
        #   un mensaje de chat en vez de un reinicio del server.
        if not args:
            # ⚠ Mismo alias que los otros bloques: el `from .basedatos import db_get_char` que hay
            #   dentro de esta función vuelve `db_get_char` LOCAL a toda `comando_chat`, así que
            #   acá el import de arriba del archivo no se ve y esto reventaba con
            #   `UnboundLocalError`. Encontrado al agregar la sonda de la campana (2026-09-15):
            #   `.lic` sin argumentos no llegaba a contestar nunca.
            from .basedatos import db_get_char as _gc_lic
            _c0 = _gc_lic(getattr(st, "usn", 0)) or {}
            _lic0 = int(_c0.get("licencia", 0) or 0)
            _nom = {0: "sin licencia", 1: "Estrella", 3: "Luna", 7: "Sol"}.get(_lic0, f"licencia {_lic0}")
            _r4 = mision_para_icono({"licencia": _lic0, "mision": int(_c0.get("mission", 0) or 0),
                                     "mision_nibbles": _c0.get("mision_nibbles")})
            return [f"vos: licencia={_lic0} ({_nom})",
                    f"se manda: rel4=0x{_r4:04X} (grupo 0x{grupo_de_licencia(_lic0):04X}) · rel6={_lic0}",
                    f"sonda manual: {SONDA_FF0C or 'vacia (todo normal)'}",
                    "uso: .lic mision 0x100 | .lic licencia 3 | .lic off"]
        if args[0].lower() in ("off", "no", "limpiar"):
            SONDA_FF0C.clear()
            _rid = getattr(st, "room_id", None)
            difundir_userlist(_rid) if _rid else enviar_userlist(st)
            return ["sonda LIMPIA - se re-emitio la lista con los valores de verdad"]
        if len(args) < 2:
            return ["falta el valor - uso: .lic mision 0x100"]
        _campo = args[0].lower()
        try:
            _val = int(args[1], 0)          # acepta 256 y 0x100 igual
        except ValueError:
            return [f"'{args[1]}' no es un numero (probá 0x100 o 256)"]
        SONDA_FF0C[_campo] = _val
        _rid = getattr(st, "room_id", None)
        if _rid:
            difundir_userlist(_rid)
        else:
            enviar_userlist(st)
        return [f"FF0C.{_campo} = {_val} (0x{_val:X}) - lista re-emitida",
                "mirá el icono del slot: si NO cambio, ese campo no lo dibuja"]

    if c in ("ayuda", "help", "?"):
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★★★ LA AYUDA MUESTRA LO QUE **VOS** PODÉS USAR, NO LA LISTA ENTERA (2026-09-15)
        # ═══════════════════════════════════════════════════════════════════════════════════════
        #   ⛔ EL PROBLEMA, señalado por anonimo03: `.ayuda` lo puede escribir cualquiera (está en
        #     `CONSOLA_SIN_GM`) y les escupía **los 20 comandos de desarrollo**. En prod esos
        #     comandos NI EXISTEN —los cierra `R2_CONSOLA_GM`— así que la ayuda le estaba
        #     ofreciendo al jugador cosas que no puede usar. Un menú lleno de botones muertos.
        #
        #   ★★ CÓMO SE EVITA QUE VUELVA A PASAR: cada línea se filtra con **`puede_usar_consola`**,
        #     que es **la misma función que decide si el comando corre**. No hay una segunda lista
        #     que mantener al día ⇒ la ayuda no puede mentir, ni por mostrar de más ni de menos.
        #     Dos copias de la misma regla es exactamente cómo se despegan (ver `registrar_sala`).
        #   ★ La tabla lleva NIVEL además del comando, y los dos filtran:
        #       · el PERMISO decide si podés correrlo  (`puede_usar_consola`, la función de verdad)
        #       · el NIVEL decide en qué sección se lista
        #     Hacen falta los dos porque no coinciden: `.pd` y `.score` los puede usar cualquiera
        #     (son del juego, se controlan solos con "sólo el anfitrión"), pero **al jugador común
        #     no se le listan** — anonimo03 pidió que su ayuda sea una línea. Siguen funcionando.
        _todo = [
            # (nivel, comando que lo habilita, línea)
            # ⚠ UNA línea para el jugador (pedido de anonimo03, lo vigila `probar_ayuda_y_gm`): el
            #   círculo (24-sep) va en la misma, no en otra
            ("jugador", "oscuro", "server: escribe .oscuro para mapa oscuro · .circulo ayuda para tu círculo"),
            ("--GM--", "--GM--", "--- solo GM (los de `gm.txt`) ---"),
            ("gm", "aviso",  ".aviso <texto>          anuncio a TODO el server (te dice a cuántos llegó)"),
            ("gm", "gm1",      ".gm1 / .gm2 / .gm3      el mismo aviso, en verde / amarillo / rojo"),
            ("gm", "tira",   ".tira [2h] <texto> | .tira | .tira quitar <id> | .tira vaciar   la TIRA de arriba del lobby, en vivo"),
            ("gm", "rate",    ".rate                   ver los multiplicadores (server, sala, efectivo)"),
            ("gm", "rate",    ".rate exp 2.0           doble experiencia para TODO el server"),
            ("gm", "rate",    ".rate coin 1.5          y lo mismo con las monedas"),
            ("gm", "rate",    ".rate sala exp 2.0      SOLO esta sala — se multiplica con el del server"),
            ("gm", "rate",    ".rate sala off          la sala vuelve a x1 (el del server sigue)"),
            ("gm", "rate",    ".rate off               todo el server vuelve a 1.0"),
            ("gm", "autoplay", ".autoplay [off]         tu personaje juega SOLO en la proxima carrera (99%)"),
            ("gm", "record", ".record | .record ganadas 199 | .record sonda | .record reset   medallas"),
            ("gm", "record", ".record cabeza 0|1|off   SONDA: la medalla arriba de la cabeza"),
            ("gm", "record", ".record anuncio 103      el aviso global de medalla, sólo a vos"),
            # ⚠ la gatea `record` (de GM) y no `circulo`, que abre para todos: la sonda pide GM por dentro
            ("gm", "record", ".circulo sonda [nombre] [a b c] | .circulo off   SONDA de la pestaña Círculo"),
            ("gm", "record", ".circulo eco [nivel|exp|dinero|marca N]   ver/editar la economia de tu circulo"),
            ("gm", "gm",    ".gm | .gm recargar      la puerta de GM"),
            ("gm", "campana", ".campana [sub] [tipo] [rcoin]   SONDA del cartel de la campana"),
            # ★ 04-oct: el STREAMER (`streamers.txt`) ve SÓLO sus dos. Al GM no se le listan: ya tiene los suyos
            ("--STREAMER--", "--STREAMER--", "--- streamer ---"),
            ("streamer", "anuncio", ".anuncio <texto>        aviso a TODO el server, por el chat"),
            ("streamer", "gm1",     ".gm1 <texto>            el cartel a TODO el server"),
            ("--DEV--", "--DEV--", "--- desarrollo (no existen en prod) ---"),
            ("dev", "npc",    ".npc N | .npc full | .npc off | .npc slots 3 4 5"),
            ("dev", "grupo",  ".grupo [alto]            (carrera en grupo: lleva a los de tu charla a una sala de 12 y larga sola; alto = los demás en 6..11)"),
            ("dev", "grande", ".grande 12 | .grande off   (carrera grande: 7..12 corredores, el 6vs6)"),
            ("dev", "carga",  ".carga charla 30 [estancia] | .carga estado | .carga parar | .carga ritmo lento|normal|rapido   (sala de charla)"),
            ("dev", "gorila", ".gorila N | .gorila off  (dar el gorila por ATRAPADO en la ronda N)"),
            ("dev", "monedas", ".monedas N [apodo]       (asigna Monedas Gorila; NO suma)"),
            ("dev", "map",    ".map N | .map off        (pista del proximo START)"),
            ("dev", "tema",   ".tema N | .tema off      (cancion del proximo START: el QA usa 7603 = Lavie)"),
            ("dev", "chase",  ".chase N | .chase off    (canciones del chase; 1 = partida corta)"),
            ("dev", "cartel", ".cartel | .cartel F | .cartel 85   (saca el cartel de resultado YA)"),
            ("dev", "salas",  ".salas N | .salas off    (salas de mentira, para probar la paginacion)"),
            ("dev", "mesas",  ".mesas | .mesas barrer | .mesas fantasma   (salas fantasma)"),
            ("dev", "pulso",  ".pulso N | .pulso off    (el empujon de lista de prod)"),
            ("dev", "pd",     ".pd on | .pd off       (tabla de puntaje de LA SALA, la fija el anfitrion)"),
            ("dev", "score",  ".score | .reset score  (el marcador de la serie, en salas por equipos)"),
            ("dev", "milesimas", ".milesimas 532 | off   (milesimas forzadas, para probar el cartel)"),
            ("dev", "lic",    ".lic formula | .lic off  (icono de licencia: la mascara por jugador)"),
            ("dev", "obs",    ".obs N | .obs bb         (sonda del modo ESPECTADOR)"),
        ]
        # ★ "¿soy dev?" se pregunta con un comando que SÓLO abre la 3ª puerta. No se mira
        #   `R2_CONSOLA_GM` acá: eso sería una segunda copia de la regla.
        _es_dev = puede_usar_consola(st, "npc")
        # ★ "¿soy GM?" igual: con un comando que abre SÓLO `gm.txt`. Separa las secciones: el streamer pasa la
        #   puerta de `.gm1` pero no tiene que ver la línea de GM «.gm1 / .gm2 / .gm3», que le ofrece dos que no puede
        _es_gm = puede_usar_consola(st, "rate")
        _lineas = []
        for _niv, _cmd, _txt in _todo:
            if _niv.startswith("--"):
                _lineas.append(("TITULO", _txt))
                continue
            if _niv == "dev" and not _es_dev:
                continue                      # ⚠ `.pd`/`.score` caen acá: se pueden usar, no se listan
            if (_niv == "gm" and not _es_gm) or (_niv == "streamer" and _es_gm):
                continue
            if puede_usar_consola(st, _cmd):
                _lineas.append(("linea", _txt))
        # ★ Un título sin nada debajo es ruido: si no quedó ninguna línea de esa sección, se cae.
        _out, _i = [], 0
        while _i < len(_lineas):
            _tipo, _txt = _lineas[_i]
            if _tipo == "TITULO" and (_i + 1 >= len(_lineas) or _lineas[_i + 1][0] == "TITULO"):
                _i += 1
                continue
            _out.append(_txt)
            _i += 1
        return _out or ["server: no tenés comandos disponibles"]

    return [f"comando desconocido: .{c} - probá .ayuda"]
