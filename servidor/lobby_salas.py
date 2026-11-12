# -*- coding: utf-8 -*-
"""lobby_salas — crear/entrar/salir de sala, ocupantes, modo y asientos.

Cada función es UNA rama del `handle_inner` original, movida tal cual.
El orden y las condiciones viven en `despacho.py`.
"""
import struct
import time

from .ajustes import (
    AVISO_DIFICULTAD_POR_CHAT,
    FF0C_LUGAR_MINIMO,
    CHASE_FF1C_TYPE,
    CHASE_FILTRO_BANDAS,
    FF13_MODE_PROBE,
    FF1C_AL_ENTRAR,
    FF1C_NO_AL_QUE_CARGA,
    FF6E_FILTRA_POR_LICENCIA,
    FF6E_CANAL_TOPE,
    CLAVE_DE_SALA_ROLES,
    GATE_LICENCIA_AL_ENTRAR,
    LICENCIA_CLIENTE_AL_TOPE,
    JEFE_SORTEAR_CAPITAN,
    NICK_MAX_FF0E,
    ESPECTADOR_CAMBIO_5B,
    ESPECTADOR_SLOTS,
    ESPECTADOR_SLOTS_12,
    ESPECTADOR12_CODIGO,
    ESPECTADOR12_A_CORREDORES,
    FF99_12_NATIVO,
    OFRECER_ESPECTADOR,
    FF1C_EN_EL_LOBBY,
    FF4B_AL_CREAR,
    FF4B_AL_ENTRAR,
    FF4B_REPETIR_AL_CREAR,
    FFBD_ANTES_DEL_FF4B,
    GHOST_SLOTS,
    HOST_SLOT,
    FF0C_ENLACE_PAREJA,
    FF0C_SOLO_EL_QUE_ENTRA,
    PAREJA_ANUNCIO_SALA,
    PAREJA_REFRESCO_FF15,
    FF41_ESPERA_LOBBY,
    FF41_INFO_DE_SALA,
    INSTANCIAS_LUGAR,
    CHARLA_COMPARTIDA,
    CIRCULO_SALA_NUMERO,
    LUGAR_CAPACIDAD,
    LUGAR_EXP_TOPE,
    TIPOS_LUGAR_CHARLA,
    FF1C_REPONE_TRAS_TYPE5,
    FF1C_RESTAURA_UNA_VEZ,
    FFC9_PICKER_UNA_VEZ,
    FF6E_SONDEO_MUDO,
    MODE_EQUIPO,
    MODE_RELEVO,
    MODE_VELOCIDAD,
    NPC_IN_ROOM,
)
from .gacha import parts_visibles, sexo
from .registro import (
    hx,
    log,
)
from .basedatos import (
    db_get_char,
)
from .progresion import (
    char_para_banda,
    licencia_actual,
    modo_texto,
    nivel_de_exp,
)
from .paquetes import (
    build_ff0c_2013,
    build_ff139_playdata,
    build_ff13_2013,
    build_ff0c_2013_real,
    build_ff6e_roomlist,
)
from .ajustes import DOCE_CON_ITEM, DOCE_CUATRO, DOCE_RELEVO
from .salas import (
    GRANDE_TOPE,
    grande_de,
    poner_grande,
    pista_propia_de,
    cola_ff13_jugador,
    _color_apodo,
    _insignia,
    ANFITRION_PENDIENTE,
    CLAVE_SALA,
    CONEXIONES,
    OCUPACION,
    _mesa_lock,
    LUGARES,
    SALAS_VIVAS,
    SWAP_PENDIENTE,
    actualizar_ocupantes_sala,
    avisar_a_la_sala,
    avisar_a_uno,
    contar_estado_de_sala,
    marcador_de,
    anfitrion_de,
    armar_ocupantes,
    buscar_sala,
    desregistrar_sala,
    dificultad_de,
    difundir_roomlist,
    difundir_capitanes,
    difundir_salida,
    difundir_ocupante,
    difundir_userlist,
    capitanes_de,
    espectadores_de,
    difundir_espectadores,
    conexiones_en_sala,
    cerrar_slot,
    elegir_anfitrion,
    entrar_lugar,
    enviar_equipos,
    enviar_ready_npcs,
    enviar_userlist,
    equipo_de,
    sala_por_equipos,
    sala_usa_capitanes,
    gente_en,
    intercambiar_asientos,
    levantar_jugador,
    liberar_asiento,
    marcar_en_juego,
    mascara_abiertos,
    mesa_de,
    mesas_del_usn,
    desregistrar_rid,
    npcs_de,
    nuevo_roomid,
    paginar_salas,
    hay_capitanes,
    poner_anfitrion,
    poner_capitan,
    poner_dificultad,
    poner_npcs,
    poner_seleccion,
    registrar_sala,
    olvidar_capitanes,
    reparar_capitanes,
    salas_publicadas,
    salir_de_lugar,
    seleccion_de,
    sentar_jugador,
    slot_anfitrion,
    slots_cerrados,
    sortear_capitanes,
    tomar_sorteo_al_volver,
)
from .carrera import (
    asegurar_canciones_chase,
    calc_bymode,
    enviar_ff4b,
)


def _tope_de_casillas(usn):
    """Hasta qué casilla de licencia **el cliente le deja marcar** a este jugador.

    ★★★★★ ÉSTA ES LA PIEZA QUE FALTABA — 2026-09-17, y es la que hacía desaparecer las salas.
      El panel tiene 7 casillas, pero el toggle `0x4A1CE0` se corta en `0x4A1D2F` contra la licencia
      del jugador: **las casillas por encima de su licencia no las puede marcar NUNCA**. O sea que
      en la máscara que nos llega, un bit alto apagado **no es una elección del jugador**: es una
      casilla que el cliente le tiene prohibida. Filtrar por ese bit escondía salas que nadie pidió
      esconder — anonimo03, con una de sol y una cuenta de luna: *"luna ya no ve la sala de sol"*.

    ⇒ Devolvemos hasta dónde llega su elección REAL. Los bits por encima se dan por encendidos.
      Con eso el original vuelve a cumplirse tal cual él lo recuerda: *"yo era luna y podía ver las
      salas de sol, pero no podía entrar"*.

    ★ El número se calcula **como lo calcula el cliente**, no como nos gustaría: `0x4863C0`, sin
      ninguna licencia marcada, cae en la rama del EXP y da `nivel < 4 -> 8` (o sea ninguna) ·
      `4..10 -> 1` · `>= 11 -> 2`.

    ★★★ Y DESDE EL 17-sep YA NO CAE AHÍ. Con `LICENCIA_CLIENTE_AL_TOPE` le mandamos el nibble que
      le marca el record 17, así que `0x4863C0` sale por la rama de arriba y devuelve **6** —
      antes de mirar la EXP. ⇒ El jugador puede marcar y desmarcar las seis primeras casillas, y
      el botón filtrar por fin sirve para algo. Es el mismo número que `FF6E_CANAL_TOPE`, y no por
      casualidad: **es el mismo `mi`** el que dibuja el ícono, esconde la fila y acota el toggle.

    Devuelve 0 = «no pudo marcar ninguna» ⇒ no se filtra nada.
    """
    if LICENCIA_CLIENTE_AL_TOPE:
        return int(FF6E_CANAL_TOPE)           # se lo dimos nosotros: no depende de su EXP
    try:
        _n = nivel_de_exp(int((char_para_banda(usn) or {}).get("exp", 0) or 0))
    except Exception as e:                                       # noqa: BLE001
        # ⚠ Nada de `except: return` mudo: un ImportError silencioso ya nos costó una caza entera.
        log("LOBBY", f"  ⚠ no pude calcular el tope de casillas de usn={usn}: {e!r} -> no filtro")
        return 0
    if _n < 4:
        return 0                              # `mi` = 8, el que no tiene licencia: no marca ninguna
    if _n <= 10:
        return 1
    return 2


def _alcanza_la_licencia(st, rid):
    """¿La licencia de este jugador le da para entrar a esa sala? Replica `0x484A00` del cliente.

    ★★★★★ ESTA FUNCIÓN EXISTE PORQUE LE SUBIMOS EL `mi` AL CLIENTE (ver `LICENCIA_CLIENTE_AL_TOPE`).
      Con el `mi` alto el cliente ya no frena a nadie, así que el candado pasa a ser nuestro. Y se
      replica **la regla del exe, tal cual**, no una nuestra que se le parezca:

          if (L == 0)  -> pasa           ; sala sin banda elegida
          if (mi == 8) -> pasa sólo L==8 ; el que no tiene licencia, sólo las de 8
          if (L == 8)  -> pasa           ; las de 8 las ve y entra cualquiera
          return mi >= L

    ⚠⚠ **El 8 es la licencia MÁS BAJA, no la más alta.** La escala real del cliente es
      `8 < 1 < 2 < 3 < 4 < 5 < 6 < 7`, y está fuera de orden: por eso el exe lo despacha en dos
      líneas aparte antes de comparar con `>=`, y por eso acá también van aparte. Tratar el 8 como
      «un canal más» y compararlo con `>=` dejaría al novato entrando a todos lados.

    ⚠ Ante la duda **se deja entrar**. Un error nuestro no puede dejar a un jugador afuera de una
      sala a la que tiene derecho: el rechazo es lo que hay que estar seguro de hacer, no el pase.
    """
    try:
        _L = dificultad_de(rid)
        if not _L:
            return True                              # sala sin banda: entra cualquiera
        _L = int(_L)
        if _L == 8:
            return True                              # el comodín «sin licencia»
        _mi = int(licencia_actual(getattr(st, "usn", 0))[1] or 0)
        if _mi == 8:
            return _L == 8                           # el que no tiene licencia, sólo las de 8
        if not (1 <= _L <= 7):
            return True                              # banda rara -> no inventamos un rechazo
        return _mi >= _L
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude comprobar la licencia de sala {rid}: {e!r} -> lo dejo entrar")
        return True


def _pasa_el_filtro(sala, mascara, tope):
    """Esta sala, con la banda que tiene, pasa el filtro que marco el jugador en su panel?

    `mascara`: bit 0 = licencia 1, ... bit 6 = licencia 7.
    `tope`: hasta qué casilla el cliente le dejó elegir (ver `_tope_de_casillas`).
    ⚠ Ante la duda **se muestra**: esconder una sala de mas es peor que no filtrar.
    """
    try:
        _b = dificultad_de(sala.get("roomid"))
        if not _b or not (1 <= int(_b) <= 7):
            return True                       # sin banda elegida -> la ve cualquiera
        if int(_b) > int(tope or 0):
            return True                       # ★★★ no podía marcar esa casilla -> no la eligió él
        return bool(mascara & (1 << (int(_b) - 1)))
    except Exception:
        return True


def h_08_ff6e(st, cmd, data):
    # rama original:  cmd == 110
    # lista de salas (payload = [tipo:u8][pagina:u16][filtros]; ej '03 00 00 3f ff 01 01').
    # ★ MEDIDO EN VIVO (trace_ff6e, 2026-07-09): la respuesta de lista VACIA = 3 bytes exactos
    #   = [b0:u8][count:u16]. Con count=0 el loop por-sala (los 0x67cfe0 repetidos del handler)
    #   corre 0 veces y consume solo la cabecera. Responder esto ASIENTA el lobby: el FF3D pasa
    #   de ~60/seg (panel refrescando sin datos) a ~1/3seg (keepalive). Poblar salas reales =
    #   siguiente paso (reversar el formato por-entrada del loop).
    # ★★ 2026-07-30: FORMATO POR-SALA REVERSADO (ver build_ff6e_roomlist). Si ROOMLIST_SALAS
    #    tiene salas, se publican; si no, se sigue mandando la lista vacía de siempre.
    # ★★ 25-oct: el FFC9 GUARDADO del personaje recién elegido en el selector del juego (lobby_menu.h_00_ff03). Va
    #   acá porque la lista de salas es lo primero que pide el cliente YA EN EL LOBBY. MEDIDO: el FFC9 refresca el
    #   botón «Button_View» del picker, cuyo sprite se DESCARGA al salir de la escena Login (0x411AE6 -> 0x531DD0) y
    #   se recarga al entrar al lobby. En la bienvenida (con el FF06) todavía está vacío y el cliente muere (0x684107).
    if getattr(st, "ffc9_pendiente", False):
        st.ffc9_pendiente = False
        from .ajustes import SELECTOR_FFC9_TARDE
        from .lobby_menu import enviar_ffc9_licencia
        if SELECTOR_FFC9_TARDE:
            enviar_ffc9_licencia(st)
        else:
            log("LOBBY", "  ★ FFC9 del personaje elegido NO se manda en el lobby (SELECTOR_FFC9_TARDE = False)")
        # ★ y su ropa y sus sets, que limpian lo que dejó el personaje anterior (conjuntos.sincronizar_al_elegir)
        from .conjuntos import sincronizar_al_elegir
        sincronizar_al_elegir(st)
    tipo = data[0] if data else 0
    pag  = struct.unpack("<H", data[1:3])[0] if len(data) >= 3 else 0
    # ★★ LA LISTA ES DEL CANAL DEL QUE PIDE. Cada canal tiene su puerto, y `st.canal` sale de
    #   `CANAL_POR_PUERTO`. Antes se mandaban TODAS las salas a todos: el usuario creaba en Libre
    #   y la sala aparecía en los 10 canales.
    _canal = getattr(st, "canal", None)
    _todas = salas_publicadas(_canal)

    # ★★★★★ EL FILTRO POR LICENCIA — «que funcione el botón de filtrar» (2026-09-17).
    #   anonimo03: *"la sala desaparece como si hubiera usado el botón filtrar, cuando no debería
    #   ocurrir eso **al menos que use la función filtrar** para que sólo muestre salas de mi
    #   licencia"*. Y tenía razón en las dos mitades: filtrar ES opcional, y las casillas que no
    #   te dan están bloqueadas.
    #
    #   ★★ EL CLIENTE NOS MANDA SU ELECCIÓN Y ESPERA QUE FILTREMOS NOSOTROS. Medido: el emisor
    #     (`0x4A36E2` / `0x5D1B20`) arma `[u8 tipo][u16 pág][u8 panel+0x12BC][u8 panel+0x466C]`,
    #     y ese último byte es la **máscara de las 7 casillas de licencia** (`0x4A1FE4` la dibuja
    #     bit a bit; el toggle `0x4A1CE0` la escribe, acotado a tu licencia por `0x4A1D2F` y sin
    #     dejarte apagarlas todas). En el log se la ve moverse: `3f 7f 01 01` con las siete
    #     marcadas, `3f 1f 01 01` con cinco.
    #   ⇒ **Nunca la miramos.** Ésta es la función que faltaba de nuestro lado.
    #
    #   ★ Se filtra por la banda REAL de la sala (`dificultad_de`), no por el `L` que mandamos:
    #     así funciona igual aunque el `L` vaya en 0 por lo del candado. Ver
    #     `documentacion/LICENCIA_DE_SALA_Y_SU_ICONO.md`.
    #   ⚠ Con red de seguridad, porque esconder salas de más es peor que no filtrar:
    #     máscara 0 o 0xFF -> no se filtra · sala sin banda -> se muestra · banda rara -> se muestra.
    if FF6E_FILTRA_POR_LICENCIA and len(data) > 4:
        _masc = data[4] & 0xFF
        # ⛔⛔ Y ACÁ ESTABA EL BUG QUE ANONIMO03 VIO EN PANTALLA (2026-09-17). Filtrábamos por los
        #   SIETE bits, y el cliente sólo le deja marcar los de su licencia ⇒ los bits altos vienen
        #   apagados siempre, y nosotros los leíamos como «no la quiero ver». Resultado: *"con o
        #   sin arreglo, la sala deja de listarse si le subo el canal — luna ya no ve la de sol"*.
        #   ★ El log lo decía con todas las letras y no lo miramos: `mascara 0x1F: 1 sala(s) -> 0`.
        #   ⇒ El tope acota el filtro a lo que el jugador PUDO elegir. Ver `_tope_de_casillas`.
        _tope = _tope_de_casillas(getattr(st, "usn", 0))
        if _masc not in (0x00, 0xFF) and _tope:
            _antes = len(_todas)
            _todas = [s for s in _todas if _pasa_el_filtro(s, _masc, _tope)]
            if len(_todas) != _antes:
                log("LOBBY", f"  ★ FF6E filtro de licencia (mascara 0x{_masc:02X}, "
                             f"sólo casillas 1..{_tope}): {_antes} sala(s) -> {len(_todas)}")
    # ★★★ EL PRIMER BYTE DE LA RESPUESTA **NO ES UN ECO DEL PEDIDO** (2026-09-03).
    #   ⛔ Le devolvíamos el mismo `tipo` que había pedido el cliente. MEDIDO sobre las 221
    #      respuestas del server de referencia, y no hay una sola excepción:
    #
    #          pide 0x0D -> responde 1 (con salas) ×182     pide 0x01 -> responde 0 (vacía) ×12
    #          pide 0x00 -> responde 1 (con salas) ×21      pide 0x00 -> responde 0 (vacía) ×3
    #          pide 0x01 -> responde 1 (con salas) ×3
    #
    #   ⛔⛔ Y ACÁ DECÍA que ese byte era **"1 = hay salas · 0 = lista vacía"**. La observación
    #      está bien; la LECTURA estaba mal. Es **el número de PÁGINAS** (`0x5E0850: cmp cl,1 /
    #      jbe` -> con >1 dibuja las pestañas). En ese corpus nunca hubo más de 12 salas, o sea
    #      nunca más de una página, y ahí los dos significados dan el mismo número.
    #      ⇒ Un corpus sólo puede desmentir lo que llegó a pasar. Ver `build_ff6e_roomlist`.
    _salas, _paginas = paginar_salas(_todas, pag)
    # ★★★★★ EL SONDEO DE FONDO NO SE CONTESTA EN VACÍO — 2026-09-09.
    #   ⛔ EL BUG, reportado por anonimo03 con una captura: estando **en la isla**, sin haber ido a
    #     multijugador, le saltaba el cartel *"No hay salas disponibles. ¿Desea crear una?"*.
    #
    #   ★★ QUIÉN SACA ESE CARTEL — leído en el handler del cliente (`0x5E0800`):
    #         005e0841  cmp  dx, word [esp+0x20]      ; ¿count == 0?
    #         005e0846  jne  0x5e08d8                 ;   con salas se va y las dibuja
    #         005e0850  cmp  cl, 1                    ; ¿páginas <= 1?
    #         005e088d  cmp  word [ecx+0x16fc], 0x28  ;   un estado que lo silencia
    #         005e08b3  push 0x12F                    ; ★ el popup 303 = ese cartel
    #     O sea: **lo dispara una lista VACÍA**, no el hecho de pedirla. Contestando `count=0` se
    #     lo sacamos nosotros.
    #
    #   ★★ Y HAY DOS PEDIDOS DISTINTOS, no uno. Separados por TRES marcas que coinciden siempre:
    #         de verdad  ->  tipo=1/2/13   pag=0        filtros=3f ?? 01 01
    #         sondeo     ->  tipo=0        pag=0xFFFF   filtros=3e ?? 00 00
    #     `0xFFFF` **no es una página**: es −1, el centinela de "ninguna". En prod son **590 de los
    #     últimos 4000 pedidos (15%)**, y llegan solos cada tanto sin que el jugador toque nada.
    #
    #   ⚠ Y LA CAPTURA DEL SERVER REAL NO TIENE NI UNO. En 5,2 MB y 11 partidas el cliente mandó
    #     17 `FF6E`, **todos con `pag=0`**. La diferencia más visible entre aquel server y el
    #     nuestro es que **allá SIEMPRE había salas** (12 en la lista): el cliente nunca se quedó
    #     sin nada que dibujar. Es una explicación coherente, no una certeza — anotada como tal.
    #
    #   ⇒ Con salas se le contesta igual que siempre (dibuja, y no hay cartel). **Vacío, se calla**:
    #     no hay nada que mostrarle y el silencio es lo único que no le saca el cartel encima.
    #   ⚠ Callarse tiene un antecedente feo en este repo (el `FF69` sin handler dejaba la animación
    #     esperando para siempre). Acá el riesgo es otro: que reintente. Si eso pasa se va a ver en
    #     el log como una ráfaga de sondeos — se mira y se decide. Interruptor: `FF6E_SONDEO_MUDO`.
    _sondeo = (pag == 0xFFFF)
    # ★★★ ACORDARSE DE EN QUE PAGINA QUEDO ESTE JUGADOR — 2026-09-12.
    #   ⛔ EL BUG: *"si estoy en pagina 2, pasan un par de segundos y me muestra la de la 1"*.
    #     `difundir_roomlist` le empuja la lista a todos cada vez que una sala arranca o termina
    #     una canción (en prod: cada ~3 s), y **siempre mandaba la página 0**.
    #
    #   ★ EL CLIENTE NO SE PUEDE DEFENDER SOLO. En su handler (`0x5E0800`):
    #         005e08de  call 0x4A17A0   ; guarda la página actual en +0x16F0
    #         005e08e9  call 0x4A05A0   ; y **pone la página en 0x28**, el centinela "ninguna"
    #     La respuesta no dice de qué página es: el cliente dibuja lo que le llegue y se olvida de
    #     dónde estaba. O sea que está hecho para que el server le mande la página que él pidió.
    #     ⇒ El único que puede acordarse somos nosotros, y el dato ya viaja en cada pedido.
    #
    #   ⚠ El SONDEO de fondo (`pag=0xFFFF`) NO cuenta: no es el jugador mirando, llega solo cada
    #     tanto y es el 15% de los pedidos. Guardarlo le pisaría la página de verdad.
    if not _sondeo:
        st.salas_pag = int(pag)
    if _sondeo and not _salas and FF6E_SONDEO_MUDO:
        log("LOBBY", f"  ★ FF6E SONDEO de fondo (tipo={tipo} pag=0x{pag:04X} "
                     f"filtros={hx(data[3:])}) y el canal {_canal} no tiene salas -> NO se "
                     f"contesta. Contestarle 'lista vacía' le saca el cartel «No hay salas "
                     f"disponibles» encima de la isla (popup 303).")
        return
    st.lista_con_salas = bool(_salas)        # ★ 26-oct: lo que tiene dibujado (lo mira `difundir_roomlist`)
    if not _salas:
        st.send_ff55(0x6E, bytes([0, 0, 0]), name="FF6E ROOMLIST lista vacia (count=0)")
        log("LOBBY", f"  ★ FF6E pidio tipo={tipo} pag={pag} filtros={hx(data[3:])} -> "
                     f"lista vacia en el canal {_canal}. Lobby asentado.")
    else:
        st.send_ff55(0x6E, build_ff6e_roomlist(_salas, paginas=_paginas),
                     name=f"FF6E ROOMLIST {len(_salas)} salas · pág {min(pag, _paginas - 1) + 1}"
                          f"/{_paginas} (pidio tipo={tipo})")
        log("LOBBY", f"  ★★ FF6E pidio tipo={tipo} pag={pag} filtros={hx(data[3:])} -> canal "
                     f"{_canal}: {len(_todas)} sala(s) en {_paginas} página(s), mando la "
                     f"{min(pag, _paginas - 1) + 1} con {len(_salas)}: "
                     f"{[s['nombre'] for s in _salas]}")


def pedido_de_sala(data):
    """El pedido de CREAR (`FF10`) o EDITAR (`FF4B`) una sala — el mismo formato los dos:

        [flags:u8][largo:u8][nombre][largo_clave:u8][clave][?:u8][colab:u8][jefe:u8]

    ⛔⛔ 29-sep: se leía `[flags][largo][nombre][c0][c1][colab][jefe]`, con la cola FIJA de 4 bytes.
      Sin clave es lo mismo (`c0` = largo 0). **Con clave, la cola se corre** tantos bytes como
      letras tenga, y el modo salía de las letras: *"la sala creada no recibe el modo, byte
      corrido"* (anonimo03). Medido en ~3.200 pedidos de los logs: `04 31 32 33 34 | 00 00 00`.
    Devuelve (flags, nombre, clave:bytes, colab, jefe).

    ★ 10-oct: el bit 0x80 de los flags es NUESTRO — «Modo de 12 jugadores» de la ventana de crear sala (la d3d9,
      `sala12.c`). El juego no lo usa (`0x46BC60`: 0x01 velocidad, 0x02 equipo, 0x10 relevo): se saca acá, para que
      no viaje a ningún otro lado, y se lee con `pide_doce(data)`.
    ★ 15-oct: y el 0x40 también — «4 equipos» (con el 0x80: la sala de 12 de 4 equipos, EQUIPOS_4.md), `pide_cuatro`."""
    flags = (data[0] if data else 0) & 0x3F
    nlen = data[1] if len(data) > 1 else 0
    nombre = data[2:2 + nlen].decode("cp1252", "replace") if nlen else ""
    cola = data[2 + nlen:]
    clen = cola[0] if cola else 0
    clave = bytes(cola[1:1 + clen])
    resto = cola[1 + clen:]
    colab = bool(len(resto) > 1 and resto[1])
    jefe = bool(len(resto) > 2 and resto[2])
    return flags, nombre, clave, colab, jefe


def pide_doce(data):
    """¿El FF10 trae «Modo de 12 jugadores»? (el bit 0x80 de los flags, ver `pedido_de_sala`)"""
    return bool(data) and bool(data[0] & 0x80)


def pide_cuatro(data):
    """★ 15-oct: ¿el FF10 trae «4 equipos»? (el bit 0x40, sólo con el 0x80 — la ventana de crear sala, `sala12.c`)"""
    return pide_doce(data) and bool(data[0] & 0x40)


def puede_poner_clave(st):
    """★ Sólo admin, GM o streamer (`CLAVE_DE_SALA_ROLES`). Los roles salen de `gm.txt`, `admin.txt` y `streamers.txt`."""
    try:
        from .gm import rol_de
        return rol_de(getattr(st, "usn", 0)) in CLAVE_DE_SALA_ROLES
    except Exception as e:                                   # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude leer el rol de usn={getattr(st, 'usn', 0)}: {e!r} -> sin clave")
        return False


# ★ 29-sep: las frases con las que el cliente RELLENA el nombre de la sala por su cuenta. Salen de
#   `rnr_script/string_lt/system.csv` (líneas 30-34 y 125). Un FF4B que trae una de éstas NO es un
#   cambio de nombre: es la ventana de configuración abierta con su frase al azar.
FRASES_DE_FABRICA = frozenset((
    "¡Disfrute el R2beat!",
    "¿Hay alguien listo para el juego?",
    "En busca de jugadores con buenos modales.",
    "¡Bienvenido!~",
    "Sala para usuarios educados.",
))


def h_09_ff10(st, cmd, data):
    # rama original:  cmd == 16
    # req = [mode:u8][namelen:u8][name: namelen bytes cp1252][flags:4B].
    # ★ RESPUESTA = CALCA AL CBT (disasm 0x5E5A70: read u16 roomid; if ==0xFFFE -> error 494;
    #   read u8 status). resp = [roomid:u16 (>0, !=0xFFFE)][status:u8]. roomid valido -> crea+entra.
    # El `mode` (0x00, 0x13, ...) es CLIENT-SIDE (mas modos que el CBT); el server solo lo guarda.
    try:
        mode, rname, _clave, _colab10, _jefe10 = pedido_de_sala(data)
        rname = rname or "sala"
        nlen = data[1] if len(data) > 1 else 0
        # ★★★★★ PRIMERO LEVANTARLO DE DONDE ESTABA — 2026-09-15, el arreglo de las SALAS FANTASMA.
        #   ⛔ Acá abajo `st.room_id` se PISA con la sala nueva. Si el jugador ya estaba sentado en
        #     otra, ese `room_id` viejo era **el único hilo** que quedaba para poder limpiarla:
        #     pisado, su asiento no lo suelta nadie nunca más y la sala se vuelve inmortal.
        #   ★ Y no es un caso raro: MEDIDO en prod, el cliente manda el MISMO `FF10` **dos veces
        #     seguidas** (`recv_ctr=97` y `98`, en el mismo segundo) y le creábamos dos salas. Ocho
        #     veces en 3 días. Ver `sacar_de_la_sala_anterior`.
        sacar_de_la_sala_anterior(st, "crear una sala nueva")
        # ★★ 2026-08-05: el roomid ERA 1 CLAVADO ("unico host local"). Con dos jugadores los dos
        #    creaban la sala 1 y se pisaban en SALAS_VIVAS. Ahora cada sala tiene su Nº.
        st.room_id = nuevo_roomid()
        st.sala_poblada = None               # ★ todavía no pidió la lista: ver `salas.difundir_ocupante`
        st.room_name = rname                 # ★ FIX: guardar el nombre real (antes FF13 mandaba 'sala' hardcodeado)
        st.room_mode = mode
        st.ghost = NPC_IN_ROOM               # ★ activar el NPC/fantasma para esta sala
        # El creador se sienta en HOST_SLOT: no se negocia, lo fija el cliente solo (me+0x40=2).
        sentar_jugador(st, st.room_id, HOST_SLOT)
        poner_anfitrion(st.room_id, st.usn)   # ★ el que crea es el anfitrión — hasta que la ceda o se vaya
        poner_npcs(st.room_id, list(GHOST_SLOTS) if NPC_IN_ROOM else [])   # nace sin NPC
        st.send_ff55(0x10, struct.pack("<H", st.room_id) + b"\x01",
                     name=f"CREATEROOM ack roomid={st.room_id} (mode=0x{mode:02X} name={rname!r})")
        # ★★ El que CREA también cambia de lugar: sin este aviso, sus amigos lo siguen viendo en el
        #   vestíbulo y no les aparece el botón «Jugar Juntos» — que es justo el caso más común,
        #   porque el que crea la sala es al que los demás quieren seguir.
        _avisar_ubicacion(st, "creó una sala")
        # ★ DIAGNOSTICO DE MODOS (2026-07-29): el 2013 tiene 4 selectores en el dialogo de crear sala
        #   (equipo/solo/relevo · velocidad/item · colaboracion · jefe) contra 2 del CBT, y TODAS las
        #   salas caen en "velocidad-solo". El byte0 cambia con la seleccion (vistos 0x00, 0x01, 0x13)
        #   => es un BITFIELD, no un enum. Logueamos byte0 en binario + la cola de 4B para armar la
        #   tabla seleccion->bits creando una sala por combinacion.
        cola = data[2 + nlen:]
        st.room_colab = _colab10          # ★ 29-sep: después de la clave (ver `pedido_de_sala`)
        st.room_boss  = _jefe10
        # ★★ LA CONTRASEÑA (29-sep) — antes de publicar: el candado viaja en el `B` de la lista.
        # ⚠ Al que no tiene rol NO se le avisa nada (anonimo03, 29-sep: «quita el aviso»): la sala sale
        #   abierta y listo. Queda en el log.
        CLAVE_SALA.pop(st.room_id, None)
        if _clave and puede_poner_clave(st):
            CLAVE_SALA[st.room_id] = _clave
            log("LOBBY", f"  🔒 sala {st.room_id} CON CONTRASEÑA ({len(_clave)} caracteres) — "
                         f"la puso usn={st.usn}, que tiene rol")
        elif _clave:
            log("LOBBY", f"  🔓 usn={st.usn} pidió contraseña y NO tiene rol -> sala {st.room_id} ABIERTA")
        # ★★★ PUBLICAR LA SALA **DESPUÉS** DE LEER LA COLA (corregido 2026-09-03).
        #   ⛔ `registrar_sala` se llamaba SIETE LÍNEAS ANTES de que se leyera `room_colab`, así
        #      que la sala se publicaba con el valor de **la sala anterior**. Síntoma exacto que
        #      reportó el usuario: *"creé la primera sala como cooperativo pero se listó como
        #      item; salí, volví a crear y se listó bien"*. La primera vez `room_colab` todavía
        #      valía `False` (la conexión venía limpia) y la segunda quedaba en `True` de la
        #      anterior, así que acertaba de casualidad.
        #   ⚠ Y explica también por qué era intermitente en vez de estar siempre mal: dependía
        #     de qué modo hubieras creado la vez anterior.
        # ★ «Modo de 12 jugadores» (10-oct, el 6vs6): la sala nace con la carrera grande de 12. Con relevo, colaboración
        #   o jefe no va (la ventana no lo deja; si llegara igual, se ignora).
        # ★ 13-oct: y con ÍTEM (`DOCE_CON_ITEM`; antes crasheaba, MODO_6VS6.md §11 y §18). Apagado = sólo velocidad
        # ★ 14-oct: y RELEVO (`DOCE_RELEVO`, RELEVO_12.md): 4 equipos de 3 en lugares fijos
        # ★ 15-oct: y EQUIPO DE 4 (`DOCE_CUATRO`, EQUIPOS_4.md): la casilla «4 equipos» (bit 0x40) con batalla en equipo
        _relevo12 = bool(mode & MODE_RELEVO) and DOCE_RELEVO
        _cuatro12 = (_relevo12 or (pide_cuatro(data) and DOCE_CUATRO and bool(mode & MODE_EQUIPO)
                                   and not (mode & MODE_RELEVO)))
        if (pide_doce(data) and (_relevo12 or not (mode & MODE_RELEVO))
                and ((mode & MODE_VELOCIDAD) or DOCE_CON_ITEM) and not st.room_colab and not st.room_boss):
            poner_grande(st.room_id, GRANDE_TOPE)
            from .salas import poner_cuatro12, poner_relevo12
            poner_cuatro12(st.room_id, _cuatro12)
            poner_relevo12(st.room_id, _relevo12)
            log("LOBBY", f"  ⚔️ CREATEROOM: sala {st.room_id} de 12 JUGADORES "
                         f"({'RELEVO de 4 equipos de 3' if _relevo12 else 'EQUIPO de 4 equipos de 3' if _cuatro12 else '6 contra 6' if mode & MODE_EQUIPO else '12 todos contra todos'})")
        registrar_sala(st)                   # ★★ MATCHER: la sala pasa a existir en la lista del lobby
        # ★★★ Y AL QUE ACABA DE CREARLA, LAS REGLAS + CÓMO CAMBIARLAS — 2026-09-14, idea de anonimo03.
        #   ⛔ El agujero original: el que ENTRA recibía la línea (por `FF11`), pero el que CREA
        #     va por ACÁ (`CREATEROOM`, `FF10`), que es otro camino ⇒ **al anfitrión, justo el
        #     único que puede tocar la perilla, nunca le llegaba**.
        #
        #   ⛔⛔ Y MANDARLA ACÁ NO ALCANZA — medido en el log del 14-sep, segundo intento:
        #
        #       19:57:31  TX FF08 'PD Valofe'                     ← se mandó, send_ctr=26
        #       19:57:31  TX FF08 'master de sala: .pd on / ...'  ← se mandó, send_ctr=27
        #       19:57:32  RX FF13   ← ★ recién ACÁ el cliente pide dibujar la sala
        #
        #     O sea: el server las mandó bien y el cliente **todavía estaba cambiando de
        #     pantalla**. El chat cayó en la ventana del vestíbulo, que se destruye al entrar a
        #     la sala. anonimo03 creó una sala y no vio nada, y el log lo explica entero.
        #
        #   ⇒ Se DEJA ANOTADO y se manda cuando la sala ya está dibujada, al final del `FF0C`
        #     (que es lo último que pide el cliente para armarla). Es el mismo molde que ya usa
        #     `ff4b_repetir` cinco líneas más abajo de allá, y por el mismo motivo.
        st.pd_por_contar = (st.room_id, True)     # (sala, es_el_master)
        log("LOBBY", f"  ★ CREATEROOM: {modo_texto(mode, st.room_colab, st.room_boss)} "
                     f"[flags=0x{mode:02X} 0b{mode:08b} cola={cola.hex(' ')}] name={rname!r} "
                     f"-> roomid={st.room_id} (ack; cliente pedira FF13/FF0C)")
    except Exception as e:
        log("LOBBY", f"  CREATEROOM parse err: {e!r} data={hx(data)}")


def h_15_ff65(st, cmd, data):
    # rama original:  cmd == 101
    # ★★★★ FF65 = LA LISTA DE INSTANCIAS del lugar (handler cliente `0x5D09C0`).
    #   Es el panel de arriba a la izquierda ("Sala de Conversación | Estado" + botón Seleccionar).
    #   PEDIDO: 1 byte = el roomType (emisor `0x5CC650`, lo arma `0x585A91` con `xor cl,0xEF`).
    #   RESPUESTA:
    #       [count:u16]
    #       por entrada: [A:u16][ocupantes:u8]   (+ [len:u8][nick] SÓLO si (A>>11)==0x0B)
    #   ★ El número que se ve ("Libre 0", "Libre 1"…) es **literalmente `A & 0x7FF`**:
    #     `0x5D0A96: and ecx,0x7FF` justo antes del sprintf con el texto 219 ("Libre %d").
    #   ⚠ La capacidad (40) está HORNEADA en el cliente (`0x5D0C24`), no se manda.
    #   ⚠ Al tocar "Seleccionar" el cliente manda un `FF11` con **ESE** `A` ⇒ el server tiene que
    #     aceptar cualquier número 0..2047, no sólo el 965 que usa el botón por defecto.
    #     (Nuestra rama de lugares especiales ya acepta cualquiera: sólo mira el tipo.)
    _t65 = data[0] if data else 5
    # ★★ LA SALA DE CONVERSACIÓN COMPARTIDA (24-sep): todas sus estancias 0..N-1 con la gente real.
    from . import charla
    if CHARLA_COMPARTIDA and charla.es_publica(_t65):
        _p65 = charla.lista_ff65(_t65)
        st.send_ff55(0x65, _p65, name=f"FF65 charla tipo={_t65}: {len(_p65) // 3} estancia(s)")
        log("LOBBY", f"  💬 FF65 charla tipo={_t65}: {_p65.hex(' ')}")
        return
    # ★★ LA SALA DEL CÍRCULO (25-sep): un renglón, con la gente de SU círculo.
    if charla.es_del_circulo(_t65):
        _p65 = charla.lista_ff65_circulo(st, CIRCULO_SALA_NUMERO)
        st.send_ff55(0x65, _p65, name=f"FF65 sala del círculo: {_p65.hex(' ')}")
        return
    # ★★ EL `ocupantes` VA SIEMPRE EN 0 — NO ES UNA DECISIÓN DE DISEÑO, ES UNA BOMBA:
    #   MEDIDO en el handler `0x5D09C0`, el byte de `ocupantes` se lee **encima del byte alto del
    #   `count`** (las dos `lea` difieren en 1: `8d442418` vs `8d542417`). Con ocupantes != 0 el
    #   contador salta a `ocupantes*256 + resto` y el cliente sigue leyendo entradas inexistentes;
    #   como el lector deja BASURA DE PILA cuando el payload se acaba, un `A` basura que caiga en el
    #   caso tipo 11 lee un `[len]` de hasta 255 sobre un buffer de 64 B ⇒ desborde.
    #   ⇒ La columna "Estado" (gente por instancia) NO se puede llenar por acá hasta entender esto.
    # ⚠ SIGUE EN 0 a propósito: ver el comentario de abajo. Ya tenemos la cuenta real
    #   (`gente_en(tipo, num)`), pero mandarla != 0 rompe el contador del cliente.
    _ocup = 0
    _ent = bytearray()
    # ★ Se incluye SIEMPRE la instancia en la que el jugador YA está: el encabezado la muestra
    #   ("Libre 965") y el panel la busca para resaltarla; si no está en la lista, la búsqueda no
    #   encuentra nada. (Sospecha del agente, la estamos probando.)
    _yo = getattr(st, "lugar_a", None)
    _vistos = []
    if _yo is not None and (_yo >> 11) == (_t65 & 0x1F):
        _vistos.append(_yo)
    for i in range(INSTANCIAS_LUGAR):
        _a = ((_t65 & 0x1F) << 11) | i
        if _a not in _vistos:
            _vistos.append(_a)
    for _a in _vistos:
        _ent += struct.pack("<HB", _a, _ocup)
        if (_a >> 11) == 0x0B:             # sólo el tipo 11 lleva el nick del dueño
            _nb = str((db_get_char(getattr(st, "usn", 0)) or {}).get("nick", "") or "").encode("cp1252", "replace")[:15]
            _ent += bytes([len(_nb)]) + _nb
    _n65 = len(_vistos)
    st.send_ff55(0x65, struct.pack("<H", _n65) + bytes(_ent),
                 name=f"FF65 lista de instancias tipo={_t65} -> {_n65} entrada(s)")
    # ⛔ acá antes se logueaba `list(range(_n65))` — o sea 0,1,2… en vez de los números REALES.
    #   Mentía: decía "[0]" cuando estábamos mandando la 965. Casi me hace diagnosticar mal.
    log("LOBBY", f"  ★★★★ FF65: {_n65} instancia(s) del tipo {_t65} -> nº "
                 f"{[a & 0x7FF for a in _vistos]}  (A = {[hex(a) for a in _vistos]})")


def _ocupante_espectador(con, incluir12=False):
    """El dict de `FF0C` de un ESPECTADOR: su personaje, en su slot de mirar (6..11).
    ★ 14-oct · sala de 12: el de 12..17 sólo con `incluir12` — se le manda SÓLO a los espectadores: el cliente se busca
    a sí mismo en el padrón (0x4440A0 → +0xC3 «soy espectador» → C01); sin su FF0C no se encuentra, cree que es un
    corredor más con el lugar 12 y se cae (ESPECTADOR_12.md). A los jugadores no (su sala de 12 lugares)."""
    from .medallas import medalla_puesta                                  # noqa: PLC0415
    _se = getattr(con, "slot_espectador", None)
    if _se is None or (_se >= 12 and not incluir12):   # ★ 14-oct: el de la sala de 12 (12..17): sólo a espectadores
        return None
    ch = db_get_char(getattr(con, "usn", 0)) or {}
    cid = ch.get("char_id", 0x0001FF54)
    return {"usn": getattr(con, "usn", 0), "char_id": cid, "parts": parts_visibles(ch),
            "nick": ch.get("nick", ""), "guild": ch.get("guild", ""),
            "texto_cabeza": ch.get("guild", ""),        # ★ el círculo (`FF0C cola[4]`, 24-sep)
            "circulo_insignia": _insignia(getattr(con, "usn", 0), ch),   # ★ marca y nivel (25-sep)
            "color_apodo": _color_apodo(getattr(con, "usn", 0), ch),     # ★ el lápiz del apodo
            "identity": _se, "slot": _se, "equipo": 0,
            # ★ el ÍCONO del que mira: `gacha.sexo`, no el último dígito (2026-09-09). Se corrigió
            #   en los cuatro paquetes y el ocupante ESPECTADOR quedó afuera — el que mira con un
            #   personaje del gacha puesto salía con el distintivo cambiado. Quinto sitio.
            "exp": int(ch.get("exp", 0) or 0), "gender": sexo(cid),
            "mision": int(ch.get("mission", 0) or 0),
            "licencia": int(ch.get("licencia", 0) or 0),
            "marco": _marco_de(ch),
            "tarjeta": _tarjeta_de(ch),
            "medalla": medalla_puesta(getattr(con, "usn", 0)),
            "mision_nibbles": list(ch.get("mision_nibbles") or [])}


def _marco_de(ch):
    from .catalogo import marco_puesto                                     # noqa: PLC0415
    return marco_puesto((ch or {}).get("parts"))[0]


def _tarjeta_de(ch):
    from .catalogo import tarjeta_puesta                                   # noqa: PLC0415
    return tarjeta_puesta((ch or {}).get("parts"))


def _clave_del_ff11(data):
    """La contraseña del `FF11`: `@7` = largo, `@8` = las letras (0 = sin contraseña)."""
    n = data[7] if len(data) > 7 else 0
    return bytes(data[8:8 + n])


def h_18_ff11(st, cmd, data):
    # rama original:  cmd == 17
    # REQ medido en vivo (13B): [A:u16][0xFFFFFFFF:u32][01 00:u16][5B en cero]
    #   A = el MISMO u16 de la lista: el Nº de sala está en los 11 bits bajos (`A & 0x7FF`);
    #   los bits altos se los pone el cliente (no son los que mandamos nosotros).
    #
    # ⚠ **[H] EL BYTE @6 DIFIERE SEGÚN DE DÓNDE VENGAS** — anotado el 2026-09-12, SIN RESOLVER:
    #       desde la lista de salas  ->  @6 = 1
    #       con «Jugar Juntos»       ->  @6 = 0
    #   Hoy **todo funciona con los dos valores** y no lo miramos: el arreglo del auto-join fue
    #   por otro lado (el 2º byte de la RESPUESTA, ver más abajo).
    #   ★ La hipótesis es de anonimo03 y queda COMO HIPÓTESIS, no como hecho: *"ese puede ser
    #     realmente de la función de VISITAR A UN AMIGO"*. Encaja con que Mi Casa (tipo 11)
    #     aparece en este mismo camino y está excluida a propósito del «Jugar Juntos»
    #     (`0x44D5B6: and eax,0xF800 / cmp eax,0x5800 / je -> no mostrar el botón`).
    #   ⇒ Es el primer lugar donde mirar si aparece algo raro al entrar a salas, y el punto de
    #     partida si algún día se implementa visitar la casa de un amigo. **No lo des por cierto.**
    # RESP (parser 0x5CD8D0) = ★ SOLO 2 BYTES: [slot:u8][b:u8]
    # ★★★ TABLA COMPLETA, MEDIDA DEL DISASM 2026-08-05 (cadena de `cmp` plana, sin jump table).
    #   El byte0 **ES** el slot: el cliente hace `me+0x40 = byte0`.
    #     0x00-0x0B  ENTRA (slot 0..11)
    #     0xFD       ENTRA, pero sólo si pasa el gate 0x49F980 ([[0x9314AC]+0x1951]==5)
    #     0x14       no hace nada
    #     0x0E  popup id 442 = "contraseña incorrecta"
    #     0x0F  popup id 548 = "No hay lugares suficientes en la sala."   <- el de SALA LLENA
    #     0x10  popup id 519 = "¿Desea ser espectador?" (2 botones + pedido de vuelta 0x4A1700)
    #     0x11  popup id 549 = el círculo no se parece
    #     0x15  popup id  84 = nivel no adecuado
    #     0xFE  popup id 493 = limitaciones de nivel
    #     resto (0x0C,0x0D,0x12,0x13,0x16-0xFC,0xFF) -> popup id 65 genérico "No se puede entrar…"
    #   ⛔ CORRECCIÓN de la nota vieja: **0x07 NO es "no hace nada"** — el `cmp al,7` existe pero es
    #      CÓDIGO MUERTO, porque el `cmp al,0x0C / jb ENTRA` de antes ya lo atrapó. 0x07 ENTRA.
    _a   = struct.unpack("<H", data[0:2])[0] if len(data) >= 2 else 0
    _rid = _a & 0x7FF
    # ★★★★★ 2026-08-05 — `A = (TIPO << 11) | numero`, y el 2º BYTE DE LA RESPUESTA **ES EL TIPO**.
    #   MEDIDO: el ACK entra por `0x5CD150`, que hace `SetRoomType(byte1)` -> `0x58D3D0`:
    #       movzx eax, byte [esp+4] ; xor eax, 0x1FEF ; mov [cRoom+0x957C], eax
    #   y después TODO el juego lee `byte[cRoom+0x957C] ^ 0xEF`:
    #       0x0B = MI CASA   ·   0x0C = sala de charla del CÍRCULO   ·   ★ 0x0D = SALA DE CARRERA
    #   ⛔⛔ ACÁ DECÍA "0x0C = sala de carrera", Y ERA FALSO — corregido el 2026-09-12. Lo tumban
    #      tres cosas independientes: `TIPOS_LUGAR_CHARLA` incluye el 12; el rótulo de unas líneas
    #      abajo dice `{12: "charla EN CÍRCULO"}`; y **ningún `FF11` real trae 12** (los medidos en
    #      los logs traen 13 desde la lista de salas y 2 desde un lugar). El error estuvo meses sin
    #      hacer nada porque el único camino que usaba ese valor no existía todavía; lo destapó
    #      «Jugar Juntos». ⇒ Si volvés a leer "0x0C" como sala de carrera, mirá primero un FF11 real.
    #   ⛔ Nosotros mandábamos **byte1 = 0 SIEMPRE** ⇒ el tipo de sala quedaba en 0 y los ~7
    #      sitios del cliente que preguntan "¿estoy en una sala de carrera?" veían que NO.
    #      Es el mismo `957C^EF` que volcamos cuando peleábamos el modo de sala y daba 0: no
    #      estaba vacío por casualidad, nunca lo llenamos.
    #   La respuesta segura es **devolver el mismo tipo que pidió el cliente**.
    _tipo = (_a >> 11) & 0x1F
    _sala = buscar_sala(_rid)
    # ★★ LUGARES ESPECIALES (tipo 5..12): Sala de Conversación, Mi Casa y charla de Círculo.
    #   El número lo hornea el CLIENTE (tabla en `cChatRoom.cpp`), así que estas "salas" NO están
    #   ni tienen por qué estar en nuestra lista del FF6E: el camino FF11 -> ACK -> SetRoomType
    #   no la consulta. Alcanza con aceptar y devolver el tipo.
    #     5..10 = Sala de Conversación (libre + los 5 grupos de país)
    #     11    = casa de un jugador (el FF11 trae el NICK del dueño al final)
    #     12    = charla EN CÍRCULO (el cliente ya chequeó local que tengas círculo)
    if _sala is None and 5 <= _tipo <= 12:
        _quien = ""
        if _tipo == 11 and len(data) > 13:
            _n = data[13]
            _quien = f" de {data[14:14 + _n].decode('cp1252', 'replace')!r}"
        _nombre_tipo = {11: "MI CASA", 12: "charla EN CÍRCULO"}.get(_tipo, "Sala de Conversación")
        # ★ se recuerda DÓNDE está para que el FF13 que viene enseguida no le arme una sala de
        #   carrera encima (síntoma: "mitad casa, mitad pantalla de jugar, con botón de Listo").
        # ★★ UNIRSE a la instancia PERSISTENTE (existe desde que arrancó el server), en vez de
        #   inventar una sala nueva en cada entrada. El slot sale de la ocupación real.
        # ★★ SALA DE CONVERSACIÓN COMPARTIDA (24-sep, `charla.py`): el botón pide 965..969 y se
        #   traduce a la estancia 1..N con lugar; el `A` que vuelve (FF11/FF61/FF13) es el de ESA
        #   estancia, y el título sale «Libre 1», «PE 2»… (anonimo03: *"no usaremos 965"*).
        from . import charla
        if CHARLA_COMPARTIDA and charla.es_publica(_tipo):
            _n_ch = charla.numero_para(_tipo, _rid)
            _slot_lug = charla.entrar(st, _tipo, _n_ch) if _n_ch is not None else None
            if _slot_lug is not None:
                _rid = _n_ch
                _a = ((_tipo & 0x1F) << 11) | (_n_ch & 0x7FF)
        elif charla.es_del_circulo(_tipo):
            # ★★ LA SALA DEL CÍRCULO (25-sep): la estancia es SU círculo (el 970 es de todos). El
            #   `A` que vuelve es el que pidió. Sin círculo no entra (el cliente ya lo chequea,
            #   pero su dato puede estar viejo: lo echaron mientras tanto).
            _cid = charla.circulo_de(st)
            if _cid is None:
                # 0x11 = el popup 549 del propio cliente para esto (la tabla de arriba)
                st.send_ff55(0x11, bytes([0x11, _tipo]),
                             name=f"FF11 sala del círculo: usn={getattr(st, 'usn', 0)} SIN círculo -> popup 549")
                log("LOBBY", f"  ⚠ FF11: usn={getattr(st, 'usn', 0)} pidió la sala del círculo y no tiene círculo")
                return
            _slot_lug = charla.entrar(st, _tipo, _cid)
            if _slot_lug is not None:
                # ★ el título lo arma el cliente: «<círculo><nº>» (`0x5CD675`, `"%s%d"`)
                _rid = CIRCULO_SALA_NUMERO
                _a = ((_tipo & 0x1F) << 11) | (_rid & 0x7FF)
                log("LOBBY", f"  💬 sala del círculo #{_cid}: usn={getattr(st, 'usn', 0)} -> slot {_slot_lug}")
        else:
            _slot_lug = entrar_lugar(st, _tipo, _rid)
        if _slot_lug is None:
            st.send_ff55(0x11, bytes([0x0F, _tipo]),
                         name=f"FF11 lugar tipo={_tipo} nº{_rid} LLENO ({LUGAR_CAPACIDAD}) -> popup 548")
            log("LOBBY", f"  ⚠ FF11: la instancia (tipo={_tipo}, nº={_rid}) está LLENA")
            return
        st.lugar_tipo = _tipo
        st.lugar_num  = _rid
        st.lugar_a    = _a
        st.lugar_quien = _quien.replace(" de ", "").strip("'") if _quien else ""
        st.room_id = None
        st.send_ff55(0x11, bytes([_slot_lug & 0xFF, _tipo]),
                     name=f"FF11 lugar especial tipo={_tipo} nº{_rid} ({_nombre_tipo}{_quien}) "
                          f"-> slot {_slot_lug} de {charla.cupo(_tipo) if charla.es_compartida(_tipo) else LUGAR_CAPACIDAD}")
        # ★★★★★ EL PAQUETE QUE FALTABA: **FF61** (handler cliente `0x5EA420`).
        #   El ACK del FF11 NO alcanza — y no por poco: su propio handler hace
        #       0x5CD196:  mov dword [game+0x9580], 0x1FEF        ⇒ placeId = 0
        #   y `cRoom::LoadStage` (`0x59AB80`) decide la escena con ese `placeId`:
        #       placeId == 0  ->  escena de CARRERA + `rnr_room/random.bmp` (los paneles ALEATORIA)
        #       placeId != 0  ->  **`rnr_ui_bg/2012_club/club_chatting.md9` = LA SALA GRANDE**
        #   El FF61 es el único que lo pone en 1 (`mov [game+0x9580], 0x1FEE`), y de paso fija
        #   el slot (`[0x931660]+0x40`), llama `SetRoomType` y empuja el cambio de escena.
        #   ⇒ Sin FF61 el cliente entra pero se queda en la sala de carrera: grilla de 6 asientos,
        #     paneles ALEATORIA y sin poder moverse. Con él, cambia de escena.
        #   Layout (4 bytes): [A:u16 LE][slot:u8][roomType:u8]
        #   ★ El slot va 0..39 -> la capacidad de estas salas es **40**, no 6 (de ahí la "sala
        #     grande, con mucha capacidad"). 0x28=40 -> popup 65; 0x29..0x2D = errores propios.
        st.send_ff55(0x61, struct.pack("<HBB", _a & 0xFFFF, _slot_lug & 0xFF, _tipo & 0xFF),
                     name=f"FF61 entrar al lugar (placeId=1 -> club_chatting) tipo={_tipo} "
                          f"slot={_slot_lug}")
        log("LOBBY", f"  ★★★★ FF61: placeId=1 ⇒ el cliente carga la SALA GRANDE "
                     f"(club_chatting.md9) en vez de la escena de carrera")
        log("LOBBY", f"  ★★ FF11 LUGAR ESPECIAL: tipo={_tipo} nº={_rid} = {_nombre_tipo}{_quien} "
                     f"-> slot {_slot_lug}, SetRoomType({_tipo})")
        return
    if _sala is None:
        # ⛔ Acá iba 0x0E, que el cliente muestra como **"contraseña incorrecta"** (popup 442) —
        #    mensaje equivocado para una sala que no existe. 0x0C cae en el genérico (id 65)
        #    "No se puede entrar a una sala…", que es lo que corresponde.
        # ★ 2026-09-06 — y se OLVIDA la sala anterior. Si no, el que hace clic en una sala que ya
        #   no está publicada se queda con el `room_id` viejo y el server lo sigue creyendo adentro
        #   de aquélla. Mismo problema que el de "sala llena", de acá abajo.
        st.room_id = None
        st.send_ff55(0x11, bytes([0x0C, 0]), name=f"FF11 ENTERROOM sala {_rid} INEXISTENTE (popup 65)")
        log("LOBBY", f"  ⚠ FF11 ENTERROOM a la sala {_rid}, que no está publicada -> error 0x0C")
    elif CLAVE_SALA.get(_rid) and _clave_del_ff11(data) != CLAVE_SALA[_rid]:
        # ★★ 29-sep — LA CONTRASEÑA. El cliente la manda en el `FF11` (`@7` largo, `@8` letras; lo
        #   arma `0x5E51B0`) después de pedírsela al jugador: la ventana sale sola porque la fila de
        #   la lista trae el bit 0x01 del `B` (`0x4A33F2 cmp byte [fila+0x116],0`).
        #   `0x0E` = el popup ORIGINAL 442, «contraseña incorrecta» (tabla de arriba).
        #   ⚠ «Jugar Juntos» no pasa por esa ventana (manda largo 0): a una sala con clave, tampoco.
        _vacia = not _clave_del_ff11(data)
        st.room_id = None
        st.send_ff55(0x11, bytes([0x0E, _tipo & 0xFF]),
                     name=f"FF11 sala {_rid} CONTRASEÑA INCORRECTA -> popup 442")
        log("LOBBY", f"  🔒 FF11: usn={getattr(st, 'usn', 0)} a la sala {_rid} con contraseña "
                     + ("VACÍA" if _vacia else "INCORRECTA") + " -> popup 442")
    elif GATE_LICENCIA_AL_ENTRAR and not _alcanza_la_licencia(st, _rid):
        # ★★★★★ EL CANDADO DE LA LICENCIA, AHORA NUESTRO — 2026-09-17.
        #   Al subirle el `mi` al cliente para que vea todas las salas, el cliente dejó de frenar
        #   la entrada él mismo (`0x4A84BD` usa la misma `0x484A00` que la lista). Lo frenamos acá.
        #   ★★ Y con el popup ORIGINAL: `0x15` es **el id 84, «Su nivel no es adecuado para esta
        #     sala.»**, según la tabla de respuestas de acá arriba. El jugador ve el cartel de
        #     siempre; lo único que cambió es quién lo decide.
        #   ⇒ Los dos criterios de anonimo03, juntos: *"cualquier usuario, incluso uno novato, debería
        #     poder VER la sala — no no poder entrar (popup)"*.
        # ★ Se olvida la sala, igual que en los otros rechazos: si no, el server lo sigue creyendo
        #   adentro de una sala en la que nunca entró (el bug de «sala llena» del 06-sep).
        st.room_id = None
        st.send_ff55(0x11, bytes([0x15, _tipo & 0xFF]),
                     name=f"FF11 sala {_rid} banda {dificultad_de(_rid)} > licencia de "
                          f"usn={getattr(st, 'usn', 0)} -> popup 84 «nivel no adecuado»")
        log("LOBBY", f"  ★ FF11: la sala {_rid} pide banda {dificultad_de(_rid)} y "
                     f"usn={getattr(st, 'usn', 0)} no la tiene -> popup 84 (el original)")
    else:
        # ★★★ 2026-08-05 — EL QUE ENTRA YA NO RECIBE `HOST_SLOT`.
        #   Antes se le contestaba HOST_SLOT igual que al que creaba ⇒ los dos jugadores se creían
        #   el ocupante 2, cada uno armaba su propio FF0C con él mismo + el NPC, y no se veían.
        #   El slot del que entra lo decide el SERVER y viaja en el byte0 de esta respuesta: el
        #   cliente lo escribe en `me+0x40` (parser 0x5CD8D0).
        _era_demo = SALAS_VIVAS.get(_rid) is None      # los maniquíes de SALAS_DEMO no tienen mesa
        # ★★★★★ NO SE ENTRA A UNA SALA QUE YA ESTÁ CORRIENDO (2026-09-06, visto en producción).
        #   Medido en el log, sala 1, con `cuenta_admin` adentro:
        #       09:10:07  FF24 START -> LOADGAME a 4 jugadores      ← arranca la carrera
        #       09:10:24  FF11 ENTERROOM: 'jugador32' entra al slot 0  ← 17 s DESPUÉS
        #       09:10:24  FF0C x5 a todos                           ← "ha entrado a la partida"
        #       (y esa carrera NUNCA emitió su `FF28 GAMEOVER`: quedó colgada)
        #   Las dos carreras anteriores de esa misma sala sí cerraron. La única diferencia fue el
        #   que entró en el medio.
        #   ⇒ El que llega se sienta en un asiento que la carrera ya repartió, y a los que están
        #     jugando les llega un `FF0C` que **inserta** un ocupante nuevo en plena partida.
        #     Nadie reporta, el cartel espera para siempre, y quedan todos trabados.
        #   ⚠ El código 0x0F dice "no hay lugares suficientes", que no es exacto — pero es el
        #     único rechazo MEDIDO en este cliente, y dejarlo entrar rompe la carrera de todos.
        #     Si algún día se mide un popup de "partida en curso", va acá y es un byte.
        if not _era_demo and sala_en_carrera(_rid):
            st.send_ff55(0x11, bytes([0x0F, 0]),
                         name=f"FF11 ENTERROOM sala {_rid} EN CARRERA -> rechazado")
            log("LOBBY", f"  ⛔ FF11 ENTERROOM: la sala {_rid} está EN CARRERA -> NO entra "
                         f"(entrar a mitad de partida la deja colgada para todos)")
            return
        # ★ los NPC a esquivar son LOS DE LA SALA (antes se usaban los del que entraba, que no
        #   veía los del anfitrión y se le sentaba encima).
        # ★★ ¿VENÍA MIRANDO? Se pregunta ACÁ, antes de sentarlo: `sentar_jugador` borra la marca de
        #   espectador (son excluyentes), así que después ya no hay a quién preguntarle. Sirve para
        #   el camino de vuelta —*"pasar de espectador a jugador"*—: si el cliente lo pide con un
        #   `FF11` normal, esto ya lo deja andando. Y si pide con otro paquete, la sonda del
        #   `handle_inner` lo va a mostrar.
        _venia_mirando = getattr(st, "slot_espectador", None)
        _slot = (HOST_SLOT if _era_demo
                 else sentar_jugador(st, _rid, ocupados_extra=npcs_de(_rid)))
        if _slot is None:
            # ⚠ byte0: en el 2013 **0x00-0x0B ENTRA**, así que los códigos de error del CBT (6 y 9)
            #   acá serían slots válidos. 0x0F está MEDIDO en este cliente = popup id 548
            #   "No hay lugares suficientes en la sala." — justo el mensaje que corresponde.
            # ★★★ 2026-09-07 — Y CON `OFRECER_ESPECTADOR` VA EL **0x10** EN VEZ DEL 0x0F.
            #   El 0x10 saca el popup id 519 — *"No hay lugares vacíos en la sala. ¿Desea ser
            #   espectador del juego en lugar de ello?"* — con DOS BOTONES y un pedido de vuelta
            #   (`0x4A1700`). Estaba medido y anotado en la tabla de arriba desde el 2026-08-05.
            #
            #   ⇒ ES LA PUERTA DEL MODO ESPECTADOR, y la estuvimos buscando por el lado
            #     equivocado: se decide **al entrar**, no estando sentado. Por eso ninguna sonda
            #     sobre el `FF99` movía a nadie a la lista.
            #
            #   ⏳ LO QUE FALTA MEDIR, y es justo lo que este cambio destapa: **qué manda el
            #     cliente cuando el jugador aprieta que SÍ**. Los candidatos son el `FFBA`
            #     (`CmdJoinRoomMassOb`) y el `FFBB` (`CmdUpdateMassObservers`), pero eso el
            #     cliente sólo lo manda DESPUÉS de este cartel — ninguna sonda podía provocarlo.
            #     Va a caer en `SIN handler` y ahí se lee del log.
            # ★★★★★ Y SI YA ACEPTÓ, NO SE LE VUELVE A PREGUNTAR (2026-09-07).
            #   ⛔ El bug que esto arregla, visto en pantalla: el usuario apretaba OK y el popup
            #     salía otra vez, en bucle. El cliente **reenvía el MISMO `FF11`** con un byte
            #     cambiado, y nosotros no lo mirábamos.
            #   ★ MEDIDO comparando los dos pedidos del log, uno al lado del otro:
            #         entrar normal :  01 68 ff ff ff ff 01 00 00 00 00 00 00
            #         tras aceptar  :  01 68 ff ff ff ff 01 00 c0 42 00 00 01
            #                                                             ^^
            #     ⇒ el ÚLTIMO byte (@12) es el flag "entro como ESPECTADOR".
            #   ★ Y la respuesta sale de la tabla que ya teníamos: `0x00-0x0B ENTRA (slot 0..11)`
            #     — DOCE slots, cuando la sala tiene SEIS asientos. Los 6..11 son los de mirar.
            #   ⏳ Esto es la primera vuelta: entra y se le da un slot de espectador. Falta ver en
            #     pantalla si además hay que mandarle el `FF0C`/`FFBB` para que se DIBUJE en la
            #     sección, y si los demás lo ven. Se mide con esto puesto.
            # ★★★★★ EN COOPERATIVO NO SE MIRA — 2026-09-08, la otra mitad del mismo guard.
            #   El usuario lo cazó probando: *"el cliente está capeado, no deja cambiar a modo
            #   cooperativo si hay espectadores… pero desde la LISTA está dejando entrar"*. O sea
            #   que el juego prohíbe **llegar a esa combinación por un lado y no por el otro**, y
            #   nosotros no cerrábamos ninguno de los dos.
            #   ⚠ Es la combinación con la que se cayeron los dos espectadores el 14:53 (ver
            #     `h_25_ff4b`, que tapa la otra mitad: cambiar a cooperativo con gente mirando).
            #   ⇒ Si la sala es cooperativa, ni se ofrece: va el rechazo seco de sala llena, que es
            #     el que el jugador ya conoce.
            _sala_colab = bool(_sala.get("colab", False))
            _quiere_ver = (len(data) >= 13 and data[12] == 1) and not _sala_colab
            if _quiere_ver and OFRECER_ESPECTADOR:
                _ocup_esp = {getattr(c, "slot_espectador", None)
                             for c in CONEXIONES.values() if getattr(c, "room_id", None) == _rid}
                # ★ El orden sale de `ESPECTADOR_SLOTS`, que además es la SONDA del crash: ver su
                #   comentario en `ajustes.py` (el experimento es poner el 8 primero).
                from .salas import asientos_de_la_sala as _asientos_esp
                _slots_esp = ESPECTADOR_SLOTS_12 if _asientos_esp(_rid) == 12 else ESPECTADOR_SLOTS   # ★ 14-oct
                _se = next((s for s in _slots_esp if s not in _ocup_esp), None)
                if _se is not None:
                    # ★★ Igual que en la rama del que se sienta: se lo levanta de la sala anterior
                    #   recién con el casillero conseguido. ⚠ ANTES de escribir `slot_espectador`,
                    #   porque `sacar_de_la_sala_anterior` lo pone en None al terminar (las dos
                    #   marcas son excluyentes) y le borraría el que acaba de recibir.
                    sacar_de_la_sala_anterior(st, f"mirar la sala {_rid}", menos=_rid)
                    st.slot_espectador = _se
                    # ★ El TIPO de sala que pidió el cliente: se guarda para poder contestarle el
                    #   `FF11` más adelante sin inventarlo (lo usa el `FF99` de cambiar de puesto).
                    st.room_tipo = _tipo
                    # ★★★★ Y SE LE BORRA EL ASIENTO VIEJO — 2026-09-08, EL BUG DEL AVATAR QUE CAMINA.
                    #   ⛔ Reportado: *"los que entran de espectador se están moviendo en la sala,
                    #     NO TODOS pero algunos sí, como si estuvieran en la sala"*.
                    #   `st.room_slot` lo escribe `sentar_jugador` y sólo lo borra `levantar_jugador`.
                    #   El que entra a MIRAR nunca se sienta ⇒ se quedaba con el asiento de la sala
                    #   ANTERIOR colgado, y el relevo del `FF23` (movimiento en sala) firma con
                    #   `st.room_slot or HOST_SLOT`. O sea: el espectador caminaba y el server le
                    #   movía a los demás el avatar de ESE asiento.
                    #   ★ Y ahí está el *"no todos"*, que es el dato que lo delató: dependía de lo que
                    #     cada conexión traía de antes — el que venía de un asiento pisaba un avatar
                    #     real, el recién conectado caía en `HOST_SLOT` y movía al anfitrión. No era
                    #     un campo mal puesto: era ESTADO VIEJO. Van cinco veces con el mismo molde
                    #     (estado de la conexión que en realidad es de la sala).
                    from .charla import salir as _salir_charla
                    _salir_charla(st, "se fue a una sala de carrera")   # ★ el asiento y el FF0E en la charla
                    st.room_slot = None
                    st.lugar_tipo = None
                    st.room_id = _rid
                    st.sala_poblada = None   # ★ todavía no pidió la lista: ver `salas.difundir_ocupante`
                    st.room_name = _sala.get("nombre", "sala")
                    # ★★ EL ESTADO DE LA SALA, IGUAL QUE AL QUE SE SIENTA (2026-09-07).
                    #   ⛔ Reportado: *"los que entran ven el modo incorrecto, item + solo, cuando
                    #     cree la sala como equipo + velocidad"*. Acá se le daba `room_id` y
                    #     `room_name` y nada más, así que el modo le quedaba en el DEFAULT. El
                    #     espectador mira la misma partida: tiene que ver la misma sala.
                    st.room_mode  = _sala.get("flags", MODE_VELOCIDAD)
                    st.room_colab = bool(_sala.get("colab", False))
                    st.room_boss  = bool(_sala.get("boss", False))
                    _cod_se = (ESPECTADOR12_CODIGO + _se - 12) if _se >= 12 else _se    # ★ 14-oct: sala de 12
                    st.send_ff55(0x11, bytes([_cod_se & 0xFF, _tipo]),
                                 name=f"FF11 ENTERROOM sala {_rid} como ESPECTADOR (slot {_se}, código 0x{_cod_se:02X})")
                    # ★ Y los paquetes que pintan la sala. El `FF13` lleva el modo y la pista; el
                    #   `FF0C` los ocupantes; el `FFBB` prende la sección de espectadores (lee un
                    #   u32 y con > 0 hace `[cRoom+0xC1C] = 1`, ver su handler `0x5D7EC0`).
                    #   ⏳ Que esto ALCANCE para que la sección se dibuje es lo que falta medir.
                    enviar_roominfo(st, motivo=" (espectador)")
                    enviar_userlist(st)
                    # ★ El que entra a MIRAR ve el mismo cartel al final, así que le importa la
                    #   misma regla. ⚠ DEMORADO igual que los otros dos: ver la nota del `FF0C`.
                    st.pd_por_contar = (_rid, False)
                    # ★★★★ LOS EQUIPOS Y LOS CAPITANES, IGUAL QUE A CUALQUIERA (2026-09-08).
                    #   El espectador entra a una sala que ya puede estar en modo jefe con los
                    #   capitanes sorteados, y sin esto su padrón queda VACÍO. Y un cliente cuyo
                    #   `FindCaptain` no encuentra capitán devuelve `0xFF` y **se cae** — está
                    #   escrito en `difundir_capitanes` desde el 2026-09-07 y es el candidato nº1
                    #   del crash reportado: *"cargó la escena fija correcta, pero crashea"*.
                    try:
                        enviar_equipos(st, _rid)
                    except Exception as _e_eq:
                        log("LOBBY", f"  ⚠ no pude pintarle los equipos al espectador: {_e_eq!r}")
                    _esp = espectadores_de(_rid)
                    # ★★ EL CONTADOR VA A TODA LA SALA, no sólo al que llega (2026-09-08).
                    #   Antes el `FFBB` salía únicamente para el recién llegado ⇒ los demás nunca
                    #   se enteraban de cuántos miraban, y la fila del lobby tampoco. Además
                    #   refresca el `E`/`F` del `FF6E`, que es el corchete de la lista de salas.
                    difundir_espectadores(_rid, motivo=" (entró uno a mirar)")
                    # ★★ Y EL INTENTO DE POBLAR LA LISTA (2026-09-08). El `FFBB` sólo prende la
                    #   bandera (`[cRoom+0xC1C]=1`): no lleva QUIÉNES son. La apuesta es que el
                    #   `FF0C` sirva igual, porque **inserta por slot** y el `FF11` acepta slots
                    #   0..11 — o sea que el cliente tiene DOCE, y los 6..11 son los de mirar.
                    #   ⏳ Si la sección sigue vacía, el `FF0C` no es el camino y hay que buscar
                    #     el paquete propio de la lista. Queda anotado para no repetir el intento.
                    for _e in _esp:
                        _oc = _ocupante_espectador(_e, incluir12=True)
                        if _oc is None:
                            continue
                        for _c in conexiones_en_sala(_rid):
                            if (_oc["slot"] >= 12 and getattr(_c, "slot_espectador", None) is None
                                    and not ESPECTADOR12_A_CORREDORES):
                                continue                     # ★ 14-oct: el de 12+ sólo a los que miran (17-oct: a todos)
                            _c.send_ff55(0x0C, build_ff0c_2013_real(_oc, k=2),
                                         name=f"FF0C espectador {_oc['nick']!r} slot {_oc['slot']}")
                    log("LOBBY", f"  ★★★ FF11 ESPECTADOR: usn={getattr(st, 'usn', None)} entra a "
                                 f"mirar la sala {_rid} en el slot {_se} (6..11 = los de mirar). "
                                 f"⏳ Si no se dibuja en la sección, falta el FF0C/FFBB.")
                    return
                log("LOBBY", f"  ⚠ FF11 ESPECTADOR: no quedan slots de mirar (6..11) en la sala {_rid}")
            _cod11 = 0x10 if (OFRECER_ESPECTADOR and not _sala_colab) else 0x0F
            if _sala_colab:
                log("LOBBY", f"  ⛔ FF11: la sala {_rid} es COOPERATIVA -> NO se ofrece mirar "
                             f"(esa combinación es la que tiró a los dos espectadores el "
                             f"2026-09-08 14:53). Va el rechazo de sala llena.")
            st.send_ff55(0x11, bytes([_cod11, 0]),
                         name=f"FF11 ENTERROOM sala {_rid} LLENA -> 0x{_cod11:02X} "
                              + ("(¿ser espectador?)" if _cod11 == 0x10 else "(popup 548)"))
            log("LOBBY", f"  ⚠ FF11 ENTERROOM: la sala {_rid} está llena -> popup 0x{_cod11:02X} "
                         + ("★ OFRECIDO ESPECTADOR: mirá qué manda el cliente si acepta "
                            "(candidatos FFBA/FFBB) " if _cod11 == 0x10 else "")
                         + "(NO se le anota la sala: rebotó, sigue en el lobby)")
        else:
            # ★★★★ 2026-09-06 — EL ESTADO DE LA CONEXIÓN SE ESCRIBE **ACÁ**, DESPUÉS DE TENER SILLA.
            #   Estas seis líneas estaban ARRIBA del `sentar_jugador`, o sea que se anotaban antes
            #   de saber si había lugar — y en la rama de "sala llena" nadie las deshacía. El que
            #   rebotaba veía el cartel y se quedaba en el lobby, pero para el server seguía
            #   ADENTRO de esa sala: sin asiento en la mesa, con `room_id` apuntando ahí.
            #   Consecuencia medida en el camino de desconexión (`lobby.py`) y en el `FF12`: los dos
            #   leen `st.room_id`, así que al irse disparaba `difundir_salida` + `difundir_userlist`
            #   sobre una sala AJENA — y `difundir_userlist` re-manda la lista COMPLETA (un `FF0C`
            #   por ocupante a cada ocupante, y en este cliente el FF0C **inserta**). De ahí los
            #   "X ha entrado a la sala" con nombres que no correspondían, incluso en plena carrera.
            #   ★ Mover esto es seguro: `sentar_jugador` usa `st.usn` y `npcs_de` recibe el rid por
            #     parámetro. Ninguno de los dos lee lo que se movió.
            # ★★★★★ Y SE LO LEVANTA DE LA SALA ANTERIOR — 2026-09-15, arreglo de las SALAS FANTASMA.
            #   Va ACÁ, con la silla ya conseguida, y no arriba: si el `sentar_jugador` hubiera
            #   fallado (sala llena) lo habríamos sacado de su sala para dejarlo en el limbo.
            #   ⚠ `menos=_rid` es imprescindible: sin eso se saca de la mesa en la que **acaba** de
            #     sentarse, y el jugador queda invisible en su propia sala — el mismo daño que este
            #     arreglo viene a evitar, cometido por el arreglo.
            sacar_de_la_sala_anterior(st, f"entrar a la sala {_rid}", menos=_rid)
            from .charla import salir as _salir_charla
            _salir_charla(st, "se fue a una sala de carrera")   # ★ el asiento y el FF0E en la charla
            st.lugar_tipo = None      # ★ vuelve a una sala de carrera: se olvida el lugar especial
            st.room_tipo  = _tipo     # ★ para poder re-contestar el FF11 (ver `h_ff99_cambiar_de_puesto`)
            st.room_id    = _rid
            st.room_name  = _sala.get("nombre", "sala")
            st.room_mode  = _sala.get("flags", MODE_VELOCIDAD)
            st.room_colab = bool(_sala.get("colab", False))
            st.room_boss  = bool(_sala.get("boss",  False))
            # ★ Y se le APAGA el NPC: si no, el fantasma le ocupa la silla al jugador de verdad.
            st.ghost      = NPC_IN_ROOM and _era_demo
            # ★★★★★ EL 2º BYTE ES EL **TIPO DE SALA**, Y EL DEFAULT ESTABA MAL — 2026-09-12.
            #   Lo destapó «Jugar Juntos»: el que se unía veía el escenario equivocado (anonimo03:
            #   *"es como si estuviera aterrizando en Mi Casa de ese usuario"*) y al salir la
            #   lista de salas le salía vacía. **Los dos síntomas eran este byte.**
            #
            #   ⛔ El default era `0x0C`, y **`0x0C` NO es "sala de carrera"** — el comentario de
            #     más arriba lo decía y era falso. Lo refutan tres cosas de nuestro propio código:
            #       · `TIPOS_LUGAR_CHARLA = (5,6,7,8,9,10,12)`  -> el 12 es un LUGAR DE CHARLA
            #       · `{11: "MI CASA", 12: "charla EN CÍRCULO"}` (unas líneas más arriba)
            #       · y ningún `FF11` real trae 12: los medidos traen **13** y **2**
            #
            #   ★★ POR QUÉ NUNCA FALLÓ ANTES: en la entrada normal **el cliente manda el tipo él
            #     mismo** en el `A` del pedido (medido sobre TODOS los FF11 de los logs:
            #         desde la lista ->  A = 0x6801 (tipo 13)  ·  A = 0x1001 (tipo 2)
            #         auto-join      ->  A = 0x0001 (tipo  0)  <- ★ el ÚNICO que cae en el default
            #     ) ⇒ el `or` **jamás se evaluaba**. El default existía para un camino que hasta
            #     el «Jugar Juntos» no existía. Molde exacto de *"el bug que no falla"*.
            #
            #   ⇒ Va **0x0D (13)**, que es lo que trae la entrada normal que SÍ funciona. No es un
            #     número elegido: es copiar el caso bueno.
            st.send_ff55(0x11, bytes([_slot & 0xFF, _tipo or 0x0D]),
                         name=f"FF11 ENTERROOM OK sala {_rid} {st.room_name!r} -> slot {_slot} "
                              f"(tipo {_tipo or 0x0D})")
            log("LOBBY", f"  ★★ FF11 ENTERROOM: entra a la sala {_rid} {st.room_name!r} "
                         f"(modo=0x{st.room_mode:02X}) en el slot {_slot}. Mesa: {mesa_de(_rid)}")
            # ★★ AVISARLE A MIS AMIGOS DÓNDE ESTOY AHORA. Sin esto, para ellos sigo en el
            #   vestíbulo — y el cliente ESCONDE el botón «Jugar Juntos» de quien está ahí
            #   (`0x44D480`). Era el *"funciona una o dos veces"* que reportó anonimo03.
            _avisar_ubicacion(st, "entró a una sala")
            # ⛔⛔ ACÁ IBA EL CARTEL/ENLACE DE PAREJA, Y ERA DEMASIADO PRONTO — sacado el
            #   2026-09-12. El `FF48` lleva el enlace adentro y llegaba **antes** del `FF0C` que
            #   dibuja al recién llegado, así que el cliente no lo encontraba por nombre y
            #   terminaba **estampándole «soltero» al que YA estaba**. No se perdía: borraba.
            #   ⇒ Ahora va pegado al `FF0C`, en la línea siguiente: `salas.difundir_ocupante`.
            # ★★★ EL QUE VENÍA MIRANDO Y SE SIENTA: hay que SACARLO de la sección de espectadores.
            #   El `FF0C` sólo inserta ⇒ sin esto quedaría dibujado en los dos lados a la vez, en su
            #   asiento nuevo y en el casillero de mirar. El único que borra es el `FF0E`, por
            #   nombre (ver `difundir_salida`), y el `FFBB` deja el contador al día.
            #   ⏳ Esto es el camino de vuelta *"pasar de espectador a jugador"*, servido para
            #     cuando el cliente lo pida por `FF11`. Si resulta que lo pide con otro paquete, la
            #     sonda de `handle_inner` lo va a mostrar y sólo hay que enrutarlo hasta acá.
            if _venia_mirando is not None:
                _nkv = str((db_get_char(getattr(st, "usn", 0)) or {}).get("nick", "") or "")
                _crv = _nkv.encode("cp1252", "replace")[:NICK_MAX_FF0E]
                if _crv:
                    # ⚠ A ÉL NO: el `FF0E` borra por NOMBRE y se borraría a sí mismo de su propia
                    #   sala. Más abajo va `difundir_userlist(menos=st)`, así que tampoco habría
                    #   quién se la reponga. Misma nota que en `h_ff99_cambiar_de_puesto`.
                    for _cv in conexiones_en_sala(_rid):
                        if _cv is st:
                            continue
                        _cv.send_ff55(0x0E, bytes([len(_crv)]) + _crv,
                                      name=f"FF0E sacar {_nkv!r} de los espectadores (pasa a jugar)")
                difundir_espectadores(_rid, motivo=" (uno pasó de mirar a jugar)")
                log("LOBBY", f"  ★★★ DEJA DE MIRAR: usn={getattr(st,'usn',None)} pasa del "
                             f"casillero {_venia_mirando} al ASIENTO {_slot} de la sala {_rid}")
            if not _era_demo:
                # ★★★★ ANTES DE DIBUJARLO, LIBERAR SU ASIENTO — 2026-09-08.
                #   El `FF0C` **crea si el asiento está libre y si no, se va sin hacer nada**. Si
                #   algún cliente se quedó con ese asiento sucio (un ocupante viejo que no borró),
                #   al que entra **no lo dibuja NUNCA**, y re-mandarle la lista no lo arregla.
                #   ⇒ Se manda primero el `FF0E` del anterior. Ver `salas.liberar_asiento`.
                liberar_asiento(_rid, _slot, motivo=" (entra alguien nuevo)")
                # ★ El que YA estaba se entera acá: se le re-manda el FF0C con los dos adentro.
                #   (No se manda FF13, y ahora se sabe por qué: reenviarlo BORRABA el modo, porque
                #    nuestro FF13 mandaba @8 = 0. Con el @8 puesto ya no borra nada — pero igual no
                #    hace falta reenviarlo acá, así que se deja como está.)
                # ★★★ SÓLO EL QUE ENTRÓ, no la lista entera (2026-09-12).
                #   ⛔ Acá iba `difundir_userlist`, que le manda a cada uno **todos** los
                #     ocupantes. Con 5 adentro, cada cliente recibía 5 `FF0C` de los cuales 4 eran
                #     de gente que ya tenía — y el cliente saca *"%s ha entrado a la sala de
                #     juego."* por cada uno que procesa.
                #   ⇒ anonimo03 lo vio como spam de carteles **con nombres de otros**: *"hay 5
                #     jugadores, entra 1 nuevo, sólo el nombre de él debería aparecer"*.
                #   ★ Y de paso el tráfico de entrar baja de N² a N.
                if FF0C_SOLO_EL_QUE_ENTRA:
                    difundir_ocupante(_rid, getattr(st, "usn", 0), menos=st)
                else:
                    difundir_userlist(_rid, menos=st)
                actualizar_ocupantes_sala(_rid)   # el contador de la lista del lobby
                # ★★★★ 2026-08-05 — Y DETRÁS DEL FF0C, EL COLOR DE EQUIPO DEL RECIÉN LLEGADO.
                #   `0x5938F0` sólo asigna equipo a asientos que YA están en el mapa, así que al
                #   nuevo hay que pintarlo DESPUÉS del FF0C que lo inserta.
                #   ⛔ Acá se mandaba un `FF4B` a cada uno — andaba, pero re-aplicaba el modo de
                #      sala ENTERO para pintar un asiento. Ahora va el `0x99`, que es el paquete
                #      nativo de evento de asiento y toca sólo lo que se le pide (ver enviar_equipos).
                for _u11 in mesa_de(_rid).values():
                    _c11 = CONEXIONES.get(_u11)
                    if _c11 is not None and not getattr(_c11, "cerrado", False):
                        _c11.room_mode = getattr(st, "room_mode", 0)   # el modo lo manda la sala
                        # ★ Y el JEFE también, que no viaja en `room_mode` sino aparte (cola+44 del
                        #   FF13). Sin esto, `sala_por_equipos` daba False en las copias y el modo
                        #   jefe se quedaba sin pintar los asientos.
                        _c11.room_boss = bool(getattr(st, "room_boss", False))
                        enviar_equipos(_c11, _rid)
                # ★★★ Y LOS CAPITANES, AL QUE ACABA DE ENTRAR (2026-09-07).
                #   ⛔ Bug reportado: *"al crear la sala, los que van entrando ninguno recibe
                #     capitán"*. El sorteo se hacía al cambiar de modo, pero el que entraba
                #     DESPUÉS no se enteraba: `difundir_capitanes` sólo había corrido para los que
                #     estaban en ese momento.
                #   ⚠ No es cosmético: el padrón de capitán es de CADA cliente. El que no lo
                #     recibe tiene `FindCaptain` devolviendo `0xFF`, y **ese** cliente se cae al
                #     arrancar (índice 255 de un vector de 6). Ver `jefe_puede_arrancar`.
                #   ⚠ Se REEMITE lo que ya hay, no se re-sortea: sortear acá haría saltar el
                #     distintivo cada vez que entra alguien, que es justo lo que se quería evitar.
                #   ⚠⚠ La condición es `hay_capitanes` (= los DOS equipos), no "hay alguno". Con
                #     el creador solo en la sala el sorteo devuelve UN capitán —el suyo— y si eso
                #     contara como "ya está", al entrar el segundo su equipo se quedaría SIN
                #     capitán para siempre. Que es exactamente el crash que esto evita.
                if getattr(st, "room_boss", False):
                    if not hay_capitanes(_rid) and JEFE_SORTEAR_CAPITAN:
                        sortear_capitanes(_rid)
                    _caps11 = capitanes_de(_rid)
                    if _caps11:
                        difundir_capitanes(_rid, _caps11, motivo=" (entró alguien a la sala)")
                # ★★★ Y LAS REGLAS DE LA SALA, AL QUE ACABA DE ENTRAR — 2026-09-14.
                #   ⛔ Reportado por anonimo03: *"cuando cambiamos el pd, el jugador que ya está en la
                #     sala es notificado, pero el que recién entró no se entera del estado del pd"*.
                #     El aviso salía en el MOMENTO del cambio ⇒ el que llegaba después jugaba con
                #     una regla que nadie le dijo, y se enteraba mirando un número raro al final.
                #   ⚠ Va ÚLTIMO a propósito: el chat tiene que llegar con la sala ya dibujada.
                #   ⚠ Y va sólo a él (`avisar_a_uno`): repetírselo a los que ya estaban sería
                #     ruido en el chat cada vez que entra alguien.
                # ⛔⛔ ACA IBA LA LLAMADA DIRECTA, Y ERA UNA CARRERA — 14-sep, visto en pantalla.
                #   La primera prueba anduvo y la segunda NO, sin cambiar una línea de este
                #   camino: el `FF08` sale ANTES de que el cliente pida dibujar la sala, así que
                #   **depende de si el cliente alcanzó a cambiar de pantalla**. Cuando no llega,
                #   el chat cae en la ventana del vestíbulo y ésa se destruye al entrar.
                #   ★ Es el mismo problema que tenía el que CREA la sala, y ya está resuelto:
                #     se anota y se manda al final del `FF0C`, que es lo último que el cliente
                #     pide para armarla. Si está pidiendo a quién dibujar, el chat ya existe.
                #   ⇒ Un camino menos que depende de la suerte. Ver `la-maquina-lenta-ve-las-carreras`.
                st.pd_por_contar = (_rid, False)


def enviar_roominfo(st, motivo=""):
    """Arma y manda el `FF13` de la sala a UNA conexión.

    Estaba en línea dentro de `h_19_ff13`, que además manda el `FFC9` y el `FF4B`. Se saca
    acá porque ahora hay que reemitir el `FF13` **solo**, cuando cambia la pista o la
    canción: reusar el handler entero dispararía el `FF4B` en cada cambio, y ése abre el
    cartel "el modo de juego ha cambiado".

    ⚠ El paquete NO es idéntico para todos: la `banda` del filtro del picker sale del nivel
      de cada jugador (ver `build_ff13_2013` @2). Por eso se arma por destinatario y no una
      vez para toda la sala.
    """
    _modo  = getattr(st, "room_mode", 0)
    # ★★★ LA DIFICULTAD DE LA SALA MANDA SOBRE LA DEL JUGADOR (2026-09-07).
    #   Si alguien tocó el interruptor (`FFC9`), ese valor es de LA SALA y lo tienen que ver todos
    #   igual. Recién si nadie lo tocó se cae en la banda del que pregunta, que es como venía.
    #   Sin esto, el que elige la dificultad la ve cambiada y el resto no: el mismo error de la
    #   pista y la canción. Ver `salas.DIFICULTAD_SALA`.
    _banda = dificultad_de(getattr(st, "room_id", None))
    if not _banda:
        _banda = licencia_actual(getattr(st, "usn", 0))[1]
    _rid13 = getattr(st, "room_id", None) or 1
    _colab13 = bool(getattr(st, "room_colab", False))
    _boss13  = bool(getattr(st, "room_boss",  False))
    _bymode13 = 0 if (_colab13 or _boss13) else calc_bymode(_modo)
    # ★★ 29-sep: bit 0x01 = SALA CON CONTRASEÑA — el candadito de arriba, adentro de la sala. Medido en el
    #   referente: dos salas creadas con clave `1234` reciben el FF13 con @8 = 0x11 (equipo 0x10 + 0x01);
    #   las sin clave, 0x10 / 0x00. Es la misma codificación que el `B` de la lista (bit 0x01 = candado).
    if CLAVE_SALA.get(_rid13):
        _bymode13 |= 0x01
    _sel = seleccion_de(getattr(st, "room_id", None))
    # ★★★★ EL `@6` ES EL ASIENTO DEL ANFITRIÓN **DE LA SALA** (2026-09-05). Acá iba `HOST_SLOT`,
    #   o sea el 2 clavado. Andaba de casualidad —el que crea SIEMPRE se sienta en el 2— y por eso
    #   nadie lo miró: se rompía sólo cuando el anfitrión CAMBIA, que es justo lo que faltaba.
    #   Con el 2 fijo, el que quedaba solo en la sala miraba un asiento vacío como "anfitrión" y
    #   la sala se quedaba sin dueño (ni START ni cambiar modo).
    _host13 = slot_anfitrion(getattr(st, "room_id", None))
    # ★★ LA PISTA PROPIA (2026-10-08): si este jugador eligió una para sí, el @14 de SU FF13 dice ésa — es lo
    #   que dibuja su recuadro «Pista». A los demás les sigue llegando la de la sala. Ver `salas.ELECCION_JUGADOR`.
    _pista13 = _sel["pista"]
    _propia13 = pista_propia_de(getattr(st, "room_id", None), getattr(st, "usn", None))
    if _propia13 is not None:
        _pista13 = _propia13
    _ff13 = build_ff13_2013(roomid=_rid13,
                            name=getattr(st, "room_name", "sala"), host_slot=_host13,
                            occ_mask=0x04, open_mask=mascara_abiertos(_rid13),
                            room_mode=_modo, banda=_banda,
                            room_bymode=_bymode13, room_colab=_colab13, room_boss=_boss13,
                            pista=_pista13, cancion=_sel["cancion"],
                            campanas=_campanas_ff13(_rid13))
    # ★ y la cola NUESTRA (08-oct): sus obstáculos y la condición de victoria, para la d3d9 (`panel_sala.c`)
    _cola13 = cola_ff13_jugador(st)
    st.send_ff55(0x13, _ff13 + _cola13,
                 name=f"FF13 ROOMINFO roomid={_rid13} name={getattr(st,'room_name','sala')!r} "
                      f"anfitrion_slot={_host13} open=0x3F banda={_banda} byMode=0x{_bymode13:02X} "
                      f"colab={_colab13} jefe={_boss13} "
                      f"pista={_pista13}{' (la suya)' if _propia13 is not None else ''} "
                      f"cancion={_sel['cancion']}{motivo}")


def restaurar_musica(st, motivo=""):
    """Repone el CARTEL DE MÚSICA con la canción de la sala. `FF1C type 0`.

    ★★★ EL `FF13` NO ALCANZA, Y ACÁ ESTÁ EL PORQUÉ (2026-09-04). El cartel de "Música" se
    dibuja de `[cRoom+0x10e90]`:

        005903d6  movzx ecx, word [ebp+0x10e90]   ; la canción de la sala
        005903e1  mov   ecx, [0x9314d8]
        005903e7  call  0x40c970                  ; buscarla -> el objeto de la canción
                  ... y dibuja su banner

    Y a ese campo **sólo lo escribe `cRoom::SetMusic` (`0x59C6D0`)**, que se dispara con el
    `FF1C` de tipo **0, 5 o 6** — el `FF13` no lo toca. Por eso la canción se sincronizaba
    mientras el host elegía (relayamos su `type 0`) pero **no se reponía al volver**: ahí
    sólo mandábamos el `FF13`.

    ⚠ Y el `type 5` —el que el cliente manda al soltar el picker, y que pasa en el camino de
      vuelta— es `SetMusic(**0**)`: le BORRA la canción. O sea que no es que no la
      restauráramos, es que alguien la borraba y nadie la reponía.

    ⚠⚠ ORDEN: ESTO VA **DESPUÉS** DEL `FF1C type 0x1F`, no antes. `0x5BEAC0` no es
      `SetPlaySequence` —ese nombre era una suposición vieja y arrastró la decisión— sino
      **SetTab**: escribe la PESTAÑA del selector (`[cMusicList+0x48]`), y de esa pestaña sale
      el dibujo de la tapa para el ANFITRIÓN (`0x58F360`).
          `type 0`    = tab **4** = ★ la canción
          `type 0x1F` = tab **3** = `Random20_new.bmp`
      Mandarlos al revés le dejaba al host la tapa en "aleatorio": eso era el "anda para todos
      menos el host". Ver la nota larga en `h_20_ff0c`, con el disasm.
    """
    # ★★ (119) EN COOPERATIVO NO SE REPONE NADA (26-oct): el server sortea las 3 y la manera de lista tiene que quedar en
    #   el `0x1F` que acaba de armar el picker. Un «aleatorio» acá es el «Elija una música» de la sala 9 de prod.
    #   Ver `COOP_SIN_CARTEL_SALA` en ajustes.
    from .ajustes import COOP_SIN_CARTEL_SALA
    if COOP_SIN_CARTEL_SALA and getattr(st, "room_colab", False):
        log("LOBBY", f"  ♪ cooperativo: NO repongo el cartel de la sala a usn={getattr(st, 'usn', '?')} — queda el "
                     f"0x1F (TOP 20, exento del «Elija una música»){motivo}")
        return
    _sel = seleccion_de(getattr(st, "room_id", None))
    # ★★ LOS MODOS AL AZAR (29-sep): no hay canción que reponer, hay un CARTEL. Al anfitrión el de su modo
    #   (el `0x1F` de «construir el picker» le dejó el de TOP 20), al invitado «Aleatoria». Va SIEMPRE, no
    #   una vez: el `0x1F` también va siempre. Ver `PICKER_CARTEL_SALA`.
    from .ajustes import PICKER_MODOS, PICKER_CARTEL_SALA
    from .picker import ff1c_cartel
    _rid_c = getattr(st, "room_id", None)
    _cart = (ff1c_cartel(_sel.get("modo"), anfitrion_de(_rid_c) == getattr(st, "usn", None))
             if (PICKER_MODOS and PICKER_CARTEL_SALA) else None)
    if _cart:
        st.send_ff55(0x1C, _cart, name=f"FF1C type=0x{_cart[0]:02X} (repone el cartel de «{_sel['modo']}»)")
        log("LOBBY", f"  ♪ cartel del modo «{_sel['modo']}» repuesto a usn={getattr(st, 'usn', '?')}{motivo}")
        return
    if not _sel["cancion"]:
        return
    # ★★★★ ¿Y EL LUGAR DE LA LISTA? — investigado el 2026-09-09, pedido de anonimo03:
    #   *"también se podría guardar la ubicación de la lista del picker, el lugar en que me quedé"*.
    #
    #   ⛔ NO SE PUEDE GUARDAR: **el cliente nunca nos lo dice.** Comprobado por dos caminos.
    #     (a) El `FF1C` son 5 bytes y están todos ocupados — `[type][music:u16][loopType][filtro]`.
    #         Se miraron TODOS los que manda este cliente y no hay ningún índice de lista.
    #     (b) ★ CRUZADO CON EL 2019 (el oráculo, que trae los nombres de los devs):
    #             `CmdEditMusic` / `SendEditMusicMulti`  -> la canción elegida
    #             `CmdSelectingMusicStage` (cmd 0x79)    -> **[estado][tipo]**, 2 bytes; medido
    #                                                       acá: sólo `06` (música) y `02` (pista)
    #             `Scroll_Musiclist`                     -> **un WIDGET de UI**, puro cliente
    #     ⇒ No hay paquete que lleve la posición. Lo que no llega no se puede reponer.
    #
    #   ★ LA ÚNICA PALANCA QUE NOS QUEDA es cuántas veces le hacemos RECONSTRUIR la lista: cada
    #     `FF1C` cambia de PESTAÑA (`0x5BEAC0` = SetTab: `type 0` -> tab 4 · `0x1F` -> tab 3), y un
    #     cambio de pestaña repuebla la lista y la manda al principio.
    #     ⚠ Y ahí hay una diferencia con el REFERENTE: al entrar a una sala **él manda UN solo
    #       paquete** (`1f 00 00 00 ff`); nosotros mandamos ESE y además este `type 0`.
    #     ⇒ Con `FF1C_RESTAURA_UNA_VEZ` este repuesto va **sólo la primera vez que entrás a la
    #       sala**. Al VOLVER de la carrera se saltea, y la canción la repone el `FF13` — que es
    #       exactamente el mecanismo del referente, y el mismo que ya usamos tras el `type 5`.
    #     ⚠ QUÉ MIRAR SI SE ROMPE: el cartel de Música en blanco al volver. Si pasa, el `FF13` no
    #       alcanza en ese camino y esto se apaga. Es un EXPERIMENTO con interruptor, no una
    #       certeza — el scroll no lo podemos medir desde el server.
    _rid_m = getattr(st, "room_id", None)
    if FF1C_RESTAURA_UNA_VEZ and getattr(st, "musica_restaurada_sala", None) == _rid_m:
        log("LOBBY", f"  ★★ PICKER: NO repongo el cartel (ya lo hice para la sala {_rid_m}) — "
                     f"un `FF1C` menos es un cambio de pestaña menos, y así la lista puede "
                     f"quedarse donde estaba. La canción la repone el FF13.")
        return
    st.musica_restaurada_sala = _rid_m
    st.send_ff55(0x1C, bytes([0]) + struct.pack("<H", _sel["cancion"]) + bytes([0, 2]),
                 name=f"FF1C type=0 music={_sel['cancion']} (repone el cartel de Música)")
    log("LOBBY", f"  ★★ cartel de Música repuesto: canción {_sel['cancion']} de la sala "
                 f"{getattr(st, 'room_id', None)}{motivo}")


def difundir_roominfo(rid, motivo=""):
    """Reemite el `FF13` a TODA la sala. Es como se enteran los demás de la pista/canción.

    ★★★ Ésta es la pieza que faltaba. El `FF1B` (cambiar pista) se echoaba al que lo mandó y
    nada más — y encima el handler del `FF1B` en el cliente (`0x5C5400`) es un **stub** que
    lee un byte y lo tira, así que ese eco no podía hacer nada. La pista se dibuja del
    `FF13`, y el `FF13` había que reemitirlo.
    """
    if rid is None:
        return
    # ★ Y a los que MIRAN: la pista de la sala también es suya (ver `difundir_userlist`).
    for otro in conexiones_en_sala(rid):
        usn = getattr(otro, "usn", None)
        if otro is None or getattr(otro, "cerrado", False):
            continue
        try:
            enviar_roominfo(otro, motivo)
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude reemitir el FF13 a usn={usn}: {e!r}")


def h_ff79_seleccionando(st, cmd, data):
    """★★★ `FF79` — EL CARTEL "SELECCIONANDO MÚSICA". C→S `[u8 estado][u8 tipo]` · S→C `[u8 estado]`.

    Es el paquete que faltaba para que el que NO es anfitrión vea el cartelito mientras el
    host revuelve el picker. Se llegó por el lado del dibujo, no por el del protocolo:

    1. La imagen existe y está en el cliente: **`rnr_room/selecting.bmp`**. La carga
       `0x5B8370` en `[cRoom+0x1d838]`, junto con `random.bmp`, `loop.bmp` y `newhot.bmp`.
    2. La condición que la dibuja (`0x58F662`) es de dos partes:

           cmp  byte [cRoom+0xa42b], 2   ; ← el estado
           jne  saltar
           mov  ecx, [0x931660]          ; el padrón (la global del parche del impulsor)
           mov  bl,  [ecx+0x40]          ; MI slot
           call 0x5272f0                 ; -> [padrón+0x41] = el slot del ANFITRIÓN
           cmp  al, bl
           je   saltar                   ; si el que elige soy yo, no dibujo nada
           ... dibujar "selecting"

    3. Y `[cRoom+0xa42b]` lo escribe **este comando**, directo. El handler del cliente
       (`0x5D2380`) es de cuatro renglones:

           mov  ecx,[esp+0xc] / push 1 / lea eax,[esp+0x10] / push eax
           call 0x67d200                 ; lee UN byte
           mov  cl, [esp+0xc]
           mov  edx,[0x9314c0]           ; cRoom
           mov  byte [edx+0xa42b], cl    ; ★ y lo guarda ahí mismo
           ret  0xc

    ⇒ mandar `FF79 02` = "estoy eligiendo música", y cada cliente que no sea el host saca el
      cartel. La segunda mitad de la condición **ya la cumplimos**: el `@6` del `FF13` es el
      slot del anfitrión y aterriza justo en `[padrón+0x41]`.

    ★ Y el cliente ya nos lo venía mandando. En `mitm_20260904_102312` la causalidad está
      capturada entera, con el server de referencia contestando **un solo byte** (sin el
      tipo):

          RX `02 06` -> TX `02`      RX `00 06` -> TX `00`
          RX `01 06` -> TX `01`      RX `00 06` -> TX `00`

    ⛔ Nosotros no lo atendíamos: el cliente mandaba 18 de estos y se caían en el vacío. Por
      eso el cartel no salía nunca — no faltaba nada del lado del cliente.

    ⚠ El `tipo` toma dos valores en el corpus: **6** (el del picker, 16 muestras) y **3** (2
      muestras, las dos con estado 0, y el referente **no las relaya**). Se relaya sólo el 6;
      el 3 queda anotado y sin mapear, que es distinto de ignorarlo.
    """
    estado = data[0] if data else 0
    tipo   = data[1] if len(data) > 1 else 0
    _rid79 = getattr(st, "room_id", None)
    if tipo != 6:
        log("LOBBY", f"  · FF79 estado={estado} tipo={tipo} — sin relayar: el referente sólo "
                     f"reenvía el tipo 6. Tipo {tipo} SIN MAPEAR (2 muestras en el corpus).")
        return
    _n79 = 0
    # ★ Y a los que MIRAN el cartel de "seleccionando música": lo pidió el usuario en pantalla
    #   (*"los espectadores no ven el 'selecting music now' ni la música seleccionada"*). Es de la
    #   sala, así que va a los que la miran — ver `difundir_userlist`.
    for otro in (conexiones_en_sala(_rid79) if _rid79 else []):
        usn = getattr(otro, "usn", None)
        if otro is None or getattr(otro, "cerrado", False):
            continue
        otro.send_ff55(0x79, bytes([estado & 0xFF]),
                       name=f"FF79 estado={estado} -> [cRoom+0xa42b]")
        _n79 += 1
    if not _n79:                                  # fuera de sala, al menos al que preguntó
        st.send_ff55(0x79, bytes([estado & 0xFF]), name=f"FF79 estado={estado} (eco suelto)")
        _n79 = 1
    log("LOBBY", f"  ★★ FF79 estado={estado} tipo=6 -> difundido a {_n79}"
                 + ("  ⇒ los que NO son anfitrión sacan 'seleccionando música'"
                    if estado == 2 else "  ⇒ cartel apagado"))


def h_19_ff13(st, cmd, data):
    # rama original:  cmd == 19
    # tras crear/entrar. LAYOUT 2013 mapeado del disasm (reads 0x67cfe0), total 69B+namelen:
    #   off 0-1  = roomid u16
    #   off 2-22 = 21B de campos (host_pos/mode/speed/map/song = PENDIENTE mapear fino; ceros por ahora)
    #   off 23   = namelen u8   +   name (namelen bytes, cp1252, null-term interno)
    #   cola 45B tras el nombre: +33..36 = SLOT_MASK u32 (loop 6-bits en 0x5cdca0: bit i=1 -> slot i ABIERTO)
    # roomid=1, nombre = el que mando el cliente en FF10 (st.room_name), slots 0x3F = 6 abiertos.
    _modo = getattr(st, "room_mode", 0)          # flags del FF10 (bit0 velocidad · bit1 equipo · bit4 relevo)
    # ★★★ LA BANDA DEL PICKER va en el @2 de este mismo paquete (ver build_ff13_2013). Se usa el
    #   byte del FFC9, que es EXACTAMENTE la misma numeracion (rookiechobo 8 · rookie 1 ·
    #   starchobo 2 · star 3 · moonchobo 4 · moon 5 · sunchobo 6 · sun 7). Mandando 0 el picker
    #   quedaba VACIO hasta que el jugador clickeaba un icono de banda a mano.
    _banda = licencia_actual(getattr(st, "usn", 0))[1]
    # ⚠ `or 1`, NO `getattr(..., 1)`: al SALIR de la sala el FF12 deja `st.room_id = None`, y el
    #   atributo EXISTE, así que el default del getattr no se usa. Si después llegaba un FF13
    #   (pasa: el cliente lo pide al volver al lobby) reventaba con TypeError al hacer `None & 0xFFFF`.
    _rid13 = getattr(st, "room_id", None) or 1
    # ★★★ @6 = EL SLOT DEL **ANFITRIÓN**, NO "mi slot". MEDIDO 2026-08-05 en el disasm:
    #     FF13 @6 -> struct+0x10 -> `0x59D0E6: mov byte [[0x931660]+0x41], bl`
    #   y en ese gestor:  **+0x40 = MI slot**  ·  **+0x41 = el slot del ANFITRIÓN**.
    #   El cliente decide "soy el anfitrión" comparando los dos (30 sitios hacen ese `cmp`).
    #   ⛔ ERROR PROPIO (mismo día, corregido en el acto): lo cambié para mandarle a cada jugador
    #      SU slot, creyendo que el 2 clavado era un resto de la época de un solo jugador. Con eso
    #      al invitado le quedaban +0x40 y +0x41 iguales ⇒ **se creía el anfitrión** (los dos
    #      clientes rotulaban su propio asiento como "Anfitrión"). Va el del HOST para TODOS.
    #   ★ El me-detect NO se rompe: ése usa `+0x40`, que llega por el byte0 del FF11 (al que entra)
    #     y por el ack del FF10 (al que crea).
    # ★★★★ LUGAR ESPECIAL (Mi Casa / Sala de Conversación / charla de Círculo).
    #   El FF13 tiene que llevar **el MISMO `A`** que pidió el cliente (bits 11-15 = TIPO), no un
    #   roomid de sala de carrera. MEDIDO: el switch del nombre visible está en `0x5CD57B` sobre
    #   `(A>>11)-5`, y el caso 11 (casa) usa `"%s"` = el nombre CRUDO que mande el server (por eso
    #   la casa del retail muestra el nick del dueño); los tipos 5..10 usan textos fijos del cliente.
    #   ⛔ SÍNTOMA si no se hace: el cliente entra a la casa y ENCIMA le montamos una sala de
    #     carrera -> "mitad casa, mitad pantalla de jugar, con botón de Listo" (visto en vivo).
    #   ⚠ Y NO van el FFC9 (filtro del picker), ni el FF4B (modo de sala), ni el FF0C de carrera.
    _lt = getattr(st, "lugar_tipo", None)
    if _lt is not None:
        _nom = getattr(st, "lugar_quien", "") or ""
        _a13 = getattr(st, "lugar_a", 0)
        st.send_ff55(0x13, build_ff13_2013(roomid=_a13, name=_nom, host_slot=0,
                                           occ_mask=0x01, open_mask=0x01, room_mode=0, banda=0),
                     name=f"FF13 ROOMINFO LUGAR ESPECIAL tipo={_lt} A=0x{_a13:04X} name={_nom!r}")
        log("LOBBY", f"  ★★ FF13 de lugar especial (tipo={_lt}, A=0x{_a13:04X}): "
                     f"sin FFC9 ni FF4B — esto NO es una sala de carrera")
        return
    # ★★★ EL MODO DE LA SALA VA EN EL @8 DE ESTE PAQUETE (ver la nota larga en `build_ff13_2013`).
    #   Sale de `calc_bymode`, el MISMO cálculo que el `FF4B`: en el corpus el @8 del `FF13` es
    #   literalmente el eco del byte de modo del `FF4B`, así que tienen que salir de una sola cuenta
    #   y no de dos copias que después se despeguen.
    #   ★★ COOPERATIVO y JEFE **no** van acá: van en la COLA de este mismo paquete (+42 y +44),
    #     igual que el `r9`/`r11` del `FF4B`. El byMode sólo lleva velocidad/ítem y solo/equipo
    #     (en el cliente aterriza en `cRoom+0x6D80` y `+0x6D84`, nada más).
    #     ⛔ Acá le forcé un `0` al byMode cuando la sala era colaborativa, copiando la regla del
    #        campo `B` de la lista. En el `B` es correcto; acá no arreglaba nada y encima escondía
    #        el bug: el que entraba a una sala cooperativa la veía **"velocidad + solo"**, que es
    #        justo lo que dibuja un byMode 0. El modo no se le pisaba — nunca le llegaba.
    #   ★ Y en cooperativo/jefe el byMode va en CERO, esto sí MEDIDO en el corpus: la sala 6 (la
    #     del gorila) manda `@8 = 0x00`, no `0x04`. El motivo: el cliente manda esos dos modos con
    #     `flags = 0x00`, y `calc_bymode` lee "sin bit de velocidad" como **ítem** — pero ahí el
    #     cliente no eligió ítem, no eligió NADA. Es el mismo cuidado que ya tiene el campo `B`.
    #     (Para jefe no hay muestra: nadie jugó modo jefe contra el server de referencia. Va por
    #     el mismo razonamiento que el cooperativo, que sí está medido.)
    enviar_roominfo(st)
    # ★★ PEDIR EL `FF13` ES LA SEÑAL DE "VOLVÍ A LA SALA": es lo primero que hace el cliente al
    #   salir de la carrera y del cartel. Sirve para dos cosas, las dos del anfitrión:
    #     · apagar el `en_carrera` (que es lo que hace esperar al aviso de traspaso), y
    #     · soltar el `FF9B` que quedó pendiente si el dueño cambió mientras se corría.
    #   El `FF13` de arriba ya lleva el `@6` bueno, así que la mitad importante se arregla sola;
    #   lo que falta es prenderle la UI al nuevo.
    # ★★★ ¿VUELVE DE UNA CARRERA? — 2026-09-14, pedido de anonimo03: *"falta avisar el score al
    #   regresar a la sala"*. Y tiene todo el sentido: es el momento en que el marcador ACABA DE
    #   CAMBIAR, porque alguien ganó. Volver y ver «Score 2 - 1» es justo lo que uno quiere.
    #   ⚠ Se mira ANTES de apagar la marca, que es lo único que distingue "vuelvo del cartel" de
    #     las otras veces que el cliente pide el `FF13` (entrar, cambiar de pista…). Sin esto, al
    #     que entra le llegaría el marcador dos veces.
    _volvia = bool(getattr(st, "en_carrera", False))
    st.en_carrera = False
    st.carrera_colgada = False                         # ★ 17-oct: volvió (ver lobby_carrera, el reloj del cartel)
    # ★★ 16-oct: los `FF0E` de los que se fueron mientras corría (en carrera de equipos lo tumbaban).
    #   Y si era el último en volver, también a los que miraban. Ver `salas.soltar_ff0e_pendientes`.
    try:
        from .salas import soltar_ff0e_pendientes, espectadores_de
        soltar_ff0e_pendientes(st)
        if _volvia and not sala_en_carrera(getattr(st, "room_id", None)):
            for _esp in espectadores_de(getattr(st, "room_id", None)):
                soltar_ff0e_pendientes(_esp)
    except Exception as _e_f0e:                                      # noqa: BLE001
        log("LOBBY", f"  ⚠ FF0E guardados: {_e_f0e!r}")
    if _volvia:                                                      # ★ 15-oct: la misión de hoy que quedó pendiente
        try:
            from . import mision_hoy
            mision_hoy.al_volver(st)
        except Exception as _e_mh:                                   # noqa: BLE001
            log("LOBBY", f"  ⚠ misión de hoy al volver: {_e_mh!r}")
    _rid_pend = getattr(st, "room_id", None)
    # ★ El marcador, al que vuelve. Va sólo A ÉL: cada uno vuelve del cartel a su ritmo, y
    #   difundirlo haría que la sala reciba la misma línea una vez por jugador.
    # ⚠⚠ Y va ACÁ AFUERA, no adentro del `if` de abajo. Ese `if` pide que **ya no quede nadie
    #   corriendo**, así que el PRIMERO en volver —que suele ser el que ganó— se lo perdería.
    #   Éste es de los errores que no se notan probando de a uno: con un solo jugador el `if`
    #   siempre se cumple y todo parece andar.
    if _volvia and _rid_pend is not None and sala_por_equipos(st):
        from .salas import texto_marcador
        avisar_a_uno(st, texto_marcador(_rid_pend))
    # ★ y si ya no queda NADIE corriendo, la sala vuelve a figurar como disponible
    if _rid_pend is not None and not sala_en_carrera(_rid_pend):
        marcar_en_juego(_rid_pend, False)
        # ★★★★ Y ACÁ, EN MODO JEFE, EL SORTEO DE CAPITANES — 2026-09-08.
        #   Pedido del usuario: *"el sorteo sólo debe ocurrir al regresar a sala, no al presionar
        #   start … la mecánica de ceder el puesto de jefe queda pisada"*. El `FF175` (cederle el
        #   puesto a un compañero) es la mecánica del modo; si el START re-sorteaba, la cesión se
        #   borraba justo al empezar la partida — o sea, nunca llegaba a servir.
        #   ⇒ Los capitanes cambian ENTRE carreras, y de ahí hasta el START mandan las cesiones.
        #   ⚠ Va detrás del `sala_en_carrera` **y** de una marca de un solo uso: este handler lo
        #     dispara CADA jugador al volver, y sortear en cada uno haría saltar el distintivo seis
        #     veces. Con las dos condiciones, sortea el ÚLTIMO que vuelve, una sola vez.
        #   ⚠ Si nadie vuelve a pedir el `FF13` (todos se fueron), la marca muere con la sala o con
        #     el cambio de modo. El START siguiente no queda desprotegido: allá se REPARA, que es lo
        #     que evita el `0xFF` que crashea.
        if tomar_sorteo_al_volver(_rid_pend):
            if getattr(st, "room_boss", False) and JEFE_SORTEAR_CAPITAN and mesa_de(_rid_pend):
                _caps_v = sortear_capitanes(_rid_pend)
                if _caps_v:
                    difundir_capitanes(_rid_pend, _caps_v,
                                       motivo=" (sorteo AL VOLVER de la carrera)")
            else:
                log("LOBBY", f"  ★ sala {_rid_pend}: había sorteo pendiente pero ya no es jefe "
                             f"(o quedó vacía) -> se descarta")
    if _rid_pend is not None and ANFITRION_PENDIENTE.get(_rid_pend) == getattr(st, "usn", None):
        ANFITRION_PENDIENTE.pop(_rid_pend, None)
        # ⚠ Sin `if`: si TODAVÍA queda alguien corriendo, `_avisar_anfitrion` lo vuelve a dejar
        #   pendiente él solo. Poner acá la condición era perder el aviso en ese caso.
        _avisar_anfitrion(_rid_pend, st.usn, " [aviso diferido: volvió de la carrera]")
    # ★★★ REAFIRMAR LA BANDA YA DENTRO DE LA SALA (2026-08-04). El `FFC9` (= `cmd 0xC9`) es el
    #   ⚠⚠ TRES DIRECCIONES DE ESTE BLOQUE ESTABAN MAL, corregidas el 2026-09-09 (las cazó un
    #     agente investigando el picker, y se verificaron con `tabla_rx.py` y `fn_start`):
    #         el handler del `FFC9`  ->  **0x5D8490**, no 0x5D8C00
    #         `SetMusicLevelFilter`  ->  **0x58EDF0**, no 0x58EEA0
    #         `Show()`               ->  **0x58EEB0**, no 0x58EEE0
    #     Las tres viejas **caen en el MEDIO de otras funciones**. El mecanismo descrito abajo es
    #     correcto — lo que estaba mal eran los números —, pero un `disasm.py fn` sobre una
    #     dirección que no es el inicio de nada te muestra basura y te hace dudar de todo.
    #     ★ La regla que deja: **una dirección se comprueba con `fn_start`**; si no coincide
    #       consigo misma, no es una función y el comentario está mintiendo.
    #   camino corto y CONFIABLE: su handler `0x5D8490` es recto, sin condiciones salvo "0 = no-op",
    #   y hace DOS cosas —
    #       `0x58EDF0` cRoom::SetMusicLevelFilter(banda)  ->  [cRoom+0x9512] = banda
    #       `0x58EEB0` -> cRoomMusicSelect::Show()        ->  RE-APLICA el filtro y repuebla
    #   Lo mandabamos SOLO en el login (con el cRoom del lobby); acá se manda de nuevo con la sala
    #   ya armada, que es cuando el picker lo necesita.
    #   ⚠ Ojo con el orden: va DESPUES del FF13, porque el handler del FF13 tambien escribe ese
    #     mismo byte (`0x5CDF17`, incondicional) y nos lo pisaria.
    #   ⚠ La banda debe ser **1..8**: `LevelToMask` (`0x5BA360`) devuelve un solo bit para ese rango
    #     y **0 para cualquier otro valor** -> mascara vacia -> picker VACIO.
    # ★★★★★ Y ACÁ SE PISABAN LAS BANDAS QUE EL ANFITRIÓN HABÍA PRENDIDO — 2026-09-09.
    #   Reportado por anonimo03: *"al jugar, el máster activa ciertas bandas en el picker; eso debería
    #   mantenerse entre partidas, y ahora se reinicia a Sol"*. **Sol es su licencia** — o sea,
    #   exactamente lo que manda este `FFC9`.
    #   ★ El picker guarda una MÁSCARA de bandas (el `byMusicLevelFilter` que el cliente nos manda:
    #     `0x0c` = bits 2 y 3 = dos prendidas). Este `FFC9` toma **UNA** banda y adentro le aplica
    #     `LevelToMask` (`0x5BA360`), que da **un solo bit** ⇒ por diseño no puede devolver lo que
    #     el anfitrión tenía. Mandarlo de nuevo al volver **sólo puede empeorarlo**.
    #   ⇒ Se manda UNA vez por sala: al entrar. Al VOLVER de la carrera se saltea, y el cliente
    #     conserva las bandas que tenía prendidas.
    #   ⚠ El primer envío NO se toca: sin él el picker nace vacío (`LevelToMask(0)` = máscara 0 =
    #     lista vacía, medido). Lo que se saca es el REPETIDO.
    #   ⚠ Y si algún día hace falta devolver la máscara entera, el dato ya se está guardando
    #     (`seleccion_de(rid)["filtro"]`); lo que falta es POR DÓNDE mandársela, y el `FFC9` no es.
    _ya_ffc9 = getattr(st, "ffc9_picker_sala", None)
    if _banda and FFC9_PICKER_UNA_VEZ and _ya_ffc9 == _rid13:
        log("LOBBY", f"  ★★ PICKER: NO re-mando el FFC9 (ya se lo mandé para la sala {_rid13}) — "
                     f"así conserva las bandas que prendió el anfitrión. Filtro que él nos dijo: "
                     f"{seleccion_de(_rid13).get('filtro')}")
    elif _banda:
        st.ffc9_picker_sala = _rid13
        st.send_ff55(0xC9, bytes([_banda & 0xFF]),
                     name=f"FFC9 banda={_banda} EN SALA (fija el filtro + repinta el picker)")
        # ★★★★★ Y SE ANOTA COMO LA BANDA DE LA SALA, para que el ÍCONO de la lista salga desde
        #   que la sala se crea. anonimo03: *"al crear la sala el icono no aparece, solamente si uso
        #   el picker de banda; luna creó sala, el ícono debe anunciarse como luna"*.
        #   ★ Y es **el valor donde CAE el picker**, no uno deducido: es exactamente el byte que
        #     le acabamos de mandar en el `FFC9` de arriba, el que hace que se pose ahí.
        #   ⛔ Antes probé calcularlo del `exp` → `nivel` → banda, y anonimo03 lo frenó con razón:
        #     *"ver exp y otras cosas me parece no muy nativo de nuestra parte"*. Y además **daba
        #     mal**: para su cuenta salía banda 8 cuando el picker le cae en luna. Re-derivar un
        #     dato que el cliente ya tiene es cómo se llega a dos verdades distintas.
        #   ⚠ Sólo si nadie eligió todavía: en cuanto el anfitrión toca el picker, manda su propio
        #     `FFC9` y `poner_dificultad` gana.
        try:
            if dificultad_de(_rid13) is None:
                poner_dificultad(_rid13, _banda)
                # ★★ Y SE REPUBLICA LA LISTA. El orden importa y nos mordió: la sala se publica
                #   en el `CREATEROOM` y la banda se anota acá, **un segundo después** — así que
                #   la lista salía sin ícono y recién aparecía al refrescar. anonimo03: *"salió sin
                #   ícono, y sólo apareció al refrescar; debería aparecer al instante de la
                #   creación"*. Sin este empuje el dato llega tarde a la pantalla.
                difundir_roomlist()
        except Exception as e:                                           # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude anotar la banda inicial de la sala {_rid13}: {e!r}")
        # mascara real de `LevelToMask` (0x5BA360): banda 8 -> bit0; bandas 1..7 -> bit N.
        _mask = 1 if _banda == 8 else (1 << _banda)
        log("LOBBY", f"  ★★★ PICKER: FFC9 banda={_banda} tras el FF13 -> [cRoom+0x9512]={_banda} "
                     f"y Show() reaplica el filtro (mascara 0x{_mask:02X})")
    if FF4B_AL_CREAR:
        # ★★ El modo elegido en el DIALOGO DE CREACION se aplica solo: el FF10 ya nos trajo el
        #    mismo `flags` que manda el FF4B, asi que reusamos la misma respuesta acá.
        # ⚠⚠ EL ORDEN IMPORTA Y SE MIDIO A LOS GOLPES (2026-07-30):
        #   - FF4B **antes** del FF13 -> **CRASHEA** el cliente al crear la sala
        #     (EXCEPTION_ACCESS_VIOLATION leyendo NULL en 0x6855B8, codigo de UI): el applier
        #     0x5971F0 corre sobre una sala que todavia no esta armada.
        #   - FF4B **despues** del FF13 -> no crashea, pero el applier REARMA LOS SLOTS (ya lo
        #     vimos resetear el LISTO del NPC) y pisa el **mi-slot** (`me+0x41` = @6 del FF13),
        #     con lo cual el host deja de ser master y el boton vuelve a LISTO.
        #   ⇒ Solucion: FF13 -> FF4B -> **FF13 de nuevo**. El primero arma la sala (para que el
        #     applier tenga con que trabajar), el FF4B aplica el modo, y el segundo repone el
        #     mi-slot como ultima palabra.
        # ★★ PRUEBA 2026-08-05 — EL TÍTULO SE APLICA PERO LOS SLOTS NO.
        #   Reportado en pantalla: al CREAR con "equipo + velocidad" el título sale bien pero los
        #   slots quedan dibujados como SOLO. Si después se cambia a solo y se vuelve a equipo
        #   desde el menú, **sí** se acomodan — con el MISMO FF4B, byte por byte.
        #   La única diferencia entre los dos caminos es que el manual arranca con un `FFBD` que
        #   el cliente pide y nosotros concedemos. La hipótesis es que ese FFBD lo deja en el
        #   estado en el que el applier redibuja los asientos.
        #   ⇒ Se prueba mandándolo sin que lo pida, justo antes del FF4B. Si abre el diálogo de
        #     configuración en pantalla, o no cambia nada, se apaga y esperamos al disasm.
        if FFBD_ANTES_DEL_FF4B:
            st.send_ff55(0xBD, b"\x00", name="FFBD concedido (para que el FF4B redibuje los slots)")
        # ★ Sólo si está habilitado: este camino corre AL ENTRAR, y el FF4B abre el cartel
        #   "el modo de juego ha cambiado". Ver FF4B_AL_ENTRAR en ajustes.py.
        if FF4B_AL_ENTRAR:
            enviar_ff4b(st, _modo, getattr(st, "room_name", "sala"),
                        getattr(st, "room_colab", False), getattr(st, "room_boss", False))
        # ★ Y se deja ARMADO un segundo FF4B idéntico, que sale con el primer paquete que el
        #   cliente mande ya estando dentro de la sala. Ver el bloque al inicio de handle_inner().
        if FF4B_REPETIR_AL_CREAR and FF4B_AL_ENTRAR:
            st.ff4b_repetir = (_modo, getattr(st, "room_name", "sala"),
                               getattr(st, "room_colab", False), getattr(st, "room_boss", False))
        # ⛔ NO reenviar el FF13 acá. Se probo (2026-07-30) y **BORRA EL MODO APLICADO**: el usuario
        #    dejo de ver el cooperativo en el titulo y en el icono. Queda el conflicto anotado:
        #      FF4B pone el modo pero pisa el mi-slot  ·  FF13 repone el mi-slot pero borra el modo
        #    ⇒ no se resuelve por orden. Hay que MEDIR con Frida si el FF4B realmente rompe el
        #      master (me+0x41) o si el START se traba por otra cosa, antes de tocar mas.
        # ★ El PlayData del chase va AL FINAL: si va antes, el FF13 le pisa el estado de
        #   "cancion lista" y el cartel "elija una musica" vuelve a salir.
        # ⛔ 2026-09-05: acá el `and getattr(st, "chase_songs", None)` hacía que, creando la
        #    sala YA en cooperativo, no saliera ningún PlayData — porque el sorteo sólo existía
        #    si antes habías pasado por el `FF4B`. Ahora se sortea si falta.
        if getattr(st, "room_colab", False):
            _cs13 = asegurar_canciones_chase(st, "sala creada en cooperativo (FF13)")
            st.send_ff55(0x139, build_ff139_playdata(_cs13[0]),
                         name=f"FF139 PlayData (chase) song={_cs13[0]}")
            log("LOBBY", f"  ★★ CHASE: PlayData con la 1ª ({_cs13[0]}) al final, "
                         f"para que el FF13 no lo pise")
    _colab13 = bool(getattr(st, "room_colab", False))
    _boss13  = bool(getattr(st, "room_boss",  False))
    # ★★★★★ Y SI EN ESTA SALA YA SONÓ UNA CAMPANA, SE LE PLANTA — 2026-09-15.
    #   ⛔ anonimo03: *"el que entra a la sala no ve las campanas ni el buff aplicado al título de la
    #     sala"*. El `plantar` se difundió UNA vez, cuando sonó; el que llega después nunca lo
    #     recibió, y el objeto vive en el CLIENTE, no en el server — para él la sala está vacía.
    #   ★ Va acá, en el `FF13`, porque es lo que el cliente pide **al terminar de entrar** a una
    #     sala: es el único punto por el que pasan todos los caminos de entrada (crear, entrar,
    #     volver de la carrera) sin tener que engancharlos uno por uno.
    # ⛔⛔ 29-sep — PERO ACÁ ES DEMASIADO TEMPRANO (anonimo03: «al volver sólo se ve una campana, y no donde
    #   se tocó»). Medido en el log: el `FF13` llega ANTES de que el cliente pida los ocupantes (`FF0C`,
    #   2 s después), y el `FFF5` (`0x5DB900` -> `0x587AC0`) busca a cada uno en el mapa de ocupantes
    #   (`cRoom+0x9C`): si todavía no está, lo IGNORA. Sin el asiento movido, las dos campanas del mismo
    #   jugador caían en el mismo punto. ⇒ Acá sólo se ANOTA; se manda detrás del `FF0C` (`h_20_ff0c`).
    from .ajustes import CAMPANA_TRAS_FF0C
    if CAMPANA_TRAS_FF0C:
        st.campanas_por_plantar = getattr(st, "room_id", None)
    else:
        _plantar_campanas_y_posiciones(st)
    log("LOBBY", f"  ★ FF13 -> anfitrión slot {slot_anfitrion(getattr(st, 'room_id', None))} (@6) "
                 f"+ open_mask=0x{mascara_abiertos(getattr(st, 'room_id', None)):02X} | "
                 f"★byMode=0x{0 if (_colab13 or _boss13) else calc_bymode(_modo):02X} en @8 + "
                 f"colab={int(_colab13)} en cola+42 + "
                 f"jefe={int(_boss13)} en cola+44 (flags=0x{_modo:02X} = "
                 f"{modo_texto(_modo, _colab13, _boss13)})"
                 + (f" | sonda modo={FF13_MODE_PROBE}" if FF13_MODE_PROBE is not None else ""))


def _campanas_ff13(rid):
    """Las campanas que sonaron en la sala, para el FF13. Vacío si `CAMPANA_EN_FF13` está apagado."""
    from .ajustes import CAMPANA_EN_FF13
    if not CAMPANA_EN_FF13 or rid is None:
        return None
    try:
        from .lobby_campana import campanas_para_ff13
        return campanas_para_ff13(rid)
    except Exception as _e_cf:                                        # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude armar las campanas del FF13: {_e_cf!r}")
        return None


def _plantar_campanas_y_posiciones(st):
    """Las campanas que ya sonaron en la sala (cada una en su lugar) y las posiciones que conocemos."""
    from .ajustes import CAMPANA_EN_FF13
    if CAMPANA_EN_FF13:
        # ★ Las campanas ya viajaron en el FF13 (camino nativo, sin animación). Queda el sync.
        try:
            from .lobby_campana import sincronizar_posiciones
            sincronizar_posiciones(st, getattr(st, "room_id", None))
        except Exception as _e_sp:                                    # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude mandar las posiciones: {_e_sp!r}")
        return
    try:
        from .lobby_campana import reenviar_campanas, sincronizar_posiciones
        # ⚠ EL ORDEN LO MANEJA `reenviar_campanas`, y es delicado: el cliente planta cada campana
        #   en la posición que tiene guardada para ESE ASIENTO (`0x444260` -> `0x595070`), así que
        #   antes de cada una hay que mover el asiento a donde estaba cuando la tocó. Si no, dos
        #   campanas del mismo jugador caen en el mismo punto y una tapa a la otra.
        #   ★ Si no había campanas, igual se manda el sync suelto.
        if not reenviar_campanas(st, getattr(st, "room_id", None)):
            sincronizar_posiciones(st, getattr(st, "room_id", None))
    except Exception as _e_camp13:                                   # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude re-plantar las campanas de la sala: {_e_camp13!r}")


def h_20_ff0c(st, cmd, data):
    # rama original:  cmd == 12
    # tras el FF13 para DIBUJAR los ocupantes de la sala (host + otros). MEDICION: bloque de ceros
    # -> count de ocupantes=0 -> loop por-usuario vacio -> consume solo su cabecera. trace_ff0c.py mide.
    # ★ USERLIST real: 1 ocupante = YO (el char de la DB) en el slot del host (2). identity=slot -> me-detect
    #   'soy yo'. Layout mapeado byte-a-byte (trace_ff0c_reads) en build_ff0c_2013.
    # ★★ EN UN LUGAR ESPECIAL el userlist va DISTINTO y sin nada de sala de carrera:
    #   · YO voy en el **slot 0**, el mismo que le dimos en el FF61. El cliente decide "cuál de
    #     estos soy yo" comparando contra `[0x931660]+0x40`, que el FF61 dejó en 0; si el FF0C me
    #     lista en el slot 2 **no se encuentra a sí mismo** (mismo tipo de bug que ya nos mordió
    #     con el `+0x40` en las salas compartidas).
    #   · NO van los NPC listos (FF17) ni el FF4B de equipos: acá no hay "listo" ni equipos.
    #   ⚠ Los slots de estas salas van 0..39 (capacidad 40), no 0..5.
    if getattr(st, "lugar_tipo", None) is not None:
        # ⛔ REGRESIÓN PROPIA, corregida: acá me armaba el ocupante A MANO con 4 campos
        #   (slot/nick/char_id/parts) y el panel "Lista de Usuarios" salía con MENOS datos que antes.
        #   `armar_ocupantes()` construye el registro COMPLETO (exp -> nivel, ropa, etc.), y como en
        #   un lugar especial no hay mesa, usa `st.room_slot` ⇒ alcanza con fijarlo en 0.
        #   ★ LECCIÓN (van dos hoy): reusar el armador que ya existe en vez de re-armar un subconjunto.
        # el MISMO slot que le dimos en el FF61 (me-detect por [0x931660]+0x40)
        st.room_slot = LUGARES.get(getattr(st, 'lugar_clave', None), {}).get(
            'ocupantes', {}).get(getattr(st, 'usn', 0), 0)
        st.ghost     = False    # sin NPC: no es una sala de carrera
        # ★★ La SALA DE CONVERSACIÓN COMPARTIDA: todos los de la estancia + el aviso a los demás.
        from . import charla
        if (CHARLA_COMPARTIDA and charla.es_publica(st.lugar_tipo)) or charla.es_del_circulo(st.lugar_tipo):
            charla.mandar_lista(st)
            return
        # ★ registro COMPLETO pero con la exp acotada (ver LUGAR_EXP_TOPE arriba)
        if not FF0C_LUGAR_MINIMO:
            _ocs = armar_ocupantes(st)
            if LUGAR_EXP_TOPE:
                for _o in _ocs:
                    if _o.get("exp", 0) > LUGAR_EXP_TOPE:
                        _o["exp"] = LUGAR_EXP_TOPE
            st.send_ff55(0x0C, build_ff0c_2013(_ocs),
                         name=f"FF0C lugar: {len(_ocs)} ocupante(s), exp acotada a {LUGAR_EXP_TOPE}")
            log("LOBBY", f"  ★ FF0C de lugar: {len(_ocs)} ocupante(s) COMPLETOS con exp<={LUGAR_EXP_TOPE} "
                         f"(licencia 1 = no bloquea el movimiento)")
            return
        if FF0C_LUGAR_MINIMO:
            _c = db_get_char(getattr(st, "usn", 0)) or {}
            st.send_ff55(0x0C, build_ff0c_2013([{ "slot": st.room_slot,
                                                  "nick": _c.get("nick", "?"),
                                                  "char_id": int(_c.get("char_id") or 0),
                                                  "parts": _c.get("parts") or [] }]),
                         name=f"FF0C lugar: ocupante MÍNIMO en slot {st.room_slot} (bisección del movimiento)")
            log("LOBBY", "  ★ FF0C MÍNIMO (FF0C_LUGAR_MINIMO=True): si con esto SE MUEVE, el bloqueo "
                         "está en algún campo del registro completo")
            return
        enviar_userlist(st)
        log("LOBBY", "  ★ FF0C de lugar especial: 1 ocupante REAL en el SLOT 0 (coincide con el "
                     "FF61); sin FF17 de listo ni FF4B de equipos")
        return
    enviar_userlist(st)
    # ★★★★★ EL ENLACE DE PAREJA VA **DESPUÉS** DE LA LISTA DE OCUPANTES (2026-09-12).
    #   ⛔ LO TENÍA EN EL `ENTERROOM`, Y ERA DEMASIADO PRONTO. Medido en el log: los `FF15` del
    #     enlace salían **77 líneas antes** que los `FF0C` que pueblan la sala. El paquete era
    #     correcto y llegaba a tiempo… para una escena en la que el otro **todavía no existía**.
    #   ★ Y el CBT ya había dejado anotado el porqué, como cabo suelto: el escritor del enlace
    #     (`0x527B00`) hace `map.find(slot)` y **sale sin escribir si la entrada no existe**.
    #     Ahí estaba la explicación, esperando a que alguien la necesitara.
    #   ⇒ Reportado por anonimo03: *"M sale de la sala y vuelve a entrar, el slot de F no actualiza"*.
    #     Justamente F, la que **ya estaba**: para ella M no existía cuando llegó el enlace.
    #   ★★ Es el molde de [[la-maquina-lenta-ve-las-carreras]]: **un paquete correcto mandado
    #     antes de tiempo**. Acá no hacía falta una máquina lenta — el orden ya estaba mal.
    #   ⚠ El CARTEL se queda en el `ENTERROOM` a propósito: acá saldría cada vez que alguien pide
    #     la lista, y el jugador vería «ha llegado» una y otra vez.
    refrescar_enlaces_de_pareja(getattr(st, "room_id", None), " (tras poblar la sala)")
    # ★★★★ EL `FF1C` QUE CONSTRUYE EL PICKER DE MÚSICA DE LA SALA (2026-09-03).
    #   ⛔ Éste es el paquete que faltaba, y es la CAUSA del diluvio de `FF3D`.
    #   La documentación del CBT (`D:\R2Beat\docs\MULTIPLAYER.md`) lo tenía descripto sin
    #   saber cuál era el paquete:
    #       «Causa raíz: null-deref del PICKER DE MÚSICA DE SALA `[room+0xC350]`. La Update
    #        POR-FRAME `0x543780` lo desreferencia sin null-check. Se crea condicionalmente,
    #        disparado por **un paquete S→C que NO mandamos** (familia `FF1C`).»
    #   Síntoma nuestro: el cliente manda `FF3D` **~59 veces por segundo** —una por frame—
    #   desde unos 6 segundos después de entrar a la sala. En el CBT eso CRASHEABA al cliente;
    #   acá no crashea, pero son 3500 paquetes por minuto de ancho de banda y CPU tirados.
    #
    #   MEDIDO en la captura: el server de referencia lo manda **justo después del `FF0C`**,
    #   en cada entrada a sala, y su cliente manda 54 `FF3D` en toda una sesión (nosotros,
    #   47.000). El paquete que ya armábamos para el camino de cooperativo es **byte por byte
    #   idéntico** al suyo (`1f 00 00 00 ff`): sólo estaba en el lugar equivocado.
    if FF1C_AL_ENTRAR:
        st.send_ff55(0x1C, bytes([CHASE_FF1C_TYPE & 0xFF]) + struct.pack("<H", 0)
                     + bytes([0, CHASE_FILTRO_BANDAS & 0xFF]),
                     name=f"FF1C type=0x{CHASE_FF1C_TYPE:02X} (construye el picker de la sala)")
        # ★ El cliente contesta esto con un `FF1C` tipo 5 PROPIO (medido 29-sep): no es el anfitrión
        #   eligiendo Aleatorio. Ver `PICKER_FF1C_AUTO_S`.
        from .ajustes import PICKER_FF1C_AUTO_S as _auto_s
        st.ff1c_auto_hasta = time.time() + _auto_s
        # ★★ Y EL INVENTARIO DETRÁS. El `FF1C` de arriba le hace reconstruir la interfaz de la
        #   sala desde su copia del inventario, que conserva los consumibles agotados; sin esto
        #   el ítem gastado reaparece —con 0 cargas y clickeable— cada vez que se entra a una
        # ⛔ ACÁ NO VA NADA MÁS. Estuvo un rato un MyRecord + un `FF3E` por cada consumible
        #   agotado, para matar el "ítem fantasma" que reaparecía al entrar a la sala. Era un
        #   parche sobre un problema propio: el fantasma lo creaba el `FF69` que mandábamos al
        #   usar la campana, que **borra la fila y la vuelve a crear** con count 0. Sacado ése,
        #   no hay nada que limpiar. Ver `_avisar_cuantas_quedan` en `lobby_campana.py`.
        #   ⚠ Y no era gratis: cada `FF69`/`FF3E`/`FF6A` dispara una reconstrucción completa del
        #     panel (`0x4CF340`). Eran ~15 por entrada a sala — el repintado que se oía.
        #   ⛔ Además el parser del MyRecord **ACUMULA** las cargas (`0x48F3E0`:
        #     `rec.count = viejo + count`), así que un MyRecord de más las duplicaría; hoy no se
        #     nota porque los `FF69` de refresco las re-asignan. Es deuda aparte, anotada.
    # ★★★★★ Y LA CANCIÓN **DESPUÉS** DEL 0x1F. EL ORDEN ES EL BUG DEL ANFITRIÓN (2026-09-04).
    #
    #   ⛔ Estaba al revés, y el comentario decía que el `type 0` "mueve la secuencia de play a 4
    #     y el 0x1F la deja en 2". **`0x5BEAC0` NO es SetPlaySequence: es SetTab** — escribe
    #     `[cMusicList+0x48]`, la PESTAÑA del selector de música. Ese nombre era una suposición
    #     vieja y arrastró la decisión de mandar la canción primero.
    #
    #   ★ Y de esa pestaña sale el dibujo de la tapa. El panel es `0x58F360`, y se parte en dos:
    #
    #       0058f3d7  cmp  cl, [eax+0x41]      ; ¿mi slot == el del anfitrión?
    #       0058f3da  jne  0x58f54c            ; NO anfitrión -> otra rama
    #       0058f3e6  mov  eax, [cMusicList+0x48]   ; ★ SOY el anfitrión: manda la PESTAÑA
    #       0058f3f2  jmp  [eax*4 + 0x58f760]
    #
    #     tab 1 -> `random.bmp`  ·  tab 2 -> `Random20_top.bmp`  ·  tab 3 -> `Random20_new.bmp`
    #     tab 4 -> ★ la CANCIÓN de `[cRoom+0x10e90]`
    #
    #     Y al que NO es anfitrión `0x5BEAC0` le fuerza la pestaña a 4 SIEMPRE, ignorando el
    #     argumento (`0x5BEAD9  mov dword [ebp+0x48], 4`). Por eso a ellos les da igual.
    #
    #   ⇒ `type 0x1F` = **SetTab(3)** = Random20_new · `type 0` = **SetTab(4)** = la canción.
    #     Mandando el `type 0` primero y el `0x1F` después, **le dejábamos al anfitrión la
    #     pestaña en 3** y su panel dibujaba el fondo de "Random20_new" en vez de la canción.
    #     Eso es, exactamente, el "anda para todos menos el host".
    #
    #   ★ Y "ALEATORIA" no es un panel vacío ni un fallo de búsqueda: en el `music_lt.txt` del
    #     cliente el **índice 0 se llama "Aleatoria"** y su tapa es `random_chobo.bmp`. O sea que
    #     `[cRoom+0x10e90] == 0` **encuentra** una canción y dibuja ésa.
    restaurar_musica(st, " (al entrar/volver a la sala, DESPUÉS del 0x1F)")
    # ★ marcar a los NPC como LISTOS: FF17 [position=slot][ready=1] (recv 0x5CE2C0). El cliente pone
    #   occupant[slot].ready=1 -> cartel "LISTO"; ignora el FF17 si position==mi slot (no es el caso).
    #   Debería desbloquear el botón START del host (todos los NO-host listos).
    enviar_ready_npcs(st)
    # ★★★★ 2026-08-05 — EL FF4B DE LOS EQUIPOS VA **DESPUÉS** DEL FF0C, Y ÉSTE ES EL PORQUÉ:
    #   el applier `0x5971F0` reparte los equipos llamando `0x5938F0(cRoom, slot, team)`, y esa
    #   función **busca el slot en el mapa de ocupantes (`cRoom+0x9c`) y si está VACÍO se va sin
    #   hacer nada**. Al crear, la secuencia es FF13 -> FF4B -> (el cliente pide) FF0C: cuando el
    #   FF4B corría, la sala **todavía no tenía ocupantes**, así que no había a quién sentar en
    #   qué equipo. Por eso el arreglo a mano funcionaba: para entonces ya estabas en el mapa.
    #   ⇒ Se manda acá, inmediatamente después de la lista de ocupantes. El orden en el socket se
    #     respeta, así que el cliente procesa primero el FF0C (que lo inserta) y después el FF4B.
    _rep0c = getattr(st, "ff4b_repetir", None)
    if _rep0c is not None:
        st.ff4b_repetir = None
        log("LOBBY", "  ★★ FF4B tras el FF0C: ahora que la sala YA tiene ocupantes, el applier "
                     "puede acomodar los paneles de los asientos")
        enviar_ff4b(st, *_rep0c)
    # ★ Y el color, con el paquete nativo. El FF4B acomoda los PANELES (sus offsets salen del
    #   byMode), pero para el COLOR no hace falta re-aplicar nada: el 0x99 pinta el asiento y no
    #   depende de que el applier haya corrido. Mandarlo acá lo hace inmune al orden.
    _rid0c = getattr(st, "room_id", None)
    if _rid0c is not None and mesa_de(_rid0c):
        enviar_equipos(st, _rid0c)
    # ★★★ Y ACÁ, POR FIN, LAS REGLAS AL QUE CREÓ LA SALA (2026-09-14).
    #   El `FF0C` es lo ÚLTIMO que pide el cliente para armar la sala: si está pidiendo los
    #   ocupantes para dibujarlos, la ventana de chat de la sala ya existe. Mandarlo antes lo
    #   tiraba a la ventana del vestíbulo, que se destruye en el cambio de pantalla.
    #   ⚠ La marca se consume de una sola vez: el `FF0C` se pide muchas veces (cada vez que
    #     alguien entra o se mueve), y sin el `pop` esto sería un mensaje repetido para siempre.
    # ★★ LAS CAMPANAS Y LAS POSICIONES, AHORA QUE EL CLIENTE YA TIENE A LOS OCUPANTES (29-sep). Anotadas
    #   en el `FF13`; se consumen una vez. Ver `CAMPANA_TRAS_FF0C`.
    if getattr(st, "campanas_por_plantar", None) is not None:
        _rid_camp = st.campanas_por_plantar
        st.campanas_por_plantar = None
        if _rid_camp == getattr(st, "room_id", None):
            _plantar_campanas_y_posiciones(st)
    _pend0c = getattr(st, "pd_por_contar", None)
    if _pend0c is not None and _pend0c[0] == _rid0c:
        st.pd_por_contar = None
        contar_estado_de_sala(st, _rid0c, es_anfitrion=_pend0c[1])


def h_22_ff17(st, cmd, data):
    # rama original:  cmd == 23
    # el server BROADCASTEA FF17 [slot][ready] a la sala -> el cliente pone occupant[slot].ready y pinta el cartel
    # "LISTO" (mismo formato que ya usamos para el auto-ready del NPC, recv 0x5CE2C0). ⚠ El cliente IGNORA el FF17
    # de SU PROPIO slot (lo compara con [me+0x40]): el que clickeó se pinta local. O sea que en solitario esto NO
    # cambia nada visual — importa para (a) no dejar el paquete "SIN handler" y (b) que un 2º jugador real vea el
    # estado del otro. NO tiene relación con el master/START: ese botón es el del host, este es el del invitado.
    # ★★★ 2026-08-05 — ESTO NO LO VEÍA NADIE. Se echaba al MISMO que apretó, y con `HOST_SLOT`
    #   clavado: el cliente descarta el FF17 de su propio slot (lo compara con `me+0x40`), así que
    #   el paquete se tiraba a la basura. Ahora va **con el slot real del que apretó** y **a los
    #   OTROS** de la sala, que son los que tienen que ver el cartel "LISTO".
    ready = (data[0] & 1) if data else 1
    st.ready = bool(ready)
    _mi_slot = getattr(st, "room_slot", None)
    if _mi_slot is None:
        _mi_slot = HOST_SLOT
    # ★★ 2026-08-05 (2ª vuelta) — VA A TODOS, **INCLUIDO EL QUE APRETÓ**.
    #   Primero lo mandaba sólo a los otros, porque la nota decía "el cliente ignora el FF17 de su
    #   propio slot y se pinta local". Medido en pantalla: al invitado el host SÍ le ve el cartel,
    #   pero **en su propia pantalla el botón no se actualiza** ⇒ en el 2013 no se pinta solo.
    #   Incluirlo es como lo hace el CBT y, si de verdad lo ignorase, no costaría nada.
    _rid17 = getattr(st, "room_id", None)
    # ★ Y a los ESPECTADORES el estado de "listo": es lo que miran. Misma causa que el chat.
    _dest17 = conexiones_en_sala(_rid17) if _rid17 else [st]
    _dest17 = [c for c in _dest17 if c is not None and not getattr(c, "cerrado", False)] or [st]
    for _c in _dest17:
        try:
            _c.send_ff55(0x17, bytes([_mi_slot & 0xFF, ready]),
                         name=f"FF17 READY de slot={_mi_slot} ready={ready}")
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude relevar el FF17: {e!r}")
    # ★ 16-oct: con el usn y la sala (con tráfico, las líneas de varias salas se mezclan: el QA filtra por acá)
    log("LOBBY", f"  ★ FF17 READY slot={_mi_slot} ready={ready} usn={getattr(st, 'usn', None)} sala={_rid17} "
                 f"-> {len(_dest17)} destinatario(s)")


def h_25_ff4b(st, cmd, data):
    # rama original:  cmd == 75
    # C->S: al aceptar el diálogo de configuración, el cliente manda el modo con EL MISMO formato
    #   que el FF10:  [flags:u8][namelen:u8][name][c0][c1][colab][jefe]
    #   Capturado en vivo: 0x13 relevo+velocidad · 0x03 equipo+velocidad · 0x02 equipo+item ·
    #   0x00 +cola[2]=1 COLABORACION · 0x00 +cola[3]=1 JEFE. (El diálogo sólo se abre si antes
    #   contestamos el FFBD; ver abajo.)
    # S->C: handler del cliente 0x5CFE20 (slot 0x20898 = 0x203E8 + 0x4B*0x10, registrado en
    #   0x5F6B14). Loguea "<Room Change> CmdChangeRoomMode result: %d". LAYOUT por conteo de
    #   lecturas (0x67CFE0):
    #       [result:u8]  ⚠ si != 1 ABORTA (0x5CFE68) -> tiene que ser 1
    #       [byMode:u8]  -> 1er arg del applier 0x5971F0 ("ChangeRoomMode byMode: %d,
    #                       bySuperRoomCoupons: %d")
    #       [len1:u8][str1][len2:u8][str2]   (los dos strings pasan por 0x46C120/0x46C190, que
    #                       devuelven indices chicos comparados contra 1 y 0/2 -> son NUMERICOS)
    #       [r7][r8][r9][r10][r11]  5 u8; r9 != 0 -> flags|=4 ; r11 != 0 -> flags|=8, y esos
    #                       flags van como bySuperRoomCoupons (test bl,4 -> cRoom+0x951C).
    # ⛔ 29-sep: la cola se leía fija y con clave salía corrida — ver `pedido_de_sala`.
    flags, pedido, _clave4b, colab, boss = pedido_de_sala(data)
    # ⚠ El NOMBRE que viene en el FF4B a veces NO es el de la sala: la ventana de configuración se
    #   abre con una de las frases de fábrica del cliente ("¡Bienvenido!~", …) y si el jugador sólo
    #   toca el modo, viaja esa. Reflejarla cambiaba el título solo (reportado por el usuario).
    # ⛔⛔ 29-sep: y por eso se IGNORABA SIEMPRE — también cuando el jugador escribía un nombre de
    #   verdad. anonimo03: *"cambiar el nombre de la sala, hasta ahora no estaba funcionando"*. En los
    #   logs hay cientos: «GM jugador52» 58, «Luna» 30, «De chill...» 17… todos tirados.
    #   ⇒ Se acepta el nombre salvo que sea una frase de fábrica (`FRASES_DE_FABRICA`).
    _nombre_nuevo = pedido.strip() if pedido and pedido.strip() not in FRASES_DE_FABRICA else ""
    rname = _nombre_nuevo or getattr(st, "room_name", None) or pedido or "sala"
    # ★★★★★ COOPERATIVO **NO** CONVIVE CON ESPECTADORES — 2026-09-08, y la regla es DEL CLIENTE.
    #   ⛔ EL CRASH QUE ESTO EVITA, medido en producción: a las 14:52:28 entró el 2º espectador a
    #     la sala 2, a las **14:52:34 la sala pasó a colaboración**, a las 14:53:13 arrancó la
    #     carrera y **los DOS espectadores se cayeron** con 16 s de diferencia (los 6 jugadores
    #     terminaron bien). De las 18 carreras con espectadores del día anterior, **ninguna** era
    #     cooperativa: esa combinación no se había dado nunca.
    #
    #   ★★ Y LA REGLA NO LA INVENTAMOS NOSOTROS: el usuario lo probó y **el cliente ya la tiene** —
    #     *"al intentar poner cooperativo, si hay espectadores, salta un popup que no lo permite"*.
    #     O sea que el juego lo prohíbe… y nosotros lo aplicábamos igual, saltándonos su propio
    #     guard. Por eso pasó: el pedido llegó y lo obedecimos sin mirar.
    #
    #   ⇒ Es el patrón de siempre en este repo: **si el cliente ya sabe la regla, el server la
    #     hace cumplir en vez de confiar en que nadie la esquive.**
    #   ⚠ Se le devuelve el modo que TENÍA (más abajo se difunde `st.room_*`), así que su pantalla
    #     vuelve sola; y se le explica por chat, que si no parece que el botón está roto.
    if colab and not getattr(st, "room_colab", False) and espectadores_de(getattr(st, "room_id", None)):
        _n_esp = len(espectadores_de(st.room_id))
        _txt = (f"No se puede pasar a cooperativo con {_n_esp} espectador(es) mirando. "
                f"Pediles que compitan o que salgan.")
        _rb = _txt.encode("cp1252", "replace")[:0xFF]
        _sys = b"Servidor"
        st.send_ff55(0x08, bytes([len(_sys)]) + _sys + bytes([len(_rb)]) + _rb + bytes([2, 0]),
                     name="FF08 sistema: cooperativo bloqueado por espectadores")
        log("LOBBY", f"  ⛔ FF4B COOPERATIVO RECHAZADO en la sala {st.room_id}: hay {_n_esp} "
                     f"espectador(es) mirando. El cliente ya lo prohíbe con un popup; acá se hace "
                     f"cumplir. Es la combinación con la que se cayeron los dos espectadores el "
                     f"2026-09-08 a las 14:53.")
        return
    # ★★★ ¿ESTA SALA ACABA DE PASAR A MODO EQUIPO? — 2026-09-14, pedido de anonimo03.
    #   Se mira ANTES de pisar `room_mode`, porque después ya no hay con qué comparar.
    #   ⚠ El RELEVO cuenta como equipo: se juega 2v2 o 3v3 y lleva el mismo marcador de serie.
    #     Es la misma regla que usa el cartel (`_es_equipo28`) y la que usa el cliente
    #     (`sala_por_equipos`), no una lista aparte que se desincronice.
    _antes_eq = bool(getattr(st, "room_mode", 0) & (MODE_EQUIPO | MODE_RELEVO))         or bool(getattr(st, "room_boss", False))
    _ahora_eq = bool(flags & (MODE_EQUIPO | MODE_RELEVO)) or bool(boss)
    st.room_mode, st.room_colab, st.room_boss = flags, colab, boss
    # ★ 15-oct · los 4 equipos de la sala de 12 siguen al MODO al editarla (EQUIPOS_4.md): a relevo = el relevo de 12
    #   (siempre de 4), de relevo a equipo = el equipo de 4, a personal = sin equipos.
    _rid4b = getattr(st, "room_id", None)
    if _rid4b is not None and grande_de(_rid4b) == 12:
        from .salas import es_cuatro12, poner_cuatro12, poner_relevo12
        if flags & MODE_RELEVO and DOCE_RELEVO:
            poner_relevo12(_rid4b, True)
        elif flags & MODE_EQUIPO:
            _c4b = es_cuatro12(_rid4b)
            poner_relevo12(_rid4b, False)
            poner_cuatro12(_rid4b, _c4b)
        else:
            poner_cuatro12(_rid4b, False)
    if _nombre_nuevo and _nombre_nuevo != getattr(st, "room_name", None):
        log("LOBBY", f"  ✏ sala {getattr(st, 'room_id', None)}: nombre {getattr(st, 'room_name', None)!r} "
                     f"-> {_nombre_nuevo!r}")
    st.room_name = rname
    # ★★ LA CONTRASEÑA AL EDITAR (29-sep). Ponerla o cambiarla, sólo con rol.
    #   ⛔ Una clave VACÍA NO la saca: medido en la 1ª prueba de anonimo03, al cambiar sólo el NOMBRE el
    #     cliente mandó la clave vacía (la ventana se abría "sin contraseña": el server nunca le decía
    #     que la sala la tenía). Sin poder distinguir "la borré" de "la ventana vino en blanco", gana lo
    #     seguro: el candado no se pierde solo. Para sacarla, se cierra la sala. ⚠ El cliente REENVÍA la clave que ya tenía la sala en cada cambio de modo: si
    #   un GM le pasó la sala a un jugador, la MISMA clave de vuelta no es "ponerla", se respeta.
    _rid_cl = getattr(st, "room_id", None)
    if _rid_cl is not None and SALAS_VIVAS.get(_rid_cl) is not None:
        _vieja = CLAVE_SALA.get(_rid_cl, b"")
        if not _clave4b:
            if _vieja:
                log("LOBBY", f"  🔒 sala {_rid_cl}: el FF4B trajo la clave VACÍA -> se CONSERVA la que tenía")
        elif _clave4b == _vieja:
            pass
        elif puede_poner_clave(st):
            CLAVE_SALA[_rid_cl] = _clave4b
            log("LOBBY", f"  🔒 sala {_rid_cl}: contraseña {'CAMBIADA' if _vieja else 'PUESTA'} "
                         f"por usn={getattr(st, 'usn', 0)} ({len(_clave4b)} caracteres)")
        else:
            log("LOBBY", f"  🔓 sala {_rid_cl}: usn={getattr(st, 'usn', 0)} quiso poner/cambiar "
                         f"la contraseña sin rol -> queda " + ("con la de antes" if _vieja else "abierta"))
    if pedido and not _nombre_nuevo and pedido != rname:
        log("LOBBY", f"  · FF4B traía nombre {pedido!r} (frase de fábrica del cliente) -> IGNORADO, "
                     f"la sala sigue siendo {rname!r}")
    # ★★★ 2026-08-05 — EL CAMBIO DE MODO SE LE AVISA A TODA LA SALA.
    #   Reportado en pantalla: el host cambiaba el tipo de sala desde el menú y el invitado
    #   seguía viendo el modo viejo. Se le mandaba el FF4B **sólo al que lo pidió**.
    #   Estructura tomada del CBT (`broadcast_roominfo`): la SALA es la fuente de verdad del
    #   modo, y al cambiar se sincroniza a cada conexión antes de que cada una arme su paquete.
    #   ⚠ Acá se manda el FF4B (no el FF13): reenviar el FF13 BORRA el modo recién aplicado
    #     — está medido y anotado más abajo.
    _rid4b = getattr(st, "room_id", None)
    _dest4b = [st]
    if _rid4b is not None:
        if SALAS_VIVAS.get(_rid4b) is not None:
            # ★★★ RE-PUBLICAR LA SALA (2026-09-03). Acá se actualizaban SÓLO los campos
            #   internos (`flags`/`colab`/`boss`), pero los que viajan en la lista —`B`, `L`,
            #   `M`, `O`— quedaban con el valor del momento en que se creó la sala. Síntoma
            #   reportado: *"si cambio el tipo de sala, el otro que ve la lista no recibe
            #   ningún cambio"*, y **ni siquiera al refrescar**, porque la entrada publicada
            #   seguía siendo la vieja.
            #   `registrar_sala` recalcula la entrada entera desde `st` y además empuja la
            #   lista a los que están en el lobby, así que resuelve las dos mitades.
            registrar_sala(st)
        # ★ Y a los ESPECTADORES: miran la misma sala, tienen que ver el mismo modo.
        _dest4b = conexiones_en_sala(_rid4b) or [st]
    for _c in _dest4b:
        if _c is not st:                        # el invitado hereda el modo nuevo
            _c.room_mode, _c.room_colab, _c.room_boss = flags, colab, boss
            _c.room_name = rname                # ★ el nombre también: si hereda la sala, no vuelve el viejo
        enviar_ff4b(_c, flags, rname, colab, boss)
    if len(_dest4b) > 1:
        log("LOBBY", f"  ★★ FF4B modo difundido a {len(_dest4b)} jugador(es) de la sala {_rid4b}")
    # ★★★ Y AL PASAR A MODO EQUIPO, EL COMANDO DEL MARCADOR (2026-09-14).
    #   ⚠ Sólo en el FLANCO (no era equipo y ahora sí): repetirlo cada vez que el master toca
    #     cualquier cosa de la config sería ruido en el chat.
    #   ⚠ Y sólo al master: es el único que puede usarlo.
    if _ahora_eq and not _antes_eq and _rid4b is not None:
        _m1_4b, _m2_4b = marcador_de(_rid4b)
        # ⚠ EL MARCADOR VA A TODA LA SALA. Acaban de pasar a un modo que lleva marcador: a todos
        #   les importa con cuánto arranca la serie, no sólo al que apretó el botón.
        from .salas import texto_marcador
        _n4b = avisar_a_la_sala(_rid4b, texto_marcador(_rid4b))
        # ⚠ Pero el COMANDO sólo al master: es el único que puede usarlo.
        _duenio4b = anfitrion_de(_rid4b)
        if _duenio4b is None or _duenio4b == getattr(st, "usn", None):
            avisar_a_uno(st, "Master sala .reset score")
        log("LOBBY", f"  ★ la sala {_rid4b} pasó a modo equipo -> marcador {_m1_4b} - {_m2_4b} "
                     f"avisado a {_n4b} jugador(es); el comando, al master")
    # ⛔ NO reenviar el FF13 acá tampoco (mismo motivo: borra el modo que acabamos de aplicar).
    # ★ Y el PlayData del chase, TAMBIEN acá: al pasar a cooperativo DESDE LA CONFIG hay que
    #   satisfacer el gate de la cancion igual que al crear la sala. (Faltaba: lo tenia sólo en el
    #   camino de creacion, asi que cambiando el modo a mano el cartel "elija una musica" seguia.)
    #   Va DESPUES del FF13 para que no se lo pise.
    if colab:
        _csm = asegurar_canciones_chase(st, "cambio de modo desde la config")
        st.send_ff55(0x139, build_ff139_playdata(_csm[0]),
                     name=f"FF139 PlayData (chase) song={_csm[0]}")
        log("LOBBY", f"  ★★ CHASE: PlayData con la 1ª ({_csm[0]}) tras el cambio de modo")
    # ★★★ LOS CAPITANES SE SORTEAN AL PASAR A MODO JEFE, NO EN EL START (2026-09-07).
    #   Pedido del usuario: *"el sorteo debe realizarse al cambiar de modo … ya que cada capitán
    #   tiene la opción de ceder su puesto a otro miembro del equipo"*. Con el sorteo en el START
    #   nadie llegaba a usar esa opción: los capitanes se conocían cuando la carrera ya arrancó.
    #   ⚠ SÓLO SI NO HAY. El aviso que estaba escrito en el START sigue valiendo — re-sortear cada
    #     vez que alguien se sienta hace que el distintivo salte por la pantalla. Acá se sortea UNA
    #     vez, al entrar al modo, y de ahí en más manda el `FF175` (cederlo a mano).
    #   ⚠ El START conserva su propio sorteo como RED: si la sala se armó por otro camino o alguien
    #     se fue, ahí se vuelve a mirar. Un equipo sin capitán es el `0xFF` que crashea.
    if boss and JEFE_SORTEAR_CAPITAN and _rid4b is not None:
        #   ⛔ ACÁ DECÍA `and not hay_capitanes(...)`, y fallaba al **volver** a modo jefe: los
        #     capitanes seguían guardados de la vez anterior, así que no se sorteaba… pero tampoco
        #     se difundía, y los clientes se habían olvidado. Reportado: *"el sorteo falló al
        #     cambiar a otro modo y regresar a modo jefe"*.
        #   ⇒ Se REPARA (que no cambia nada si están bien) y se DIFUNDE SIEMPRE. Sortear de nuevo
        #     haría saltar el distintivo; no avisar deja clientes sin capitán, que es el `0xFF`
        #     que crashea. Difundir siempre es barato y no tiene ese costo.
        if not hay_capitanes(_rid4b):
            sortear_capitanes(_rid4b)
        else:
            reparar_capitanes(_rid4b)
        _caps4b = capitanes_de(_rid4b)
        if _caps4b:
            difundir_capitanes(_rid4b, _caps4b, motivo=" (modo JEFE: capitanes al día)")
    elif _rid4b is not None:
        # ★★ Y AL SALIR DEL MODO JEFE, LOS CAPITANES SE OLVIDAN — 2026-09-08.
        #   Se guardaban para siempre (sólo los borraba `desregistrar_sala`), y esa herencia es la
        #   que hacía que una sala ya en SOLO siguiera difundiendo capitanes cada vez que alguien
        #   se iba. Son un dato del MODO, no de la sala. Ver `salas.sala_usa_capitanes`.
        #   ⚠ Volver a jefe los re-sortea (`hay_capitanes` da False) y los difunde, que es
        #     justamente lo que el bloque de arriba garantiza.
        olvidar_capitanes(_rid4b)


def h_26_ffbd(st, cmd, data):
    # rama original:  cmd == 189
    # 2026-07-30). C->S FFBD con payload VACIO = "quiero cambiar el tipo de sala".
    # ★ HANDLER DEL CLIENTE REVERSADO: 0x5D87C0 (slot 0xBD de la tabla RX, registrado en 0x5F739D:
    #   `mov ecx,0x5D87C0 ; mov [esi+0x20FB8],ecx`, y 0x20FB8 = 0x203E8 + 0xBD*0x10). Es cortito:
    #       read(1 byte) -> al
    #       al == 0  ->  cRoom=[0x9314c0]; call 0x5904D0     ← APLICA / abre la config de sala
    #       al == 1  ->  cartel de error 118 · al == 2 -> cartel de error 2 · otro -> nada
    #   => la RESPUESTA es UN SOLO BYTE y 0x00 = concedido.
    #   `0x5904D0` lee `[cRoom+0x9580] ^ 0x1FEF` (el campo que el propio handler del FF10 pone en 0
    #   en 0x5E5B1D) y arranca la transición a la pantalla de configuración.
    # Por qué importa: es el equivalente del FF4B del CBT ("al dar OK en el popup el cliente manda el
    # modo elegido"). Nunca contestábamos este paquete, así que el cliente NUNCA aplicaba el modo y el
    # cartel de la sala quedaba clavado en el default "velocidad + solo".
    st.send_ff55(0xBD, b"\x00", name="FFBD cambiar-tipo-de-sala CONCEDIDO (00)")
    log("LOBBY", "  ★★ FFBD -> 00 (concedido): el cliente deberia ABRIR la config de sala "
                 "(applier 0x5904D0). Si en vez de eso sale un cartel de error, probar 01/02.")


def h_29_ff1c(st, cmd, data):
    # rama original:  cmd == 28
    # (`re/leer_network_log.py`), que imprime: "SendEditMusicFromRoom (type music, loop filter)" y
    # "CmdEditMusic type:0, music:4128, byMusicLoopType:0, byMusicLevelFilter:255".
    #   [type:u8][music:u16][byMusicLoopType:u8][byMusicLevelFilter:u8]
    # ⚠⚠ NO es siempre un "commit de cancion": el `type` manda.
    #   type 0/1 = seleccion real de cancion (music = songid de verdad)
    #   type 5   = filtro/scroll del picker -> viene con **music=0** (ej '05 00 00 02 ff', y en el login
    #              'SendEditMusicFromRoom (5 0, 2 64)'). Guardarlo PISABA room_song con 0.
    # ★ CAUSA DEL CRASH EN LA PANTALLA DE CARGA (2026-07-30): tomabamos el music de CUALQUIER type, asi
    #   que el ultimo FF1C antes del START (un type 5) dejaba room_song=0 y el FF25 LOADGAME salia con
    #   songid 0 -> el cliente carga una cancion inexistente y muere. Nada que ver con los NPC ni el modo.
    # ★★ LOS NOMBRES SON DE LOS PROPIOS DEVS. El handler real (`0x5CDD40`, no el `0x5CE4C0` de
    #   la tabla vieja) trae un log de depuración adentro, en `0x886538`:
    #       "[MUSIC] CmdEditMusic type:%u, music:%u, byMusicLoopType:%u, byMusicLevelFilter:%u"
    #   Confirma los 5 bytes que acá estaban deducidos del log de texto del cliente.
    #   Y tiene TABLA DE SALTOS de 33 tipos (0..0x20, índice en `0x5CE050`): los tipos 15..21 y
    #   26..30 caen en el default y no hacen nada. En el cable se ven 0, 1, 2 y 5.
    #   ⚠ `0x4E9C10`, el predicado que consultan casi todos los casos, es `xor al,al; ret` =
    #     **siempre falso**: la mitad de las ramas del FF1C están muertas en este build.
    mtype  = data[0] if data else 0xFF
    music  = struct.unpack("<H", data[1:3])[0] if len(data) >= 3 else 0
    _rid1c = getattr(st, "room_id", None)
    # ★★ EL FILTRO DE BANDAS — el ultimo byte, `byMusicLevelFilter`: la MASCARA de los iconos
    #   encendidos arriba del picker (2026-09-09). El cliente nos lo manda en cada `FF1C` y hasta
    #   hoy lo tirabamos. Visto en el log: `00 63 03 00 0c` -> `0x0c` = bits 2 y 3 = dos bandas.
    #   ⚠ Se guarda de TODOS los tipos, incluido el 5: el `type 5` es justo el que manda el cliente
    #     mientras se mueve por el picker, o sea el que trae el filtro mas fresco.
    _filtro = data[4] if len(data) >= 5 else None
    if _filtro is not None and _rid1c is not None:
        poner_seleccion(_rid1c, filtro=_filtro)
    # ★★★ LAS MANERAS DE LISTA (29-sep, `picker.py` §4, `documentacion/PICKER_SISTEMA.md` §3).
    #   El modo lo elige el ANFITRIÓN: tipo 0 = una canción · 6 = En orden (trae la que toca) ·
    #   5 = Aleatorio · 0x1F = TOP 20 · 0x20 = NUEVOS 20. Los tres al azar los sortea el START.
    #   ⛔ El tipo 1 NO es «elegí esta canción»: también es TILDAR una casilla (`0x5BAA74`). Con
    #     `mtype in (0, 1)` tildar cambiaba la canción de la sala. El doble clic manda 0 y 1 juntos,
    #     así que con el 0 alcanza.
    from .ajustes import PICKER_MODOS, PICKER_FF1C_AUTO_S
    _es_host1c = _rid1c is not None and anfitrion_de(_rid1c) == getattr(st, "usn", None)
    if PICKER_MODOS and _es_host1c:
        from .picker import modo_de_ff1c
        _modo1c = modo_de_ff1c(mtype)
        if _modo1c:
            _auto1c = mtype == 5 and time.time() < getattr(st, "ff1c_auto_hasta", 0)
            _previo1c = seleccion_de(_rid1c).get("modo")
            if _auto1c and _previo1c:
                log("LOBBY", f"  ♪ FF1C tipo 5 AUTOMÁTICO (pegado al picker que armamos): la sala "
                             f"{_rid1c} sigue en «{_previo1c}»")
            elif _modo1c != _previo1c:
                poner_seleccion(_rid1c, modo=_modo1c)
                log("LOBBY", f"  ♪ MANERA DE LISTA de la sala {_rid1c}: {_previo1c or '-'} -> {_modo1c}"
                             + (" (la de fábrica, al entrar)" if _auto1c else ""))
                # ★ EL CARTEL DE LOS DEMÁS (29-sep): en un modo al azar la canción de la sala es la 0
                #   («Aleatoria»). Si no, el invitado seguía viendo la última elegida. Ver `PICKER_CARTEL_SALA`.
                from .ajustes import PICKER_CARTEL_SALA
                from .picker import ff1c_cartel
                if PICKER_CARTEL_SALA and ff1c_cartel(_modo1c, False) and not _auto1c:
                    poner_seleccion(_rid1c, cancion=0)
                    _n_cart = 0
                    for _otro in conexiones_en_sala(_rid1c) or []:
                        if _otro is None or _otro is st or getattr(_otro, "cerrado", False):
                            continue
                        _otro.send_ff55(0x1C, ff1c_cartel(_modo1c, False),
                                        name=f"FF1C type=5 (cartel «Aleatoria»: la sala está en {_modo1c})")
                        _n_cart += 1
                    difundir_roominfo(_rid1c, motivo=f" (la sala pasó a {_modo1c}: canción 0 = «Aleatoria»)")
                    log("LOBBY", f"  ♪ cartel «Aleatoria» a {_n_cart} de la sala {_rid1c} ({_modo1c})")
    if music and (mtype in (0, 6) or (mtype == 1 and not PICKER_MODOS)):
        st.room_song = music
        poner_seleccion(_rid1c, cancion=music)
    # ★★★ DIFUNDIR, no echoar. Antes esto volvía SÓLO al que lo mandó, así que el host elegía
    #   canción y el invitado no se enteraba. El server de referencia hace las DOS cosas, y se
    #   ve entero en `mitm_20260904_102312` a las 10:25:49:
    #       RX FF1C type=0 · RX FF1C type=1   ->   TX FF1C x3  +  TX FF13 x2
    #   O sea: reenvía el FF1C a la sala Y reemite el FF13 (que es donde viaja la canción, @19).
    #   El host manda SIEMPRE dos: `type 0` y después `type 1`, con la misma canción.
    # ★★★★★ SÓLO SE DIFUNDEN LOS TIPOS DE SELECCIÓN (0 y 1). MEDIDO CON FRIDA, 2026-09-04.
    #
    #   ⛔ Antes se difundían TODOS, y **el que borraba el cartel de la música éramos nosotros**.
    #   El `type 5` es lo que el cliente manda al SOLTAR el picker, y su handler hace
    #   `push 0; call 0x59c6d0` = **`cRoom::SetMusic(0)`**. Reenviárselo a los demás les borra la
    #   canción, y ellos nunca tocaron nada.
    #
    #   La secuencia entera, capturada en el cliente vivo con milisegundos
    #   (`taller/re2013/capturas/batuta_20260904_142906.txt`):
    #
    #     145.028  el cliente MANDA su type 5      SendEditMusicFromRoom (5 0, 2 32)
    #     145.413  llega nuestro type 0 music=867  -> SetMusic(867)          ✓
    #     145.414  llega nuestro type 0x1F (picker)
    #     145.416  ★ VUELVE EL type 5, relayado por NOSOTROS
    #     145.416  ★★ SetMusic(0)   [cRoom+0x10e90]: 867 -> 0    ← lo borra
    #     145.523  llega el FF13 (UpdateRoomInfo)
    #     145.529  ★ SetMusic(867)  0 -> 867                     ← el FF13 lo repone
    #
    #   ⇒ Era una CARRERA: si el `FF13` llegaba después del `type 5`, el cartel se salvaba; si
    #     llegaba antes, quedaba en blanco. Cada cliente suelta el picker en un instante distinto
    #     ⇒ "una carrera lo recuperan casi todos, la siguiente algunos, la siguiente uno solo".
    #     Contenido siempre correcto; lo que fallaba era el orden.
    #
    #   ★ No difundir el `type 5` saca la carrera de raíz: el que lo mandó **ya se lo aplicó
    #     localmente**, y a los demás no les aporta nada.
    #
    #   ⚠ El referente SÍ lo relaya (y después manda el `FF13` para reponer). Nosotros hacemos
    #     menos y salimos mejor parados. Si algún día aparece algo que dependa de recibir el
    #     `type 5` ajeno, acá está el porqué de no mandarlo.
    _relayar = (mtype in (0, 1) if not PICKER_MODOS else
                # el 1 sólo si es la pareja del doble clic (misma canción que el 0), no una casilla;
                # el 6 es «En orden» avanzando: a los invitados sólo les hace SetMusic.
                (mtype in (0, 6) or (mtype == 1 and music == seleccion_de(_rid1c)["cancion"])))
    _n1c = 0
    if _relayar:
        # ★ Los que MIRAN comparten el panel de música de la sala (2026-09-08).
        _destinos = conexiones_en_sala(_rid1c) if _rid1c else [st]
        _saltados = []
        for _otro in _destinos or [st]:
            if _otro is None or getattr(_otro, "cerrado", False):
                continue
            # ★ (100) 22-oct, la caja negra 0x684107 (34 en prod): al que TODAVÍA CARGA la sala no se le manda el FF1C.
            #   El FF1C le actualiza el botón «orden de reproducción» del panel de música y, si su dibujo todavía no
            #   cargó, el cliente se cae (0x6840F0 sin tabla de cuadros). Casi todos: entran a la sala y en 1-20 s el
            #   anfitrión cambia la canción. El que carga recibe igual la canción al terminar (`FF1C_AL_ENTRAR`) y el
            #   FF13 de abajo. Mismo criterio que `difundir_ocupante` (al que carga no se le manda nada suelto).
            if (FF1C_NO_AL_QUE_CARGA and _otro is not st and _rid1c
                    and getattr(_otro, "sala_poblada", None) != _rid1c):
                _saltados.append(getattr(_otro, "usn", "?"))
                continue
            _otro.send_ff55(0x1C, data, name=f"FF1C CmdEditMusic type={mtype} music={music}")
            _n1c += 1
        if _saltados:
            log("LOBBY", f"  · FF1C type={mtype}: a {_saltados} no se le manda, todavía cargan la sala (le llega al entrar)")
        # ★ Y el `FF13` detrás, que es lo que fija la canción en la sala. MEDIDO en el mismo log:
        #   `UpdateRoomInfo` dispara `SetRoomChange ... 0x363` y de ahí sale un `SetMusic(867)`.
        #   ⛔ Acá decía que el `FF13` NO reponía el cartel. Era falso: se dedujo de que sólo
        #     `SetMusic` escribe `[cRoom+0x10e90]` —cierto— sin ver que el `FF13` llega a
        #     `SetMusic` por otro camino. El hook lo mostró en una corrida.
        difundir_roominfo(_rid1c, motivo=f" (tras el FF1C type={mtype})")
    log("LOBBY", f"  ★ FF1C CmdEditMusic type={mtype} music={music}"
                 + (f" -> difundido a {_n1c} + FF13; canción de la sala = {music}" if _relayar
                    else f" -> NO se difunde (sólo los tipos 0 y 1; el {mtype} es local del que lo "
                         f"mandó). Canción de la sala: {seleccion_de(_rid1c)['cancion']}"))
    # ★★★★★ EL PICKER SE RESETEABA AL VOLVER DE LA CARRERA — 2026-09-09.
    #   Reportado por anonimo03: *"el picker funciona bien hasta empezar el juego, pero al regresar a
    #   la sala se resetea"*. Y la causa es **el propio cliente borándose la canción a sí mismo**:
    #
    #       17:32:18  TX FF1C 0x1F              (construimos el picker)
    #       17:32:18  TX FF1C type=0 music=867  (reponemos la canción)
    #       17:32:18  RX FF1C : 05 00 00 02 08  ← el cliente manda su `type 5`, DESPUÉS
    #
    #   El handler del `type 5` (`0x5CDE65`) hace `0x59C6D0(0)` = **`cRoom::SetMusic(0)`**: al
    #   soltar el picker, el cliente **se borra su propia canción**. Nosotros ya habíamos dejado de
    #   RELAYARLO (eso arreglaba que se la borrara a los DEMÁS), pero al que lo mandó **no se la
    #   reponía nadie**. Es la misma carrera de siempre, vista desde el otro lado.
    #
    #   ★ Y el referente ya hacía lo correcto, escrito arriba desde el 2026-09-04: *"el referente
    #     SÍ lo relaya y después manda el `FF13` para reponer"*. De esas dos cosas nos quedamos con
    #     ninguna. La que hay que hacer es la segunda: **el `FF13` lleva la canción en el `@19` y
    #     llega a `SetMusic` por su propio camino** (medido con el hook, ver la nota de arriba).
    #   ⚠ Va **sólo al que mandó el `type 5`**, no a la sala: el único que se quedó sin canción es
    #     él. Difundirlo sería repetir el error que ya arreglamos, al revés.
    #   ⚠ Y sólo si la sala TIENE canción: si nadie eligió nada todavía, no hay nada que reponer y
    #     mandar un `FF13` de más es ruido.
    if (FF1C_REPONE_TRAS_TYPE5 and mtype == 5 and _rid1c is not None
            and seleccion_de(_rid1c)["cancion"]):
        enviar_roominfo(st, motivo=" (repone la canción que el type 5 le borró al picker)")
        log("LOBBY", f"  ★★ PICKER: el `type 5` le borró la canción a usn={getattr(st,'usn','?')} "
                     f"(SetMusic(0) del propio cliente) -> se la repongo con el FF13 "
                     f"(canción {seleccion_de(_rid1c)['cancion']})")
    # ★★★ EL PICKER, TAMBIÉN EN EL LOBBY. Éste `type=5` del login es EXACTAMENTE el punto donde
    #   arranca el diluvio de `FF3D` (medido con 6 clientes a la vez: los seis empiezan acá, a ~52/s,
    #   uno por frame). El paquete es el mismo que ya mandamos al entrar a una sala. Ver
    #   `FF1C_EN_EL_LOBBY` en `ajustes.py` para la comparación con el server de referencia.
    #   Se manda UNA sola vez por conexión y sólo fuera de sala, para no pisar el de la sala.
    if (FF1C_EN_EL_LOBBY and mtype == 5 and not getattr(st, "room_id", None)
            and not getattr(st, "ff1c_lobby_hecho", False)):
        st.ff1c_lobby_hecho = True
        st.send_ff55(0x1C, bytes([CHASE_FF1C_TYPE & 0xFF]) + struct.pack("<H", 0)
                     + bytes([0, CHASE_FILTRO_BANDAS & 0xFF]),
                     name=f"FF1C type=0x{CHASE_FF1C_TYPE:02X} (construye el picker YA EN EL LOBBY)")
        log("LOBBY", "  ★★★ FF1C type=0x1F en el LOBBY: es donde arranca el diluvio de FF3D. "
                     "Si no baja, apagá FF1C_EN_EL_LOBBY y buscá por otro lado.")


def sacar_de_la_sala_anterior(st, motivo="", menos=None):
    """Lo levanta de CUALQUIER sala en la que estuviera sentado, antes de sentarlo en otra.

    `menos` = la sala en la que **sí** tiene que quedarse (la de destino, cuando ya se sentó).

    ⛔⛔ POR QUÉ EXISTE — **las salas fantasma**, reportadas por anonimo03 el 2026-09-15 y medidas en
      el log de producción. El retrato completo está en la nota de `salas.barrer_mesas_huerfanas`;
      el resumen es que `levantar_jugador` limpia **una sola** sala (la de `st.room_id`) y que ni
      `CREATEROOM` ni `ENTERROOM` sacaban al jugador de la anterior: los dos daban por hecho que el
      cliente manda un `FF12 EXITROOM` primero. Cuando no llega —**8 dobles `FF10` en 3 días**, más
      los crashes— el `usn` queda sentado en una mesa que nadie va a limpiar nunca, y esa mesa
      vuelve la sala **inmortal** (`desregistrar_rid` sólo borra si no queda NADIE).

    ★ Hace lo mismo que el `FF12` **menos el eco**: el eco le dice al cliente "volvé al vestíbulo",
      y acá el jugador no está volviendo a ningún lado — está yendo a otra sala. Mandárselo lo
      sacaría de la sala a la que justo está entrando.

    ⚠ Y recorre `mesas_del_usn`, no `st.room_id`: si ya quedaron varias pegadas de antes, se van
      todas. Mirar sólo `room_id` es **la línea que causó el bug**.
    """
    _yo = getattr(st, "usn", None)
    if _yo is None:
        return []
    _viejas = [r for r in mesas_del_usn(_yo) if r and r != menos]
    if not _viejas:
        return []
    _limpias = []
    for _rv in _viejas:
        _antes = getattr(st, "room_id", None)
        st.room_id = _rv                      # `levantar_jugador` lee de acá; se repone abajo
        try:
            _r, _quedaba = levantar_jugador(st)
            if _quedaba:
                difundir_salida(_rv, st)
                difundir_userlist(_rv, menos=st, por_salida=True)
                actualizar_ocupantes_sala(_rv)
                if getattr(st, "slot_espectador", None) is not None:
                    difundir_espectadores(_rv, motivo=" (se fue uno que miraba)")
                traspasar_anfitrion_al_salir(_rv, st)
            desregistrar_rid(_rv)
            _limpias.append(_rv)
        except Exception as e:
            log("LOBBY", f"  ⚠ sacando a usn={_yo} de la sala {_rv}: {e!r}")
        finally:
            st.room_id = _antes
    st.slot_espectador = None                 # las dos marcas son excluyentes; ver `sentar_jugador`
    log("LOBBY", f"  ★★ usn={_yo} SE LEVANTA de {_limpias} antes de {motivo or 'sentarse en otra'} "
                 f"— sin esto la/s vieja/s quedaba/n de FANTASMA con él sentado")
    return _limpias


def h_33_ff12(st, cmd, data):
    # rama original:  cmd == 18
    # ★ En el LOBBY/ENTRENAMIENTO (sin sala) el cliente manda FF12 como tick de idle/AFK (~cada 2min de inactividad).
    #   Echarlo = ejecuta la salida al lobby y te SACA (bug reportado). Solo debe salir cuando estas en una SALA real.
    #   Fix: echo SOLO si room_id (sala creada via FF10). En cualquier otro estado -> NO responder = te quedas parado.
    # ★★ SALIR DE UN LUGAR ESPECIAL (Mi Casa / Sala de Conversación). Ahí NO hay `room_id`, así
    #   que sin esta rama el eco no salía y el jugador quedaba ATRAPADO adentro (visto en vivo).
    if getattr(st, "lugar_tipo", None) is not None:
        _lt12 = st.lugar_tipo
        from . import charla
        if charla.es_compartida(_lt12):
            _cl12 = charla.salir(st, "FF12")    # ★ + el FF0E a los que quedan
        else:
            _cl12 = salir_de_lugar(st)          # ★ libera el asiento en la instancia persistente
        st.lugar_tipo = None
        st.send_ff55(0x12, b"", name=f"FF12 eco (salir del lugar especial tipo={_lt12})")
        log("LOBBY", f"  ★ FF12: sale del lugar {_cl12} -> vuelve al lobby. Quedan {(charla.gente(*_cl12) if charla.es_compartida(_lt12) else gente_en(*_cl12)) if _cl12 else 0} adentro (la instancia SIGUE VIVA)")
        return
    if getattr(st, "room_id", None):
        st.send_ff55(0x12, b"", name="FF12 eco (EXITROOM -> lobby)")
        # ★ El que MIRA también se va por acá. Se anota antes de soltarlo y se limpia la marca:
        #   si no, la conexión se lleva el casillero de espectador puesto a la sala siguiente —
        #   que es exactamente el molde que causó el bug del avatar que caminaba.
        _era_esp12 = getattr(st, "slot_espectador", None) is not None
        st.slot_espectador = None
        _rid12, _quedaba = levantar_jugador(st)   # ★ me saco de la mesa
        if _quedaba:
            # ★ PRIMERO el FF0E (que es lo que REALMENTE lo borra de la pantalla del otro) y
            #   después el FF0C, para dejar la lista consistente. Ver difundir_salida().
            difundir_salida(_rid12, st)
            difundir_userlist(_rid12, menos=st, por_salida=True)
            actualizar_ocupantes_sala(_rid12)
            if _era_esp12:
                difundir_espectadores(_rid12, motivo=" (se fue uno que miraba)")
            traspasar_anfitrion_al_salir(_rid12, st)   # ★ si el que se va era el dueño, hay heredero
        desregistrar_sala(st)                # ★★ MATCHER: sale de la lista SOLO si quedó vacía
        st.sala_poblada = None
        st.room_id = None
        log("LOBBY", f"  ★ FF12 EXITROOM en sala {_rid12} -> eco (dispara cRoom->cLobby)"
                     + (f"; quedan {len(mesa_de(_rid12))}" if _quedaba else "; sala vacía"))
        # ★★ Y AVISARLE A MIS AMIGOS QUE VOLVÍ AL VESTÍBULO. Va DESPUÉS de `st.room_id = None`,
        #   porque `_sala_de` lee ese campo: llamándolo antes mandaría la sala vieja.
        _avisar_ubicacion(st, "salió de la sala")
        # ★ Y al salir también: el que queda tiene que dejar de ver el enlace con quien se fue.
        refrescar_enlaces_de_pareja(_rid12, " (se fue alguien)")
        # ★★ Y a sus amigos del alma que quedan, la joya del que se fue se les tiene que ir:
        #   se les manda su FF15 con la lista nueva (ver `salas.actualizar_ocupantes`).
        from .salas import actualizar_ocupantes, almas_presentes
        actualizar_ocupantes(_rid12, almas_presentes(getattr(st, "usn", 0), _rid12),
                             motivo=" (se fue su amigo del alma)")
        # ⛔⛔ PERO ESO NO ALCANZABA, y anonimo03 lo vio: *"al salir la pareja de X, el adorno de
        #   pareja sigue activo"*. Dos motivos encadenados, los dos ya escritos en este repo:
        #     1. `refrescar_enlaces_de_pareja` **saltea a los que no están enlazados** — y el que
        #        queda deja de estarlo en cuanto el otro se va ⇒ no le llega nada.
        #     2. Y aunque le llegara, **el `FF15` no sirve para APAGAR**: `0x591FD0` nunca escribe
        #        `nodo+0x50`. El apagado nativo es el **`FF48` sub 0** (`0x5939B0`), que llama a
        #        `0x527B00(slotA, 0, slotB)` en los dos sentidos y **no dibuja cartel**
        #        (cero llamadas a `0x433380` en sus 0x180 bytes — medido).
        #   ⇒ Se manda el `FF48 sub 0` con los dos nombres, a los que quedan en la sala.
        try:
            from .lobby_pareja import _s2c_pareja_en_sala          # noqa: SLF001
            from .basedatos import db_pareja_de, db_get_char
            _yo12 = int(getattr(st, "usn", 0) or 0)
            _pj12 = db_pareja_de(_yo12) if _yo12 else 0
            if _pj12 and int(_pj12) in {int(u) for u in mesa_de(_rid12).values()}:
                # ⚠ Los DOS nombres van siempre: el handler los lee igual, y mandar uno solo le
                #   hace escribir un cero en un offset arbitrario de su propia pila.
                _n1 = str((db_get_char(_yo12) or {}).get("nick", "") or "")
                _n2 = str((db_get_char(int(_pj12)) or {}).get("nick", "") or "")
                _pk = _s2c_pareja_en_sala(0, _n1, _n2, sub=0)
                _n = 0
                for _u12 in mesa_de(_rid12).values():
                    _c12 = CONEXIONES.get(int(_u12))
                    if _c12 is not None and not getattr(_c12, "cerrado", False):
                        _c12.send_ff55(0x48, _pk,
                                       name=f"FF48 sub0 APAGAR el enlace «{_n1} & {_n2}» "
                                            f"(se fue uno de los dos)")
                        _n += 1
                log("LOBBY", f"  ★★ PAREJA: {_n1!r} se fue de la sala {_rid12} -> apagado el "
                             f"enlace con {_n2!r} en {_n} cliente(s)")
        except Exception as _e12:                                  # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude apagar el enlace de pareja al salir: {_e12!r}")
    else:
        log("LOBBY", "  ★ FF12 (idle/AFK en lobby-entrenamiento) -> IGNORADO (sin eco; te quedas)")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ EL ANFITRIÓN DE LA SALA — `FF9B` (cederlo) y la HERENCIA (cuando se va)
#
# Los dos síntomas que abrieron esto (2026-09-05, reportados en pantalla):
#   1. *"transferir anfitrión"* no hacía nada — el `FF9B` llegaba y **no había handler**.
#   2. al irse el anfitrión, el que quedaba no pasaba a serlo — el `FF13` mandaba `@6` clavado
#      en `HOST_SLOT`, así que la sala se quedaba mirando un asiento vacío como dueño.
#
# ── LO MEDIDO EN NUESTRO PROPIO LOG (18:22:36, sala 1, `testest` slot 2 · `jugador33` slot 3) ──
#     RX FF9B len=1 : 03        ← el anfitrión hace clic en el otro y elige "transferir"
#     RX FF9B len=1 : 03        ← nada pasa, lo intenta de nuevo
#     RX FF9B len=1 : 03        ← y otra vez
#     RX FF12                   ← se cansó y se fue de la sala
#   ⇒ **C→S `FF9B [slot_destino]`, UN solo byte.** Es el asiento del que va a recibir la sala.
#
# ── LO MEDIDO EN EL BINARIO (`R2Beat.exe.pristino`, handler `0x5D5500`) ──────────────────────
#   Lee TRES bytes (`0x67D200` ×3) y los usa así:
#       [0] slot   ·   [1] sin usar en este handler   ·   [2] estado
#     · `0x5D5533  cmp byte[estado], 0 / jne 0x5D55D5` -> distinto de 0 abre el popup 0x209
#       (el "no se pudo"). ⇒ **el OK va con [2] = 0**.
#     · `0x5D553E  cmp [[0x931660]+0x40], [slot]` -> compara MI asiento contra el del paquete:
#       **si no soy yo el destinatario, el handler no hace absolutamente nada.**
#   ⇒ Es ENABLE-ONLY y POR DESTINATARIO: se le manda AL NUEVO, no a la sala.
#
#   ★★★ Y LO IMPORTANTE, QUE ES DONDE EL CBT ENGAÑA: **el `FF9B` NO cambia de anfitrión.**
#   En todo el handler no hay una sola escritura a `+0x41`, que es el byte del que sale el
#   "soy el anfitrión" (lo escribe el `@6` del `FF13`, en `0x59D0E6`). El `FF9B` sólo prende la
#   UI del nuevo dueño. **Quien manda de verdad es el `FF13`** — por eso acá se difunde a TODA
#   la sala, y no sólo al que recibe: sin eso el viejo anfitrión se quedaría con el botón.
#
# ⚠ Se sigue mandando el `FF9B` igual que el CBT, porque el cliente lo espera y hace su parte de
#   UI. Pero si algún día esto falla, el sospechoso es el `FF13`, no el `FF9B`.
# ═════════════════════════════════════════════════════════════════════════════════════════════
# ★★★ AVISO DIFERIDO — heredado de un golpe que ya se pegó el CBT, no de una teoría.
#   `D:\R2Beat\server\servidor\lobby_salas.py` lo dejó escrito con todas las letras: *"lo que
#   TUMBABA a la VM cuando el HOST se iba era el `FF9B` (transferir líder) + `FF13`"* — el cliente
#   está en la carrera o en el CARTEL DE RESULTADO y no tolera que le rearmen la sala ahí.
#   El `FF0E` + la lista, en cambio, sí se pueden mandar en el momento (allá está medido y acá ya
#   se venía haciendo).
#   ⇒ Si la sala está corriendo, el traspaso se hace **igual y en el acto server-side** (nadie
#     queda sin dueño), pero el AVISO espera a que el jugador vuelva a la sala. Y "volvió" no se
#     adivina: es que él mismo pida el `FF13`, que es lo primero que hace al volver.
#   El dict vive en `salas.py` (junto a `ANFITRION`) para que lo limpie `desregistrar_sala`.


def sala_en_carrera(rid):
    """¿Hay alguien de esta sala adentro de una carrera (o en el cartel de resultado)?"""
    if rid is None:
        return False
    for _u in mesa_de(rid).values():
        _c = CONEXIONES.get(_u)
        # ★ 17-oct: el COLGADO (el reloj del cartel lo dio por no llegado y su conexión sigue abierta) no cuenta
        if _c is not None and getattr(_c, "en_carrera", False) and not getattr(_c, "carrera_colgada", False):
            return True
    return False


def _avisar_anfitrion(rid, usn, motivo=""):
    """`FF9B [slot][00][00]` al NUEVO anfitrión + `FF13` a toda la sala. Devuelve el slot o None."""
    if rid is None or usn is None:
        return None
    _slot = next((s for s, u in mesa_de(rid).items() if u == usn), None)
    if _slot is None:
        return None
    from .ajustes import ANFITRION_AVISO_EN_CARRERA
    if sala_en_carrera(rid) and not ANFITRION_AVISO_EN_CARRERA:
        ANFITRION_PENDIENTE[rid] = usn
        log("LOBBY", f"  ★★ ANFITRIÓN: la sala {rid} está EN CARRERA -> el traspaso a usn={usn} "
                     f"(slot {_slot}) ya está hecho, pero el FF9B/FF13 espera a que vuelva a la "
                     f"sala. Mandarlo ahora es lo que tumbaba al cliente en el CBT.{motivo}")
        return _slot
    _nuevo = CONEXIONES.get(usn)
    if _nuevo is not None and not getattr(_nuevo, "cerrado", False):
        try:
            # ⚠ Los TRES bytes son obligatorios: el handler lee 3 sí o sí, y el 3º (estado) tiene
            #   que ser 0 — con cualquier otro valor abre el cartel de error en vez de dar la sala.
            _nuevo.send_ff55(0x9B, bytes([_slot & 0x7F, 0x00, 0x00]),
                             name=f"FF9B sos el anfitrión (slot {_slot}){motivo}")
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude avisarle al nuevo anfitrión usn={usn}: {e!r}")
    # ★ Y el FF13 a TODOS: es el que realmente mueve el `+0x41`. Al viejo dueño le saca el botón.
    difundir_roominfo(rid, f" (anfitrión -> slot {_slot}){motivo}")
    return _slot


def traspasar_anfitrion_al_salir(rid, st):
    """El anfitrión se fue (`FF12` o se cayó la conexión): que la sala no quede sin dueño.

    ⚠ Se llama DESPUÉS de `levantar_jugador`, o sea con el que se va ya fuera de la mesa.
    ★ No hace nada si el que se fue no era el anfitrión — que es el caso normal.
    """
    if rid is None:
        return None
    _usn = getattr(st, "usn", None)
    # ★★★ Y LOS CAPITANES, ANTES DEL RETURN DE ABAJO (2026-09-07). Si el que se fue era capitán,
    #   su equipo queda sin uno — el mismo agujero del anfitrión, por el mismo camino. Va ACÁ
    #   porque esta función ya se llama en los TRES modos de salir (el `FF12`, que lo echen con el
    #   `FF20` y que se caiga la conexión), y repetirlo en los tres era pedir que se olvidara uno.
    #   ⚠ Va ANTES del `return` de invitado: el que se va puede no ser el anfitrión y ser capitán
    #     igual. Ese return sólo habla del dueño de la sala.
    #   ⚠ El nombre de esta función quedó corto para lo que hace. Se dejó así para no tocar sus
    #     tres llamadores; lo que hace de verdad es "reacomodar los puestos que dejó el que se va".
    # ⛔⛔ …PERO SÓLO EN LAS SALAS QUE USAN CAPITANES — corregido 2026-09-08 con el log de PROD.
    #   Esto corría en TODOS los modos, y `CAPITANES[rid]` sobrevivía al cambio de modo, así que
    #   una sala que había pasado por jefe y volvió a solo seguía difundiendo capitanes cada vez
    #   que alguien se iba: **25 `FF37` con equipo 1 y 2 a 5 clientes, en una sala solo+velocidad**
    #   (medido a las 12:15:49, y 80 de las 88 difusiones del día salieron por una SALIDA).
    #   De ahí las dos capturas: los asientos pintados como equipo, y alguien que deja de dibujarse
    #   (el `FF37` con equipo != 0 dispara el `0x5AFFD0` que nunca mapeamos — ver `enviar_equipos`).
    #   ⇒ El porqué entero está en `salas.sala_usa_capitanes`.
    if sala_usa_capitanes(rid):
        _caps_s, _cambio_s = reparar_capitanes(rid)
        if _cambio_s and mesa_de(rid):
            difundir_capitanes(rid, _caps_s, motivo=f" (se fue usn={_usn}, era capitán)")
    if anfitrion_de(rid) not in (None, _usn):
        return None                                   # se fue un invitado: el dueño sigue siendo el mismo
    _nuevo = elegir_anfitrion(rid, excluir=_usn)
    if _nuevo is None:
        log("LOBBY", f"  ★ la sala {rid} se quedó sin nadie: no hay a quién pasarle el anfitrión")
        return None
    _slot = _avisar_anfitrion(rid, _nuevo, " [herencia: se fue el dueño]")
    log("LOBBY", f"  ★★ ANFITRIÓN HEREDADO en la sala {rid}: se fue usn={_usn} -> ahora manda "
                 f"usn={_nuevo} (slot {_slot}). Antes la sala quedaba sin dueño y nadie podía "
                 f"arrancar ni cambiar el modo.")
    return _nuevo


def h_ff20_expulsar(st, cmd, data):
    """`FF20 [slot]` — el anfitrión echa de la sala al que está en ese asiento.

    ⛔ NO EXISTÍA. El cliente lo manda desde el mismo menú que el «pasar anfitrión», pero acá
      caía en «SIN handler» y no pasaba nada: el jugador apretaba «expulsar» y el otro se quedaba
      sentado. Visto en vivo el 2026-09-07 en el log del server local:
          RX FF55 -> FF20 · inner FF20 len=1 : 03 · SIN handler
      El `03` es el SLOT (el ocupante del asiento 3 era justo al que se quiso echar).

    ★ QUÉ HAY QUE MANDAR — ya estaba documentado en `ANFITRION_DE_SALA.md` §7, del CBT:
        · al expulsado  -> `FF20`  (su handler `0x5CE080` lo devuelve al lobby)
        · a los que quedan -> `FF0E`, que es el ÚNICO que borra a alguien de la pantalla.
          El `FF0C` sólo INSERTA (upsert por slot, sin clear): re-mandarlo con uno menos no saca
          a nadie. Eso ya está medido y explicado en `difundir_salida()`.

    ⇒ De ahí en más es exactamente la salida voluntaria del `FF12`, pero ejecutada sobre OTRA
      conexión: sacarlo de la mesa, avisar a los que quedan, refrescar la sala y, si el que sale
      era el dueño, heredar. Se reusa el mismo camino en vez de escribir uno paralelo.
    """
    _rid = getattr(st, "room_id", None)
    if not _rid or not data:
        log("LOBBY", f"  ⚠ FF20 sin sala o sin cuerpo (rid={_rid}, {len(data)}B) -> nada que hacer")
        return
    _yo = getattr(st, "usn", None)
    _duenio = anfitrion_de(_rid)
    if _duenio is not None and _duenio != _yo:
        # El cliente sólo dibuja el menú para el dueño, así que por la vía normal no pasa. Se
        # rechaza igual: es la única puerta para que un invitado eche a otro.
        log("LOBBY", f"  ⚠ FF20 RECHAZADO: usn={_yo} no es el anfitrión de la sala {_rid} "
                     f"(lo es usn={_duenio})")
        return
    _slot = data[0] & 0x7F
    # ★★ EXPULSAR A UN ESPECTADOR (2026-09-08). Reportado: *"intente expulsar siendo master a un
    #   espectador y no fue expulsado"*. Buscabamos solo en `mesa_de`, que son los SENTADOS — y un
    #   espectador vive en los slots 6..11, fuera de la mesa. Misma familia que el chat, el modo,
    #   el "listo" y el arranque: el que mira no esta en la mesa y hay que ir a buscarlo aparte.
    if 6 <= _slot <= 11:
        _ce = next((c for c in espectadores_de(_rid)
                    if getattr(c, "slot_espectador", None) == _slot), None)
        if _ce is None:
            log("LOBBY", f"  ⚠ FF20: no hay espectador en el slot {_slot} de la sala {_rid}")
            return
        _ce.send_ff55(0x20, bytes([_slot]), name=f"FF20 ESPECTADOR EXPULSADO (slot {_slot})")
        _ce.slot_espectador = None
        _ce.room_id = None
        log("LOBBY", f"  ★★★ FF20: el anfitrion echo al ESPECTADOR usn={getattr(_ce,'usn',None)} "
                     f"(slot {_slot}) de la sala {_rid}")
        # ★★ Y BORRARLO DE LA LISTA DE LOS DEMAS. El `FF0C` sólo INSERTA: re-mandarlo con uno
        #   menos no saca a nadie. El único que borra es el `FF0E`, por NOMBRE. Es la misma regla
        #   que ya estaba escrita para los jugadores en `difundir_salida`.
        #   Reportado: *"expulsar funciona, pero la lista de espectadores no se actualiza"*.
        _nk = str((db_get_char(getattr(_ce, "usn", 0)) or {}).get("nick", "") or "")
        _cr = _nk.encode("cp1252", "replace")[:NICK_MAX_FF0E]
        for _c in conexiones_en_sala(_rid):
            if _cr:
                _c.send_ff55(0x0E, bytes([len(_cr)]) + _cr,
                             name=f"FF0E quitar espectador {_nk!r}")
            enviar_roominfo(_c, motivo=" (se fue un espectador)")
        difundir_espectadores(_rid, motivo=" (echaron a uno que miraba)")
        return
    _victima = mesa_de(_rid).get(_slot)
    if _victima is None or _victima == _yo:
        log("LOBBY", f"  ⚠ FF20: el slot {_slot} de la sala {_rid} está vacío o soy yo "
                     f"(mesa: {mesa_de(_rid)}) -> no echo a nadie")
        return
    _con = CONEXIONES.get(_victima)
    if _con is None or getattr(_con, "cerrado", False):
        # Se fue justo antes (o es un NPC): igual hay que dejar la mesa limpia.
        with _mesa_lock:
            OCUPACION.get(_rid, {}).pop(_slot, None)
        actualizar_ocupantes_sala(_rid)
        log("LOBBY", f"  ★ FF20: el slot {_slot} (usn={_victima}) ya no tenía conexión; "
                     f"se libera el asiento y listo")
        return

    _con.send_ff55(0x20, bytes([_slot]), name=f"FF20 EXPULSADO (slot {_slot})")
    _rid20, _quedaba = levantar_jugador(_con)
    _con.room_id = None
    if _quedaba:
        difundir_salida(_rid20 or _rid, _con)
        difundir_userlist(_rid20 or _rid, menos=_con, por_salida=True)
        actualizar_ocupantes_sala(_rid20 or _rid)
        traspasar_anfitrion_al_salir(_rid20 or _rid, _con)
    desregistrar_sala(_con)
    log("LOBBY", f"  ★★★ FF20 EXPULSIÓN en la sala {_rid}: el anfitrión usn={_yo} echó a "
                 f"usn={_victima} (slot {_slot}). FF20 al echado + FF0E a los que quedan"
                 + (f"; quedan {len(mesa_de(_rid))}" if _quedaba else "; la sala quedó vacía"))


def h_ff87_cerrar_slot(st, cmd, data):
    r"""`FF87 [modo][slot]` — el anfitrión cierra (o abre) un asiento vacío.

    ⛔ NO EXISTÍA: caía en `SIN handler`. Lo destapó el usuario probando los botones, y el log dejó
      el rastro con el spam de clicks (apretaba varias veces porque no pasaba nada):

          21:59:52  inner FF87 len=2 : 00 00      ← el asiento 0, seis veces
          21:59:55  inner FF87 len=2 : 00 05      ← el asiento 5, cinco veces

      ⇒ **@1 es el SLOT.** Coincide con los dos botones que apretó.

    ⏳ **@0 NO ESTÁ CONFIRMADO.** En las once muestras vale siempre `00`, así que no hay con qué
      distinguir "cerrar" de "abrir": puede ser un modo (0=cerrar / 1=abrir) o puede ser basura.
      Se toma como MODO —`0` cierra, cualquier otro abre— porque es la lectura que no rompe si
      resulta ser otra cosa: si el cliente manda siempre `0`, el asiento queda cerrado y se abre
      desde el mismo botón cuando el cliente mande algo distinto.
      ⚠ Si al probar en pantalla NO se puede volver a abrir, la respuesta es que @0 no es el modo
        y esto pasa a ser un TOGGLE. Es un `if` y está anotado acá para no re-descubrirlo.

    ★ El asiento cerrado viaja en el `open_mask` del `FF13` (bit en 1 = abierto), que hasta hoy
      iba clavado en `0x3F`. Ver `salas.mascara_abiertos`.
    """
    _rid = getattr(st, "room_id", None)
    if not _rid or len(data) < 2:
        log("LOBBY", f"  ⚠ FF87 sin sala o corto (rid={_rid}, {len(data)}B)")
        return
    _duenio = anfitrion_de(_rid)
    if _duenio is not None and _duenio != getattr(st, "usn", None):
        log("LOBBY", f"  ⚠ FF87 RECHAZADO: usn={getattr(st, 'usn', None)} no es el anfitrión "
                     f"de la sala {_rid}")
        return
    _modo, _slot = data[0], data[1] & 0x7F
    _cerrar = (_modo == 0)
    if _cerrar and mesa_de(_rid).get(_slot) is not None:
        # Cerrar un asiento OCUPADO sería echar a alguien por la puerta de atrás. Para eso está
        # el `FF20`, que además le avisa al que se va.
        log("LOBBY", f"  ⚠ FF87: el asiento {_slot} está OCUPADO -> no lo cierro "
                     f"(para echar a alguien está el FF20)")
        return
    _cerrados, _cambio = cerrar_slot(_rid, _slot, _cerrar)
    if not _cambio:
        return                                   # ya estaba así: el spam de clicks no hace nada
    # El `FF13` lleva el `open_mask`, así que reemitirlo a todos es lo que pinta el cambio.
    # ★★ Y "TODOS" INCLUYE A LOS QUE MIRAN — 2026-09-08. Reportado: *"si el master abre un slot,
    #   esto no se sincroniza con los espectadores"*. Recorría `mesa_de` = los sentados, así que el
    #   espectador seguía viendo la máscara vieja: los asientos que se abrían le quedaban cerrados
    #   en pantalla. Y eso importa más que la estética — es de donde su cliente saca si hay lugar
    #   para pasar a jugar.
    for _c in conexiones_en_sala(_rid):
        enviar_roominfo(_c, motivo=f" (asiento {_slot} {'cerrado' if _cerrar else 'abierto'})")
    log("LOBBY", f"  ★★★ FF87 asiento {_slot} {'CERRADO' if _cerrar else 'ABIERTO'} en la sala "
                 f"{_rid} (modo={_modo}) · cerrados ahora: {sorted(_cerrados) or 'ninguno'} · "
                 f"open_mask=0x{mascara_abiertos(_rid):02X}")


def equipo_del_puesto(st, rid, slot):
    r"""El equipo que hay que mandar en el `FF99` para ese asiento — o `0xFF` si la sala NO usa equipos.

    ⛔⛔ EL BUG QUE ESTO ARREGLA, visto en producción el 2026-09-08 y confirmado en el log.
      Reportado con captura: *"la sala es **solo + velocidad**, pero cuando el espectador entra al
      slot, los demás se pintan como si fuera **equipo**"*. Y el log lo dice con todas las letras:

          12:04:11  ★★ FF99 tipo=0: puesto 6 -> 2 (equipo 1) … (deja de mirar y se sienta)
          13:22:16  ★★ FF99 tipo=0: puesto 6 -> 3 (equipo 2) … (deja de mirar y se sienta)

      Mandábamos `equipo_de(rid, slot)`, que **nunca devuelve 0**: cuando nadie fijó un equipo cae
      en `equipo_por_defecto` = `1 si slot < 3, si no 2`. O sea que en una sala SOLO igual viajaba
      un equipo, y el handler del `FF99` —que asigna el equipo salvo que valga `0xFF`— le pintaba
      el color al asiento.

    ★ El `0xFF` es el valor neutro que el propio cliente define (ver `ESPECTADOR_CAMBIO_5B` en
      `ajustes.py`): con él, `0x5E4A40` **saltea la asignación de equipo** y sólo mueve la ficha.

    ⚠ La pregunta "¿esta sala usa equipos?" la contesta `sala_por_equipos`, que es la MISMA regla
      del cliente (`0x58BFF0`) — no una lista de bits nuestra. Por eso el jefe entra aunque su
      `room_mode` no traiga ningún bit de equipo.
    """
    return equipo_de(rid, slot) if sala_por_equipos(st) else 0xFF


def mover_de_puesto(rid, origen, destino, equipo=0, motivo=""):
    """`FF99 [0][origen][destino][0][equipo]` a TODA la sala: mueve a alguien de puesto.

    Es el camino que **no reconstruye la escena** — el porqué entero, con el disasm, está en
    `ESPECTADOR_CAMBIO_5B` (`ajustes.py`). El resumen: el handler `0x5E4A40` con `tipo 0` mueve al
    ocupante y, si el que se movió es el propio cliente, le reescribe su `me+0x40`. Los puestos
    **0..5 son asientos y 6..11 casilleros de mirar**, y el binario acepta los 6..11 a propósito.

    ⚠ Va a `conexiones_en_sala`: todos tienen que mover la misma ficha, incluidos los que miran.
    ⚠ `equipo_origen` se manda en **0 y no en 0xFF**: con 0xFF el handler fuerza el equipo del
      destino a 0 y perderíamos el color en las salas por equipos.
    """
    _cuerpo = bytes([0x00, origen & 0xFF, destino & 0xFF, 0x00, equipo & 0xFF])
    _n = 0
    for _c in conexiones_en_sala(rid):
        try:
            _c.send_ff55(0x99, _cuerpo,
                         name=f"FF99 MOVER puesto {origen} -> {destino} (equipo {equipo})")
            _n += 1
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandar el FF99 de mover: {e!r}")
    log("LOBBY", f"  ★★ FF99 tipo=0: puesto {origen} -> {destino} (equipo {equipo}) "
                 f"difundido a {_n} de la sala {rid}{motivo}")
    return _n


def h_ff99_cambiar_de_puesto(st, cmd, data):
    r"""`FF99` **VACÍO** — el botón de "mirar" ⇄ "competir". MEDIDO EN VIVO el 2026-09-08.

    ★★★ EL DATO, y es de los que ahorran una sesión entera: **los DOS botones mandan el MISMO
      paquete, sin un solo byte de payload**. El usuario hizo spam de los dos y la sonda de
      `handle_inner` los dejó uno al lado del otro:

          01:43:12  ★★★ SONDA ESPECTADOR (casillero 6): FF99 len=0 : (vacío)   ← mirar -> jugar
          01:43:14  inner FF99 len=0  ·  SIN handler                            ← jugar -> mirar

      ⇒ No es "un paquete para cada dirección" ni trae a dónde quiere ir: es un **conmutador**, y
        **el que decide es el SERVER** según de qué lado esté el que lo manda. Por eso este
        handler mira `slot_espectador` y no el contenido — no hay contenido.

    ⛔ POR QUÉ ESTUVO TANTO TIEMPO SIN ENCONTRARSE: el `FF99` ya lo conocíamos, pero **por el otro
      lado**. En `salas.enviar_equipos` lo usamos S→C con 5 bytes `[tipo][slotA][slotB][aux][equipo]`
      para pintar asientos, y la sonda `.obs` lo probó S→C "con todas las combinaciones" buscando
      convertir a alguien ya sentado — y sacaba al jugador de su asiento sin ponerlo en la lista.
      La conclusión de entonces ("el `FF99` no es el camino") era correcta **para lo que se probó**
      y ocultaba lo otro: el `FF99` C→S es el PEDIDO, y lo que faltaba era contestarlo.

    ★ CÓMO SE CONTESTA: con el mismo `FF11 [slot][tipo]` que ya usamos para entrar. El byte0 es el
      asiento y el cliente hace `me+0x40 = byte0` (parser `0x5CD8D0`); los slots **0..5 son jugar**
      y los **6..11 mirar**. O sea que las dos direcciones son la misma respuesta con otro número,
      y las dos están probadas en pantalla desde ayer.
      ⏳ SIN MEDIR: mandar ese `FF11` a un cliente que YA está adentro de la sala (hasta ahora
        siempre se mandó al que estaba ENTRANDO). Si en vez de conmutar reconstruye la escena o
        saca un cartel raro, es esta línea — y el plan B es el `FF99` S→C de 5 bytes.

    ⚠ EN CARRERA NO. Entrar a una sala que ya está corriendo dejó la partida colgada para todos
      (medido en producción, ver el guard del `FF11`); cambiar de puesto en el medio es lo mismo.
    """
    _rid = getattr(st, "room_id", None)
    if not _rid:
        log("LOBBY", "  ⚠ FF99 sin sala: no hay puesto que cambiar")
        return
    if sala_en_carrera(_rid):
        log("LOBBY", f"  ⛔ FF99: la sala {_rid} está EN CARRERA -> no se cambia de puesto "
                     f"(entrar/salir a mitad de partida la deja colgada para todos)")
        return
    # ⛔ 17-oct (EN PROD, anonimo03: «al entrar en modo espectador me mandó al tipo de sala "mi casa"»): el default era 0x0C,
    #   que NO es sala de carrera (es un lugar de charla; ver el FF11 de entrar: «los medidos traen 13 y 2»). Lo usa el
    #   que nunca mandó un FF11 (el que CREÓ la sala, el auto-join con tipo 0) ⇒ 0x0D, lo mismo que la entrada normal.
    _tipo99 = getattr(st, "room_tipo", None) or 0x0D
    _nk99 = str((db_get_char(getattr(st, "usn", 0)) or {}).get("nick", "") or "")
    _cr99 = _nk99.encode("cp1252", "replace")[:NICK_MAX_FF0E]
    _era_esp = getattr(st, "slot_espectador", None)
    from .salas import asientos_de_la_sala as _asientos99
    _doce99 = _asientos99(_rid) == 12
    # ★ 17-oct (anonimo03, en prod: «actualmente rehacemos la sala, pero nativamente no se rehacía: se cambiaba de slot»): en
    #   la de 12 va el MISMO FF99 de 5 bytes que en la de 6, con los lugares 12..17 (`0x5A0590` sólo valida 0..5; la dll
    #   le recalcula al movido la marca «soy mirón», sala12_vista.c). Rehacer la sala perdía los equipos del que mira
    #   (el ranking de 4 equipos salía mezclado). FF99_12_NATIVO = False: el camino de salir y volver a entrar.
    if _doce99 and not (FF99_12_NATIVO and ESPECTADOR_CAMBIO_5B):
        _ff99_sala_de_12(st, _rid, _tipo99, _cr99, _era_esp)
        return

    if _era_esp is not None:
        # ── MIRAR -> JUGAR ────────────────────────────────────────────────────────────────────
        # `sentar_jugador` ya respeta los asientos CERRADOS y los NPC: si no hay lugar devuelve
        # None y no se toca nada. El usuario lo pidió así: *"debe depender de si el slot está
        # abierto o cerrado"*.
        _slot99 = sentar_jugador(st, _rid, ocupados_extra=npcs_de(_rid))
        if _slot99 is None:
            log("LOBBY", f"  ⚠ FF99 MIRAR->JUGAR: no hay asiento libre y abierto en la sala {_rid} "
                         f"(mesa={mesa_de(_rid)}, cerrados={sorted(slots_cerrados(_rid)) or 'ninguno'}) "
                         f"-> se queda mirando")
            return
        if ESPECTADOR_CAMBIO_5B:
            # ★★ EL CAMINO QUE NO RECARGA LA SALA: un solo `FF99` de 5 bytes mueve la ficha en
            #   TODOS los clientes y, al que se movió, le reescribe su propio asiento. Ver el
            #   bloque de `ESPECTADOR_CAMBIO_5B` en `ajustes.py`.
            #   ⚠ Acá NO va el `FF0E`: borraría la ficha que el `FF99` tiene que mover.
            # ★ y acá también: el asiento al que se sienta puede estar sucio en algún cliente.
            #   El `FF99` MUEVE la ficha, pero si el destino ya está ocupado en ese cliente el
            #   movimiento no puede acomodarla. Ver `salas.liberar_asiento`.
            liberar_asiento(_rid, _slot99, motivo=" (uno pasa de mirar a competir)")
            mover_de_puesto(_rid, _era_esp, _slot99, equipo_del_puesto(st, _rid, _slot99),
                            motivo=" (deja de mirar y se sienta)")
        else:
            # ⏳ El camino viejo: se le contesta con el `FF11` de entrar. Anda, pero el cliente
            #   RECONSTRUYE la escena — se ve como salir de la sala y volver a entrar.
            #   ★ PRIMERO el `FF0E`, que lo saca del casillero de mirar, y DESPUÉS los `FF0C` que
            #     lo dibujan en su asiento: al revés lo borraría recién insertado.
            if _cr99:
                # ⚠ A ÉL NO. El `FF0E` borra POR NOMBRE, así que mandárselo al que acaba de
                #   sentarse le hace borrarse a SÍ MISMO de su propia sala — y en este camino
                #   después va un `difundir_userlist(menos=st)`, o sea que nadie se la repone.
                #   (Camino dormido mientras `ESPECTADOR_CAMBIO_5B` esté en True, pero el día que
                #   se apague el interruptor esto muerde.)
                for _c99 in conexiones_en_sala(_rid):
                    if _c99 is st:
                        continue
                    _c99.send_ff55(0x0E, bytes([len(_cr99)]) + _cr99,
                                   name=f"FF0E sacar {_nk99!r} de los espectadores (pasa a competir)")
            liberar_asiento(_rid, _slot99, motivo=" (uno pasa de mirar a competir)")
            st.send_ff55(0x11, bytes([_slot99 & 0xFF, _tipo99]),
                         name=f"FF11 (por FF99) DEJA DE MIRAR -> asiento {_slot99}")
        enviar_roominfo(st, motivo=" (pasó a competir)")
        enviar_userlist(st)
        difundir_userlist(_rid, menos=st)
        actualizar_ocupantes_sala(_rid)
        for _cc99 in conexiones_en_sala(_rid):
            if _cc99 is not None and not getattr(_cc99, "cerrado", False):
                enviar_equipos(_cc99, _rid)
        difundir_espectadores(_rid, motivo=" (uno pasó de mirar a competir)")
        log("LOBBY", f"  ★★★ FF99 MIRAR->JUGAR: usn={getattr(st,'usn',None)} deja el casillero "
                     f"{_era_esp} y se sienta en el ASIENTO {_slot99} de la sala {_rid}")
        return

    # ── JUGAR -> MIRAR ────────────────────────────────────────────────────────────────────────
    # ⚠ El ÚLTIMO jugador no se puede ir a mirar: la sala quedaría sin nadie que pueda arrancar,
    #   con gente adentro. Es el mismo agujero que ya se tapó con la herencia del anfitrión.
    if len(mesa_de(_rid)) <= 1:
        log("LOBBY", f"  ⚠ FF99 JUGAR->MIRAR: usn={getattr(st,'usn',None)} es el único jugador de "
                     f"la sala {_rid} -> NO lo dejo (la sala quedaría sin quién arranque)")
        return
    _ocup99 = {getattr(c, "slot_espectador", None) for c in conexiones_en_sala(_rid)}
    _se99 = next((s for s in (ESPECTADOR_SLOTS_12 if _doce99 else ESPECTADOR_SLOTS) if s not in _ocup99), None)
    if _se99 is None:
        log("LOBBY", f"  ⚠ FF99 JUGAR->MIRAR: no quedan casilleros de mirar en la sala {_rid}")
        return
    _slot_viejo = getattr(st, "room_slot", None)
    levantar_jugador(st, olvidar_eleccion=False)   # ★ libera su asiento (y le borra el `room_slot`);
                                              #   sigue EN la sala: lo que eligió para sí no vence
    st.slot_espectador = _se99
    if ESPECTADOR_CAMBIO_5B and _slot_viejo is not None:
        # ★★ Un solo `FF99`: la ficha se MUEVE del asiento al casillero en todos los clientes.
        #   ⚠ Nada de `FF0E` ni de `FF0C` acá — el `FF0E` borraría la ficha que hay que mover y el
        #     `FF0C` la insertaría de nuevo. El paquete hace las dos cosas de una.
        mover_de_puesto(_rid, _slot_viejo, _se99, 0, motivo=" (deja de competir y pasa a mirar)")
        enviar_roominfo(st, motivo=" (pasó a mirar)")
    else:
        difundir_salida(_rid, st)             # ★ FF0E: lo saca del asiento en la pantalla de todos
        st.send_ff55(0x11, bytes([_se99 & 0xFF, _tipo99]),
                     name=f"FF11 (por FF99) PASA A MIRAR -> casillero {_se99}")
        enviar_roominfo(st, motivo=" (pasó a mirar)")
        enviar_userlist(st)
        # ★ Y que los demás lo vean en la sección: su `FF0C` en el casillero 6..11.
        _oc99 = _ocupante_espectador(st)
        if _oc99 is not None:
            for _c99 in conexiones_en_sala(_rid):
                _c99.send_ff55(0x0C, build_ff0c_2013_real(_oc99, k=2),
                               name=f"FF0C espectador {_oc99['nick']!r} slot {_oc99['slot']}")
    difundir_espectadores(_rid, motivo=" (uno dejó de competir)")
    # ★ Y si el que se fue a mirar era el ANFITRIÓN o un CAPITÁN, la sala hereda: es el mismo
    #   camino que usar el `FF12`, que lo echen o que se le caiga la conexión.
    traspasar_anfitrion_al_salir(_rid, st)
    log("LOBBY", f"  ★★★ FF99 JUGAR->MIRAR: usn={getattr(st,'usn',None)} deja el asiento "
                 f"{_slot_viejo} y pasa al casillero {_se99} de la sala {_rid}")


def _ff99_sala_de_12(st, rid, tipo, crudo, era_esp):
    r"""★ 17-oct · (87) el `FF99` (mirar ⇄ competir) en la SALA DE 12 — anonimo03: *«hoy sólo se puede espectar cuando la
    sala está llena»*.

    ⚠ El camino de la de 6 (`FF99` de 5 bytes que MUEVE la ficha) no sirve acá: los lugares de mirar son 12..17 y
      (1) que `0x5A0900`/`0x5B5700` los acepten no está medido, y (2) los CORREDORES de la de 12 no tienen a los que miran
      en su mapa a propósito (`_ocupante_espectador`: el de 12+ sólo a los que miran). ⇒ el que cambia SALE y VUELVE A
      ENTRAR por los dos `FF11` que ya andan: el de entrar a mirar (código `ESPECTADOR12_CODIGO + k`, la dll lo
      convierte en el lugar 12 + k) y el de sentarse. El cliente rearma la sala (se ve como salir y entrar); la etiqueta
      del botón la pone la dll según su lugar (`sala12_vista.c`, s12v_esp_boton).
    """
    if era_esp is not None:
        # ── MIRAR -> JUGAR: el FF0E sólo a los que miran (los corredores nunca lo tuvieron), y el FF11 de sentarse ──
        _slot = sentar_jugador(st, rid, ocupados_extra=npcs_de(rid))
        if _slot is None:
            log("LOBBY", f"  ⚠ FF99 (sala de 12) MIRAR->JUGAR: no hay asiento libre y abierto en la sala {rid} "
                         f"-> se queda mirando")
            return
        if crudo:
            for _c in conexiones_en_sala(rid):
                if _c is not st and (ESPECTADOR12_A_CORREDORES or getattr(_c, "slot_espectador", None) is not None):
                    _c.send_ff55(0x0E, bytes([len(crudo)]) + crudo,
                                 name=f"FF0E sacar {crudo!r} de los espectadores (pasa a competir, sala de 12)")
        liberar_asiento(rid, _slot, motivo=" (uno pasa de mirar a competir, sala de 12)")
        st.send_ff55(0x11, bytes([_slot & 0xFF, tipo]), name=f"FF11 (por FF99) DEJA DE MIRAR -> asiento {_slot}")
        enviar_roominfo(st, motivo=" (pasó a competir)")
        enviar_userlist(st)
        difundir_userlist(rid, menos=st)
        actualizar_ocupantes_sala(rid)
        for _c in conexiones_en_sala(rid):
            if _c is not None and not getattr(_c, "cerrado", False):
                enviar_equipos(_c, rid)
        difundir_espectadores(rid, motivo=" (uno pasó de mirar a competir)")
        log("LOBBY", f"  ★★★ FF99 (sala de 12) MIRAR->JUGAR: usn={getattr(st, 'usn', None)} deja el lugar {era_esp} "
                     f"y se sienta en el ASIENTO {_slot} de la sala {rid}")
        return

    # ── JUGAR -> MIRAR ──
    if len(mesa_de(rid)) <= 1:
        log("LOBBY", f"  ⚠ FF99 (sala de 12) JUGAR->MIRAR: usn={getattr(st, 'usn', None)} es el único jugador de la "
                     f"sala {rid} -> NO lo dejo (la sala quedaría sin quién arranque)")
        return
    _ocup = {getattr(c, "slot_espectador", None) for c in conexiones_en_sala(rid)}
    _se = next((s for s in ESPECTADOR_SLOTS_12 if s not in _ocup), None)
    if _se is None:
        log("LOBBY", f"  ⚠ FF99 (sala de 12) JUGAR->MIRAR: no quedan lugares de mirar en la sala {rid}")
        return
    _slot_viejo = getattr(st, "room_slot", None)
    difundir_salida(rid, st)                       # FF0E: lo saca del asiento en la pantalla de todos
    levantar_jugador(st, olvidar_eleccion=False)
    st.slot_espectador = _se
    _cod = ESPECTADOR12_CODIGO + _se - 12
    st.send_ff55(0x11, bytes([_cod & 0xFF, tipo]),
                 name=f"FF11 (por FF99) PASA A MIRAR -> lugar {_se} (código 0x{_cod:02X}, sala de 12)")
    # lo mismo que el FF11 de entrar a mirar (`h_18_ff11`, rama del espectador)
    enviar_roominfo(st, motivo=" (pasó a mirar)")
    enviar_userlist(st)
    st.pd_por_contar = (rid, False)
    try:
        enviar_equipos(st, rid)
    except Exception as _e_eq:
        log("LOBBY", f"  ⚠ no pude pintarle los equipos al que pasó a mirar: {_e_eq!r}")
    difundir_espectadores(rid, motivo=" (uno dejó de competir)")
    _oc = _ocupante_espectador(st, incluir12=True)
    if _oc is not None:
        for _c in conexiones_en_sala(rid):
            if _c is not st and (ESPECTADOR12_A_CORREDORES or getattr(_c, "slot_espectador", None) is not None):
                _c.send_ff55(0x0C, build_ff0c_2013_real(_oc, k=2),
                             name=f"FF0C espectador {_oc['nick']!r} slot {_oc['slot']}")
    traspasar_anfitrion_al_salir(rid, st)
    log("LOBBY", f"  ★★★ FF99 (sala de 12) JUGAR->MIRAR: usn={getattr(st, 'usn', None)} deja el asiento "
                 f"{_slot_viejo} y pasa al lugar {_se} de la sala {rid}")


def h_ff175_ceder_capitan(st, cmd, data):
    r"""`FF175 [slot]` — el capitán le cede el puesto a un compañero de SU equipo.

    ⛔ NO EXISTÍA: caía en `SIN handler` y el menú no hacía nada. Lo destapó el usuario probándolo
      en vivo el 2026-09-07, una vez por equipo, y el log dejó las dos pruebas seguidas:

          21:34:51  inner FF175 len=1 : 01     (equipo rojo,  cederle al slot 1)
          21:34:55  inner FF175 len=1 : 03     (equipo azul,  cederle al slot 3)

      El byte es el SLOT de destino. Se confirmó contra lo que él hizo en pantalla: los capitanes
      de ese momento eran los slots 2 y 4, y les cedía a un compañero de cada equipo.

    ⚠ OJO CON EL NÚMERO: `FF175` es `0x175` = **373**, no 175. El 175 decimal es `0xAF` = `FFAF`,
      que ya está tomado por la tienda. El log escribe los comandos en hex.

    ★ Se difunde con `FF37` y no con el `FF175` S→C: el `FF37` aplica equipo + capitanía de una
      vez y ya está probado en el sorteo. Ver `salas.enviar_ff37`.
    """
    _rid = getattr(st, "room_id", None)
    if not _rid or not data:
        log("LOBBY", f"  ⚠ FF175 sin sala o sin cuerpo (rid={_rid}, {len(data)}B)")
        return
    _yo_slot = getattr(st, "room_slot", None)
    if _yo_slot is None:
        return
    _eq = equipo_de(_rid, _yo_slot)
    _caps = capitanes_de(_rid)
    if _caps.get(_eq) != _yo_slot:
        # El cliente sólo le dibuja el menú al capitán; se rechaza igual porque es la única puerta
        # para que un cualquiera se quede con la capitanía de su equipo.
        log("LOBBY", f"  ⚠ FF175 RECHAZADO: el slot {_yo_slot} no es capitán del equipo {_eq} "
                     f"(lo es el {_caps.get(_eq)})")
        return
    _destino = data[0] & 0x7F
    if _destino == _yo_slot:
        return                                   # cederse a sí mismo: nada que hacer
    _nuevos = poner_capitan(_rid, _eq, _destino)
    if _nuevos is None:
        log("LOBBY", f"  ⚠ FF175: el slot {_destino} está vacío o no es del equipo {_eq} "
                     f"-> no le cedo la capitanía (dejaría al equipo sin capitán)")
        return
    difundir_capitanes(_rid, _nuevos,
                       motivo=f" (el slot {_yo_slot} le CEDIÓ el puesto al {_destino})")


def h_ffc9_dificultad(st, cmd, data):
    r"""`FFC9 [banda]` — el anfitrión cambia la DIFICULTAD de la sala.

    ⛔ NO EXISTÍA. Reportado por el usuario el 2026-09-07: *"el interruptor de licencia de la sala
      libre, le haré spam unas 5 veces, sólo me deja hasta novato estrella"*. En el log del server
      local se ve el pedido llegando y muriendo ahí:
          inner FFC9 len=1 : 01 · SIN handler
          inner FFC9 len=1 : 02 · SIN handler
      El cliente pide el cambio, no le contestamos nada, y el interruptor se queda donde estaba.

    ★ LA RECETA, MEDIDA sobre el server de referencia (`taller/re2013/capturas/mitm_20260907_183811`):
      **8 pedidos, 8 respuestas, correlación perfecta y sin una sola excepción**. Al llegar el
      `FFC9` hace TRES cosas, y las tres hacen falta:

        1. **eco** del MISMO byte, sólo al que lo pidió
               RX FFC9 : 04   ->   TX FFC9 : 04
        2. **`FF13` a TODOS** los de la sala, con el valor en `cola[41]`
               FFC9=04 -> el FF13 termina en `04 00 00 00`   (y 03 -> 03, 02 -> 02, 01 -> 01)
        3. un **chat de sistema** a todos, con el nick literal `Servidor`:
               "Servidor.<nick> pone la dificultad de la sala en N"

    ⚠ Y ese chat le pone NOMBRE al campo: lo que viaja acá es la **dificultad de la sala**, no la
      licencia del jugador. Por eso el valor se guarda en `salas.DIFICULTAD_SALA` (room-level) y no
      en `st`: si viviera en la conexión, el que lo cambia lo vería y el resto no — el mismo error
      que ya se pagó con los NPC, la pista, la canción y el anfitrión.

    ⚠⚠ El eco va SÓLO al que pidió, no a toda la sala. Así lo hace el referente (una respuesta por
      pedido, nunca una ráfaga) y tiene sentido: a los demás lo que les cambia la pantalla es el
      `FF13`, no el `FFC9`, que además le reaplica el filtro al picker del que lo tocó.
    """
    _rid = getattr(st, "room_id", None)
    if not _rid or not data:
        log("LOBBY", f"  ⚠ FFC9 sin sala o sin cuerpo (rid={_rid}, {len(data)}B) -> nada que hacer")
        return
    _yo = getattr(st, "usn", None)
    _duenio = anfitrion_de(_rid)
    if _duenio is not None and _duenio != _yo:
        # El cliente sólo le dibuja el interruptor al dueño, así que por la vía normal no pasa.
        # Se rechaza igual: es la única puerta para que un invitado le cambie la sala al anfitrión.
        log("LOBBY", f"  ⚠ FFC9 RECHAZADO: usn={_yo} no es el anfitrión de la sala {_rid} "
                     f"(lo es usn={_duenio})")
        return
    _pedida = data[0] & 0xFF
    _banda = poner_dificultad(_rid, _pedida)
    if _banda is None:
        # Fuera de 1..8. No lo guardamos, pero queda anotado: si algún día aparece (p.ej. el 9, que
        # `0x58CEF0` traduce a "categoría 13 = LIBRE"), lo vemos acá en vez de que entre en silencio.
        log("LOBBY", f"  ⚠ FFC9 con banda {_pedida} FUERA de 1..8 en la sala {_rid} -> no se guarda. "
                     f"Si esto aparece seguido, hay que medir qué significa (¿el 9 = LIBRE?)")
        return

    # 1 · el eco, sólo al que lo pidió
    st.send_ff55(0xC9, bytes([_banda]), name=f"FFC9 eco dificultad={_banda} (la pidió él)")

    # 2 · el FF13 nuevo a todos  (+ 3 · el aviso por chat, sólo si está prendido)
    _nick = str((db_get_char(_yo) or {}).get("nick", "") or "").strip() or "alguien"
    _chat = None
    if AVISO_DIFICULTAD_POR_CHAT:
        _texto = f"{_nick} pone la dificultad de la sala en {_banda}"
        _rb = _texto.encode("cp1252", "replace")[:0xFF]
        _sysnick = b"Servidor"                  # ★ literal del referente: "Servidor.<nick> pone…"
        _chat = bytes([len(_sysnick)]) + _sysnick + bytes([len(_rb)]) + _rb + bytes([2, 0])
    _n = 0
    # ★ Y a los que MIRAN: la dificultad es de la sala (2026-09-08, ver `difundir_userlist`).
    for _c in conexiones_en_sala(_rid):
        if _c is None or getattr(_c, "cerrado", False):
            continue
        enviar_roominfo(_c, motivo=f" (dificultad -> {_banda})")
        if _chat is not None:
            _c.send_ff55(0x08, _chat, name=f"FF08 sistema: dificultad {_banda}")
        _n += 1
    log("LOBBY", f"  ★★★ FFC9 DIFICULTAD de la sala {_rid} -> {_banda} (la puso usn={_yo} "
                 f"{_nick!r}): eco al que pidió + FF13 a {_n} jugador(es)"
                 + ("" if _chat is not None else " (sin aviso por chat)"))


def h_48_ff9b(st, cmd, data):
    """`FF9B [slot]` — el anfitrión le cede la sala al que está en ese asiento."""
    # rama nueva:  cmd == 155
    _rid = getattr(st, "room_id", None)
    if not _rid or not data:
        log("LOBBY", f"  ⚠ FF9B sin sala o sin cuerpo (rid={_rid}, {len(data)}B) -> nada que hacer")
        return
    _yo = getattr(st, "usn", None)
    _duenio = anfitrion_de(_rid)
    if _duenio is not None and _duenio != _yo:
        # El cliente sólo dibuja el menú para el dueño, así que esto no debería pasar nunca por la
        # vía normal. Se rechaza igual: es la única puerta para robarle la sala a otro.
        log("LOBBY", f"  ⚠ FF9B RECHAZADO: usn={_yo} no es el anfitrión de la sala {_rid} "
                     f"(lo es usn={_duenio})")
        return
    _slot = data[0] & 0x7F
    _destino = mesa_de(_rid).get(_slot)
    if _destino is None or _destino == _yo:
        log("LOBBY", f"  ⚠ FF9B: el slot {_slot} de la sala {_rid} está vacío o soy yo "
                     f"(mesa: {mesa_de(_rid)}) -> no se traspasa")
        return
    poner_anfitrion(_rid, _destino)
    _slot_ok = _avisar_anfitrion(_rid, _destino, " [cedido a mano]")
    log("LOBBY", f"  ★★★ FF9B TRASPASO DE ANFITRIÓN en la sala {_rid}: usn={_yo} -> usn={_destino} "
                 f"(slot {_slot_ok}). FF9B al nuevo (prende su UI) + FF13 a todos (mueve el +0x41, "
                 f"que es lo que de verdad decide quién manda).")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ INTERCAMBIO DE ASIENTOS — `FF6B` / `FF6C`
#
# Es el mecanismo con el que se ordenan los TURNOS del modo RELEVO: los tramos van por posición
# dentro del equipo (0 vs 3, después 1 vs 4, al final 2 vs 5), así que elegir turno = elegir
# asiento. Los dos handlers ya estaban COMPILADOS en el cliente y nunca les mandamos un byte.
#
# Todo lo de abajo está VERIFICADO desensamblando `R2Beat.exe.pristino` (2026-09-05).
# Doc completa: `documentacion/MODO_RELEVO.md` §1.
# Guía: `D:\R2Beat\server\docs\FF6B_INTERCAMBIO_SLOTS.md` (el mismo mecanismo, medido en el CBT).
#
#   C→S  FF6B [slot]           el clic en la flechita de ESE asiento     (sender 0x5D1270)
#   C→S  FF6B [slot|0x80]      ⏳ segunda variante, sin mapear            (envoltorio 0x5DFFA0)
#   S→C  FF6C [slot]           abre el popup Sí/No "¿intercambiamos?"    (handler 0x5E47A0)
#   C→S  FF6C [slot][1|0]      la respuesta: ★ 1 = ACEPTO · 0 = RECHAZO  (sender 0x5D13D0)
#   S→C  FF6C [slot|0x80]      cartel de un botón: "te dijeron que no"
#   S→C  FF6B [sA][eA][sB][eB] EL INTERCAMBIO                            (handler 0x5EB450)
#
# ⚠⚠ DOS DIFERENCIAS CON EL CBT que muerden si se calca su código:
#   1. **Los equipos NO van cruzados.** El CBT pinta `0x52FB70(slotA, teamB)`; el 2013 hace
#      `0x592F40(slotA, teamA)` y `0x592F40(slotB, teamB)` — cada equipo se pinta en SU asiento.
#      Medido en `0x5A09F7`. Traducido: `eA` es el equipo que le toca a la POSICIÓN `sA`.
#   2. **Un asiento vacío NO necesita otro comando.** El applier del 2013 se ramifica solo
#      (`0x5A0A8A` -> `0x5A0590`) y hace la mudanza. El CBT tenía que mandar su `FF37`.
#
# ★ Cuándo dibuja el cliente la flechita — gate `0x594390(cRoom, slot)`, medido:
#     · `[cRoom+0x9568] != 2` (CooperationMode != RELEVO)  -> NO hay flechas en ningún asiento
#     · sobre MI propio asiento                            -> no
#     · sobre el asiento del ANFITRIÓN (`[0x931660]+0x41`) -> no
#     · sobre un asiento VACÍO                             -> SÍ
#   ⇒ **Al anfitrión no se le pide: el anfitrión ordena.** Con sólo dos jugadores el invitado
#     únicamente tiene huecos y al anfitrión (deshabilitado) ⇒ para probar el pedido entre dos
#     NO-anfitriones hace falta un TERCERO. (Le pasó igual al CBT el 14-ago.)
# ═════════════════════════════════════════════════════════════════════════════════════════════

def _aplicar_intercambio(rid, slot_a, slot_b, motivo=""):
    """Mueve la mesa y le manda a TODA la sala el `FF6B` de 4 bytes que lo aplica en pantalla."""
    _usn_a, _usn_b = intercambiar_asientos(rid, slot_a, slot_b)
    _eq_a, _eq_b = equipo_de(rid, slot_a), equipo_de(rid, slot_b)
    # [slotA][teamA][slotB][teamB], SIN cruzar: cada equipo es el de su propia posición (ver arriba).
    body = bytes([slot_a & 0xFF, _eq_a & 0xFF, slot_b & 0xFF, _eq_b & 0xFF])
    # ★★★ AL OTRO PARTICIPANTE, LOS PARES AL REVÉS.
    #   El handler sólo refresca "mi asiento" cuando el PRIMER par del paquete es el suyo:
    #     0x5EB4B4  cmp al, [[0x931660]+0x40]   ; al = el primer slot
    #     0x5EB4BF  call 0x417690               ;   -> recién ahí refresca
    #   Con un único cuerpo para todos, el que no va primero se queda creyendo que sigue en su
    #   asiento viejo. Invertir es seguro porque el intercambio es SIMÉTRICO: como los equipos van
    #   por POSICIÓN y no cruzados, dar vuelta los pares produce las MISMAS escrituras; lo único
    #   que cambia es a quién le toca el refresco.
    #   ⚠ Es una precaución HEREDADA del CBT (allá está medido: dos jugadores reportando el mismo
    #     slot tras un swap). Acá el síntoma todavía no se vio — no cuesta nada, pero no lo anotes
    #     como medido en este cliente.
    reverso = bytes([slot_b & 0xFF, _eq_b & 0xFF, slot_a & 0xFF, _eq_a & 0xFF])
    _n = 0
    # ★ Y a los que MIRAN el intercambio, con el cuerpo NORMAL: el `reverso` es la precaución para
    #   el que se movió, y el que mira no se movió (2026-09-08, ver `difundir_userlist`).
    for _c in conexiones_en_sala(rid):
        _usn = getattr(_c, "usn", None)
        if _c is None or getattr(_c, "cerrado", False):
            continue
        _cuerpo = reverso if (_usn_b is not None and _usn == _usn_b) else body
        try:
            _c.send_ff55(0x6B, _cuerpo, name=f"FF6B intercambio {slot_a}<->{slot_b}")
            # ★★★★★ Y REPINTAR TODOS LOS ASIENTOS, PARA CADA UNO. El `FF6B` sólo pinta los DOS
            #   asientos que se movieron; con varios intercambios seguidos algún asiento queda con
            #   el color de una posición vieja. Medido en pantalla el 2026-09-05: sala llena en
            #   relevo, el asiento 5 se veía AZUL cuando la regla es 0-2 azul / 3-5 rojo.
            #   ⚠ VA ADENTRO DEL BUCLE, y esto es lo que el CBT dejó escrito con todas las letras:
            #     `enviar_equipos` manda por `st.send_ff55`, o sea **sólo al que la llama**.
            #     Invocándola una vez, el que aplicó el intercambio veía bien y los demás se
            #     quedaban con el color viejo.
            #   ★ En relevo el color es del ASIENTO, no del jugador: los tres de la izquierda son
            #     siempre azules y los tres de la derecha siempre rojos, pase quien pase por ahí.
            enviar_equipos(_c, rid)
            _n += 1
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandar el FF6B a usn={_usn}: {e!r}")
    log("LOBBY", f"  ★★ FF6B {motivo}: asientos {slot_a} <-> {slot_b} en la sala {rid} "
                 f"(usn {_usn_a} -> {slot_b}, usn {_usn_b} -> {slot_a}) -> {_n} destinatario(s), "
                 f"cuerpo={body.hex()}"
                 + (f" / al otro {reverso.hex()}" if _usn_b is not None else ""))
    actualizar_ocupantes_sala(rid)
    # ★★★ SI EL QUE SE MOVIÓ ERA CAPITÁN, SU EQUIPO VIEJO NO PUEDE QUEDARSE SIN UNO (2026-09-07).
    #   ⛔ Reportado: *"al pasar el jefe del equipo azul al rojo, el equipo azul se quedó sin
    #     jefe"*. Y el usuario agregó bien que *"puede pasar a la inversa"*: es simétrico.
    #   ★ Va acá porque **todos** los cambios de asiento pasan por esta función (el `FF18` de
    #     cambiar de equipo y el `FF6B/FF6C` de permutar), así que se arregla una vez para los tres
    #     caminos en vez de repetirlo en cada handler.
    #   ⚠ `reparar_capitanes` sólo toca lo que está roto: si el capitán sigue sentado y sigue
    #     siendo de su equipo, no se lo cambia — el distintivo no salta.
    _caps_i, _cambio_i = reparar_capitanes(rid)
    if _cambio_i:
        difundir_capitanes(rid, _caps_i, motivo=f" (reparado tras {motivo})")


def h_45_ff6b(st, cmd, data):
    # rama nueva:  cmd == 107   (el comando existía en el cliente; el server lo tiraba)
    # C→S FF6B [slot] = "quiero el asiento de ESE". Un solo byte (sender `0x5D1270`: un
    # `write(ptr,1)` y después `cmd = 0x6B`).
    rid = getattr(st, "room_id", None)
    if not rid or not data:
        return
    destino = data[0] & 0x7F
    mio = getattr(st, "room_slot", None)
    if mio is None:
        mio = HOST_SLOT
    mio &= 0x7F
    if data[0] & 0x80:
        # ⏳ La segunda variante del sender (`0x5DFFA0`: `or al,0x80`) es un envoltorio suelto y
        #   todavía no se sabe qué botón la dispara. Se REGISTRA y se ignora, en vez de adivinar.
        log("LOBBY", f"  ⏳ FF6B variante 0x80 (data={data[0]:#04x}) de slot={mio} — SIN MAPEAR, ignorada")
        return
    # ★★ Y NO A UN ASIENTO CERRADO (2026-09-07). Es el mismo agujero que el del `FF18`, por la
    #   otra puerta: acá el jugador PIDE un asiento concreto, y si está cerrado lo mudábamos igual.
    #   Se revisa antes del rango para que el log diga el motivo de verdad y no "fuera de rango".
    from .salas import asientos_de_la_sala
    _tope6b = asientos_de_la_sala(rid) - 1                 # ★ 14-oct: la sala de 12 llega al 11 (la flechita del relevo)
    if 0 <= destino <= _tope6b and destino in slots_cerrados(rid) and mesa_de(rid).get(destino) is None:
        log("LOBBY", f"  · FF6B RECHAZADO: el asiento {destino} está CERRADO por el anfitrión "
                     f"(cerrados={sorted(slots_cerrados(rid))})")
        return
    if destino > _tope6b or destino == mio:
        # El propio cliente aborta con "CNetwork::CmdSwap- Error" si los dos slots son iguales
        # (`0x5EB495`). Cortamos antes: el paquete no serviría para nada.
        log("LOBBY", f"  · FF6B IGNORADO: slot {mio} -> {destino} (fuera de rango o el mismo)")
        return
    _otro_usn = mesa_de(rid).get(destino)
    if _otro_usn is None:
        # ASIENTO VACÍO: no hay a quién preguntarle, y el applier del cliente hace la mudanza solo.
        _aplicar_intercambio(rid, mio, destino, motivo=f"mudanza de usn={st.usn} a un hueco")
        return
    # ★★★ CON OCUPANTE HAY QUE PEDIRLE PERMISO — no se aplica de una. El `FF6C [mi_slot]` le abre
    #   al otro el popup de Sí/No (`0x5E47A0` -> `0x4214C0` con tipo `0x13` y los dos callbacks
    #   `0x5DFF60`/`0x5DFF80`), y su respuesta vuelve como `FF6C [slot][1|0]`.
    SWAP_PENDIENTE[rid] = {"de": st.usn, "para": _otro_usn, "slot_de": mio, "slot_para": destino}
    _oc = CONEXIONES.get(_otro_usn)
    if _oc is not None and not getattr(_oc, "cerrado", False):
        _oc.send_ff55(0x6C, bytes([mio & 0xFF]),
                      name=f"FF6C ¿me cambio con vos? (lo pide el slot {mio})")
    log("LOBBY", f"  ★ FF6B PEDIDO: usn={st.usn} (slot {mio}) le pregunta a usn={_otro_usn} "
                 f"(slot {destino}) -> FF6C [{mio}]")


def h_46_ff6c(st, cmd, data):
    # rama nueva:  cmd == 108
    # C→S FF6C [slot_del_solicitante][respuesta] — ★ 1 = ACEPTO · 0 = RECHAZO.
    # Los dos botones del popup llaman a la MISMA función (`0x5D13D0`) con distinto segundo byte:
    #   `0x5DFF60` -> manda 1     ·     `0x5DFF80` -> manda 0
    # ⚠ En el `push` van al revés de como se leen (`push 0x5DFF80` primero), y el CBT ya se comió
    #   una vez ese error: leyó el primero como el "Sí" y le quedaron los botones invertidos —
    #   aceptar rechazaba y cancelar aplicaba.
    if len(data) < 2:
        return
    rid = getattr(st, "room_id", None)
    pend = SWAP_PENDIENTE.get(rid) if rid else None
    if not pend or pend["para"] != getattr(st, "usn", None):
        log("LOBBY", f"  · FF6C de usn={getattr(st, 'usn', None)} sin pedido pendiente para él -> ignorado")
        return
    SWAP_PENDIENTE.pop(rid, None)
    _quien = CONEXIONES.get(pend["de"])
    if data[1] == 0:
        # RECHAZO. Al que pidió se le manda `FF6C [slot|0x80]`: esa rama del handler hace
        # `xor cl,0x80` para recuperar el asiento (`0x5E47F5`), busca el NOMBRE de quien está ahí
        # (`0x44F070`) y saca el cartel de la string 262 con un solo botón.
        if _quien is not None and not getattr(_quien, "cerrado", False):
            _quien.send_ff55(0x6C, bytes([(pend["slot_para"] | 0x80) & 0xFF]),
                             name="FF6C RECHAZO (cartel de un botón)")
        log("LOBBY", f"  ★ FF6C RECHAZO de usn={st.usn} -> aviso a usn={pend['de']}")
        return
    _mesa = mesa_de(rid)
    if _mesa.get(pend["slot_de"]) != pend["de"] or _mesa.get(pend["slot_para"]) != pend["para"]:
        # Alguno se movió o se fue mientras el popup estaba abierto.
        log("LOBBY", f"  · FF6C ACEPTADO pero la mesa ya cambió ({pend}) -> se descarta")
        return
    _aplicar_intercambio(rid, pend["slot_de"], pend["slot_para"],
                         motivo=f"aceptado por usn={st.usn}")


def h_47_ff18(st, cmd, data):
    # rama nueva:  cmd == 24
    # ★★★ FF18 = CAMBIAR DE EQUIPO. El cliente lo manda y lo estábamos tirando.
    #
    # C→S `FF18 [equipo]`, **1 byte**, `equipo` ∈ {1, 2}. Sender `0x5C70F0` (un solo
    # `write(ptr,1)` y `cmd = 0x18`), y su ÚNICO llamador es `0x58D180`, que es la prueba de
    # impacto de los DOS botones del cartelito de equipo — dos rectángulos de 0x57 × 0x51
    # relativos al centro de pantalla:
    #     0x58D1E6  push 1 ; call 0x5C70F0      ; el de la izquierda
    #     0x58D22D  push 2 ; call 0x5C70F0      ; el de la derecha
    # ⇒ **1 = rojo (asientos 0-2) · 2 = azul (3-5)**, que es nuestro `equipo_por_defecto`.
    #
    # ⚠ NO hay que contestar con un `FF18`: **el handler S→C del `FF18` es un `ret 0xc` pelado**
    #   (`0x5C4180`, un stub que comparten 10 comandos). El que mueve de verdad es el `FF6B`, que
    #   ya sabe hacer las dos cosas — mudarse a un hueco y permutar con un ocupante.
    #
    # ★ No hace falta gatear por modo: el cliente sólo corre la prueba de impacto cuando el
    #   cartelito está abierto (`0x5AA610: cmp byte [cRoom+0x9361], 0 / je`), y `0x58D180` lo cierra
    #   al disparar. O sea que este comando no llega "de rebote" desde otra pantalla.
    rid = getattr(st, "room_id", None)
    if not rid:
        return
    equipo = (data[0] & 0xFF) if data else 1
    # ★★★ EL ORDEN IMPORTA: se busca el asiento MÁS CERCANO AL CENTRO, no el de número más bajo.
    #   Los dos equipos se miran de frente y se tocan en el medio (2 | 3), así que el rojo se llena
    #   desde el 2 hacia la izquierda y el azul desde el 3 hacia la derecha.
    #   ⚠ Antes era `(0,1,2)` y `(3,4,5)`: con el asiento 2 ocupado, el que cambiaba de equipo
    #     aterrizaba en el 0, en la otra punta. Reportado en pantalla (2026-09-05).
    from .salas import lado_del_equipo
    lado = lado_del_equipo(rid, equipo)             # ★ la sala de 12 tiene sus filas (10-oct)
    mio = getattr(st, "room_slot", None)
    if mio is None:
        mio = HOST_SLOT
    mio &= 0x7F
    if mio in lado:
        log("LOBBY", f"  · FF18 equipo={equipo}: usn={st.usn} ya está de ese lado "
                     f"(asiento {mio}) -> nada que mover")
        return
    _mesa18 = mesa_de(rid)
    _npc18 = npcs_de(rid)
    # ★★★ LOS ASIENTOS CERRADOS NO SON "LIBRES" (2026-09-07).
    #   ⛔ EL BUG, cazado por el usuario en pantalla: cerró dos asientos, quiso pasarse al equipo
    #     azul, y **el server lo mudó a un asiento CERRADO**. De ahí salía todo lo demás: quedaba
    #     un jugador en un asiento que la máscara informa cerrado, los equipos se descuadraban y
    #     la sala terminaba con TRES jefes marcados (dos del mismo equipo).
    #   ⇒ Acá se miraba `_mesa18` y `_npc18` pero NO `slots_cerrados`. El `FF87` es nuevo de hoy,
    #     así que este camino nunca lo había tenido en cuenta. Es exactamente lo que dijo el
    #     usuario: *"la regla sería: si no hay slot abierto, no puede cambiar"*.
    _cerr18 = slots_cerrados(rid)
    _libre = next((s for s in lado
                   if s not in _mesa18 and s not in _npc18 and s not in _cerr18), None)
    if _libre is not None:
        _aplicar_intercambio(rid, mio, _libre,
                             motivo=f"FF18 equipo={equipo} de usn={st.usn} (había hueco)")
        return
    # ★★★ EL LADO ESTÁ LLENO -> SE INTERCAMBIA, no es un error.
    #   Es la corrección que el CBT hizo sobre su propio código: antes contestaba *"Ese equipo está
    #   lleno."* y el botón quedaba inservible **con la sala en 6/6, que es justo cuando más se
    #   usa** — para acomodar los turnos del relevo. Sin hueco al que mudarse, la única forma de
    #   cambiar de lado es permutar con alguien de ese lado.
    #   ⚠ Este intercambio va SIN preguntarle al otro, a diferencia del de la flechita.
    #   ★★★ Y ACÁ DECÍA "no está confirmada contra el juego original". **YA ESTÁ CONFIRMADA**
    #     (2026-09-07), y el binario lo dice solo:
    #       · en el cliente moderno, que está simbolizado, `FF18` es **`CmdEditTeam`** y `FF37`
    #         **`CmdEditTeamResponse`** — o sea el `FF37` ES la respuesta de este comando.
    #       · y el handler del `FF37` en NUESTRO cliente (`0x5CE8B0`) trae el intercambio ADENTRO:
    #             005ce8fe  cmp cl, al        ; ¿los dos slots que mando el server son distintos?
    #             005ce900  je  0x5ce913      ;   iguales -> sólo aplicar equipo+capitán
    #             005ce90a  call 0x5A0590     ;   ★ DISTINTOS -> INTERCAMBIAR LOS ASIENTOS
    #     ⇒ El protocolo PREVÉ que la respuesta a "cambiame de equipo" mueva a dos jugadores. La
    #       permuta no es una invención del CBT: es lo que el comando fue diseñado para hacer.
    #   ⏳ Lo que sigue sin confirmarse es si el server original permutaba SIEMPRE o sólo a veces.
    #     No hay un solo `FF18` en las capturas del referente (nadie usó el botón mientras se
    #     grababa), así que eso no se puede medir con lo que hay.
    #   ⚠ Y para PERMUTAR también: sólo con alguien sentado en un asiento ABIERTO. Permutar con
    #     uno que está en un asiento cerrado movería al que cambia hacia el asiento cerrado, que
    #     es el mismo bug por la otra puerta.
    _otro = next((s for s in lado if s in _mesa18 and s not in _cerr18), None)
    # ★ 14-oct · EL RELEVO DE 12 (anonimo03): «que las banderitas sirvan si hay slot libre; si no hay, tendrán que hacerlo
    #   con la flechita» — la del `FF6B`, que LE PREGUNTA al otro (`FF6C`). Acá no se permuta.
    from .salas import es_cuatro12
    if _otro is not None and es_cuatro12(rid):                # ★ 15-oct: también el equipo de 4
        log("LOBBY", f"  · FF18 equipo={equipo} (4 equipos de 12): el lado {lado} está lleno -> no se permuta; "
                     f"el cambio va por la flechita (FF6B, con pregunta)")
        try:
            from .salas import avisar_a_uno
            avisar_a_uno(st, "Ese equipo está completo: para cambiar con alguien, usá la flechita de su tarjeta.")
        except Exception:                                   # noqa: BLE001
            pass
        return
    if _otro is None:
        #   ⚠ Sin hueco y sin nadie con quien permutar: NO SE MUEVE. Es la regla que pidió el
        #     usuario. Antes esto sólo pasaba con un lado lleno de NPC; ahora también cuando el
        #     anfitrión cerró todos los asientos de ese lado, que es el caso que lo destapó.
        log("LOBBY", f"  · FF18 equipo={equipo} RECHAZADO: en el lado {lado} no hay ningún asiento "
                     f"ABIERTO donde ponerlo (cerrados={sorted(_cerr18) or 'ninguno'}, "
                     f"npc={sorted(_npc18) or 'ninguno'}) -> no muevo nada")
        return
    _aplicar_intercambio(rid, mio, _otro,
                         motivo=f"FF18 equipo={equipo} de usn={st.usn} (lado LLENO -> permuta)")



# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ FF41 — `CmdGetRoomInfo`: LA INFO DE UNA SALA, Y EL MOTOR DEL «JUGAR JUNTOS» (2026-09-11)
#
#   anonimo03: *"hay una función llamada «jugar juntos» … me mueve al canal del amigo, pero la
#   función está incompleta, debería mandarme a la sala donde está mi amigo, como un auto-join"*.
#
#   ★★ LA FUNCIÓN **NO** ESTÁ INCOMPLETA EN EL CLIENTE. Está entera, y el que no contestaba era
#      este server: el `FF41` no tenía handler y el cliente se quedaba esperando en el lobby.
#
#   EL CICLO COMPLETO, medido en el exe prístino:
#       1. `0x44D5CA`  el cliente compara el canal del amigo con el mío:
#              distinto -> `or [esi+0x18a4],0x1000` = ★ dibuja el botón «Jugar Juntos»
#              igual    -> NO dibuja botón y manda el `FF41` DERECHO (`0x44D5DA`)
#          ⇒ el botón significa *"primero hay que mudarse de canal"*. Que no aparezca estando en
#            el mismo canal **no es un bug**: ahí el cliente entra solo.
#       2. al aceptar, guarda la sala destino en `[roommgr+0x132c]` y cambia de canal
#       3. ya en el canal nuevo: `[roommgr+0x12ea] = 1` y manda el `FF41` (`0x4A7EB6`/`0x4A7EC4`)
#       4. al llegar la respuesta, `0x5CEC7A` lee esa marca y decide:
#              con marca -> ★ ENTRA A LA SALA (`0x4A8150`)
#              sin marca -> sólo refresca esa fila de la lista de salas (`0x4A8420`)
#
#   ⇒ **El mismo paquete sirve para las dos cosas y quien decide es el cliente.** Contestamos
#     igual en los dos casos; no hay que adivinar para qué lo pidieron, ni distinguirlos.
#
#   ── EL PEDIDO (C2S) ──────────────────────────────────────────────────────────────────────────
#       [u16 A]   el `A` empaquetado de la sala  (emisor `0x5C93B0`: escribe 2 bytes)
#     ⚠ El largo real se LOGUEA entero abajo: el emisor arma el cuerpo con un buffer de pila y no
#       pude atar el offset con certeza. Si algún día llega con más bytes, el log lo va a mostrar
#       y este handler no se rompe (lee los 2 primeros y listo).
#
#   ── LA RESPUESTA (S2C), leída campo por campo en `0x5CEB60` con `campos13.py` ────────────────
#       [u8  result ]  ★ TIENE QUE SER 1  (`0x5CEC8E: cmp al,1 / jne`) o no entra
#       [u16 A      ]  la sala, (TIPO << 11) | número
#       [u8  ?      ]  [NM]
#       [u8  ?      ]  [NM]
#       [u8  ?      ]  [NM]
#       [u8  banda  ]  ★ `0x5CECA1: cmp byte[..],al / jbe` contra `0x4863C0` (MI banda de licencia)
#                      si es MAYOR que la mía -> texto #84 *"Su nivel no es adecuado para esta sala"*
#       [u8  ?      ]  [NM] ⚠ distinto de 0 dispara `0x58E760` — por eso va en CERO
#       [u8 len][nombre de la sala]
#       [u8  ?      ]  [NM] ⚠ distinto de 0 prende un bit de una máscara — por eso va en CERO
#
#   ⚠⚠ **5 de los 10 campos están [NM]**: sé el tamaño y el orden, no el significado. Van en cero,
#      que es el único valor del que está MEDIDO que no dispara ninguna rama. No los "completes"
#      con datos plausibles sin medir antes: dos de ellos tienen efectos colaterales conocidos.
#
#   ── EL 2019 (oráculo de nombres, NO la ley) ──────────────────────────────────────────────────
#     `FF041 = CNetwork::CmdGetRoomInfo` (`Network\Network.cpp`), y lee **la misma secuencia**
#     (1, 2, 1, 1, 1, …, len+str, 1) ⇒ confirma la lectura del 2013 por un camino independiente.
#     ⛔ PERO el 6º campo allá es un **u32** y acá es un **u8**. Calcar el layout del 2019
#        desincroniza 3 bytes y el nombre de la sala sale basura.
#     ⛔⛔ Y el 2019 tiene `CmdEnterFriend` (FF032) y `CmdUpdateFriendPlace` (FF034), que serían
#        el camino elegante… pero **en el 2013 esos dos handlers están VACÍOS** (`0x5C4180` es un
#        `ret 0xC`; el `FF34` drena). Implementarlos escribe un handler perfecto que no hace
#        NADA, y el síntoma es idéntico al de "mi paquete está mal armado". Acá el único camino
#        que existe es este `FF41`.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _avisar_ubicacion(st, motivo):
    """Le avisa a mis amigos que cambié de lugar. Envoltorio con el import adentro.

    ⚠ El import va ACÁ y no arriba: `lobby_social` cuelga de `salas`, y traerlo al tope de
      `lobby_salas` ata los tres módulos en un orden de carga que hoy no existe. Mismo patrón
      que `salas._codigo_de_licencia`, por la misma razón.
    ⚠ Y va envuelto en try: **un problema avisando no puede tumbar la entrada a la sala**. El
      aviso es un extra; entrar es lo que el jugador pidió.
    """
    try:
        from .lobby_social import avisar_mi_ubicacion
        avisar_mi_ubicacion(st, motivo)
    except Exception as e:                                   # noqa: BLE001
        log("LOBBY", f"  ⚠ no se pudo avisar la ubicación a los amigos ({motivo}): {e!r}")


def h_ff41_info_de_sala(st, cmd, data):
    if not FF41_INFO_DE_SALA:
        log("LOBBY", f"  · FF41 recibido ({len(data)} B) pero FF41_INFO_DE_SALA=False -> no contesto")
        return
    if len(data) < 2:
        log("LOBBY", f"  ⚠ FF41 con {len(data)} byte(s), esperaba 2 -> no contesto : {data.hex(' ')}")
        return
    if len(data) > 2:
        # ⚠ No es un error: es el aviso de que el pedido trae más de lo que creíamos. Se anota
        #   para poder re-medir, y se sigue igual — los 2 primeros bytes alcanzan.
        log("LOBBY", f"  ⚠ FF41 trae {len(data)} bytes (esperaba 2). Cola: {data[2:].hex(' ')}")
    # ★★★ ¿El lobby de este cliente ya terminó de armarse? El propio cliente lo avisa con el
    #   `FF1D`; hasta que no llegue, contestar acá lo hace entrar a la sala a medio armar y se ve
    #   el fondo mal cargado. Ver la nota larga de `FF41_ESPERA_LOBBY` en `ajustes.py`.
    if FF41_ESPERA_LOBBY and not getattr(st, "lobby_asentado", False):
        # ★★★ LA RED DE SEGURIDAD: si el cliente INSISTE, se le contesta igual.
        #   ⛔ La primera versión esperaba un paquete puntual (`FF1D`) y nada más. A la primera
        #     prueba real ese paquete dejó de llegar —la cola de la secuencia del cliente varía—
        #     y el pedido quedó guardado para siempre: «Jugar Juntos» dejó de andar del todo.
        #   ⇒ Un segundo `FF41` es el propio cliente diciendo "no me contestaste". Esperar dos
        #     veces al mismo dato ya no es prudencia, es quedarse mudo. Con esto, el peor caso
        #     vuelve a ser "entra con el lobby a medio armar" (el bug cosmético de antes) en vez
        #     de "no entra nunca".
        if getattr(st, "ff41_pendiente", None):
            log("LOBBY", "  ▶ FF41 REPETIDO: el cliente insiste y el marcador de lobby armado no "
                         "llegó -> contesto igual (red de seguridad)")
            st.ff41_pendiente = None
            _responder_ff41(st, data[:2])
            return
        st.ff41_pendiente = bytes(data[:2])
        log("LOBBY", "  ⏸ FF41 GUARDADO: el lobby todavía no está armado. Se contesta al llegar "
                     "el FF1D o el FF137 — o si el cliente lo repite")
        return
    _responder_ff41(st, data[:2])


def despachar_ff41_pendiente(st, motivo=""):
    """Contesta el `FF41` que quedó esperando a que el lobby terminara de armarse.

    La llama el handler del `FF1D` (`lobby_menu.h_41_ff45`), que es **la última parada del
    arranque del lobby** — medido: llega 3 de 3 veces en una entrada normal al canal.

    ⚠ Corre en el hilo de la conexión, igual que todo lo demás: no hay temporizador ni hilo
      aparte, a propósito. Un `FF55` mandado desde otro hilo se sale del orden del contador del
      cifrado, que es justo lo que costó el arreglo grande del 2026-09-10.
    """
    _pend = getattr(st, "ff41_pendiente", None)
    if not _pend:
        return
    st.ff41_pendiente = None
    log("LOBBY", f"  ▶ FF41 pendiente despachado ({motivo}): el lobby ya está armado")
    _responder_ff41(st, _pend)


def _responder_ff41(st, data):
    _a41 = struct.unpack("<H", data[:2])[0]
    _tipo41 = (_a41 >> 11) & 0x1F
    _num41  = _a41 & 0x7FF
    _nombre41, _existe41 = "", False
    if _tipo41:
        # Lugar persistente (charla, isla, casa…). `lugar_de` los crea al vuelo, así que
        # preguntar por uno que no existe lo inventaría: se chequea contra la lista horneada.
        _existe41 = _tipo41 in TIPOS_LUGAR_CHARLA
        # El mismo rótulo que usa el `FF11` al entrar (línea ~366): un solo criterio para los dos.
        _nombre41 = {11: "MI CASA", 12: "charla EN CÍRCULO"}.get(_tipo41, "Sala de Conversación")
    else:
        # Sala de juego: tiene que estar VIVA. Los maniquíes y las salas de paginación no
        # cuentan — no se puede entrar a ellas (igual que en el `FF11`).
        _s41 = SALAS_VIVAS.get(_num41)
        if _s41 is not None:
            _existe41 = True
            _nombre41 = str(_s41.get("nombre", "") or "")

    if not _existe41:
        # ★ El amigo se fue mientras el otro se mudaba de canal: es el caso NORMAL, no un error.
        #   Con result != 1 el cliente no entra y se queda en el lobby, que es lo correcto.
        log("LOBBY", f"  ★ FF41 sala A=0x{_a41:04X} (tipo={_tipo41} nº={_num41}) NO EXISTE "
                     f"-> result=0 (el amigo ya no está ahí)")
        st.send_ff55(0x41, struct.pack("<BH", 0, _a41) + bytes(5) + bytes([0, 0]),
                     name=f"FF41 sala A=0x{_a41:04X} inexistente -> result=0")
        return

    _nb41 = _nombre41.encode("cp1252", "replace")[:0x3E]
    _p41 = struct.pack("<BH", 1, _a41)      # result=1 + la sala
    _p41 += bytes([0, 0, 0])                # [NM] x3
    _p41 += bytes([0])                      # banda mínima: 0 = no la pide (`jbe` siempre pasa)
    _p41 += bytes([0])                      # [NM] ⚠ != 0 dispara 0x58E760
    _p41 += bytes([len(_nb41)]) + _nb41
    _p41 += bytes([0])                      # [NM] ⚠ != 0 prende un bit de máscara
    st.send_ff55(0x41, _p41,
                 name=f"FF41 info de sala A=0x{_a41:04X} (tipo={_tipo41} nº={_num41}) "
                      f"'{_nombre41}' -> result=1")
    log("LOBBY", f"  ★★★ FF41 JUGAR JUNTOS: sala A=0x{_a41:04X} tipo={_tipo41} nº={_num41} "
                 f"'{_nombre41}' -> result=1, {len(_p41)} B "
                 f"(el cliente decide solo si entra o sólo refresca la fila)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ REFRESCAR EL ENLACE DE PAREJA DE TODA LA SALA (2026-09-12)
#
#   ⛔ EL SÍNTOMA, reportado por anonimo03 con una precisión que da el diagnóstico entero:
#     *"el ítem sobre sus cabezas aparece al re-entrar a sala, pero sólo ve el de ambos el que
#     entra; el otro sólo ve 1, la pareja que entró"*.
#
#   ★★ ESO ES EXACTAMENTE EL `FF0C` QUE NO RE-DIBUJA:
#       · el que ENTRA recibe el `FF0C` de todos los ocupantes ⇒ los ve a los dos ✅
#       · el que YA ESTABA recibe sólo el `FF0C` del recién llegado (a ése sí lo crea) y
#         **su propio enlace nunca se vuelve a aplicar** ⇒ ve uno solo ⛔
#     `cRoom::OnRoomUser` (`0x59FDF0`) es create-if-absent: si el ocupante ya existe, el
#     aplicador del enlace ni corre. Ver `PAREJA_PENDIENTES_AGENTE.md` §1.
#
#   ⇒ LA SALIDA es el `FF15`, que **sí entra siempre** y lleva el asiento de la pareja al mismo
#     campo del nodo. Se manda el de CADA emparejado a TODA la mesa, así el que ya estaba
#     recibe también el suyo.
#
#   ⚠ Sólo se manda por los que tienen pareja EN ESTA SALA: para los demás sería un reload de
#     modelo gratis, y el `FF15` no es barato (lleva el `worn` entero).
# ══════════════════════════════════════════════════════════════════════════════════════════════
def refrescar_enlaces_de_pareja(rid, motivo="", forzar=(), anunciar=False,
                                solo_cartel=False, quien=None, forzar_ff15=False):
    """Re-manda el `FF15` de cada emparejado de la sala a todos los de la sala.

    ⛔⛔ `forzar` EXISTE POR UN ERROR DE DISEÑO MÍO (2026-09-12). Esta función sólo mandaba el
      `FF15` de **los que TIENEN pareja**, así que al ROMPER los salteaba —ya no tienen— y el
      enlace viejo **quedaba dibujado para siempre**. Reportado por anonimo03: *"al romper no ocurrió
      el refresco de volver a no estar casados"*.
      ★ Para BORRAR un enlace hay que mandar el `FF15` igual, con `0xFF` (soltero). El que se
        quedó sin pareja necesita el paquete **más** que el que la tiene.
      ⇒ `forzar=(uid, uid…)` son los que se refrescan **aunque estén solteros**.
    """
    # ⚠⚠ LA GUARDA VA ADENTRO DEL `try`, NO AFUERA. La primera versión la tenía arriba, y cuando
    #   `FF0C_ENLACE_PAREJA` resultó no estar importado, el `NameError` saltó **antes** de entrar a
    #   la red de seguridad ⇒ la excepción escapó y **tumbó la conexión del jugador**.
    #   ★ Una red que no cubre la primera línea no es una red. Si algo puede fallar, que falle
    #     ADENTRO.
    try:
        if rid is None or not FF0C_ENLACE_PAREJA:
            return 0
        from .paquetes import build_ff15_2013
        from .catalogo import face_id, wing_id
        from .basedatos import db_pareja_de, db_anillo_de_pareja
        _mesa = mesa_de(rid)
        _por_usn = {int(u): int(s) for s, u in _mesa.items()}
        _dest = [CONEXIONES.get(int(u)) for u in _mesa.values()]
        _dest = [c for c in _dest if c is not None and not getattr(c, "cerrado", False)]
        _n = 0
        _forzar = {int(u) for u in (forzar or ())}
        for _u, _sl in _por_usn.items():
            _pj = db_pareja_de(_u)
            _enlazado = bool(_pj) and _pj in _por_usn
            if not _enlazado and _u not in _forzar:
                continue      # soltero de siempre: mandarle un FF15 sería un reload gratis
            from .salas import _ocupante_de
            _occ = _ocupante_de(_u, _sl)
            _prt = _occ.get("parts") or []
            _worn = [_occ["char_id"]] + [p for p in _prt if p]
            # ★★ `forzar_ff15`: manda el FF15 aunque la perilla global esté apagada.
            #   ⚠ La perilla se apagó porque el FF15 **en cada entrada** parpadeaba (re-escribe la
            #     entrada del ocupante). Pero para un evento PUNTUAL —cambiar el anillo— es
            #     justamente la herramienta nativa: lo que cambió ES el ocupante.
            #   ★ Y el repintado del equipo ya va detrás (ver más abajo), que es la lección que
            #     nos costó seis repeticiones.
            if solo_cartel or not (PAREJA_REFRESCO_FF15 or forzar_ff15):
                # ⚠ `PAREJA_REFRESCO_FF15=False` deja SÓLO el cartel y el enlace que ya viaja en
                #   el FF0C. Es el lado B del A/B que pidió anonimo03: si el recuadro igual se ve,
                #   este refresco sobra y el parpadeo del equipo se va con él.
                _n += 1
                continue
            # ★★ Ver `salas.ff15_de`: además de la pareja lleva el equipo, el capitán y las
            #   joyas del alma — armado a mano los borraba (2026-09-23).
            from .salas import ff15_de
            _p15 = ff15_de(_occ, rid, pareja_slot=_por_usn[_pj] if _enlazado else 0xFF)
            for _c in _dest:
                _c.send_ff55(0x15, _p15,
                             name=f"FF15 enlace de pareja slot {_sl} <-> " + (str(_por_usn[_pj]) if _enlazado else "SOLTERO") + motivo)
            _n += 1
        if _n:
            # ★★★★★ Y REPINTAR EL EQUIPO DETRÁS — SEXTO CASO DE ESTA FAMILIA (2026-09-12).
            #   ⛔ Reportado por anonimo03 con las MISMAS palabras que la vez anterior: *"se casaron,
            #     el slot actualizó, pero estaba en modo equipo y el slot de uno de los dos pasó a
            #     color de modo solo"*.
            #   ★ El equipo vive en DOS lados del cliente y el `FF15` llena uno solo:
            #       · el `rel12` del `FF0C` — el asiento
            #       · `sRoomUser+0x4A`, el PADRÓN, al que sólo se llega con el `FF37`
            #     El `FF15` **re-escribe la entrada del ocupante**, así que sin repintar detrás el
            #     asiento queda con la paleta de "solo".
            #   ⇒ Es exactamente lo que ya hacen el cambio de ropa y la entrada a la sala. Lo
            #     omití porque copié el envío del `FF15` sin la línea que viene detrás.
            #   ★ En modo solo no hace nada: `enviar_equipos` sale por `sala_por_equipos()`.
            for _c in _dest:
                enviar_equipos(_c, rid)
            # ★★★ Y EL CARTEL «<A> & <B> ha llegado.» — sólo al ENTRAR alguien.
            #   ⚠ Se manda UNA sola vez por pareja (no una por cada miembro), o el cartel saldría
            #     duplicado. `_anunciadas` lleva la cuenta dentro de esta corrida.
            if anunciar and PAREJA_ANUNCIO_SALA:
                from .lobby_pareja import _s2c_pareja_en_sala
                from .basedatos import db_anillo_de_pareja as _anillo
                # ⛔ ACÁ ANUNCIABA **TODAS** las parejas de la sala cada vez que entraba
                #   cualquiera. Reportado por anonimo03: *"sigue saliendo el cartel de pareja «llegó a
                #   la sala» aunque el que entró no sea la pareja del otro"*.
                #   ⇒ El cartel es de **quien acaba de llegar**: si el que entró no es de una
                #     pareja que esté completa acá, no hay nada que anunciar.
                _ya = set()
                for _u, _sl in _por_usn.items():
                    if quien is not None and int(_u) != int(quien):
                        continue                    # ★ sólo la pareja DEL QUE ENTRÓ
                    _pj = db_pareja_de(_u)
                    if not _pj or _pj not in _por_usn:
                        continue
                    _clave = tuple(sorted((int(_u), int(_pj))))
                    if _clave in _ya:
                        continue
                    _ya.add(_clave)
                    _n1 = str((db_get_char(_u) or {}).get("nick", "") or "")
                    _n2 = str((db_get_char(_pj) or {}).get("nick", "") or "")
                    _p48 = _s2c_pareja_en_sala(_anillo(_u), _n1, _n2)
                    for _c in _dest:
                        _c.send_ff55(0x48, _p48,
                                     name=f"FF48 ★ cartel «{_n1} & {_n2} ha llegado.»")
                    log("LOBBY", f"  ★★★ PAREJA: cartel de sala «{_n1} & {_n2} ha llegado.» "
                                 f"a {len(_dest)} de la sala {rid}")
            log("LOBBY", f"  ★★ PAREJA: refrescado el enlace de {_n} emparejado(s) "
                         f"a {len(_dest)} de la sala {rid}{motivo} (+ equipos repintados)")
        return _n
    except Exception as e:                                       # noqa: BLE001
        # ⚠ Es un adorno: no puede romper la entrada ni la salida de una sala.
        log("LOBBY", f"  ⚠ no pude refrescar los enlaces de pareja: {e!r}")
        return 0
