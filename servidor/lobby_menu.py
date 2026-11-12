# -*- coding: utf-8 -*-
"""lobby_menu — chat, perfil, MyRecord, amigos y el resto del menú.

Cada función es UNA rama del `handle_inner` original, movida tal cual.
El orden y las condiciones viven en `despacho.py`.
"""
import json
import os
import time
import struct

from .ajustes import (
    CHAT_CACHE_SEG,
    CIRCULOS,
    FF77_PAREJA,
    FF77_PAREJA_ANILLO,
    FORZAR_CANAL_LIBRE,
    HOST_SLOT,
    LIBRE_TIER_BYTE,
    MISION_PROGRESO,
    OWNED_SONGS_2013,
    PAREJA_REGISTRO_ANILLOS,
    REPLAY_MISIONES,
    SEND_FF49_LISTA,
    SEND_FFC9_LICENSE,
)
from .registro import (
    RESUMIR,
    hx,
    log,
)
from .gacha import registros_ff49, parts_visibles
from .basedatos import (
    db_char_por_nick,
    db_uids_por_nick,
    db_expire,
    db_get_char,
    db_load,
    db_save,
    db_save_uno,
    parse_create_char,
)
from .progresion import (
    char_para_banda,
    licencia_actual,
    nivel_de_exp,
)
from .misiones import (
    db_add_mision_por_mascara,
    db_create_char,
    replay_misiones,
)
from .myrecord import (
    enviar_myrecord,
    build_myrecord,
)
from .paquetes import (
    build_create_ack,
    build_ff49,
    build_ff77_myinfo,
    build_ff78_verinfo,
    build_ff81_progreso,
    inventario_para_ff49,
)
from .salas import (
    CONEXIONES,
    conexiones_en_sala,
    mesa_de,
)
from .lobby_social import (
    presencia_al_entrar,
)
from .tira import enviar_tira
from .chat import (
    a_ascii,
    comando_chat,
)


def _tiempo_hoy(st):
    """Los segundos conectados de hoy para el cartel de la Misión de hoy (va en el FF49 y en el FF03). Ver `mision_hoy`."""
    try:
        from .mision_hoy import segundos_hoy_de
        return segundos_hoy_de(getattr(st, "usn", 0))
    except Exception as _e_mh:                                       # noqa: BLE001
        log("LOBBY", f"  ⚠ misión de hoy (tiempo del FF49): {_e_mh!r}")
        return 0


def h_00_ff03(st, cmd, data):
    # rama original:  cmd == 3
    db_expire(getattr(st, "usn", 0))                                    # Fase B: quitar ítems temporales vencidos antes de armar
    # ★★ El FF49 va PRIMERO: dentro del handler del MyRecord hay un bounds-check contra
    #    `word[G+0x8C]`, que arranca en 0xFFFF y SOLO lo escribe el SelectByKey de este paquete.
    #    Si el MyRecord llega antes, el cliente se mata solo (0xC0000417). Ver build_ff49().
    if SEND_FF49_LISTA:
        _ch = db_get_char(getattr(st, "usn", 0)) or {}
        # ★★ 25-oct: el juego con SELECTOR (FFF6) va como una cuenta SIN personaje: ni FF49 ni ficha. MEDIDO: con
        #   la ficha vacía pero el FF49 lleno, el cliente igual cargó el personaje y fue a la bienvenida.
        from .cuenta_personajes import eligiendo
        if eligiendo(getattr(st, "usn", 0)):
            _ch = {}
        # ★★★ LA LISTA VA COMPLETA: el base + los personajes ganados en el gacha (2026-09-08).
        #   Antes iba UN registro (el base) y por eso el personaje del gacha no se podía poner:
        #   `0x487F40` no lo encontraba y devolvía el primero en silencio. Ver `gacha.registros_ff49`.
        _cid, _regs = registros_ff49(_ch)
        if _cid:
            st.send_ff55(0x49, build_ff49(_cid, _regs,
                                   inventario=inventario_para_ff49(getattr(st, "usn", 0)),
                                   canciones=OWNED_SONGS_2013, tiempo_hoy=_tiempo_hoy(st)),
                         name=f"FF49 lista de personajes + SelectByKey (puesto={_cid}, "
                              f"{len(_regs)} registro(s): {[k for k, _ in _regs]})")
        else:
            log("LOBBY", "  ⚠ FF49 NO enviado: el personaje no tiene char_id (key 0 = fila descartada)")
    # ★★★★★ SIN REGISTRO DE PERSONAJE SI YA FUE EL `FF49` — 2026-09-08, MEDIDO EN VIVO.
    #   ⛔ Con frida enganchado al cliente, la lista salía así:
    #         ids = [130900, 130030, 130900]      cantidad=3
    #     El `FF49` manda los 2 registros buenos (el base y el del gacha) y **este MyRecord agrega
    #     un tercero repitiendo el base**. El bucle de personajes del MyRecord sólo AGREGA; lo
    #     único que vacía el vector es el propio `FF49`.
    #   ⚠ Ya había tapado esto en los refrescos (`con_personaje=False`) y **me olvidé del arranque**,
    #     que es justo el que duplica. La medición lo mostró en la primera línea.
    #   ★ Va atado a `SEND_FF49_LISTA`: si algún día ese envío se apaga, este registro vuelve a ser
    #     necesario — es el único que llevaría el cuerpo.
    #   ⛔⛔ …Y SACARLO ROMPIÓ EL PADRÓN DEL GACHA. Medido el 2026-09-08, 23:48:
    #         buscar en el padron del gacha: id=130030 -> ★★★ NO ESTA (nulo)   (y 130031, y 130029)
    #     La pestaña «Personaje» se pobló por primera vez a las 21:43, cuando la lista de personajes
    #     viajaba en ESTE paquete. A las 23:19 le saqué el registro de personaje para matar el
    #     duplicado… y **desde ahí el cliente dejó de parsear la lista del gacha**, que va en la
    #     cola de este mismo paquete. Sin padrón, `0x46F3E0` devuelve nulo y el temporizador del
    #     agotamiento revienta a los 4 segundos.
    #   ⇒ Vuelve a mandarse ENTERO. El duplicado es feo pero **no crashea**; esto sí.
    #   ⏳ El duplicado se resuelve aparte (y bien): hay que entender por qué el registro de
    #     personaje y la lista de la cola están atados, en vez de sacarlo a ciegas como hice yo.
    enviar_myrecord(st, "MyRecord (FF03)", saldo=True)
    # ★★ 25-oct: el personaje RECIÉN ELEGIDO en el selector del juego vuelve a entrar desde la creación, y ahí el
    #   FFC9 lo mata (MEDIDO: 0x684107, el picker sin imagen). Se manda ya en el lobby (lobby_salas.h_08_ff6e).
    from .cuenta_personajes import recien_elegido
    if recien_elegido(getattr(st, "usn", 0)):
        st.ffc9_pendiente = True
        log("LOBBY", "  ★ FFC9 guardado para cuando esté en el lobby (FF6E): personaje recién elegido en el selector")
    else:
        enviar_ffc9_licencia(st)
    # ★★ LA LISTA DE AMIGOS, EMPUJADA (2026-09-10). El cliente **nunca pide** el `FF42`: medido
    #    en una sesión entera de prueba, 0 pedidos. Si no la empujamos acá, la ventana de amigos
    #    queda vacía para siempre aunque la base tenga las amistades bien guardadas.
    #    ★ Y al revés: avisarle a MIS amigos que YO entré, para que me vean conectado. Sin esto,
    #      el que ya estaba adentro me seguía viendo offline hasta que se reconectara.
    #    ⚠ Las dos cosas están adentro de `presencia_al_entrar`, que TAMBIÉN se llama desde el
    #      `FF06`: al cambiar de canal el cliente NO manda este `FF03` y el amigo quedaba
    #      desconectado para siempre. Es idempotente, así que llamarla dos veces no duplica nada.
    presencia_al_entrar(st, "al entrar")
    from .conjuntos import enviar_lista as _sets_al_entrar          # ★ 12-oct: los sets del armario
    _sets_al_entrar(st, "al entrar")
    from .preferidos import enviar_lista as _pref_al_entrar         # ★ 12-oct: «Mis preferidos» de la tienda
    _pref_al_entrar(st, "al entrar")
    # ★ La TIRA DE ANUNCIOS de arriba del lobby (FFBF, 29-sep). Detrás de la presencia: el lobby ya está.
    enviar_tira(st, "al entrar")
    if MISION_PROGRESO:
        # ★★ PROGRESO DE MISIONES: otorga las licencias cuya máscara está en {6,7,8}
        st.send_ff55(0x81, build_ff81_progreso(MISION_PROGRESO),
                     name=f"FF81 progreso de misión = {MISION_PROGRESO} (-> [player+0x335])")
    if REPLAY_MISIONES:
        # ⛔⛔ 29-sep: acá decía `replay_misiones(st)`, SIN la cuenta ⇒ buscaba las misiones del usn 0,
        #   que no existe, y no mandaba nada. Desde que la base es por cuenta, NINGÚN login restauró
        #   las misiones: volvían a «Reto» en cada entrada. Es el mismo `0` del premio (mapeo_misiones §9).
        replay_misiones(st, getattr(st, "usn", 0))
    # ★ 15-oct: la MISIÓN DE HOY (el FF117 lo empuja el server: el cliente nunca lo pide). Ver `mision_hoy.py`.
    try:
        from . import mision_hoy
        mision_hoy.al_entrar(st)
    except Exception as _e_mh:                                       # noqa: BLE001
        log("LOBBY", f"  ⚠ misión de hoy al entrar: {_e_mh!r}")



def enviar_ffc9_licencia(st):
    """El `FFC9` con el tier del jugador: el ícono y el nombre de licencia del lobby.

    ★★★★★ POR QUÉ ESTÁ SUELTO — LA INTERFAZ MUERTA AL CAMBIAR DE CANAL (2026-09-10).

      anonimo03: *"me quedé sin poder interactuar con la interface"* al pasarse a «Libre». Comparando
      las DOS conexiones de la misma sesión, paquete por paquete, sale una sola diferencia en lo
      que manda EL SERVER por su cuenta:

          login de verdad  ->  FF49 · FF03 · **FFC9** · …
          cambio de canal  ->  FF49 · FF03 ·  ——      · …

      El resto de los huecos (`FF1D`, `FF1C`, `FF45`, `FF54`) son cosas que **el cliente no pidió**;
      el `FFC9` es el único que sale de nosotros. Y vivía DENTRO del handler del `FF03` — que en
      un cambio de canal **no corre**, porque ahí el cliente pide `FF49` y nunca `FF03`.

    ⚠ Esto NO lo causó ningún cambio de hoy: el `FFC9` nunca salió por ese camino. Lo que hizo
      falta fue mirar las dos conexiones al lado.
    ⏳ Y sigue siendo una HIPÓTESIS de la causa: es el único paquete que falta, pero que su
      ausencia sea lo que mata la interfaz no está comprobado en el exe. Se prueba jugando.
    """
    if not SEND_FFC9_LICENSE:
        return
    # ★ 2026-07-30: la licencia YA NO ES FIJA — sale del NIVEL, con la misma tabla del exe que
    #   usa el muro de canal (BANDAS_LICENCIA). Así el ícono/nombre de licencia y el canal al
    #   que te manda el matcher no pueden contradecirse.
    _nivel = nivel_de_exp(int(char_para_banda(getattr(st, "usn", 0)).get("exp", 0)))   # ★ sin char = la plantilla
    _clave, _tier, _lic = licencia_actual(getattr(st, "usn", 0))
    if FORZAR_CANAL_LIBRE or getattr(st, "libre", False):
        _clave, _tier = "all (LIBRE)", LIBRE_TIER_BYTE
    st.send_ff55(0xC9, bytes([_tier & 0xFF]),
                 name=f"FFC9 licencia/tier byte={_tier} (nivel {_nivel} -> banda {_clave!r}, @19={_lic})")


def h_01_ff04(st, cmd, data):
    # rama original:  cmd == 4
    try:
        char = parse_create_char(data)

        # ═══════════════════════════════════════════════════════════════════════════════════════
        # ★★★ EL APODO TIENE QUE SER ÚNICO — 2026-09-10
        # ═══════════════════════════════════════════════════════════════════════════════════════
        # Hasta hoy esto NO se chequeaba, y el esquema tampoco lo impone (`nickname TEXT NOT NULL`,
        # sin `UNIQUE`). Resultado medido sobre los 4807 personajes de la base:
        #       **203 apodos repetidos → 483 cuentas (el 10 %)**
        #       `jugador40` ×18 · `jugador9` ×8 · `jugador7` ×8 · `asdasd` ×6
        #
        # ⚠⚠ POR QUÉ IMPORTA Y NO ES COSMÉTICO: el cliente identifica a la gente **por el apodo**.
        #    En una solicitud de amistad el `uid` llega en CERO (medido en prod) y el nick es lo
        #    único que viaja. Con apodos repetidos, "mandale una solicitud a jugador40" **le llega a
        #    uno cualquiera de los dieciocho**, y no falla: le escribe a otra persona, en silencio.
        #    Lo mismo va a pasar con el susurro, la pareja y el círculo.
        #
        # ★ LA RESPUESTA ES NATIVA, no inventada. El handler del cliente (`0x5E71D0`) mira el
        #   `status` del ack y tiene DOS ramas de error, cada una con su cartel:
        #       status ==  0  -> texto #62 = "El sobrenombre ya ha sido\nregistrado antes."  ← ésta
        #       status == -1  -> texto #91 = "¡Usaremos un lenguaje respetuoso!"  (groserías)
        #       cualquier otro-> éxito
        #   ⇒ Con `status=0` el jugador ve el cartel correcto, **ya traducido al español**, y la
        #     pantalla lo deja elegir otro nombre. Cero parches de cliente.
        #
        # ⚠ La comparación es la de SQLite (`lower()`), que es **sólo ASCII**: `jugador37` y `BAÑATE`
        #   se seguirían considerando distintos. Hay UN solo apodo con acento en toda la base, así
        #   que no se resuelve hoy; queda dicho para que nadie lo descubra de nuevo.
        # ⛔ Esto NO toca los 203 repetidos que YA existen: sólo corta la sangría. Qué hacer con
        #    los viejos lo decide anonimo03 (renombrarlos no es gratis).
        _nick_nuevo = (char.get("nick", "") or "").strip()
        _duenos = [u for u in db_uids_por_nick(_nick_nuevo) if u != getattr(st, "usn", 0)]
        if _duenos:
            st.send_ff55(0x04, build_create_ack(char, status=0),
                         name=f"CREATE rechazado: el apodo {_nick_nuevo!r} ya existe")
            log("LOBBY", f"  ⛔ CREATE_CHAR RECHAZADO: el apodo {_nick_nuevo!r} ya lo usa "
                         f"{'la cuenta' if len(_duenos) == 1 else 'las cuentas'} {_duenos[:5]}"
                         f"{' …' if len(_duenos) > 5 else ''} -> status=0 (cartel #62)")
            return

        db_create_char(st.usn, char)
        # ★ 11-oct: el cliente abre «¿Quién te invitó?» con este ack (`0x5E71D0`): se anota que puede contestar.
        from .referido import al_crear as _referido_al_crear
        _referido_al_crear(st.usn)
        # ★ 11-oct: el SET BÁSICO que eligió (las 4 puestas), guardado YA: al cambiarse se perdía para siempre.
        from .catalogo import asegurar_basico as _asegurar_basico
        _asegurar_basico(st.usn)
        st.send_ff55(0x04, build_create_ack(char), name=f"CREATE ack ({char['nick']!r} +{len(char['parts'])} parts)")
        log("LOBBY", f"  ★ CREATE_CHAR OK: {char}")
        # ★ EMPUJAR FF136 status=0 proactivamente: el cliente encola su propio FF136 pero no lo
        # vacia (se cuelga). Su handler RX 0x5CEF70 procesa un FF136 ENTRANTE igual -> status=0 =
        # exito -> dispara la reconexion ("pequeño loading" -> lobby con el char).
        st.send_ff55(0x136, b"\x00", name="FF136 push status=0 (avanzar/reconectar)")
    except Exception as e:
        log("LOBBY", f"  CREATE_CHAR parse err: {e!r} data={hx(data)}")


def h_02_ff136(st, cmd, data):
    # rama original:  cmd == 310
    # Handler cliente 0x5CEF70: status 1-7 = ERROR (dialogo); status=0 = EXITO (avanza a bienvenida).
    st.send_ff55(0x136, b"\x00", name="FF136 enter-game OK (status=0)")
    log("LOBBY", "  ★ FF136 -> status=0 (avanzar a bienvenida)")


_DURACIONES_FF8C = None


def duraciones_ff8c():
    """Las 112 duraciones de las animaciones de tropezar (`tablas-cliente/duraciones_tropiezo.json`).
    `[]` si no está la tabla — y entonces sale n = 0, como antes. Ver `FF8C_DURACIONES`."""
    global _DURACIONES_FF8C
    if _DURACIONES_FF8C is None:
        from .ajustes import _DIR_SERVIDOR
        try:
            with open(os.path.join(_DIR_SERVIDOR, "tablas-cliente", "duraciones_tropiezo.json"),
                      encoding="utf-8") as f:
                _DURACIONES_FF8C = [float(v) for _n, v in json.load(f)["duraciones"]]
        except Exception as e:                                       # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude leer duraciones_tropiezo.json ({e!r}): el FF8C va vacío "
                         f"y el cliente va a mandar FF3D para siempre")
            _DURACIONES_FF8C = []
    return _DURACIONES_FF8C


def armar_ff8c():
    """`[u8 n] n × [f32]` (handler `0x5E9E00`). Ver `FF8C_DURACIONES` en `ajustes.py`."""
    from .ajustes import FF8C_DURACIONES
    _d = duraciones_ff8c() if FF8C_DURACIONES else []
    return bytes([len(_d) & 0xFF]) + b"".join(struct.pack("<f", v) for v in _d)


def h_03_ff8c(st, cmd, data):
    # rama original:  cmd == 140
    # ★ Las 112 duraciones del anti-trampa de las animaciones: con n = 0 el cliente mandaba FF3D
    #   para siempre (y 1 de cada 10, uno por cuadro). Ver `FF8C_DURACIONES`.
    _p = armar_ff8c()
    st.send_ff55(0x8C, _p, name=f"FF8C {_p[0]} duraciones de tropiezo")


def h_04_ff97(st, cmd, data):
    # rama original:  cmd == 151
    # ★★★★★ FF97 lleva UNA CADENA, no un ack vacío (2026-09-05).
    #   Layout: `[len:u8][ascii]`. Lo que va adentro sale de la **captura** de un server que
    #   funciona, y ahí es un timestamp de 14 caracteres.
    #   ⚠ Ese server **no es la verdad**: está lleno de code caves y sólo sirve como referencia de
    #     lo que el cliente ACEPTA. Lo que acá se copia es la FORMA (`[len][ascii]`, no vacío);
    #     que el contenido sea la hora es su elección, y podría ser cualquier texto.
    #   Capturado dos veces, con 8 segundos de diferencia, y se ve el reloj correr:
    #       14:45:07  0e 32 30 32 36 30 39 30 32 31 33 34 35 30 35   = "20260902134505"
    #       14:45:15  0e 32 30 32 36 30 39 30 32 31 33 34 35 31 33   = "20260902134513"
    #   Nosotros contestábamos `00` = **cadena vacía**. El cliente pide esto cada pocos segundos.
    #
    #   ⏳ Es una PRUEBA contra el diluvio de `FF3D`, no una certeza. La pista viene del proyecto
    #   del cliente Latino 2012, que midió el mecanismo: *"sin respuesta -> vence el watchdog ->
    #   FF9E (telemetría, NO crash) + FF3D -> cartel 'no se puede conectar'"*. Una respuesta vacía
    #   puede contar como "sin respuesta" para lo que sea que el cliente arma con esta cadena
    #   (el `ticker.tga` aparece en su log de texturas). Si el diluvio no baja, esto igual queda:
    #   mandar la hora es más correcto que mandar vacío.
    _ts = time.strftime("%Y%m%d%H%M%S").encode("ascii")
    st.send_ff55(0x97, bytes([len(_ts)]) + _ts,
                 name=f"FF97 Notice = hora del server {_ts.decode()}")


def _uid_del_ff77(st, nick, otro):
    """El uid del personaje que el `FF77` está mostrando.

    ⛔ NO se saca de `db_char_por_nick`: **ese registro no trae el uid**. Ya está anotado en
      `basedatos.py` y costó un `KeyError('uid')` en su momento — por eso existe
      `db_uids_por_nick`, que es la función que sí lo devuelve. Ver [[no-deducir-de-un-nombre]].

    ⚠ El apodo NO es único (203 repetidos sobre 4807). Se elige **al que está conectado**, la
      misma regla que ya usan la propuesta de pareja y las solicitudes de amistad: si no, la
      ficha podría traer la pareja de un homónimo.
    """
    if not otro:
        return int(getattr(st, "usn", 0) or 0)        # «mi info»: el pedido es mi propio apodo
    _uids = [int(u) for u in (db_uids_por_nick(nick) or [])]
    if not _uids:
        return 0
    return next((u for u in _uids if CONEXIONES.get(u) is not None), _uids[0])


def _pareja_para_ff77(uid):
    """Lo que necesita `build_ff77_myinfo` para dibujar el mini char de la pareja, o `None`.

    ★★ Devuelve `None` —y el bloque no se manda— en cuanto falte algo. Un bloque a medias es
      peor que ninguno: las seis ranuras pasan por el resolver de avatar del cliente y un valor
      que no sea prenda base **lo cierra**.

    ⚠ La FECHA se arma con `lobby_pareja._fecha7`, que es el **único** sitio del proyecto donde
      se construye ese bloque de 7 bytes. No se replica acá: es *"el campo que más veces se
      equivocó el proyecto"* y una segunda copia es una segunda oportunidad de equivocarlo.
    """
    if not FF77_PAREJA or not uid:
        return None
    try:
        from .basedatos import db_anillos_de, db_pareja_de
        from .gacha import parts_visibles as _pv
        from .lobby_pareja import _fecha7                          # noqa: SLF001
        _pj = db_pareja_de(int(uid))
        if not _pj:
            return None                                            # soltero: el flag queda en 0
        _ch = db_get_char(int(_pj)) or {}
        if not _ch:
            # ⚠ Casado con un uid que ya no tiene personaje. Pasa con cuentas borradas a mano.
            log("LOBBY", f"  ⚠ FF77: uid={uid} figura casado con {_pj}, que no tiene personaje")
            return None
        # ★ La fecha sale de la fila VIVA de `anillos` (la del casamiento vigente). Si no hay
        #   fila —parejas hechas antes de que existiera esa tabla— van 7 ceros, que es lo que
        #   el cliente espera para *"esta fecha no aplica"*. No se inventa un 1/1/1970.
        _viva = next((f for f in (db_anillos_de(int(uid)) or [])
                      if f.get("estado") == 1 and int(f.get("partner_uid") or 0) == int(_pj)), None)
        from .basedatos import db_anillo_de_pareja, db_confesion_de
        return {"anillo":  int(db_anillo_de_pareja(int(uid)) or 0) if FF77_PAREJA_ANILLO else 0,
                "nick":    str(_ch.get("nick", "") or ""),
                # ★ 27-sep: «Mi confesión» es la del DUEÑO del perfil (la escribe él en su ventana
                #   «Mi Pareja»), y la licencia es la de la PAREJA (va junto a su nick).
                "confesion": db_confesion_de(int(uid)),
                "nivel":     nivel_de_exp(int(_ch.get("exp") or 0)),
                "licencia":  int(_ch.get("licencia") or 0),
                "char_id": int(_ch.get("char_id") or 0),
                "partes":  _pv(_ch),
                "fecha":   _fecha7(_viva.get("desde") if _viva else 0)}
    except Exception as e:                                         # noqa: BLE001
        # ⚠ Nunca se cae el panel entero por el adorno de la pareja: sin bloque, «mi info» sale
        #   igual que ayer. Es el mismo criterio que el resto de los adornos del proyecto.
        log("LOBBY", f"  ⛔ FF77: no pude armar el mini char de la pareja de uid={uid}: {e!r}")
        return None


def h_05_ff77(st, cmd, data):
    # rama original:  cmd == 119
    # subtipo==1 -> camino CORTO 0x5e9fe2 (no lee mas bytes, llama UI(0), ret) = SEGURO.
    # subtipo!=0..1 (ej 0) -> bloque GRANDE de 49 campos (u32/u8/strings/3 subbloques por flag);
    # mandar mal el largo = desync/crash. Por ahora respondemos SEGURO (subtipo=1); el bloque
    # completo con datos reales (nivel/coin cruzados con el MyRecord) = siguiente iteracion.
    # ★★★ 2026-09-02 — SE MANDA EL RÉCORD DE VERDAD (subtipo 0), no el byte suelto.
    #   El `\x01` era un stub puesto cuando no se conocía el layout: el cliente tomaba el
    #   camino corto y dibujaba el mini char por defecto, **sin la ropa ni las alas**.
    #   Ahora se arma con `build_ff77_myinfo`, calcado byte a byte de un server que
    #   funciona (ver documentacion/FF77_MYINFO.md). Verificado: con los mismos datos
    #   sale IDÉNTICO a los dos paquetes capturados, el de 119 B y el de 123 B.
    # ★★ EL PEDIDO TRAE EL APODO DEL QUE SE QUIERE MIRAR — arreglado el 2026-09-10.
    #   Estaba anotado como pendiente desde el 02-sep: *"mirar la ficha de OTRO todavía devuelve
    #   la propia"*. Nadie lo notaba porque el único camino que llegaba acá era «mi info».
    #   Lo destapó AMIGOS: anonimo03 tocó «ver info» de un amigo y **le salió su propio perfil**.
    #   ⇒ Si el apodo que piden es de otro y existe, se contesta CON ESE personaje.
    #   ⚠ Si no existe, se cae al propio a propósito: es el caso de «mi info», donde el cliente
    #     manda su mismo apodo. Mostrar un panel vacío ahí sería peor que mostrar lo de uno.
    _nick77 = data[1:1 + data[0]].decode("cp1252", "replace") if data else ""
    _otro77 = db_char_por_nick(_nick77) if _nick77 else None
    _ch77 = _otro77 or db_get_char(getattr(st, "usn", 0)) or {}
    _cid77 = int(_ch77.get("char_id") or 0)
    if not _cid77:
        # Sin personaje no hay nada que dibujar, y un récord con char_id 0 deja el mini
        # char roto: el camino corto de siempre es la salida segura.
        st.send_ff55(0x77, b"\x01", name="MyInfo subtipo=1 (sin personaje: camino corto)")
        return
    # ★★★★★ Y EL MINI CHAR DE LA PAREJA AL LADO (2026-09-15, pedido de anonimo03). Era nativo: el
    #   bloque estaba entero en el cliente y nosotros mandábamos su flag en cero.
    #   ⚠ La pareja que se muestra es la **del personaje que se está mirando**, no la mía: si
    #     abro la ficha de otro, tiene que salir la pareja de ÉL. Por eso el uid se resuelve del
    #     mismo lado del que salió `_ch77`.
    _uid77 = _uid_del_ff77(st, _nick77, _otro77)
    _anotar_perfil_visto(st, _uid77)
    # ★★ EL RÉCORD Y LAS MEDALLAS (24-sep): las columnas del perfil y el bloque de las medallas salen
    #   de la tabla `record` DEL QUE SE MIRA. Ver `medallas.py`.
    #   `.record sonda` pone números reconocibles UNA vez, sólo en la ficha propia del que la pidió.
    _col77, _med77, _rk77 = {}, b"", 0
    try:
        from . import medallas
        from .basedatos import db_record_de
        if getattr(st, "record_sonda", False) and _uid77 == int(getattr(st, "usn", 0) or 0):
            st.record_sonda = False
            _col77, _med77, _rk77 = (medallas.SONDA_COLUMNAS, medallas.bloque_ff77(medallas.SONDA_RECORD),
                                     medallas.SONDA_RANKING)
            log("LOBBY", f"  🔬 FF77 SONDA DEL PERFIL: columnas {_col77} · medallas {medallas.SONDA_RECORD} "
                         f"· ranking {_rk77}")
        elif _uid77:
            _rec77 = db_record_de(_uid77)
            _col77, _med77 = medallas.columnas_ff77(_rec77), medallas.bloque_ff77(_rec77)
            # ★ El RANKING del perfil = el puesto en el server por EXP total (anonimo03, 24-sep: *"el valor
            #   ranking dejó de poblarse"* — nunca tuvo valor real: sólo la sonda le puso 7).
            from .basedatos import db_puesto_por_exp
            _rk77 = db_puesto_por_exp(_uid77)
    except Exception as _e77:                                        # noqa: BLE001
        # ⚠ El récord es un adorno del panel: si falla, la ficha sale igual que ayer (en cero).
        log("LOBBY", f"  ⚠ FF77: no pude armar el récord de uid={_uid77}: {_e77!r}")
        _col77, _med77, _rk77 = {}, b"", 0
    # ★ la MARCA del círculo y su EXP (el emblema y la insignia de nivel en «Mi Info», 25-sep)
    _marca77 = _exp_c77 = 0
    if _ch77.get("guild") and _uid77:
        try:
            from .basedatos import db_circulo_de, db_economia_circulo
            _k77 = db_circulo_de(_uid77)
            if _k77:
                _eco77 = db_economia_circulo(_k77["id"])
                # ★ el TOPE del nivel, no la EXP (25-sep): `0x527300` da el primer nivel cuyo tope
                #   ALCANZA el valor (≤), y en el nivel 10 la EXP queda clavada justo en el tope del
                #   9 ⇒ salía «nivel 9». Lo mismo que el FF0C (`cola[36..39]`).
                from .circulos import tope_de
                _marca77, _exp_c77 = _eco77["marca"], tope_de(_eco77["nivel"])
        except Exception as _e77c:                                   # noqa: BLE001
            log("LOBBY", f"  ⚠ FF77: no pude leer la marca del círculo de uid={_uid77}: {_e77c!r}")
    st.send_ff55(0x77, build_ff77_myinfo(_cid77, parts_visibles(_ch77),
                                         pareja=_pareja_para_ff77(_uid77),
                                         columnas=_col77, medallas=_med77, ranking=_rk77,
                                         circulo=_ch77.get("guild", ""),
                                         marca=_marca77, circulo_exp=_exp_c77,
                                         presentacion=_presentacion_ff77(_uid77),
                                         lista=_preferidos_ff77(_uid77)),
                 name=f"MyInfo char_id={_cid77} pedido={_nick77!r}"
                      + ("  ← ficha de OTRO" if _otro77 else "  (la propia)"))


def _preferidos_ff77(uid):
    """El carrito («Mis preferidos» de la tienda) de `uid` para la grilla de su perfil (`FF77` @54), o None = la ropa
    puesta como antes. Desde ahí, el que mira a OTRO tiene el botón «Regalo» en cada casilla (va por el `FF53`)."""
    from .ajustes import PERFIL_LISTA_PREFERIDOS                           # noqa: PLC0415
    if not (PERFIL_LISTA_PREFERIDOS and uid):
        return None
    try:
        from . import almacen                                              # noqa: PLC0415
        return almacen.preferidos_de(uid)
    except Exception as _e77f:                                             # noqa: BLE001
        log("LOBBY", f"  ⚠ FF77: no pude leer los preferidos de uid={uid}: {_e77f!r}")
        return None


def _presentacion_ff77(uid):
    """`(edad, texto)` de la presentación de `uid` para su ficha (`FF77`), o None. Ver `presentacion.py`."""
    from .ajustes import PRESENTACION_EN_FF77                              # noqa: PLC0415
    if not (PRESENTACION_EN_FF77 and uid):
        return None
    try:
        from .presentacion import estado                                    # noqa: PLC0415
        _l, _e, _t = estado(uid)
        return (_e, _t) if _l in ("Y", "N") else None
    except Exception as _e77p:                                              # noqa: BLE001
        log("LOBBY", f"  ⚠ FF77: no pude leer la presentación de uid={uid}: {_e77p!r}")
        return None


def _tarjeta_de(ch):
    from .catalogo import tarjeta_puesta                                   # noqa: PLC0415
    return tarjeta_puesta((ch or {}).get("parts"))


def armar_ff86(usn, paso, resultado, nombre_crudo):
    """`[u32 usn][u8 paso][u8 resultado][u8 len][nombre]` (handler `0x5D9260`). Ver `CAMBIO_DE_NOMBRE`."""
    _n = bytes(nombre_crudo or b"")[:0xFF]
    return (struct.pack("<I", int(usn or 0) & 0xFFFFFFFF) + bytes([paso & 0xFF, resultado & 0xFF, len(_n)])
            + _n)


def veredicto_nombre(usn, crudo):
    """El resultado para el cartel del cliente: 0 = libre · 3 = en uso · 5 = largo · 6 = sin el ítem."""
    from .ajustes import ITEM_CAMBIO_NOMBRE, NOMBRE_LARGO
    from .basedatos import inv_ids
    _nick = crudo.decode("cp1252", "replace").strip()
    if not (NOMBRE_LARGO[0] <= len(crudo) <= NOMBRE_LARGO[1]) or _nick != crudo.decode("cp1252", "replace"):
        return 5
    if ITEM_CAMBIO_NOMBRE not in inv_ids(db_get_char(usn) or {}):
        return 6                                   # «System Error : code 6»: no tiene el ítem
    if db_uids_por_nick(_nick):                    # sin importar mayúsculas, como al crear
        return 3                                   # (el propio apodo también cuenta: no hay cambio)
    return 0


def h_d2_ffd2(st, cmd, data):
    # ★ PONERSE UNA MEDALLA (24-sep). C→S `[u32 id]` (emisor `0x5D8BE0`: el panel «Mis Medallas» y el
    #   botón del cartel «¡Medalla adquirida!»). S→C `[u8 resultado][u32 id]` (`0x5E1540`): con 0 el
    #   cliente se la pone (`cfg+0x644` y el `[0]` del panel). Ver `medallas.py`.
    from . import medallas
    _usn = int(getattr(st, "usn", 0) or 0)
    if len(data) < 4 or not _usn:
        log("LOBBY", f"  ⚠ FFD2 corto o sin usuario: {hx(data)}")
        return
    _mid = struct.unpack_from("<I", data, 0)[0]
    _res = medallas.poner_medalla(_usn, _mid)
    st.send_ff55(0xD2, medallas.armar_ffd2(_res, _mid),
                 name=f"FFD2 medalla {_mid} -> {'PUESTA' if _res == 0 else 'rechazada (no la tiene)'}")
    # ★ Y si está en una sala, que la vean todos YA: el `FF15` (el camino nativo para actualizar a un
    #   ocupante que ya está adentro) lleva la medalla en su `T7`. anonimo03, 24-sep: *"el cambio en vivo
    #   de la medalla no se refleja en la sala"* — el FF0C sólo se lee al entrar.
    _rid = getattr(st, "room_id", None)
    if _res == 0 and _rid is not None:
        from .salas import actualizar_ocupantes
        actualizar_ocupantes(_rid, [_usn], motivo=" (se puso una medalla)")


def h_86_ff86(st, cmd, data):
    # ★ CAMBIAR EL GAME ID. Ver `CAMBIO_DE_NOMBRE` en `ajustes.py`.
    from .ajustes import CAMBIO_DE_NOMBRE, ITEM_CAMBIO_NOMBRE
    _usn = getattr(st, "usn", 0)
    if len(data) < 2 or 2 + data[1] > len(data):
        log("LOBBY", f"  ⚠ FF86 corto: {hx(data)}")
        return
    paso, crudo = data[0], bytes(data[2:2 + data[1]])
    if not CAMBIO_DE_NOMBRE:
        st.send_ff55(0x86, armar_ff86(_usn, paso, 4, crudo), name="FF86 cambio de nombre APAGADO -> 4")
        return
    _viejo = (db_get_char(_usn) or {}).get("nick", "")
    res = veredicto_nombre(_usn, crudo)
    if paso == 1 and res == 0:
        from .basedatos import db_del_inventory
        _ch = db_get_char(_usn) or {}
        if not db_del_inventory(_usn, ITEM_CAMBIO_NOMBRE):
            res = 6
        else:
            _ch = db_get_char(_usn) or {}
            if ITEM_CAMBIO_NOMBRE in (_ch.get("parts") or []):     # es familia `skin`: por si quedó puesto
                _ch["parts"].remove(ITEM_CAMBIO_NOMBRE)
            _ch["nick"] = crudo.decode("cp1252", "replace")
            db_save_uno(_usn, _ch)
            st.send_ff55(0x6A, struct.pack("<I", ITEM_CAMBIO_NOMBRE),
                         name=f"FF6A se gastó el ítem {ITEM_CAMBIO_NOMBRE} (cambio de nombre)")
            res = 1
            log("LOBBY", f"  ★★ CAMBIO DE NOMBRE: usn={_usn} {_viejo!r} -> {_ch['nick']!r}")
    st.send_ff55(0x86, armar_ff86(_usn, paso, res, crudo),
                 name=f"FF86 cambio de nombre paso={paso} {crudo!r} -> resultado {res}")
    if res not in (0, 1):
        log("LOBBY", f"  ⛔ CAMBIO DE NOMBRE: usn={_usn} ({_viejo!r}) pidió {crudo!r} (paso {paso}) "
                     f"-> {res} (3 = en uso · 5 = largo · 6 = sin el ítem)")


def _anotar_perfil_visto(st, uid):
    """Qué perfil abrió este jugador por última vez (FF77/FF78), y cuándo.

    ★ Lo usa el «i» de «Info Pareja» (27-sep): el cliente manda el mismo `FF40 01 [nick]` que
      «agregar por nombre», y la única forma de saber que es «ver info» es el CONTEXTO: el nick
      es la pareja del perfil que se acaba de abrir. Ver `lobby_social`, rama del `0x01`.
    """
    try:
        st.perfil_visto = (int(uid or 0), time.time())
    except Exception:                                              # noqa: BLE001
        pass


def h_05b_ff78(st, cmd, data):
    """FF78 — ver la ficha de OTRO jugador (clic sobre un ocupante de la sala).

    Pide `[u8 len][apodo]`, igual que el `FF77`, y la respuesta vuelve **por `FF78`**
    (handler cliente `0x5EA020`). Layout medido sobre 4 paquetes reales de tamaños
    distintos; ver `build_ff78_verinfo`.

    ⚠ A diferencia de "mi info", si el apodo no existe NO se cae al personaje propio:
      sería mostrarle lo suyo cuando pidió lo de otro. Va panel vacío (`result=1`).
    """
    _nick78 = data[1:1 + data[0]].decode("cp1252", "replace") if data else ""
    _ch78 = db_char_por_nick(_nick78)
    if not _ch78:
        st.send_ff55(0x78, b"\x01", name=f"FF78 panel vacío (no existe {_nick78!r})")
        log("LOBBY", f"  FF78 ver-info de {_nick78!r} -> no está en la DB")
        return
    # ★★ Y SU PAREJA al lado, igual que en el `FF77` (2026-09-23): mismo bloque, misma función.
    _uid78 = _uid_del_ff77(st, _nick78, _ch78)
    _anotar_perfil_visto(st, _uid78)
    st.send_ff55(0x78, build_ff78_verinfo(_ch78.get("parts") or [],
                                          char_id=int(_ch78.get("char_id") or 0),
                                          pareja=_pareja_para_ff77(_uid78),
                                          tarjeta=_tarjeta_de(_ch78)),
                 name=f"FF78 ver-info de {_nick78!r} char_id={_ch78.get('char_id')}")


def h_06_ff06(st, cmd, data):
    # rama original:  cmd == 6
    # El handler 0x5E4830 es un switch de 4 casos sobre [status:u8]:
    #   0 = OK       -> transición de pantalla, ENTRA AL CANAL (estado [obj+0x1d8]=5/6)
    #   1 = FULL     -> "LobbyServer : <CmdJoinChannel> - FULL"     + popup 0x3D
    #   2 = EXPLIMIT -> "LobbyServer : <CmdJoinChannel> - EXPLIMIT" + popup 0x3F  (★ el canal
    #                   TIENE banda de nivel, y la rechaza el SERVER: acá es donde se hace el muro)
    #   3 = ERROR    -> "LobbyServer : <CmdJoinChannel> - ERROR"    + popup 0x3F
    st.send_ff55(0x06, b"\x00", name="★ FF06 CmdJoinChannel status=0 (OK, entra al canal)")
    log("LOBBY", f"  ★ FF06 CmdJoinChannel req={hx(data)} -> status=0 (OK)")
    # ★★★ LA PRESENCIA DE AMIGOS CUELGA TAMBIÉN DE ACÁ (2026-09-11). Al CAMBIAR DE CANAL el
    #   cliente abre una conexión nueva y **no manda el `FF03`**: manda éste. Sin esta línea el
    #   amigo veía la baja y nunca el alta, y quedaba "No conectado." para siempre.
    #   Medido en el log: 01:10:56 baja · 01:10:57 reconecta en 'Libre' · ningún alta.
    #   Es idempotente por conexión, así que en el login normal (donde llegan el FF03 y éste)
    #   no duplica ni la lista ni el aviso.
    presencia_al_entrar(st, "al entrar al canal")
    from .conjuntos import enviar_lista as _sets_al_canal
    _sets_al_canal(st, "al entrar al canal")
    from .preferidos import enviar_lista as _pref_al_canal
    _pref_al_canal(st, "al entrar al canal")
    enviar_tira(st, "al entrar al canal")


def h_07_ff08(st, cmd, data):
    # rama original:  cmd == 8
    # [len1:u8][str1][len2:u8][str2][b5:u8][b6:u8] = 2 strings + 2 bytes. Hipótesis: str1=nick emisor,
    # str2=mensaje. Echo con el nick del host para que se dibuje "nick: msg". CALIBRAR b5/b6 si sale mal.
    mlen = data[0] if data else 0
    msg  = data[1:1 + mlen]
    # ★ El APODO y el ESTILO (globo/color) se guardan en la conexión CHAT_CACHE_SEG (25-sep): leer el
    #   personaje entero son ~10 consultas, y se hacía en CADA mensaje (medido: 12 por mensaje con 40
    #   en la sala, `herramientas/medir_charla.py`). Tildar un globo o un crayón lo invalida al toque
    #   (`catalogo.tildar_estilo_chat`); lo demás (un cambio de apodo) espera a que venza.
    import time as _tchat
    _cc = getattr(st, "chat_cache", None)
    if _cc and _tchat.time() - _cc[0] < CHAT_CACHE_SEG:
        char, nick, _estilo_cc = None, _cc[1], _cc[2]
    else:
        char = db_get_char(getattr(st, "usn", 0)) or {}
        nick = (char.get("nick", "") or "yo").encode("cp1252", "replace")[:0xFF]
        _estilo_cc = None
    # ★ COMANDOS DE GM por chat (como el `.gm1` del CBT): si el mensaje arranca con '.', NO se
    #   ecoa como chat normal — lo ejecuta el server y responde con una linea de sistema.
    texto = msg.decode("cp1252", "replace").strip()
    # ⚠ `comando_chat` devuelve **`None`** cuando el que escribe no tiene permiso, y eso NO es una
    #   lista vacía: con `None` se cae al chat normal de abajo. Ver `chat.puede_usar_consola` —
    #   la consola estaba abierta a cualquier jugador en producción hasta el 2026-09-09.
    #   ★ Y de paso arregla algo que molestaba: escribir "...bueno" en el chat contestaba
    #     *"comando desconocido"* en vez de decirlo.
    _rta = comando_chat(st, texto) if texto.startswith(".") else None
    if _rta is not None:
        for linea in _rta:
            # ⚠ en ASCII: el chat del cliente no dibuja tildes ni «¡» (ver `chat.a_ascii`)
            rb = a_ascii(linea).encode("ascii", "replace")[:0xFF]
            sysnick = b"SERVER"
            st.send_ff55(0x08, bytes([len(sysnick)]) + sysnick + bytes([len(rb)]) + rb + bytes([2, 0]),
                         name=f"FF08 respuesta de comando {linea!r}")
        log("LOBBY", f"  ★ FF08 COMANDO: {texto!r}")
        return
    # ★★★ 2026-08-05 — EL CHAT AHORA VA A TODA LA SALA, no sólo de vuelta al que escribió.
    #   El 5º campo (que estaba clavado en 2, que casualmente es HOST_SLOT) es **el slot del que
    #   habla**: con un solo jugador daba igual, con dos hay que mandarlo de verdad.
    #   ⚠ Eso último es INFERIDO: el handler RX 0x5CD100 lee [len][str][len][str][b5][b6] y el
    #   valor 2 venía clavado de cuando el único que hablaba era el host. Si el nombre saliera
    #   pegado al jugador equivocado, el sospechoso es este byte.
    _mi_slot8 = getattr(st, "room_slot", None)
    if _mi_slot8 is None:
        _mi_slot8 = HOST_SLOT
    # ★★★ LOS DOS ÚLTIMOS BYTES SON EL ESTILO: el GLOBO y el COLOR DE LETRA (25-sep, handler real
    #   `0x5CC980`; `documentacion/CHAT_GLOBO_Y_COLOR_EXE.md`). El globo es índice en 8 texturas
    #   (`rnr_room/chat_0..7.tga`, `sala+0x148`) y el color en una tabla de 9 (`0x886290`), los dos
    #   SIN cota (la lección del colapso del CBT del 13-ago: con 9+ caían todos).
    #   ⛔ Iba `asiento % 8` ⇒ cada asiento con un globo DE LA TIENDA sin haberlo comprado (anonimo03,
    #   25-sep: *"aleatorio"*). Ahora: los del jugador si tiene tildado uno vigente, si no (0, 0) =
    #   el globo blanco y el gris de siempre (`catalogo.estilo_chat_de`, siempre dentro de los topes).
    #   Al que habla lo encuentra el cliente por el APODO.
    # ⚠ Y los largos con cota: el apodo va a un búfer de 16 (15 + NUL) y el texto a uno de 128.
    from . import charla
    from .catalogo import estilo_chat_de
    if _estilo_cc is None:
        _estilo_cc = estilo_chat_de(getattr(st, "usn", 0), char)
        try:
            st.chat_cache = (_tchat.time(), nick, _estilo_cc)
        except Exception:                                            # noqa: BLE001
            pass
    _globo8, _color8 = _estilo_cc
    nick, msg = nick[:15], msg[:120]
    out  = bytes([len(nick)]) + nick + bytes([len(msg)]) + msg + bytes([_globo8, _color8])
    _rid8 = getattr(st, "room_id", None)
    # A TODOS, incluido el que escribió: es él quien tiene que ver su propio mensaje en el panel.
    # ★ LOS ESPECTADORES TAMBIEN OYEN EL CHAT (2026-09-08). Antes esto recorria `mesa_de`, que
    #   son solo los SENTADOS, y el que miraba quedaba en una sala muda. Ver `conexiones_en_sala`.
    _dest = conexiones_en_sala(_rid8) if _rid8 else [st]
    # ★★ Y en la SALA DE CONVERSACIÓN, a todos los de la estancia (24-sep).
    if not _rid8 and getattr(st, "lugar_clave", None) is not None:
        _dest = charla.destinos(st, con_yo=True) or [st]
    _dest = [c for c in _dest if c is not None and not getattr(c, "cerrado", False)] or [st]
    for _c in _dest:
        try:
            _c.send_ff55(0x08, out, name=RESUMIR)   # ★ la línea del mensaje sale UNA vez, abajo
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude relevar el chat: {e!r}")
    log("LOBBY", f"  ★ FF08 CHAT de {nick.decode('cp1252', 'replace')!r} slot={_mi_slot8} {msg!r} "
                 f"-> {len(_dest)} destinatario(s)")


def h_14_ff40(st, cmd, data):
    # rama original:  cmd == 64 and len(data) == 1 and (data[0] == 33)
    # ★★ FF40 subtipo 0x21 = **GuildInfo** ("dame mi círculo"), MEDIDO 2026-08-05.
    #   Despacho en el cliente: `subtipo-1` -> byte en 0x5F3194 -> salto en 0x5F30B4; el 0x21 cae
    #   en `0x5F176E`, que loguea literalmente `"GuildInfo : %d"`. Se confirma contra el log REAL
    #   de Softnyx: `(18:30:15) : GuildInfo : 0` justo después del `<CmdJoinChannel>`.
    #   ⚠ NO es de Mi Casa: lo pide al entrar a CUALQUIER canal (por eso aparecía en los dos casos).
    #   Lectura secuencial del handler:
    #       [0x21:u8][result:u8]                 result != 0 -> aborta
    #       [nameLen:u8][name]                   nameLen == 0 -> "no tengo círculo" ([obj+0xa32]=0)
    #       loop: [u32] == 0xFFFFFFFF -> FIN ; si no: [u8][u8][u32][u8][nickLen:u8][nick]
    #   ★★ 24-sep: CON CÍRCULOS. El layout completo (y la cola que al stub de 7 bytes le faltaba)
    #     está en `circulos.armar_ff40_21`. Con `CIRCULOS = False` vuelve el stub de siempre.
    if not CIRCULOS:
        st.send_ff55(0x40, b"\x21\x00\x00\xFF\xFF\xFF\xFF", name="FF40/0x21 GuildInfo: sin círculo")
        return
    from .circulos import enviar_guildinfo
    enviar_guildinfo(st, " (pedido por el cliente)")


def h_circulo_datos(st, cmd, data):
    """★ La ECONOMÍA del círculo (24-sep): el cliente pide `FFD7` (inventario) y `FFD4` (datos:
    EXP, tope/nivel, dinero, marca) al entrar a cada canal, y `FFE3 [u16 inicio]` (la lista
    completa, de a 5) desde el panel de información. Ver `circulos.armar_ffd4` / `armar_ffe3`.
    ⛔ Sin círculo NO se contesta: un resultado != 0 en el FFD4 saca el cartel de error."""
    from . import circulos
    usn = int(getattr(st, "usn", 0) or 0)
    if cmd == 0xD4:
        p = circulos.ffd4_de(usn)
        nombre = "FFD4 datos del círculo"
    elif cmd == 0xD7:
        from .circulo_tienda import ffd7_de
        p = ffd7_de(usn)
        nombre = "FFD7 inventario del círculo"
    else:
        pagina = struct.unpack_from("<H", data, 0)[0] if len(data) >= 2 else 0
        p = circulos.ffe3_de(usn, pagina)
        nombre = f"FFE3 miembros del círculo, página {pagina}"
    if p is None:
        log("LOBBY", f"  ⭕ FF{cmd:02X} de usn={usn} sin círculo: no se contesta")
        return
    st.send_ff55(cmd, p, name=f"{nombre} ({len(p)} B)")


def h_circulo_donar(st, cmd, data):
    """★ `FFD6 [u32 monto]` = DONAR Rcoin al círculo (25-sep). Ver `circulos.donar`. Si sale bien,
    el `FFD4` nuevo (EXP y dinero) le va a todos los del círculo que estén conectados."""
    from . import circulos
    usn = int(getattr(st, "usn", 0) or 0)
    monto = struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else 0
    res, saldo, cid, exp, dinero = circulos.donar(usn, monto)
    st.send_ff55(0xD6, circulos.armar_ffd6(res, saldo),
                 name=f"FFD6 donación de {monto} -> res={res}, le quedan {saldo} Rcoin")
    if res == circulos.DONAR_OK and cid is not None:
        circulos.reenviar_ffd4(cid)


def h_circulo_tienda(st, cmd, data):
    """★ La TIENDA del círculo (25-sep, `circulo_tienda.py`):
         FFD9 [u32 itemcode][u32 clave]   comprar (clave 0) o extender -> FFD9 + FFDA a todos + FFD4
         FFDF [u32 marca][u32 logo][u32 fondo]   registrar la marca  -> FFDF + FFD7 + FFD4
         FFD8 [u8 n] + n x 60 B                  guardar el arreglo  -> FFD8 (eco) + FFDA a los demás
         FFD8 [0]  «listo»                       -> FFDE (modo 1 a la sala / 2 al que no puede); ⛔ NUNCA FFD8
         FFF5 (vacío) = «guardar» sin cambios    ⛔ SÍ espera respuesta: sin ella no sale del modo edición"""
    from . import circulo_tienda as T
    from .circulos import reenviar_ffd4
    usn = int(getattr(st, "usn", 0) or 0)
    if cmd == 0xF5:
        from .charla import fff5_de
        p5 = fff5_de(st)
        st.send_ff55(0xF5, p5, name=f"FFF5 sentados: {p5[0]} (cierra la espera del «guardar»)")
        return
    if cmd == 0xF4:
        # ★ sentarse / pararse / tocar un mueble (`charla.accion_objeto`, `documentacion/CIRCULO_EXE_MUEBLES.md`)
        from .basedatos import db_circulo_de, db_items_circulo
        from .charla import accion_objeto
        clave_obj, asiento = struct.unpack_from("<IB", data, 0) if len(data) >= 5 else (0, 0)
        k = db_circulo_de(usn)
        colocados = {i["clave"] for i in db_items_circulo(k["id"]) if i["estado"] != 88} if (k and clave_obj) else set()
        accion_objeto(st, clave_obj, asiento, lambda cl: cl in colocados)
        return
    if cmd == 0xD8:
        p, cid, filas = T.acomodar(usn, data)
        if p is None:
            # el «listo»: ⛔ con FFD8 NO (medido: el contador quedaba en -1) · ★ con FFDE, que es lo
            #   que el botón espera para volver a habilitarse (`documentacion/CIRCULO_EXE_EDICION.md`)
            modo = filas
            from . import charla
            if modo == T.FFDE_LIDER_CAMBIO and cid is not None and getattr(st, "lugar_clave", None) == (charla.TIPO_CIRCULO, cid):
                dest = charla.destinos(st, con_yo=True) or [st]  # todos los de la sala: la ven rearmada
                charla.soltar_asientos(st.lugar_clave)            # el rearmado los levanta a todos
            else:
                dest = [st]
            pde = T.armar_ffde(modo)
            for c in dest:
                c.send_ff55(0xDE, pde, name=f"FFDE modo {modo} (fin del arreglo de usn={usn})")
            log("LOBBY", f"  ⭕ FFD8 [0] «listo» del arreglo (usn={usn}) -> FFDE modo {modo} a {len(dest)}")
            return
        st.send_ff55(0xD8, p, name=f"FFD8 arreglo guardado: {p[0]} ítem(s)")
        if filas:
            # ★ a TODOS, el líder INCLUIDO: el cliente tira el eco del FFD8, y sin esto su inventario
            #   queda viejo (el rearmado del FFDE modo 1 y «defecto» salen del inventario)
            T.avisar_inventario(cid, filas)
        return
    if cmd == 0xD9:
        codigo, clave = struct.unpack_from("<II", data, 0) if len(data) >= 8 else (0, 0)
        p, fila, cid = T.comprar(usn, codigo, clave)
        st.send_ff55(0xD9, p, name=f"FFD9 compra {codigo} (clave {clave}) -> res={p[1]}")
        if fila is not None:
            T.avisar_inventario(cid, [fila])
            reenviar_ffd4(cid)                                   # el dinero es de todos
        return
    marca, logo, fondo = struct.unpack_from("<III", data, 0) if len(data) >= 12 else (0, 0, 0)
    p, cid = T.marca(usn, marca, logo, fondo)
    st.send_ff55(0xDF, p, name=f"FFDF marca {marca:#x} (logo {logo}, fondo {fondo}) -> res={p[0]}")
    if cid is not None:
        T.avisar_inventario_entero(cid)                         # se gastaron el logo y el fondo
        reenviar_ffd4(cid)                                       # la marca va en el FFD4 (A+0C)


def h_circulo_subir(st, cmd, data):
    """★ `FFE1` (vacío) = SUBIR DE NIVEL el círculo (25-sep, `circulos.subir_nivel`). Si sale bien:
    los regalos al inventario (FFDA), el FFD4 nuevo a los del círculo y el cartel
    «¡Felicitaciones! Círculo X llegó al nivel N» (FF40 0x3A) a TODO el server."""
    from . import circulos
    from .basedatos import db_circulo_por_id
    from .circulo_tienda import avisar_inventario
    from .salas import CONEXIONES
    usn = int(getattr(st, "usn", 0) or 0)
    p, cid, nivel, filas = circulos.subir_nivel(usn)
    st.send_ff55(0xE1, p, name=f"FFE1 subir de nivel -> res={p[0]}" + (f", nivel {nivel}" if nivel else ""))
    if nivel is None:
        return
    if filas:
        avisar_inventario(cid, filas)
    circulos.reenviar_ffd4(cid)
    cartel = circulos.armar_ff40_3a(nivel, (db_circulo_por_id(cid) or {}).get("nombre", ""))
    n = 0
    for c in list(CONEXIONES.values()):
        if c is None or getattr(c, "cerrado", False):
            continue
        c.send_ff55(0x40, cartel, name=f"FF40/0x3A el círculo #{cid} llegó al nivel {nivel}")
        n += 1
    log("LOBBY", f"  📣 CÍRCULO #{cid} NIVEL {nivel}: cartel a {n} conectado(s)")


MISION_CIRCULO_NO_HAY = 6    # FFAC res 6 en el círculo = circle.csv 0x34 «No más misiones de círculos»


def h_ffac_mision_circulo(st, cmd, data):
    """`FFAC [u32 0][u8 0][u8 círculo]` = «CONSTRUIME UNA MISIÓN» (`0x5D6D50`; el botón «Misión de
    círculo» manda círculo=1). La respuesta (`0x5D7300`) es `[u8 res]` + 88 B de misión si res=0.
    ⏳ Las misiones de círculo no están hechas: se contesta 6 = el cartel del propio juego, y el
    cliente libera la espera. Las misiones NORMALES (círculo=0) no pasan por acá (siguen sin contestar)."""
    st.send_ff55(0xAC, bytes([MISION_CIRCULO_NO_HAY]),
                 name="FFAC misión de círculo -> 6 «No más misiones de círculos» (⏳ sin hacer)")


def h_ff40_circulo(st, cmd, data):
    """C2S `FF40` del círculo (24-sep, medidos con anonimo03 escribiendo):
         22 [u8 len][texto]   la pestaña «Círculo» del chat         -> `circulos.chat` (S2C 0x24)
         23 [u8 len][texto]   el aviso, desde el botón del parlante -> `circulos.aviso_desde_cliente` (S2C 0x25)
    """
    from . import circulos
    n = data[1] if len(data) > 1 else 0
    texto = bytes(data[2:2 + n])
    if data[0] == 0x22:
        circulos.chat(st, texto)
    else:
        for linea in circulos.aviso_desde_cliente(st, texto):
            log("LOBBY", f"  ⭕ aviso del círculo (desde el parlante): {linea}")


def h_17_ff49(st, cmd, data):
    # rama original:  cmd == 73
    # ★ El cliente PIDE el FF49 (len=0). MEDIDO: su parser es **uno solo, sin ramas por contexto**
    #   ⇒ espera exactamente la misma estructura que ya mandamos por iniciativa propia en el login.
    _ch  = db_get_char(getattr(st, "usn", 0)) or {}
    _cid, _regs = registros_ff49(_ch)          # base + los personajes del gacha
    if _cid:
        st.send_ff55(0x49, build_ff49(_cid, _regs,
                                   inventario=inventario_para_ff49(getattr(st, "usn", 0)),
                                   canciones=OWNED_SONGS_2013, tiempo_hoy=_tiempo_hoy(st)),
                     name=f"FF49 (pedido por el cliente) puesto={_cid} "
                          f"regs={[k for k, _ in _regs]}")
        # ★★★★★ Y DETRÁS, LA FICHA — VAN EN PAREJA (2026-09-09).
        #   ⛔ EL BUG: *"ya no crashea en mi armario, pero sí adentro de la sala, con sólo ir a la
        #     pestaña"*. Medido con frida: en la sala el padrón del gacha vuelve a estar VACÍO
        #     (`buscar en el padron: id=130031 -> NO ESTA (nulo)` en los tres) y el temporizador
        #     del agotamiento revienta igual que antes.
        #   ★ La causa, viéndolo en el log del server:
        #         00:03:42   FF49 + MyRecord     <- al entrar al juego, EN PAREJA
        #         00:08:31   FF49 (pedido)       <- al entrar a la sala, SOLO
        #     El `FF49` **vacía** la lista de personajes del cliente y la rellena; pero el padrón
        #     del gacha (`[0x934354]`) lo llena **la cola del MyRecord**, no este paquete.
        #     Contestando el `FF49` solo le borrábamos el padrón y no se lo devolvíamos.
        #   ⇒ La regla queda dicha: **el `FF49` nunca viaja sin su MyRecord detrás.** Es la misma
        #     pareja del login, y ahora con un motivo escrito.
        #   ★ Y la intuición fue de anonimo03: *"seguro estamos respondiendo con algo que el cliente
        #     aún no hizo, y luego crashea ahí"*. Era eso, con una vuelta de tuerca: no es que le
        #     mandemos algo de más, es que le sacamos algo y no se lo reponemos.
        enviar_myrecord(st, "MyRecord (FF03) detrás del FF49 pedido — repone el padrón del gacha")
        # ★★★ Y EL `FFC9`, que es lo que faltaba en el camino del CAMBIO DE CANAL.
        #   Ver `enviar_ffc9_licencia`: era el ÚNICO paquete nuestro que salía en un login de
        #   verdad y no salía acá, y con él se quedaba la interfaz muerta al pasar a «Libre».
        enviar_ffc9_licencia(st)
        # ★ 15-oct: la MISIÓN DE HOY en el cambio de canal (no pasa por el FF03): arranca el reloj si no estaba.
        try:
            from . import mision_hoy
            mision_hoy.al_conectar(st)
        except Exception as _e_mh:                                   # noqa: BLE001
            log("LOBBY", f"  ⚠ misión de hoy (FF49): {_e_mh!r}")
    else:
        log("LOBBY", "  ⚠ FF49 pedido pero el personaje no tiene char_id -> no se contesta")


def h_32_ff3a(st, cmd, data):
    # rama original:  cmd == 58
    # ★★★ 2026-07-31 — EL `FF3A` NO ES SÓLO "PRÁCTICA": ES EL CICLO DE MISIÓN DE LOS GRUPOS 2/3.
    # Desensamblado del handler RX `0x5E2BA0` (`re/rx_table_2013.md` idx 58). Lee CINCO campos
    # (trampa del `push size` antes del `lea dst` ya aplicada) = **12 BYTES**, no 8:
    #     @0 u8  type   ·  @1 u8  ?  ·  @2 u32 RCOIN  ·  @6 u16 ?  ·  @8 u32 EXP_DELTA
    # y en la rama **`type == 1`**:
    #     mov edx,[esp+8] ; xor edx,0x1fef ; mov [player+0x2d8],edx      -> RCOIN = @2 ^ 0x1fef
    #     call 0x486020 ; add eax,[esp+0x18] ; call 0x486000             -> EXP += @8
    #     movzx eax,word [[0x931624]+2] ; call 0x488FD0                  -> OTORGA la máscara
    # ⇒ `type=1` es **FIN DE MISIÓN**: paga moneda, suma exp y marca la misión.
    # ⛔⛔ EL BUG QUE CAUSÓ EL "NIVEL 99": contestábamos **8 bytes** y el cliente lee **12**, así que
    #    el sumando de exp salía de PILA SIN INICIALIZAR. Medido en vivo: `[player+0x2d0]^0x1fef`
    #    valía `0x74B1B8AC` — un puntero a una DLL del sistema — y el cliente le aplicó la tabla de
    #    niveles. **No era corrupción del cliente: se lo mandamos nosotros.** Ahora se responden
    #    los 12 bytes SIEMPRE (también en práctica) y el delta de exp va explícito.
    # ⛔ Y el u32 @2 tampoco era un "magic": estaba clavado en 100000 (constante del CBT) y **pisaba
    #    el saldo real** al entrar. ✅ Verificado por el usuario: con el rcoin de la DB muestra 42562.
    # ⏳ El pedido trae la máscara en @1 (`01 10 00 00 00` = fin de la 0x0010 "Novato Lunar"), pero en
    #    práctica ese mismo u16 es el SONGID (`02 1d 10 00 00` = song 4125) ⇒ el `type` decide qué es.
    #    Medido en UNA sola misión: la próxima con otra máscara lo confirma o lo tumba.
    # ⏳ EXP_DELTA queda en 0: todavía no sabemos qué exp premia cada misión (mismo pendiente que el
    #    FF63). Mandar 0 es lo correcto mientras tanto — lo que rompía era mandar BASURA, no un 0.
    FF3A_ENTRADA, FF3A_FIN, FF3A_PRACTICA = 4, 1, 2
    stype = data[0] if data else 2
    u16_1 = struct.unpack("<H", data[1:3])[0] if len(data) >= 3 else 0
    es_mision = stype in (FF3A_ENTRADA, FF3A_FIN)
    if not es_mision and u16_1:
        st.last_song = u16_1
    _rc = int((db_get_char(getattr(st, "usn", 0)) or {}).get("rcoin", 0) or 0)
    _exp_delta = 0
    echo_id = u16_1 if stype == 3 else 0
    resp = (bytes([stype, 0x01])
            + struct.pack("<I", _rc & 0xFFFFFFFF)      # @2 RCOIN (el cliente lo XORea con 0x1fef)
            + struct.pack("<H", echo_id)               # @6
            + struct.pack("<I", _exp_delta))           # @8 EXP_DELTA — ⚠ NUNCA omitir: lee basura
    st.send_ff55(0x3A, resp, name=f"SINGLEPLAY eco type={stype} v={u16_1}")
    if es_mision:
        _que = "ENTRADA" if stype == FF3A_ENTRADA else "FIN"
        log("LOBBY", f"  ★★ FF3A MISIÓN {_que} máscara=0x{u16_1:04X} -> rcoin={_rc} exp+={_exp_delta}")
        if stype == FF3A_FIN:
            _n = db_add_mision_por_mascara(getattr(st, "usn", 0), u16_1)
            log("LOBBY", f"  ★★★ misión 0x{u16_1:04X} PERSISTIDA -> nibbles={_n} "
                         f"(se marca al reloguear, vía campo E del login)")
    else:
        log("LOBBY", f"  ★ FF3A práctica type={stype} song={u16_1} -> eco (rcoin={_rc})")


def h_41_ff45(st, cmd, data):
    # rama original:  cmd in (69, 84, 29) and RESPONDER_COMO_EL_REAL
    # ★★ 2026-09-01 — EL SERVER REAL LOS CONTESTA, nosotros los dejábamos MUDOS.
    #   Medido pedido->respuesta en la captura de `<IP del referente>`:
    #       FF45 (vacío) -> `00 00 00`   ·   FF54 (vacío) -> `00`   ·   FF1D `03` -> ECO `03`
    #   ⚠ Esto CONTRADICE la nota vieja de "mantener FF1C/FF1D como NO-OP": esa decisión se
    #     tomó porque el cliente no se colgaba sin respuesta, no porque el server no deba
    #     contestar. Acá se copia lo que hace un server que funciona. Flag para volver atrás.
    # ★★★ 2026-09-12 — EL `FF45` YA NO VA VACÍO. El `bytes(3)` de abajo es `[u16 0][u8 0]`: un ack
    #   **válido pero sin ningún registro**, y por eso el anillo de la mochila nunca mostró ni el
    #   nombre de la pareja ni la fecha de aniversario. No estaba roto: estaba en blanco.
    #   ⇒ Ahora se contesta con los anillos de verdad. Ver `lobby_pareja._s2c_registro_anillos`.
    if cmd == 0x45 and PAREJA_REGISTRO_ANILLOS:
        from .lobby_pareja import mandar_registro_anillos
        mandar_registro_anillos(st, " (lo pidió el cliente)")
        return
    if cmd == 0x54:
        # ★ 12-oct: el FF54 es «¿tengo REGALOS?» (RX 0x5D0130): los avisos pendientes, o `00` como antes. Ver `regalo.py`.
        from .regalo import avisos_al_entrar
        avisos_al_entrar(st)
        return
    _resp45 = {0x45: bytes(3), 0x54: bytes(1), 0x1D: (data[:1] or bytes([3]))}[cmd]
    st.send_ff55(cmd, _resp45, name=f"FF{cmd:02X} ack (copiado del REFERENTE)")
    # ★★★ EL `FF1D` ES LA ÚLTIMA PARADA DEL ARRANQUE DEL LOBBY — 2026-09-11, medido con control:
    #   en una entrada normal al canal llega **3 de 3 veces** y es el último paquete de la
    #   secuencia; con «Jugar Juntos» llegaba **CERO veces**, porque el cliente cortaba su propio
    #   arranque a la mitad para meterse en la sala (y por eso se veía el fondo mal cargado).
    #   ⇒ Acá se marca "el lobby ya está armado" y se suelta el `FF41` que hubiera quedado
    #     esperando. Ver `FF41_ESPERA_LOBBY` en `ajustes.py` para el porqué y el riesgo.
    if cmd == 0x1D:
        st.lobby_asentado = True
        # ⚠ El import va ACÁ ADENTRO a propósito: `lobby_menu` y `lobby_salas` son hermanos y
        #   traerlo arriba los ata en un orden de carga que hoy no existe. Es el mismo patrón
        #   que `salas._codigo_de_licencia`, y por la misma razón.
        from .lobby_salas import despachar_ff41_pendiente
        despachar_ff41_pendiente(st, motivo="llegó el FF1D")


def h_44_ff94(st, cmd, data):
    # rama original:  cmd == 148  —  `CmdUpdateSearchFriendInfo`, LA PRESENTACIÓN PERSONAL.
    # ★★★ 2026-09-29 — SE CONTESTA. El formato es `[tipo][LETRA][edad][largo][texto]`, y el byte que
    #   acá se leía como *"marker 0x4e constante"* era la **letra `N`** (el «No» de «¿te registrarás en
    #   buscar amigos?»). El *"04 5a 00 00 = reporte de misión"* tampoco lo era: es el tipo 4 con la `Z`
    #   (todavía sin nivel 6), y el `04 58 00 00` es la `X` (contestó el cartel).
    #   ⛔ Sin respuesta el cliente nunca se enteraba ⇒ el cartel salía en cada entrada. Ver `presentacion.py`.
    from .ajustes import PRESENTACION_CONTESTA
    from .presentacion import atender_ff94
    r = atender_ff94(st, data)
    if r is not None and PRESENTACION_CONTESTA:
        st.send_ff55(0x94, r, name=f"FF94 presentación tipo {r[0]} resultado {r[1]}")


def h_ff138_preferidas(st, cmd, data):
    """`FF138` agregar / `FF13A` quitar PREFERIDAS (`[u16 n][u16 canción]×n`). Sin respuesta. Ver `picker.py`."""
    from .picker import cambiar_preferidas
    cambiar_preferidas(st, cmd, data)


def h_ff13b_popular(st, cmd, data):
    """`FF13B` = `CmdTopMusicList`: el puesto de popularidad de cada canción (orden «popular» y TOP 20)."""
    from .picker import respuesta_ff13b
    _r = respuesta_ff13b()
    st.send_ff55(0x13B, _r, name=f"FF13B TopMusicList ({struct.unpack_from('<H', _r)[0]} canciones)")


def h_ff6f_preferidos(st, cmd, data):
    """`FF6F` agregar / `FF70` sacar de «Mis preferidos» (el carrito de la tienda). Ver `preferidos.py`."""
    from .preferidos import atender
    atender(st, cmd, data)


def h_ff73_conjuntos(st, cmd, data):
    """`FF73` los sets del armario (Guardar / Cargar). Ver `conjuntos.py`."""
    from .conjuntos import atender
    atender(st, data)


def h_ffe2_referido(st, cmd, data):
    """`FFE2` «¿Quién te invitó?»: el apodo de quien lo trajo, o `%%1skip`. Ver `referido.py`."""
    from .referido import atender
    atender(st, data)


def h_ff158_cupon(st, cmd, data):
    """`FF158` «Ingresar cupón» del lobby: el código que escribió. Ver `cupon.py`."""
    from .cupon import atender
    atender(st, data)


def h_ff118_mision_hoy(st, cmd, data):
    """`FF118 [u32 escalón]` «Obten Premios» de la Misión de hoy. Ver `mision_hoy.py`."""
    from .mision_hoy import cobrar
    cobrar(st, data)


def h_ff52_invitar(st, cmd, data):
    """`FF52` «Invitar a los del vestíbulo» (vacío): el cartel a los del lobby. Ver `invitacion.py`."""
    from .invitacion import atender
    atender(st)


def h_ff40_invitar_amigo(st, cmd, data):
    """`FF40 0x07` «Invitar a un amigo a mi sala». Ver `invitacion.py`."""
    from .invitacion import atender_amigo
    atender_amigo(st, bytes(data[1:]))


def h_ff72_entrada_rapida(st, cmd, data):
    """`FF72` «Ingreso Rápido» del lobby. Ver `entrada_rapida.py`."""
    from .entrada_rapida import atender
    atender(st, data)


def h_ff98_espectador_datos(st, cmd, data):
    """`FF98` la transmisión al espectador. Ver `espectador_datos.py`."""
    from .espectador_datos import atender
    atender(st, data)


def h_sin_handler(st, cmd, data):
    # rama original:  else (sin handler)
    log("LOBBY", f"  inner FF{cmd:02X} SIN handler (capturado; siguiente eslabon)")

