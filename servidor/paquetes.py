# -*- coding: utf-8 -*-
"""paquetes — armar los FFxx que salen

Cortado de `server_login2013.py`. El código es el MISMO, movido tal cual.
"""
import os
import struct

from .ajustes import (
    CHALLENGE_XOR,
    FF0C_BANDERA_AURA,
    FF0C_ENLACE_PAREJA,
    FF0C_JOYA_DEL_ALMA,
    FF0C_COLOR_APODO,
    FF0C_ENTRADA_A_SALA,
    FF0C_MARCA_CIRCULO,
    FF0C_MEDALLA,
    FF0C_JOYAS_ALMA,
    MARCO_DE_ASIENTO,
    TARJETA_DE_NOMBRE,
    FF0C_TEXTO_DE_CABEZA,
    CRAYON_CIRCULO,
    FF0C_DISTINTIVO,
    FF0C_DX,
    FF0C_X0,
    FF0C_Z,
    FF0C_FONDO_X0,
    FF0C_FONDO_Z,
    FF126_TIPO_ITEM,
    FF13_COLA_CAMPOS,
    FF13_MODE_OFFS,
    FF13_MODE_PROBE,
    FF13_PREFIJO_CAMPOS,
    FF13_SENTINEL,
    FF28_WINTEAM,
    FF49_RANURAS,
    LOBBY_B,
    PWD,
    TOKEN_CFG90,
)
from .gacha import sexo
from .cifrado import (
    frame,
)
from .basedatos import (
    _exp_to_wire,
    db_get_char,
    inv_ids,
)
from .catalogo import (
    anillo_de,
    face_id,
    familia_de,
    id_wire,
    wing_id,
    wing_id_con_aura,
    worn_seguro,
)

# El módulo se lee con rutas relativas a la RAÍZ del proyecto, no a
# `servidor/`. Viene de cuando todo era un archivo solo; sacarlo rompe la
# lectura de las tablas del cliente (wing.txt / face.txt).
__file__ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server_login2013.py")   # rutas relativas como en el original
                                  #   efectos de escena no están probados. Poner 8 para experimentar.
# ⛔ MEDIDO 2026-07-30: mandar el FF81 después del MyRecord **NO otorga nada**, porque el bucle que
#    otorga licencias (`0x489103`) corre UNA VEZ en el LOGIN, justo después de que se escribe
#    `[player+0x664]`. Mismo problema de timing que tuvo la licencia. ★ PISTA: `0x5EE310` —dentro del
#    handler del MyRecord (`FF03` = `0x5ED3C0`)— TAMBIÉN escribe `[player+0x335]`, así que el progreso
#    de misión probablemente viaje en el MyRecord; si además el bucle se re-dispara ahí, esa es la vía.


def _colores_apodo():
    """el tope del color del apodo (`catalogo.COLORES_APODO`: 13 con los «Crayón Mazino» y la dll `crayones.c`)"""
    from .catalogo import COLORES_APODO                                   # noqa: PLC0415
    return COLORES_APODO


def _marca_circulo(occ):
    """★ 23-oct · el CRAYÓN DE CÍRCULO: la marca '^' + 'A'+color al principio del nombre del círculo del jugador que
    tiene uno tildado (vigente); la dll (`circulo_color.c`) la saca y pinta el nombre de ese color. Vacía si no tiene
    o si la llave está apagada. ('^' no puede estar en un nombre de círculo; 0x7F lo limpiaba el cliente del str2.)"""
    if not CRAYON_CIRCULO:
        return b""
    usn = int(occ.get("usn", 0) or 0)
    if not usn:
        return b""
    from .catalogo import color_circulo_de                                # noqa: PLC0415
    c = color_circulo_de(usn)
    return bytes([0x5E, 0x41 + (c & 0x0F)]) if c else b""

def build_ff81_progreso(a):
    """S->C FF81 de AVANCE: fija [player+0x335] = a (selector 0, f3=1)."""
    return bytes([a & 0xFF, 0x00]) + struct.pack("<I", 1) + struct.pack("<I", 0) + struct.pack("<I", 0)

def _entrada_canal(idx, ip, port, cat, name, users=1, cap=100):
    r"""Una entrada de CmdLobbyServerList (parser cliente 0x5C4C00).

    ⛔⛔ EL `users=1` ERA UN DEFAULT QUE NADIE PISABA — 2026-09-09, reportado por anonimo03:
      *"el estado de llenado del canal no está funcionando"*. Los DOS sitios que llamaban a esta
      función lo omitían, así que **los 8 canales decían siempre «1 de 100», para siempre**.
      La barra de población no estaba rota: estaba recibiendo un 1 clavado.
      ★ Se ve en la captura del REFERENTE, que sí manda los de verdad:
          'Principiantes' 0/100 · 'Novato lunar' 10/100 · **'Libre' 52/500**
      ⇒ Ahora `lobby.build_ff02` cuenta las conexiones vivas de cada canal y las pasa acá.
    ⚠ `cap` DEBE ser >= 1 y `users` no debería pasarlo: la pantalla hace `usuarios*80/capacidad`
      (`0x4a69e5`, un `idiv`), así que un 0 en `cap` **crashea el cliente**.
    """
    ipb   = ip.encode("ascii")
    nameb = name.encode("cp1252", "replace")
    assert len(ipb)   <= 15, "lenIP <=15"
    assert len(nameb) <= 30, "lenName <=30"
    p  = struct.pack("<I", idx)         # E1 idx u32
    p += struct.pack("<H", port)        # E2 PORT u16 LE  -> elem+2
    p += bytes([len(ipb)]) + ipb        # E3 lenIP + E4 IP string -> elem+8
    p += struct.pack("<H", users)       # E5 = usuarios ACTUALES del canal (numerador de la barra de población)
    p += struct.pack("<H", cap)         # E6 = capacidad MAX del canal. ★ DEBE ser >=1: la pantalla de selección
                                        #   hace idiv (0x4a69e5: usuarios*80 / capacidad); con 0 => división por cero => CRASH.
    p += bytes([cat & 0xFF])            # E7 cat -> el switch 0x5C4C00 lo vuelve (tier1 -> +1, tier2 -> +0x34),
                                        #   y 0x4A5F60 conecta a la entrada cuyo par matchea el código del jugador.
    p += bytes([len(nameb)]) + nameb    # E8 lenName + E9 name
    return p

def resp3_checkver_ack():
    """RESP-3 ACK de CmdCheckVer en la conexion Lobby: FF 01 01 00 00."""
    return frame(0x01, b"\x00")

def resp4_lobby_login_ok(token_cfg90=TOKEN_CFG90, usn=0):
    """RESP-4 respuesta al Lobby-login (cmd 0x02, handler cliente 0x5E2560).
    Layout que lee el cliente:
      [u8 status=0][u32 A challenge][u32 B -> sess+0x21b58][256B bloque de cuenta/MyInfo]
    A = token_cfg90 ^ 0xCACB1112 (debe igualar f(cfg)=[cfg+0x90] del cliente).
    El bloque de 256B (buf 0x5c64f0 +0x100) es el MyInfo; por ahora ceros (unstick).
    """
    A = (token_cfg90 ^ CHALLENGE_XOR) & 0xFFFFFFFF
    p  = b"\x00"                        # status = 0  (DEBE ser 0 para exito)
    p += struct.pack("<I", A)           # A challenge -> A ^ 0xCACB1112 == f(cfg)
    # ★★★ LA CLAVE DEL FF55 ES **POR CUENTA** (2026-08-04). El cliente la arma en `0x5C6B86`:
    #       ecx = [cfg+0x7C]        ; el USN (= atoi(argv[1]))
    #       edx = [sess+0x21B58]    ; ESTE campo, el `B` que mandamos acá
    #       add edx, ecx            ; key_base = B + USN
    #   ★ Observación del usuario que cambió el enfoque: **el USN del juego original tenía varias
    #     cifras y entra en la clave** ⇒ el cifrado era per-cuenta por DISEÑO, no una constante.
    #     Hasta hoy funcionaba de casualidad porque el USN valía 0 (le pasábamos `"SN"` como argv[1]).
    #   ⚠⚠ Un intento anterior mandaba `B = −USN` para forzar `key_base = 0`. Andaba, pero ANULABA el
    #      mecanismo: con dos clientes las dos claves darían 0 y se mezclarían. Descartado.
    #   ⇒ mandamos **B = 0** y la clave queda **key_base = USN**, distinta por jugador. El server la
    #     lleva en `st.key_base` (la conexión YA tenía el campo, sin usar).
    p += struct.pack("<I", LOBBY_B & 0xFFFFFFFF)       # B (u32) -> sess+0x21b58; key_base = B + USN
    p += PWD                            # bloque de 256B = tabla `pwd` del cifrado FF55 (ceros)
    assert len(p) == 1 + 4 + 4 + 256
    return frame(0x02, p)


def inventario_para_ff49(usn):
    """El inventario en el MISMO formato que el campo #37 del MyRecord -> [(id, vencimiento, en_uso)].

    ⚠ El MyRecord arma su propia copia de esta lista más abajo. La lección del CBT es que las dos
      tienen que salir de la MISMA fuente: cuando divergieron, el inventario se vaciaba solo.
      Unificarlas del todo queda pendiente; por ahora las dos leen `parts` + `inventory` igual.
    """
    ch = db_get_char(usn) or {}
    exp_by_id = {int(e.get('id', 0)): int(e.get('exp', 0) or 0)
                 for e in ch.get('inventory', []) if isinstance(e, dict)}
    worn  = [int(x) for x in ch.get('parts', [])]
    owned = [i for i in inv_ids(ch) if i not in worn]
    # ★ 11-oct: el SET BÁSICO, igual que en el MyRecord #37 (las dos listas salen de la MISMA fuente)
    from .catalogo import asegurar_basico                                  # noqa: PLC0415
    owned += [b for b in asegurar_basico(usn, ch) if b and b not in worn and b not in owned] if ch else []
    return ([(it, _exp_to_wire(exp_by_id.get(it, 0)), 1) for it in worn] +
            [(it, _exp_to_wire(exp_by_id.get(it, 0)), 0) for it in owned])


def build_ff49(select_key, registros, inventario=(), canciones=(), tiempo_hoy=None):
    """FF49 (cmd 0x49) — LA LISTA DE PERSONAJES + **SelectByKey**. Handler cliente `0x5E0440`.

    ⛔ Acá decía `0x5E0BB0`, que es OTRA función. Corregido el 2026-09-08 extrayéndolo con
      `tabla_rx.py 0x49`. Es la misma piedra de siempre: **la tabla se EXTRAE, no se copia**.
      El formato de abajo no cambia — estaba bien.

    ★★★★★ POR QUÉ EXISTE (2026-08-05). El cliente guarda una lista de registros de **0x30 bytes** en
    `[G+0xC8..0xCC]` (G = `[0x9314E0]`) y un **índice u16 en `[G+0x8C]`**, que arranca en `0xFFFF`.
    Dentro del handler del MyRecord (FF03) hay un bounds-check:
        if (word[G+0x8C] >= cantidad_de_registros)  ->  _invalid_parameter  ->  0xC0000417  (MUERE)
    El único que escribe ese índice es un **SelectByKey** que recorre la lista buscando
    `dword[registro+0] == select_key` y **sólo escribe si encuentra**. Sin este paquete el índice se
    queda en 0xFFFF y el cliente se mata solo al recibir el MyRecord.

    Históricamente eso se tapaba con un parche de 2 bytes en el exe (`mov ecx,0xFFFF` -> `mov ecx,0`).
    En el proyecto CBT ese parche **se pudo QUITAR** justamente mandando este FF49
    (`D:\\R2Beat\\docs\\VOZ_GENERO_BIENVENIDA.md` §2 y `MULTIPLAYER.md` §G.4/G.8, verificado en vivo
    allá: *"FF49 deja display_c8(+0xc8)=3, sel(+0x8c)=0 — idx8c VÁLIDO sin parche"*).

    Formato:  `[selectKey:u32][count:u16]{[key:u32][fieldCount:u8]{[item_id:u32]}}[c2:u16][c3:u16]`

    ⚠ El `key` de cada registro **debe ser ≠ 0** o el cliente descarta la fila.
    ⚠ El `select_key` tiene que ser el **char_id**, NO un id de canal: el getter `list[idx8c].field0`
      alimenta la resolución de género/cuerpo, y si cae en una entrada de canal el avatar sale
      "hombre por defecto y sin ropa".
    ⚠ Este paquete **RESETEA lo que toca** (en el CBT vació el picker y el inventario) ⇒ va ANTES del
      inventario y del picker, nunca después.
    """
    p = bytearray()
    p += struct.pack("<I", select_key & 0xFFFFFFFF)
    p += struct.pack("<H", len(registros))
    for key, items in registros:
        # se mandan SIEMPRE las 11 ranuras: el registro del cliente mide 0x30 y un campo que no
        # mandamos NO queda en cero, queda con basura de la pila (ver 0x67CFE0).
        ranuras = (list(items) + [0] * FF49_RANURAS)[:FF49_RANURAS]
        p += struct.pack("<IB", key & 0xFFFFFFFF, len(ranuras))
        for it in ranuras:
            p += struct.pack("<I", it & 0xFFFFFFFF)
    # ★★★★★ N2 = EL INVENTARIO. **NO es opcional**: el handler RESETEA el contenedor al entrar y este
    #   bloque es el que lo repuebla. Mandando `N2 = 0` el inventario **se vacía al cambiar de canal**.
    #   ⛔ Es exactamente el bug que el proyecto CBT arregló el 2026-08-02 — y que acá reintrodujimos
    #     igual, a pesar de que el aviso estaba escrito cuatro líneas más arriba en esta misma función.
    #   ★ REGLA (del CBT): ante cualquier *"algo se vacía al cambiar de canal"*, **el FF49 es el primer
    #     sospechoso**. Ya mordió cuatro veces: índice de personaje, música, inventario y de nuevo acá.
    #   Formato por ítem, el MISMO que el campo #37 del MyRecord: [id:u32][vencimiento:u32][en_uso:u8][u16]
    _inv = list(inventario or [])
    p += struct.pack("<H", len(_inv) & 0xFFFF)
    for _it, _fin, _uso in _inv:
        p += struct.pack("<IIBH", _it & 0xFFFFFFFF, _fin & 0xFFFFFFFF, _uso & 0xFF, 0)
    # ★★★★★ N3 = LA MÚSICA POSEÍDA. Mismo cuento que el N2: el handler VACÍA la lista al entrar y este
    #   bloque es el único que la repuebla. Con `N3 = 0` **el picker de música se vacía al cambiar de
    #   canal** — confirmado en vivo 2026-08-05, y es el mismo bug que el CBT arregló el 2026-08-02.
    #   ⛔ Yo mismo había dejado esto en 0 "hasta verificar si el parser del 2013 lo lee". Lo lee.
    #   ★ Va la MISMA lista que el LOOP A del MyRecord (`OWNED_SONGS_2013`) ⇒ el envío queda IDEMPOTENTE
    #     y deja de importar si el FF49 llega antes o después del MyRecord (que era la razón por la que
    #     el síntoma parecía aparecer "sólo al cambiar de canal").
    _songs = list(canciones or [])[:0xFFFF]
    p += struct.pack("<H", len(_songs))
    for _sid in _songs:
        p += struct.pack("<H", _sid & 0xFFFF)
    # ★ 15-oct · EL TIEMPO DE HOY (segundos) del cartel «Hoy tu inicio de sesión continúa por X horas» de la Misión de
    #   hoy: MEDIDO con frida, el cliente lee un u32 JUSTO después del bucle de canciones (`0x5E065A` → `0x480CA0`, que
    #   lo PONE y le suma 1 min por timer). Antes el paquete terminaba ahí y leía 0 pasado el final.
    if tiempo_hoy is not None:
        p += struct.pack("<I", int(tiempo_hoy) & 0xFFFFFFFF)
    return bytes(p)

def build_ff126(items, exp=0, rcoin=0, a=1, caduca=0, cant=1):
    p = bytes([a & 0xFF]) + struct.pack("<I", exp & 0xFFFFFFFF) \
        + struct.pack("<I", rcoin & 0xFFFFFFFF) + bytes([len(items) & 0xFF])
    for it in items:
        p += (struct.pack("<I", int(it) & 0xFFFFFFFF)
              + struct.pack("<I", _exp_to_wire(caduca))
              + struct.pack("<I", FF126_TIPO_ITEM)
              + struct.pack("<H", cant & 0xFFFF))
    return p

def build_ff63(exp=0, rcoin=0, flag=0, campo2=0):
    """[flag:u8][?:u32][exp:u32][rcoin:u32] — 13 bytes. `flag` != 0 lleva al cliente por otra rama
    (`0x5E5F71`), sin explorar todavía, así que se manda en 0."""
    return (bytes([flag & 0xFF])
            + struct.pack("<I", campo2 & 0xFFFFFFFF)
            + struct.pack("<I", exp   & 0xFFFFFFFF)
            + struct.pack("<I", rcoin & 0xFFFFFFFF))

def leer_ff63_pedido(data):
    """Lo que el cliente MANDA al terminar (17 B). Lectura TENTATIVA — la única parte confirmada es la
    canción: en la captura de la misión 60 el campo dio 311, que es exactamente el `Music="311"` de
    `add_1.txt`. El resto se anota crudo hasta medirlo."""
    d = data + b"\x00" * 17
    return {
        "b0":      d[0],
        "u32_1":   struct.unpack("<I", d[1:5])[0],
        "cancion": struct.unpack("<H", d[5:7])[0],     # ✅ confirmado contra el Music= del script
        "u32_7":   struct.unpack("<I", d[7:11])[0],
        "u16_11":  struct.unpack("<H", d[11:13])[0],
        "u32_13":  struct.unpack("<I", d[13:17])[0],
    }

def build_create_ack(char, status=1):
    """Respuesta a FF04 (handler cliente 0x5E77E0, rama exito): [u32 status!=0&&!=-1][u8 count][count×u32].
    ★ El [count][lista] = los PART_ID del personaje (reversado 0x580580: cada u32 = una parte,
    marcada permanente 0xeeffcbb8; char_id lo deriva el cliente = 0x1ff54+gender). Al recibir los
    parts, el cliente CONSTRUYE el char -> su lista deja de estar vacia -> dispara 0x5dc2c0(6) =
    avanzar a bienvenida. Con count=0 (vacio) la lista queda vacia -> callejon sin salida."""
    parts = char.get("parts", [])
    p = struct.pack("<I", status)          # status exito
    p += bytes([len(parts) & 0xFF])        # count = nº de parts
    for pid in parts:
        p += struct.pack("<I", pid)        # cada part_id (u32)
    return p

def build_ff139_playdata(song):
    """FF139 PlayData (handler cliente 0x5DCD70). A (1er u16) = songid = LLAVE del gate 0x5BA510:
    al pasar, this->0 = 2 = 'cancion lista' y se destraba el cartel "elija una musica".
    Los demas campos van en 0 (la cancion se carga de la DB del cliente por A)."""
    return (struct.pack("<H", song & 0xFFFF) + bytes([0]) + struct.pack("<H", 0)
            + struct.pack("<H", 0) + struct.pack("<I", 0) * 3)


def build_ff28_multi(filas, grado_final, winteam=None, b1=0, b2=0):
    """★★★ EL CARTEL CON **UNA FILA POR JUGADOR** (2026-08-05).

    Hasta hoy cada jugador recibía un cartel de UNA fila —la suya— así que nadie veía el resultado del
    otro. Medido en la partida de hoy: los dos mandaron su FF28 y los dos recibieron `CARTEL 1 fila`.

    El 4º byte de la cabecera es el CONTADOR de filas (el handler lo usa para el loop), y cada fila
    mide **41 B** (acá decía 34: mal contado; ver `build_ff28_fila`).

    ★★★ CABECERA = `[b0][b1][b2][count]`, confirmada contra el disasm del handler REAL de este
    binario (**`0x5E8C40`**, no el `0x5E9360` de la tabla vieja — ver
    `documentacion/GAMEPLAY_FIN_DE_CARRERA.md` §4):

        read(1) -> b0 -> `[[0x9314c8]+0xaf4]` vtable+0x20      = EQUIPO GANADOR
        read(1) -> b1 ; read(1) -> b2
        si b1 != 0 O b2 != 0 -> `0x4FD620(b1,b2)` -> vtable+0x30 = overlay de equipo
        si roomtype == 6 (couple) -> 2 x u32 extra ANTES del count   (el nuestro es 7 -> no van)

    ⚠ `FF28_WINTEAM` (la constante) quedó SÓLO como default para los llamadores viejos. El valor
    bueno se calcula por partida y entra por `winteam=`: mandar la constante `0` con equipos
    numerados 1 y 2 le mostraba **"perdiste" a todos**.
    """
    _b0 = FF28_WINTEAM if winteam is None else winteam
    return (bytes([_b0 & 0xFF, b1 & 0xFF, b2 & 0xFF, len(filas) & 0xFF])
            + b"".join(filas) + bytes([grado_final & 0xFF]))


def build_ff13_2013(roomid=1, name="sala", host_slot=2, occ_mask=0x04, open_mask=0x3F, room_mode=0,
                    banda=0, room_bymode=0, room_colab=False, room_boss=False,
                    pista=0, cancion=0, campanas=None):
    """FF13 ROOMINFO (handler cliente 0x5CDA80).

    ★★ `campanas` (29-sep) = `{"oro": (item, x, z, rot), "plata": (...)}`: las campanas que ya sonaron
    en la sala. Van en la cola +5..+36 y el cliente las planta SOLO, sin animación y en su lugar
    exacto (`0x59DEC0` -> `0x444260` con el flag en 0). Ver `CAMPANA_EN_FF13`. ★ ESTRUCTURA REAL mapeada del disasm 2026-07-11
    (27 reads + loop 6 slots; total 65+L). El blob viejo de 21B estaba DESALINEADO -> el cliente leía
    'mi slot' en basura -> me+0x41=0 -> botón LISTO. Ver [[r2beat-2013-sala-master]].

      @0  u16 roomid
      @2  u32
      @6  u8  = ★★ EL SLOT DEL ANFITRIÓN, para TODOS los que reciben. me+0x41 = wire[6].
              ⚠ NO es "mi slot": me+0x40 = MI slot · me+0x41 = el del ANFITRIÓN, y el cliente
              decide "soy el anfitrión" comparando los dos. Coinciden SÓLO para el host — de
              ahí venía la redacción vieja, hecha cuando se probaba con un jugador solo.
              ⛔ Mandarle a cada uno SU slot deja a todos creyéndose anfitriones (pasado y
              revertido en agosto). CONFIRMADO en la captura 2026-09-02 siendo joiner: el ack
              me puso en el slot 4 y el FF13 trajo @6 = 2 (el dueño de la sala).
              ⚠ MEDIDO 2026-07-29 con centinelas por offset; CORRIGE al doc, que decía @11 con -6.
      @7  u8
      @8  u8  = ★★ EL byMode DE LA SALA (0x04 ítem · 0x10 equipo). Ver la nota grande abajo.
      @9  u8 x2              (@9..@10)
      @11 u8  (sin mapear; el doc lo daba como mi-slot y NO lo es)
      @12 u8 ; @13 u8 ; ★@14 u16 = LA PISTA ; @16 u8 ; @17 u16 ; ★@19 u16 = LA CANCION ; @21 u8 ; @22 u8

    ★★★ @14 = LA PISTA y @19 = LA CANCION — MEDIDO (2026-09-04, `mitm_20260904_102312`).
      De los 22 `FF13` que el server de referencia manda en esa sesion, **cinco bytes se
      mueven** (@6, @14, @19, @20, @66) y los demas 65 son constantes. Dos de esos cinco
      quedan atados a una causa que se ve en el mismo dump:

          RX FF1B `63 00` (99)  ->  el FF13 de al lado sale con @14 = 0x63
          RX FF1B `0b 00` (11)  ->                             @14 = 0x0b
          RX FF1B `09 00` ( 9)  ->                             @14 = 0x09
          RX FF1C music=497     ->  @19/@20 = f1 01 = 497
          RX FF1C music=180     ->                    b4 00 = 180
          RX FF1C music=294     ->                    26 01 = 294

      Tres valores distintos cada uno, en el mismo orden, sin una sola excepcion. No es
      "encaja": es la serie entera.

    ⛔ POR QUE HACIA FALTA MEDIRLO: el handler del `FF1B` en el cliente (`0x5C5400`) es un
      STUB — lee un byte y no hace nada con el. Nuestro eco del `FF1B` no podia sincronizar
      la pista **de ninguna manera**, aunque lo mandaramos perfecto. Y el server de
      referencia lo confirma del otro lado: recibe 4 `FF1B` y no contesta ni uno. La pista
      viaja por ACA. (Ya estaba anotado como plan del CBT en `h_28_ff1b` y quedo sin hacer
      porque faltaba justamente este offset.)
      @23 u8 = L (largo del nombre) ; @24 name (L bytes, cp1252)
      @24+L u8 ; luego 7x u32 ; @53+L u32 = MASCARA DE OCUPACION (bit N = slot N ocupado; host slot2 -> 0x04)
      @57+L u32 ; @61+L u8 x4  (de esos 4: +41 banda · ★+42 COOPERATIVO · +43 · ★+44 JEFE)
    ⛔ ACA DECIA: "roomtype/mode NO va aca (vive en [[0x9314ac]+0x1951], viene del descriptor de
    sala / FF6E)". **Las dos mitades estaban mal.** El modo SI va aca, en @8 (medido sobre 101
    FF13 del corpus, ver abajo), y el `[[0x9314ac]+0x1951]` es el **tier2 del CANAL**, no el modo:
    lo escribe `0x4A7940` desde el `+0x34` de una entrada de la lista de SERVIDORES/CANALES (el
    `+0x36` de esa misma entrada va a `[roommgr+0x1328]` = el canal seleccionado), y el gate
    `0x49F980` lo compara contra 5 = una CATEGORIA de canal. Confundi la lista de canales con la
    lista de salas y arrastre la confusion a `salas.py` y a `SESION_2026-09-03.md`.

    ★ 2026-07-29: la cola se reescribio para que el total sea EXACTO 65+L (antes salia 69+L: el
    open_mask se empujaba como u32 donde el layout dice u8, y quedaban 4 ceros de mas al final).
    ⚠ Los 65+L bytes que el cliente LEE son byte-identicos antes y despues (verificado) -> esto NO
    cambia comportamiento, solo alinea el codigo con el layout. Sirve para DESCARTAR el FF13 como
    sospechoso del 'elija una musica': el mi-slot @11 SI sale en host_slot+6 = 8."""
    nb = name.encode("cp1252", "replace")[:255]
    fields = bytearray(21)                           # @2..22 (21B)
    # ★★ MI SLOT = @6, CRUDO (medido con centinelas por offset, trace_masterdiag 2026-07-29).
    #   Corrige el mapeo del doc, que estaba MAL en las dos cosas: decía @11 con ajuste -6.
    #   Las dos mediciones que lo fijan sin ambigüedad:
    #     payload normal   (@11=8, resto 0)      -> me+0x41 = 0
    #     payload centinela(@6=6,@7=7,...,@22=22)-> me+0x41 = 6
    #   Única solución consistente: fuente = @6 y transformación = NINGUNA. (El `add [esp+0xe],0xFA`
    #   de 0x5CDB15 existe, pero opera sobre OTRO local: el doc confundió los locales.)
    #   Sin esto el FF13 ENTRABA con me+0x41=2 (bien puesto por el OnEnter de cRoom 0x4C47E5) y SALÍA
    #   con 0 -> el host dejaba de ser master -> botón LISTO y "elija una música" en el picker.
    fields[4] = host_slot & 0xFF                     # @6 = MI SLOT -> me+0x41 (store 0x59D0E6)
    # ★★★ @2 (u32, byte BAJO) = LA BANDA DEL PICKER DE MUSICA. Hallado 2026-08-04 (disasm):
    #   `0x5CDEE9` toma este campo y llama `cRoom::SetMusicLevelFilter` (`0x58EDF0`), que hace
    #   `mov byte [ecx+0x9512], al`. Y de ese byte sale TODO el filtro del picker:
    #       [cRoom+0x9512] --0x5BA360 LevelToMask--> [picker+0x30] --0x5BA9B0--> [song+0x57C] --> +0x4c
    #   `LevelToMask` devuelve **UN SOLO BIT** y solo para banda 1..8: **cualquier otro valor, 0
    #   incluido, da mascara 0** ⇒ NINGUNA cancion pasa el filtro ⇒ **PICKER VACIO**.
    #   ⚠⚠ Y es INCONDICIONAL: mandando 0 aca le PISABAMOS al cliente la banda que el ya habia
    #      calculado solo. El cliente la deriva de `0x486E90 GetDefaultBand()` (licencia -> 7/6/5,
    #      misiones -> 4/3, si no por nivel: <4 -> 8 · 4..10 -> 1 · >=11 -> 2) y **nunca devuelve 0**.
    #      O sea: el picker vacio lo causabamos NOSOTROS. Por eso habia que clickear un icono de banda
    #      a mano (cada boton hace `or` sobre `[picker+0x30]`).
    #   ⇒ mandamos la MISMA banda que ya calcula el muro de canal (el byte del FFC9: star=3 moon=5
    #     sun=7 ...), que es la numeracion identica.
    #   ★ Ver TODAS las bandas a la vez NO se puede pedir por protocolo: la mascara de un bit es del
    #     `ApplyFilter`; el `0xFF` solo lo pone el boton "ALL" (`0x5C0641`).
    #   ⛔ Descartado con disasm: el `byMusicLevelFilter` del FF1C entrante es DECORATIVO (solo se usa
    #     en el printf del log; ningun destino del switch lo lee). Alternativa si esto no alcanza:
    #     el **cmd 0xC9** (`[u8 banda]`, handler `0x5D8490`) que llama al setter Y a `Show()`.
    if banda:
        fields[0] = banda & 0xFF                     # @2 byte bajo del u32
    # ★★★★★ @8 = EL byMode DE LA SALA. ACA VIAJA EL MODO, Y ES LA VIA SILENCIOSA.
    #   MEDIDO 2026-09-04 sobre los **101 FF13** que el server de referencia manda en todo el corpus:
    #     · @8 toma DOS valores y ninguno mas: 0x00 (79 veces) y **0x10** (22) = el byMode de EQUIPO.
    #       Todos los demas u8 del prefijo son constantes en las 101 muestras (@11=6, @12=3, resto 0),
    #       asi que @8 es el UNICO byte del prefijo que se mueve con algo del juego.
    #     · La causalidad esta capturada de punta a punta en `mitm_20260902_144457`, 15:15:24, sala 12:
    #           TX FF4B `01 [00] 14 <nombre> ...`  ->  el FF13 de al lado sale con @8 = 0x00
    #           TX FF4B `01 [10] 14 <nombre> ...`  ->  el FF13 de al lado sale con @8 = 0x10
    #       El byte #1 del FF4B ES el byMode (eso ya lo sabiamos, ver `enviar_ff4b`), y el FF13 lo
    #       ESPEJA. Dos cambios seguidos, el mismo segundo, la misma sala: no es correlacion floja.
    #     · Y AL CREAR **NO HAY FF4B**: la sala de equipo del 16:27:36 (`FF10` con flags 0x03) recibe
    #       derecho un FF13 con @8 = 0x10.  ⇒ **para el que crea, el FF13 es lo UNICO que fija el
    #       modo.** Ese era el agujero: nosotros mandabamos @8 = 0 siempre.
    #   Es exactamente la "via silenciosa" que documenta el CBT-2011 (alla el `FF4B` era el unico que
    #   abria el popup "el modo ha cambiado"); solo que en el 2013 el byte cae en @8, no en el #4.
    #
    #   ⚠⚠ POR QUE LAS DOS SONDAS VIEJAS LO DIERON POR MUERTO — LECCION DE METODO, VALE PARA TODO:
    #     · `FF13_MODE_PROBE` SI escribio en @8, pero le puso el valor de los **flags** (`3`). En la
    #       codificacion del byMode, `3` no prende ni el bit de item (0x04) ni el de equipo (0x10):
    #       se lee como "velocidad + solo", que es CLAVADO el sintoma de estar roto. El negativo era
    #       indistinguible del bug que buscabamos.
    #     · `FF13_BYMODE` si escribio el byMode con la codificacion buena... pero en @2..@5, porque
    #       el CBT decia "byte #4" y se asumio que caia dentro del u32 de @2. Offset equivocado.
    #     ⇒ Ninguna de las dos probo "el byMode en @8". El campo NUNCA estuvo descartado, y sin
    #       embargo quedo escrito tres veces que el FF13 estaba "DESCARTADO COMPLETO".
    #   Un negativo descarta EL PAR (offset, codificacion) que se probo, no el campo ni la idea.
    fields[6] = room_bymode & 0xFF                   # @8 = byMode (0x04 item · 0x10 equipo)
    struct.pack_into("<H", fields, 12, pista & 0xFFFF)     # @14 ★ LA PISTA
    struct.pack_into("<H", fields, 17, cancion & 0xFFFF)   # @19 ★ LA CANCION
    # ★★ @11 = 6 y @12 = 3 — LAS DOS CONSTANTES DEL REFERENTE (2026-09-04).
    #   Son constantes en **101 de 101** `FF13` del server de referencia, y nosotros
    #   mandábamos 0 en las dos. Estaban anotadas desde el 04-sep en
    #   `PENDIENTE_MODO_SALA.md` como *"de los campos que encienden buffos de sala. Probar
    #   por separado"*, y nunca se probaron.
    #
    #   ⏳ Se prenden ahora persiguiendo el CARTEL DE LA MÚSICA al volver de una carrera.
    #   El referente lo repone **con el `FF13` solo** —medido seis veces seguidas en
    #   `mitm_20260902_144457`: cartel de la 83 -> `@19=83`, de la 672 -> `@19=672`, de la
    #   245 -> `@19=245`…— y **no manda ningún `FF1C`**. Nosotros mandamos el `FF13` con la
    #   canción Y además un `FF1C type 0`, y el cartel igual vuelve a "RANDOM".
    #   Armando nuestro paquete con las mismas entradas que uno capturado, los dos dan 89 B
    #   y **quedan exactamente estos dos bytes de diferencia** (más el `open_mask`, que es
    #   configuración de la sala, y la canción de la prueba).
    #
    #   ⚠ Es una HIPÓTESIS, no una medición: nadie probó qué hacen. Si el cartel no cambia,
    #     se revierten estas dos líneas — no se dejan puestas "por las dudas".
    fields[9] = 6                                     # @11
    fields[10] = 3                                    # @12
    if FF13_MODE_PROBE == "ancho":                   # ★ sonda RESPETANDO EL ANCHO de cada campo
        for _o, _w in FF13_PREFIJO_CAMPOS:
            struct.pack_into("<B" if _w == 1 else "<H", fields, _o - 2, room_mode & 0xFF)
    elif FF13_MODE_PROBE is not None and FF13_MODE_PROBE != "cola":  # sonda vieja (byte a byte)
        objetivo = FF13_MODE_OFFS if FF13_MODE_PROBE == "todos" else [int(FF13_MODE_PROBE)]
        for _o in objetivo:
            if 2 <= _o <= 22 and _o != 6:            # nunca pisar el mi-slot
                fields[_o - 2] = room_mode & 0xFF
    if FF13_SENTINEL:
        # ★ DIAGNOSTICO (2026-07-29): medido con trace_masterdiag -> el handler del FF13 ENTRA con
        #   me+0x41=2 y SALE con 0, o sea que el mapeo "me+0x41 = wire[11]-6" NO se cumple (mandamos
        #   8 en @11 y aterriza 0; para dar 0 con -6 el byte fuente tendria que ser 6, y no hay
        #   ningun 6 en el payload). Centinela: cada u8 del prefijo lleva SU PROPIO OFFSET como
        #   valor -> el valor que aterrice en me+0x41 delata el offset fuente:
        #        me+0x41 + 6 == offset   (si el ajuste -6 es correcto)
        #   Si vuelve a aterrizar 0, el valor NO sale del prefijo (local sin init o campo de la cola).
        for _o in range(6, 23):                      # @6..@22 (los u8/u16 sin etiquetar + el @11)
            fields[_o - 2] = _o & 0xFF
    p  = struct.pack("<H", roomid & 0xFFFF)          # @0  roomid
    p += bytes(fields)                                # @2..22 campos
    p += bytes([len(nb)]) + nb                       # @23 L + name
    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★★ LA COLA, REESCRITA CON EL MAPA MEDIDO (2026-08-05). Antes eran 41 bytes (total 65+L) y
    #   el cliente lee **45** (total **69+L**) ⇒ le faltaban 4 y la cola estaba corrida.
    #
    # ⚠⚠⚠ POR QUÉ IMPORTA TANTO: `0x67CFE0(this, dst, size)` — el lector universal de campos —
    #   cuando el payload se acaba **devuelve 0 y NO TOCA EL DESTINO**. El local se queda con
    #   **BASURA DE PILA**, no con cero. O sea que los 4 campos que caían pasado el final no valían
    #   0: valían lo que hubiera quedado ahí. Y dos de ellos van a parar a lugares que se ven:
    #       @65+L -> `0x58EDF0` -> [cRoom+0x9512] = LA BANDA DEL FILTRO DEL PICKER
    #       @67+L -> struct+0x3F del descriptor de sala
    #   Eso explica que el síntoma se arrastre "desde siempre" y sea caprichoso: depende de qué
    #   dejó la pila, no de nada que mandemos.
    #
    # Mapa (offsets relativos al inicio de la cola, que es @24+L):
    #    +0  u32  MÁSCARA DE SLOTS (bit N = slot N abierto) -> loop 0x5CDCA0 -> cRoom+0x9280+slot
    #             ⚠ antes se mandaba como u8; funcionaba DE CASUALIDAD porque los 3 bytes
    #               siguientes eran cero y el u32 salía igual.
    #    +4  u8   -> struct+0x12
    #    +5  u32  -> struct+0x18        +9  f32 -> struct+0x1C     +13 f32 -> struct+0x20
    #    +17 f32  -> struct+0x24        +21 u32 -> struct+0x28     +25 f32 -> struct+0x2C
    #    +29 f32  -> struct+0x30        ⚠ ACÁ caía el `occ_mask`, y se consume como FLOAT.
    #                                     La ocupación REAL la manda el FF0C, no esto.
    #    +33 f32  -> struct+0x34        +37 u32 (muerto)
    #    +41 u8   ★ BANDA DEL PICKER    +42 u8 ★ COOPERATIVO (si !=0 -> struct+0x40 |= 4)
    #    +43 u8   -> struct+0x3F        +44 u8 ★ JEFE        (si !=0 -> struct+0x40 |= 8)
    #
    # ★★★★★ +42 = COOPERATIVO y +44 = JEFE (2026-09-04). El byMode de @8 NO los lleva: en el
    #   cliente del CBT el byMode aterriza en `cRoom+0x6D84` (solo/equipo) y `+0x6D80`
    #   (velocidad/item) y nada mas — cooperativo y jefe son OTRA cosa, y por eso el que entraba
    #   a una sala cooperativa la veia "velocidad + solo" (byMode 0) y a una de jefe "item + solo"
    #   (byMode 0x04). El modo NO se le estaba pisando: nunca le llegaba.
    #
    #   Los tres apoyos, que apuntan al mismo lugar:
    #     1. DISASM: estos dos bytes hacen `struct+0x40 |= 4` y `|= 8`. Es EL MISMO PAR que hacen
    #        `r9` y `r11` de la cola del FF4B, que alimentan el `bySuperRoomCoupons` del applier
    #        `0x5971F0`. Mismo destino, mismos bits, dos paquetes distintos.
    #     2. MEDIDO EN VIVO (2026-07-30, por aislamiento, una sonda por modo): en el FF4B
    #        **`r9` = COOPERATIVO** y **`r11` = JEFE**. Ver FF4B_COLA_COLAB / FF4B_COLA_JEFE.
    #     3. CORPUS: el `+42` vale **1 exactamente en la sala 6**, que es donde corrio el minijuego
    #        del gorila (los FF10F de 14:35 a 15:06). En las salas de equipo que creo el usuario
    #        (12, 1, 2) vale **0**. El `+44` esta en 0 en las 101 muestras: nadie jugo modo jefe
    #        contra el server de referencia, asi que ese queda apoyado en 1 y 2, no en 3.
    #
    #   ⚠ Y ES LA VIA SILENCIOSA, que es todo el punto: el FF4B aplica lo mismo pero abre el cartel
    #     "el modo de juego ha cambiado", que al que ENTRA no le corresponde.
    #   ⚠ El server de referencia no resolvio esto: al entrar a la sala 6 manda un **mensaje de
    #     CHAT** ("sala 6: Modo Cooperativo / Solo"). Un rodeo, no un arreglo.
    # ══════════════════════════════════════════════════════════════════════════════════════════
    cola = bytearray(45)                             # @24+L .. @68+L  -> total 69+L
    struct.pack_into("<I", cola, 0, open_mask & 0xFFFFFFFF)   # +0  máscara de slots abiertos
    if banda:
        cola[41] = banda & 0xFF                      # +41 la banda, ahora DENTRO del paquete
    cola[42] = 1 if room_colab else 0                # +42 -> struct+0x40 |= 4  = COOPERATIVO
    cola[44] = 1 if room_boss  else 0                # +44 -> struct+0x40 |= 8  = JEFE
    # ★★★ +5..+36 = LAS CAMPANAS QUE YA SONARON (29-sep). struct+0x18/+0x1C/+0x20/+0x24 = [item][x][z][rot]
    #   de la de ORO y struct+0x28..+0x34 de la de PLATA: `0x59DEC0`, después de `SetRoomChange`, planta
    #   cada una con `0x444260(0x47 | 0x50, …, item, flag = 0, (x, 0, z), rot)`. Con el flag en 0 no hay
    #   animación ni se mira el asiento: es el camino nativo para el que ENTRA a una sala con campanas.
    #   ⚠ `0x444260` arranca con `0x58E670(item)`: si esa campana ya está plantada no hace nada, así que
    #     a los que ya la tenían (cada FF13 difundido) no se les duplica.
    for _metal, _off in (("oro", 5), ("plata", 21)):
        _c = (campanas or {}).get(_metal)
        if _c:
            struct.pack_into("<Ifff", cola, _off, int(_c[0]) & 0xFFFFFFFF,
                             float(_c[1]), float(_c[2]), float(_c[3]))
    # +43 queda en 0 EXPLÍCITAMENTE. Antes los tres no existían y el cliente los leía de la pila.
    if FF13_MODE_PROBE == "ancho":                   # ★ sonda de la COLA respetando el ancho
        for _i, _w in FF13_COLA_CAMPOS:
            if _i + _w <= len(cola):
                struct.pack_into({1: "<B", 2: "<H", 4: "<I"}[_w], cola, _i, room_mode & 0xFFFFFFFF)
    elif FF13_MODE_PROBE == "cola":                  # sonda vieja (byte a byte)
        for _i in list(range(4, 41)):
            cola[_i] = room_mode & 0xFF
    p += bytes(cola)
    return p


def grupo_de_licencia(lic):
    """El `rel4` (grupo de misión) que hace falta para que se DIBUJE esa licencia.

    Es la parte que abre la puerta; el escalón lo elige el `rel6`. Los tres valores salen de la
    tabla de `documentacion/mapeo_misiones.md`: `0x0010` = "Licencia Canal Novato Lunar",
    `0x0100` = "Licencia Canal Novato Solar", y para Estrella no hace falta ninguna (no existe una
    misión de canal estrella — el propio doc lo dice).
    """
    lic = int(lic or 0) & 0x07
    if lic & 0x04:                                # Sol
        return 0x0100
    if lic & 0x02:                                # Luna
        return 0x0010
    return 0x0000                                 # Estrella o sin licencia


def mascara_de_nibbles(nib):
    """La máscara MÁS ALTA que los nibbles del jugador dan por alcanzada.

    ★ El nibble no es "cuántas misiones hice" sino **hasta qué máscara llegué**: el bucle
      `0x48B720` del cliente hace `for i=1..n: otorgar(i << 4*grupo)`. Así que la máscara alcanzada
      de cada grupo es `n << 4*grupo`, y la que manda es la del grupo más alto. Ver la nota larga
      de `misiones.db_add_mision`, donde este mismo malentendido ya costó una corrección.
    """
    n0, n1, n2 = ((list(nib or []) + [0, 0, 0])[:3] + [0, 0, 0])[:3]
    n0, n1, n2 = (int(x or 0) & 0xF for x in (n0, n1, n2))
    if n2:
        return n2 << 8
    if n1:
        return n1 << 4
    return n0


def mision_para_icono(occ):
    """El `rel4` que va en el `FF0C` de ese ocupante.

    ★★ VA ACÁ, en el único sitio que construye el paquete, y no en el llamador. La primera versión
      lo calculaba en `salas._ocupante_de` y la prueba lo destapó enseguida: hay OTROS caminos que
      arman un `FF0C` (el de cambiar ropa, en `lobby_tienda`), y por esos el ícono se habría
      perdido en silencio. Es el mismo criterio con el que `fecha_de_registro` vive en el único
      sitio que escribe `users`.

    Sale de LA BASE —los nibbles de misiones del jugador— y nunca baja del mínimo que su licencia
    necesita para dibujarse. Así quien ya ganó la misión conserva su avance real, y quien tiene la
    licencia pero todavía no la misión igual ve su ícono correcto.

    ⚠ `chars.mission` NO sirve para esto: `db_set_mission` lo recorta con `& 0xFF` y `0x0100`
      (Novato Solar) no entra en un byte — se truncaría a 0 y el de Sol perdería el ícono. Son dos
      cosas distintas: `mission` es el progreso del CBT y esto la máscara del protocolo.
    """
    return max(int(occ.get("mision", 0) or 0),
               mascara_de_nibbles(occ.get("mision_nibbles")),
               grupo_de_licencia(occ.get("licencia", 0)))


def build_ff0c_2013_real(occ, k=2):
    """UN ocupante, con el layout medido del REFERENTE. Ver el bloque de arriba."""
    cid   = occ.get("char_id", 0) & 0xFFFFFFFF
    slot  = occ.get("slot", 0) & 0xFF
    items = [cid] + [id_wire(p) & 0xFFFFFFFF for p in occ.get("parts", []) if p]  # ★ CUERPO primero
    name  = (occ.get("nick", "") or "").encode("cp1252", "replace")[:0xFF]
    b  = bytearray([0xFF, k & 0xFF, 0, 0])
    b += struct.pack("<I", occ.get("exp", 0) & 0xFFFFFFFF)        # rel0  EXP
    b += struct.pack("<H", mision_para_icono(occ) & 0xFFFF)       # ★ rel4 = GRUPO del ícono
    # ★★★★★ 2026-09-07 — EL `rel6` ES LA **LICENCIA**, no el género. Acá mandábamos `cid & 1`.
    #
    #   ⛔ EL SÍNTOMA, reportado por el usuario: en la sala **todos** salían con el ícono de
    #     "novato estrella / estrella", cuando `jugador31` tiene licencia de Luna y `jugador28` de
    #     Sol. Mandando 0 ó 1 el cliente no encuentra licencia y **cae en la rama por NIVEL** de
    #     `GetMyChannelCode` (`0x486E90`: nivel 4..10 -> 1 Novato, nivel >= 11 -> 2 Estrella), que
    #     es exactamente el ícono que se veía.
    #
    #   ★ LA PRUEBA, sobre los **234 ocupantes** de todas las capturas del server de referencia:
    #         rel6 toma SÓLO 0, 1, 3 y 7   ->   {0: 20, 1: 127, 3: 15, 7: 72}
    #     Y nuestra columna `chars.licencia` toma **esos mismos cuatro valores y ningún otro**
    #     ({0: 2184, 1: 1083, 3: 1329, 7: 210}). 0/1/3/7 es la escalera de bits 0, 1, 11, 111:
    #     una licencia que se acumula, no un campo suelto.
    #
    #   ⇒ Y el archivo ya venía avisando: la nota del `cola[41]` (04-sep) dice que las tres
    #     mujeres del corpus traían en `rel6` los valores 7, 0 y 7 — "el mismo 7 que varios
    #     varones". Estaba escrito que NO era el género; faltaba preguntarse qué era.
    #
    #   ⚠ El GÉNERO sigue yendo donde va: `cola[41]`, que es lo que pinta el distintivo azul/rosa
    #     arriba de la cabeza. Eso no se toca.
    #   ⛔ ACÁ DECÍA "PROBADO EL 07-sep Y **NO ES**", y **ESO ESTABA MAL**. Se había probado
    #     mandando la licencia SOLA, con el `rel4` en 0, y el ícono no cambiaba. La conclusión fue
    #     "no es el campo" cuando la conclusión correcta era "**solo no alcanza**": el cliente lee
    #     el `rel4` primero y sin grupo ni llega acá. El candidato era el bueno; falló el método.
    #     ⇒ Se deja escrito porque **descartar de más cuesta días**: éste se descartó dos veces
    #       (04-sep y 07-sep) y las dos veces era el correcto.
    #   ★★★★★★ RESUELTO EL 2026-09-07: el `rel6` **ES LA LICENCIA**, y es literalmente nuestra
    #     columna `chars.licencia` (los mismos 0/1/3/7, sin conversión). Acá iba `cid & 1`, o sea
    #     basura, y por eso todos salían con el ícono de "Novato Estrella".
    #
    #   ⛔ Por qué se descartó DOS veces antes: se probó SOLO, y solo no hace nada. El ícono
    #     necesita **los dos campos**: el `rel4` (mision) abre el GRUPO y este elige el ESCALÓN.
    #     Con el `rel4` en 0 el cliente ni llega a leer éste. Verificado en pantalla por el usuario:
    #     con el grupo lunar puesto, `rel6=1` da "Novato Luna" y `rel6=3` da **Luna**.
    #     ⇒ La regla que deja: si un campo "no hace nada", puede que le falte el compañero.
    #     El grupo lo pone `salas.grupo_de_licencia`, donde está la tabla completa y su medición.
    b += bytes([occ.get("licencia", 0) & 0xFF, 0, 0, 0, 0])       # rel6 = LA LICENCIA (0/1/3/7)
    # ★ 2026-09-07 — EL `rel12` es EL EQUIPO (1 rojo / 2 azul), y lo mandábamos siempre en 0.
    #   Acá decía "SLOT + 2 ceros".
    #
    #   Lo que lo sostiene: parseo programático de los **234 ocupantes** de todas las capturas
    #   `mitm_*` del server de referencia:
    #       rel12 toma SÓLO 0, 1 y 2  ·  rel13 vale 0 en las 234
    #       asientos 0,1,2 -> 0 ó 1, NUNCA 2      asientos 3,4,5 -> 0 ó 2, NUNCA 1
    #   Sin una sola excepción. Una correlación así en 234 muestras no es casualidad: el campo
    #   **es** el equipo.
    #
    # ⛔⛔⛔ PERO ESTE PAQUETE **NO** LLENA EL PADRÓN, Y YO ESCRIBÍ QUE SÍ (corregido el mismo día).
    #   Acá decía que el `rel12` "es el que llena `sRoomUser+0x4A`". **Es falso.** Los xrefs de
    #   `0x4EC8F0` —el ÚNICO escritor de `+0x4A`/`+0x4B`— son **siete**, y el handler del `FF0C`
    #   (`0x5E82A0`) **no está entre ellos**: ni lo llama ni escribe `+0x4A` por su cuenta.
    #   Al padrón se llega por el **`FF37`** (`0x592D90`) o por el **`FF175`** (`0x5958A0`), y de
    #   eso se encarga `salas.enviar_equipos` (ver `EQUIPO_AL_PADRON`).
    #
    #   ★ CÓMO SE CAYÓ LA AFIRMACIÓN, que es lo que hay que recordar: el disasm de `0x4EC8F0`
    #     estaba bien leído y la correlación del corpus era real — pero **nadie leyó el consumidor**.
    #     Es, otra vez, "un disasm correcto no dice quién ejecuta esa línea". Lo destapó la pantalla:
    #     sala 3v3 llena, todos listos, y el cliente cortando el START por "equipos disparejos".
    #
    #   ⇒ Este `rel12` se sigue mandando porque **es** el campo y así lo manda el referente, pero
    #     NO es lo que arregla nada. Si algún día se mide que el cliente lo ignora del todo, se
    #     puede sacar sin tocar el modo jefe.
    #
    #   ⚠ Esto NO es sólo del modo jefe: en equipo y en relevo también mandábamos 0. Andaban porque
    #     el COLOR del asiento se pinta por otro camino (el `0x99` de `enviar_equipos`, que escribe
    #     `[asiento+0x157]`), pero el PADRÓN quedaba en cero. Son dos estructuras distintas y hasta
    #     hoy sólo llenábamos una.
    #   ⚠ Quién decide el 0: el llamador (ver `salas.equipo_para_ff0c`), con la misma regla que usa
    #     el cliente para "¿esta sala exige equipos?" (`0x58BFF0`: equipo, relevo o jefe).
    b += bytes([slot, occ.get("equipo", 0) & 0xFF, 0])            # rel11 SLOT · ★rel12 EQUIPO · rel13
    b += struct.pack("<I", cid)                                   # rel14 CHAR_ID
    # ⏳ `rel18`: en los 234 ocupantes del referente vale siempre el char_id (130900/130901), y
    #   nosotros mandamos ceros. Igualarlo NO cambió nada visible, así que se deja como estaba
    #   para no meter ruido en la subida a producción. Queda anotado para cuando se retome.
    b += struct.pack("<I", 0)                                     # rel18 (ellos mandan el char_id)
    b += bytes([len(items) & 0xFF])                               # rel22 ITEMCOUNT (con el cuerpo)
    for it in items:
        b += struct.pack("<I", it)
    if slot < 6:
        b += struct.pack("<f", FF0C_X0 + FF0C_DX * slot)          # ★ X del asiento
        b += struct.pack("<f", FF0C_Z)                            # ★ Z
    elif slot < 12:                                               # ★ la 2.ª fila de la sala de 12
        b += struct.pack("<f", FF0C_FONDO_X0 + FF0C_DX * (slot - 6))
        b += struct.pack("<f", FF0C_FONDO_Z)
    else:                                                         # ★ 15-oct: el ESPECTADOR de la de 12 (12+k)
        #   no se dibuja, pero la cámara de la sala se centra en «mí»: en x = 1.900 miraba un rincón vacío y no se veía
        #   a nadie (ESPECTADOR_12.md §6) ⇒ al medio de las dos filas
        b += struct.pack("<f", (FF0C_X0 + FF0C_FONDO_X0 + FF0C_DX * 5) / 2)
        b += struct.pack("<f", (FF0C_Z + FF0C_FONDO_Z) / 2)
    b += bytes([len(name)]) + name
    # ★★★★★ 2026-09-01 — LA BANDERA QUE PRENDE EL AURA/ALAS.
    #   Las alas viajaban en la lista de ítems y NO se dibujaban en la sala (en práctica sí, porque
    #   ese camino usa el MyRecord local). Buscando en los 42 FF0C reales apareció esto:
    #       cola rel5 = 56  ->  en 5/5 de los paquetes de un jugador CON aura
    #                           en 0/37 de los paquetes de los 13 jugadores SIN aura
    #   Correlación perfecta. `rel11 = 81` también acompaña (5/5) pero aparece en 2 sin aura, así
    #   que el discriminador limpio es el rel5. Cae en el `u32 @5-8` de la cola.
    #   ⚠ Las 5 muestras con aura son del MISMO jugador (jugador12, "Alas de jugador36"), así que es
    #     UNA observación repetida, no cinco independientes. Es la mejor pista que hay; si no
    #     alcanza, el siguiente paso es el rel11.
    cola = bytearray(48)
    # ★★★★★ EL SLOT DE LA PAREJA — `cola[12]`, y **`0xFF` = SOLTERO** (2026-09-12).
    #   Es lo que dibuja el enlace entre los dos asientos de una pareja en la sala (los corazones).
    #
    #   ⛔⛔ MANDÁBAMOS 0, y **el slot 0 SÍ se reparte** ⇒ para el cliente, todo el mundo estaba
    #     emparejado con quien estuviera sentado en el asiento 0. Es EXACTAMENTE el bug que el CBT
    #     ya había cometido y dejado escrito (`ANILLO.md`: *"pareja_slot == 0 chocaba con soltero"*).
    #
    #   ★★ Y `0xFF` no es una elección nuestra: es **el valor con el que el propio cliente presetea
    #     el campo** antes de leerlo del cable. Medido en el parser del FF0C del 2013:
    #         005e8593  mov byte [esp+0x2a], 0xFF   ; el preset
    #         005e8598  call 0x67D200               ; y la lectura lo pisa
    #
    #   ★ La posición (`cola[12]`) sale de contar las lecturas del parser en orden, y **se valida
    #     sola en tres puntos**: los otros tres campos que este archivo ya midió a mano y en
    #     pantalla —alas en `cola[5]`, cara en `cola[11]`, género en `cola[41]`— caen exactos con
    #     el mismo conteo.
    #
    #   ⏳ Falta la otra mitad: el **itemId del anillo** (`desc+0x28` del lado del cliente), que
    #     todavía es [NM] — sin él el enlace se dibuja con ítem 0 y el recuadro sale vacío. Por eso
    #     acá, por ahora, **todos van como solteros**: es el estado correcto y honesto.
    cola[12] = 0xFF
    # ★★★ Y SI LA PAREJA ESTÁ EN LA SALA, van los dos campos y el cliente dibuja todo.
    #   `cola[12]` = su asiento · `cola[0..3]` = el anillo.
    #   ★★★ CONFIRMADO EN PANTALLA (2026-09-12, anonimo03): *"el recuadro apareció"*. Era [H]
    #     —derivada de calcar el CBT— y la prueba la volvió un hecho. Se deja escrito el
    #     razonamiento porque el método es lo reutilizable:
    #   ⚠ Era [H]: la posición del anillo NO estaba medida en el 2013. Salía de calcar el CBT, donde
    #     quedó resuelto como *"el campo era r26, no r28"*: allá el slot y el itemId son dos campos
    #     del mismo descriptor, y acá el slot ya está confirmado en `cola[12]`. El `u32` de
    #     `cola[0..3]` es el único otro candidato del bloque (el de `cola[5..8]` son las alas, ya
    #     medidas). ⇒ **Es una hipótesis con forma de medición, no una medición.**
    #   ★ Y es barata de comprobar: si aparece el recuadro con el anillo, acertamos; si no aparece
    #     nada, está en otro lado. No puede desincronizar: el byte ya viajaba, sólo cambia su valor.
    if FF0C_ENLACE_PAREJA:
        _psl = occ.get("pareja_slot")
        if _psl is not None:
            cola[12] = int(_psl) & 0xFF
            struct.pack_into("<I", cola, 0, int(occ.get("anillo", 0) or 0) & 0xFFFFFFFF)
    # ★★★★★ LA JOYA DE LA AMISTAD EN LA SALA — `cola[33..36]` (2026-09-15).
    #
    #   La ayuda del juego lo describe: *"La joya que tienes equipado aparece cuando estés junto a
    #   tu amigo del alma"*. ⛔ Pero **NO viaja en el `worn`**: la joya es categoría 12 y el
    #   arreglo del cliente tiene 11 ranuras — mandarla ahí le escribe la pila (ver
    #   `CATEGORIAS_WORN` en `ajustes.py`, verificado en los dos handlers).
    #
    #   ★★★ EL CAMINO REAL, medido de punta a punta:
    #
    #       0x5E868D  read(4)                  ; el parser la lee del cable
    #                 -> desc+0x58             ; 0x5E8998 `mov [esp+0x100], edx`
    #       0x528C19  mov eax, [esi+0x58]      ; el aplicador del FF0C la saca de ahí
    #       0x527D70  mov [esi+0xd4], edx      ; y la escribe en el nodo de la sala
    #
    #   ⇒ `nodo+0xD4` es al amigo del alma lo que `nodo+0x50` (el anillo) es a la pareja.
    #
    #   ★★ POR QUÉ `cola[33]` Y NO OTRO: se cuentan las lecturas del parser en orden, y la cadena
    #     **se valida sola en CUATRO puntos que este repo ya midió EN PANTALLA**:
    #         alas -> cola[5]   ·  cara -> cola[11]  ·  pareja -> cola[12]  ·  género -> cola[41]
    #     Los cuatro caen exactos con el mismo conteo que pone la joya en `cola[33]`. Que cuatro
    #     anclas independientes cierren a la vez es lo que lo vuelve identificación y no
    #     coincidencia — el mismo criterio con el que se aceptó `cola[12]`.
    #
    #   ⚠ Si no aparece nada en pantalla, **esto va a False** y no se pierde nada: el campo ya
    #     viajaba en cero, sólo cambia su valor. No puede desincronizar.
    # ★★★★★ LA JOYA DE LA AMISTAD EN LA SALA — `cola[28]`, **UN BYTE**, y `0xFF` = NINGUNA.
    #
    #   ⛔ PRIMER INTENTO FALLIDO, y vale saber por qué: probé `cola[33..36]` con el **item id**,
    #     porque el conteo cerraba contra cinco anclas. El conteo estaba bien; el significado no —
    #     `nodo+0xD4` resultó ser una **coordenada** (`0x6190A0` la ajusta con `+0x15`/`-4`).
    #     ⇒ Que el conteo cierre prueba DÓNDE cae un campo, no QUÉ es. Ver [[leer-al-consumidor]].
    #
    #   ★★★ EL BUENO, y esta vez con el consumidor leído ANTES de mandarlo:
    #
    #       0x5E866B  read(1)                       ; el parser lo lee del cable
    #                 -> desc+0x45                  ; 0x5E8A34 `mov [esp+0xed], cl`
    #       0x528BFF  movzx edx, byte [esi+0x45]
    #       0x527A20  mov [esi+0xd1], al            ; -> nodo+0xD1
    #       0x527707  cmp byte [ebp+0xd1], 0xff     ; ★★ ¿tiene joya?
    #       0x527711  setne al                      ;    devuelve SÍ si NO es 0xFF
    #
    #   ★★ NO ES EL ITEM ID: es el **`Id` de `ring.txt`** (1 · 3 · 4), y el `<Friend Id="255">`
    #     de la tabla es justamente el centinela de *"ninguna joya"*. Por eso la tabla trae ese
    #     campo `Id` que los `<Couple>` no usan — es lo único que viaja.
    #
    #   ⛔⛔ Y EL DEFAULT ES `0xFF`, NO CERO. Con 0 el cliente ve *"tiene joya, la número 0"* y
    #     sale a buscar una fila que no existe. Es **exactamente** el mismo bug que `cola[12]`
    #     (donde 0 significaba *"mi pareja está en el asiento 0"*): un valor válido que es falsy.
    if FF0C_JOYA_DEL_ALMA:
        cola[28] = 0xFF                                    # ⛔ el centinela, SIEMPRE por defecto
        _joya = int(occ.get("joya_alma", 0) or 0)
        if _joya:
            _jid = int(anillo_de(_joya).get("id") or 0)
            if _jid:
                cola[28] = _jid & 0xFF
    # ★★ LA MEDALLA PUESTA, arriba de la cabeza (24-sep): el id en `cola[28..31]` — MEDIDO con Frida
    #   en el cliente vivo (con el id en 29 el cliente buscaba la 25601 = `01 64 00 00`). Ver `FF0C_MEDALLA`.
    if FF0C_MEDALLA and int(occ.get("medalla", 0) or 0):
        struct.pack_into("<I", cola, 28, int(occ["medalla"]) & 0xFFFFFFFF)
        from .medallas import CABEZA                                   # noqa: PLC0415
        if CABEZA.get("bandera") is not None:
            cola[27] = int(CABEZA["bandera"]) & 0xFF
    # ★★★ LA MARCA Y EL NIVEL DEL CÍRCULO en la tarjeta de la sala (25-sep, anonimo03: *"el nivel de
    #   círculo ni marca no se ven correctamente en la sala de juego"* — salía «1 GM» sin emblema).
    #   Leído del parser: después de la medalla (`cola[28..31]`, MEDIDA con Frida) vienen
    #   `0x5E8681 read(4)` -> desc+0x58 -> nodo+0xD4 = la MARCA (`cola[32..35]`, la dibuja
    #   `cCircleMark` `0x6190A0`) y `0x5E8692 read(4)` -> nodo+0xD8 = el valor del que sale el NIVEL
    #   (`cola[36..39]`: `0x527300` = el primer tope del círculo que lo alcanza, la MISMA tabla
    #   `0x87E4D4`) ⇒ va el TOPE del nivel actual, como en el FFD4. Detrás, `cola[40]` = el contador
    #   de joyas. ⛔ El comentario viejo de la joya ponía nodo+0xD4 en `cola[33]` y lo creía una
    #   coordenada: el conteo estaba corrido UN byte y 0x6190A0 es el dibujo del emblema.
    #   Ver `documentacion/CIRCULO_EXE_MARCA.md`.
    if FF0C_MARCA_CIRCULO:
        _marca, _nivel = occ.get("circulo_insignia") or (0, 0)
        if _nivel:
            from .circulos import tope_de                                  # noqa: PLC0415
            struct.pack_into("<II", cola, 32, int(_marca) & 0xFFFFFFFF, tope_de(_nivel))
    if FF0C_BANDERA_AURA:
        _partes = occ.get("parts") or []
        _wid = wing_id_con_aura(_partes, occ.get("usn"))  # ★ 30-oct: + el aura de suelo arriba · (142) la montura
        if occ.get("wid") is not None:                   # ★ (142) el propio: va sin ropa, pero SU byte de flotar / montura
            _wid = int(occ["wid"]) & 0xFFFFFFFF          #   tiene que llegar (la dll lo lee de la ficha en Init)
        if _wid:
            struct.pack_into("<I", cola, 5, _wid)          # ★ alas/aura  (wing.txt)
        _fid = next((f for f in (face_id(p) for p in _partes) if f), 0)
        if _fid:
            cola[11] = _fid & 0xFF                         # ★ cara/ojos  (face.txt)
    # ★★★ EL MARCO DE ASIENTO — `cola[10]`, el `Index` de `slotpack.txt` (2026-09-23).
    #   Gemelo del `#11` del `FF15` (las dos colas van en el mismo orden: alas · ? · MARCO · cara ·
    #   pareja). 0 = sin marco. Ver `MARCO_DE_ASIENTO` en `ajustes.py`.
    if MARCO_DE_ASIENTO:
        cola[10] = int(occ.get("marco", 0) or 0) & 0xFF
    # ★★ EL COLOR DEL APODO — `cola[13]` (25-sep): `0x5E85A6` -> desc+0x44 -> `0x5B327C` ->
    #   sRoomUser+0x204, que pinta el nombre en el asiento (`0x5952AF`) y sobre la cabeza (`0x59E670`).
    #   0 = blanco; 1..6 = los lápices (`catalogo.LAPICES_APODO`). ⚠ Sin cota arriba en el cliente:
    #   sólo 0..6. Ver `documentacion/CHAT_GLOBO_Y_COLOR_EXE.md`.
    if FF0C_COLOR_APODO:
        _ca = int(occ.get("color_apodo", 0) or 0)
        # ★ 23-oct: hasta 12 (los «Crayón Mazino» 7..12, con la dll `crayones.c`); el tope era 6 y el 7 salía en 0
        cola[13] = _ca if 0 <= _ca < _colores_apodo() else 0
    # ★★ (140) LA CEREMONIA DE ENTRAR A LA SALA — `cola[17]`, el `Index` de `specialentrance.xml` (30-oct).
    #   Contando las lecturas del parser desde las medidas: `0x5E8598` pareja (cola[12], el preset 0xFF) · `0x5E85A6`
    #   color (13) · `0x5E85B8` tarjeta (14) · `0x5E85C9` u16 (15..16) · ★ `0x5E85D7` (17) -> desc+0x43 (la copia de
    #   `0x5E892E`) -> `sRoomUser+0x163` (`0x5B3262`) -> `0x5B2260` -> `0x4B1840(2, índice, cuerpo)`. 0 = ninguna.
    #   ⚠ Sólo la trae el ocupante que ENTRA (`salas.difundir_ocupante` pone `entrada_sala`): ver `FF0C_ENTRADA_A_SALA`.
    #   ⛔⛔ Y CON EL BIT 0x80 PRENDIDO: `0x5E87CC test [esp+0x1c], 0x80` -> si está, `and 0x7F` (queda el Index); si
    #     NO está, `mov [esp+0x1c], 0` ⇒ el bit alto es «este acaba de entrar». La 1.ª prueba mandó el Index pelado
    #     (8) y el cliente lo leía bien y lo borraba antes de la copia: medido con Frida, 30-oct.
    if FF0C_ENTRADA_A_SALA:
        _ix = int(occ.get("entrada_sala", 0) or 0) & 0x7F
        cola[17] = (0x80 | _ix) if _ix else 0
    # ★★★ LA TARJETA DE NOMBRE — `cola[14]`, el `index` de `namecard.xml` (2026-09-23): el fondo del
    #   recuadro del apodo en la sala. `0x5E85B8 read(1)` -> desc+0x4C -> `0x5B3301` ->
    #   sRoomUser+0x1E5, que la sala le pasa al dibujo del nombre (`0x592416`/`0x5987F5` ->
    #   `[0x93433C]`, el objeto que SÍ tiene cargada la tabla). Gemelo del `T1` del `FF15`.
    if TARJETA_DE_NOMBRE:
        cola[14] = int(occ.get("tarjeta", 0) or 0) & 0xFF
    # ★★★★★ EL GÉNERO DEL OCUPANTE VA ACÁ, EN LA COLA (2026-09-04).
    #   Es el que pinta el distintivo de arriba de la cabeza en la sala (azul / rosa).
    #   MEDIDO sobre **22 ocupantes** de cuatro capturas del server de referencia:
    #       cola+41 = 1  en las 3 MUJERES (char_id 130901)
    #       cola+41 = 0  en los 19 VARONES (char_id 130900)
    #   Sin una sola excepción, y con las tres mujeres en salas y sesiones distintas.
    #
    #   ⛔ Y de paso desmiente lo que decía este archivo: el campo `rel6` que llamábamos
    #      `gender` **no es el género**. Esas mismas 3 mujeres traen ahí 7, 0 y 7 — el mismo
    #      7 que varios varones. Ver la nota grande arriba.
    #
    #   ★ Cómo se encontró: armando NUESTRO paquete con las entradas de un ocupante real y
    #     restándolo del capturado. Los dos dan 110 B y quedaron **tres bytes** distintos;
    #     éste fue el único que partía a la gente por `char_id`. Comparar paquete contra
    #     paquete, y no leer campos sueltos, es lo que lo hizo aparecer solo.
    cola[41] = sexo(cid)          # ★ de hero.txt, no del último dígito (ver `gacha.sexo`)
    # ★★★★★ EL TEXTO SOBRE LA CABEZA — `cola[4]` es el LARGO de una string, y el texto va
    #   INMEDIATAMENTE detrás. Se mandó vacía desde siempre.
    #
    #   ⛔ EL SÍNTOMA que lo destapó (2026-09-15): al encender la joya del alma (`cola[28]`)
    #     apareció **`(null)` sobre las cabezas**, donde antes no había nada. O sea que el flag
    #     activa el dibujo de ese renglón, y el renglón se queda sin texto.
    #   ★★ Y el destino está medido: `0x5E8510` pasa esa string a **`0x463380(str, dst, 0x49, f)`**,
    #     que le mide el largo y la trunca a un ancho de 0x49 ⇒ **es un texto que se DIBUJA**, no
    #     un dato del panel como parecía.
    #
    #   ⚠⚠ POR QUÉ SE INSERTA Y NO SE ESCRIBE EN SU POSICIÓN: el texto corre **todo lo que viene
    #     detrás**. `cola` es de largo fijo con los campos en su sitio (alas 5 · cara 11 · pareja
    #     12 · joya 28 · género 41) **asumiendo string vacía**. Insertando, los cinco conservan su
    #     posición relativa y el corrimiento lo hace el propio cliente al leer. El banco comprueba
    #     las cinco anclas después del corrimiento.
    # ★★★★★ LAS JOYAS DEL ALMA — `cola[40]` es el CONTADOR de una lista, y los N `Id` van
    #   INMEDIATAMENTE detrás (2026-09-23). Ver `FF0C_JOYAS_ALMA` en `ajustes.py`.
    #   ⚠ Se INSERTAN, igual que el texto de `cola[4]`: el género (`cola[41]`) y todo lo que sigue
    #     conservan su posición relativa y el corrimiento lo hace el cliente al leer.
    #   ⛔ Tope de 3: es lo más que dibuja el cliente con posiciones propias (dummy01..03), y la
    #     lista viaja con un contador de UN byte — un número raro ahí desalinea todo el paquete.
    _joyas = [int(j) & 0xFF for j in (occ.get("joyas_alma") or [])][:3] if FF0C_JOYAS_ALMA else []
    cola_b = bytes(cola[:40]) + bytes([len(_joyas)]) + bytes(_joyas) + bytes(cola[41:])
    _txt = str(occ.get("texto_cabeza", "") or "").encode("cp1252", "replace")[:0x40]
    if _txt:
        _txt = _marca_circulo(occ) + _txt            # ★ 23-oct: el crayón de círculo
    if FF0C_TEXTO_DE_CABEZA and _txt:
        b += cola_b[:4] + bytes([len(_txt)]) + _txt + cola_b[5:]
    else:
        b += cola_b
    return bytes(b)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ★★★★★ EL MINI CHAR DE LA PAREJA EN «MI INFO» — 2026-09-15
#
#  Pedido de anonimo03: *"que «mi info» muestre el minichar de mi pareja y el mío — era una función
#  nativa si no me equivoco"*. **No se equivocaba: es nativa, y estaba entera en el cliente.**
#
#  ⛔ LO QUE PASABA HASTA HOY. El último byte de la cola del `FF77` iba en cero, y nuestro propio
#    comentario lo llamaba *"flag: != 0 abre un bloque opcional grande"* — medido en tamaño, nunca
#    en significado. Ese bloque es **la pareja**, y como el flag iba en 0 el cliente se lo saltaba
#    entero. No estaba roto: **no se lo mandábamos**.
#
#  ★★★ EL LAYOUT, leído del handler real (`0x5E92D0`) con `taller/_analisis/campos13.py`, que hasta hoy
#    se cortaba antes de llegar acá:
#
#        [u8 flag]                 ← el +59 de la cola. Si es 0, el cliente SALTA TODO (0x5e96f2)
#        [u32 A]                   ⚠ [NM]
#        [u8 len][str1]            ★ el NOMBRE de la pareja
#        [u8 B]                    ★★ HAY MUÑECO: si es 0 se saltan las ranuras (0x5e979b) PERO NO
#                                     la fecha. ⛔ Hasta el 23-sep creíamos que el gate era «flag2»
#                                     y mandábamos B=0: el muñeco de la pareja no salía nunca.
#        [u8 len][str2]            ⚠ [NM] — va vacío
#        [u8 C]                    ⚠ [NM]
#        [u8 E]                    ⚠ [NM] (el que se llamaba «flag2»; nadie lo compara en el handler)
#          [u32 char_id]           ★ el CUERPO de la pareja (el gate del render, igual que @25)
#          [u8 D]                  ⚠ [NM]
#          [u32] x6                ★★ LAS SEIS RANURAS DEL AVATAR DE LA PAREJA
#        [7 B fecha]               ★★ la fecha de casamiento — se lee SIEMPRE que flag != 0
#
#  ★★★★★ POR QUÉ SE SABE QUE ES LA PAREJA, y no es una corazonada. Tres cosas que coinciden:
#
#    1. **El patrón de tres piezas es IDÉNTICO al del avatar propio.** Arriba, el mío es
#       `[u32 char_id][u8][u32 ×6]` (@25, @29, @30). Acá abajo hay, otra vez,
#       `[u32][u8][u32 ×6]`. Es **un segundo personaje dibujado con la misma maquinaria**.
#    2. **Los 7 bytes de fecha.** Ese bloque de 7 tiene un solo formato en todo el juego:
#       `[u16 año][u8 mes][u8 día]` + 3 sin consumidor, medido en `PAREJA_PENDIENTES_AGENTE.md`
#       §3 contra los dos formateadores (`0x48BE50` pareja y `0x48C250` amigo del alma).
#       Nada más en el cliente usa una fecha de 7 bytes.
#    3. **El `FF78` (la ficha de OTRO) lleva el MISMO bloque**, palabra por palabra
#       (`0x5e9bd2` el flag, `0x5e9c87` el flag2). Que los dos paneles de "ver una ficha" lleven
#       lo mismo es exactamente lo que se espera de "y acá se muestra su pareja".
#
#  ⚠ Lo que esto **no** prueba es el rótulo de cada campo suelto: `A`, `B`, `C`, `D` y el segundo
#    string quedan **[NM]** y van en cero. Ocupan igual — el cliente lee corrido.
#  ⚠⚠ Y LA TRAMPA QUE YA COSTÓ UN CRASH, heredada tal cual del avatar propio: las seis ranuras
#    pasan por el **resolver de AVATAR**, y la cara, la mascota y los accesorios **no son piezas
#    de avatar** ⇒ el resolver devuelve null y **el cliente se cierra**. Por eso acá se usa
#    **exactamente el mismo filtro** de 4 prendas base que el avatar propio, y no una copia nueva.
# ══════════════════════════════════════════════════════════════════════════════════════════════
#   Las cuatro familias que el resolver de avatar sabe dibujar. ⚠ Una sola lista para los dos
#   avatares: tener dos copias es como se desincronizan las reglas (ver [[un-dato-derivado-se-esparce]]).
PIEZAS_DE_AVATAR = ("wardrobe_hair", "wardrobe_top", "wardrobe_bottom", "wardrobe_shoes")


def seis_ranuras(partes):
    """Las 6 ranuras del avatar 3D: **sólo las 4 prendas base**, rellenadas con ceros.

    ⚠⚠ El filtro NO es un detalle de prolijidad: el CBT lo dejó anotado con sangre. Cualquier
      cosa que no sea prenda base (la cara, la mascota, un accesorio) hace que el resolver de
      avatar devuelva null y **el cliente se cierre**. El aura tampoco va acá: viaja por `wing_id`.
    """
    _p = [id_wire(x) & 0xFFFFFFFF for x in (partes or [])
          if x and familia_de(x) in PIEZAS_DE_AVATAR][:6]
    return _p + [0] * (6 - len(_p))


def _bloque_pareja_ff77(pareja):
    """El bloque de la pareja del `FF77`. `pareja` = `{"nick", "char_id", "partes", "fecha"}`.

    ⚠ `fecha` son los **7 bytes ya armados** (`lobby_pareja._fecha7`), no un timestamp: el formato
      es el que costó varias equivocaciones al proyecto y tiene **un solo** sitio donde se arma.
      Pasarlo hecho es lo que evita que nazca una segunda versión de esa cuenta.
    """
    _nb = str(pareja.get("nick") or "").encode("cp1252", "replace")[:0x1E]
    _cid = int(pareja.get("char_id") or 0)
    _fecha = bytes(pareja.get("fecha") or b"")[:7]
    _fecha += bytes(7 - len(_fecha))
    # ⛔⛔ CORREGIDO EL 2026-09-23 — EL GATE DEL MUÑECO ERA «B», NO «flag2».
    #   anonimo03: *"al abrir la info de jugador50 debería salir en el minichar él y su pareja; sale
    #   sólo él"*. El bloque viajaba entero (190 B) y el cliente no lo dibujaba. Releído el
    #   handler (`0x5E92D0`) normalizando la pila en cada `push`:
    #       0x5E9744  read(1) -> base+0x2E8   ← el byte JUSTO DESPUÉS del nombre («B»)
    #       0x5E978F  read(1) -> base+0x30B   ← el que yo llamaba «flag2»
    #       0x5E9794  cmp byte [esp+0x2E8], 0 ; ★ compara «B»
    #       0x5E979B  je 0x5E9829             ;   en 0 SE SALTEA el char_id y las 6 ranuras
    #   ⇒ Con B en 0 el cliente no leía el cuerpo, y encima tomaba nuestro `char_id` como el
    #     principio de la FECHA: el bloque entero quedaba corrido. Por eso no se veía nada.
    #   ★ La lección, la de siempre: con los `lea [esp+N]` después de un `push`, el offset
    #     aparente está corrido 4. Hay que normalizar antes de decir qué byte compara quién.
    # ⏳ [H] «A» = el Index del anillo (ver `FF77_PAREJA_ANILLO`). Sin anillo, 0 como siempre.
    # ⛔⛔ CORREGIDO EL 2026-09-27 — LOS DOS TEXTOS ESTABAN AL REVÉS. anonimo03, en pantalla: «Ver perfil →
    #   Info Pareja» mostraba el nick de la pareja en **«Mi confesión»**, y «Mi pareja» salía vacío.
    #   Lo dicen los BUFFERS donde el handler guarda cada texto (normalizado el push):
    #       texto 1 -> base+0x264 · hasta base+0x2E8 = **132 B**  ⇒ cabe un mensaje: LA CONFESIÓN
    #       texto 2 -> base+0x2EA · hasta base+0x30A = **32 B**   ⇒ justo un nick: EL DE LA PAREJA
    #   La confesión la manda el cliente pegada al cambio de anillo (`FF40 0A/0F`, ver lobby_pareja).
    # ★ C = el NIVEL de la pareja — medido EN PANTALLA (27-sep): le mandé la licencia (7) y el
    #   juego dibujó «estrella + 7» junto al nick, o sea el 7 como NIVEL (jugador1 es 93).
    # ⏳ [H] E = la LICENCIA (0/1/3/7, como `chars.licencia`): el ícono de al lado. A medir.
    _conf = str(pareja.get("confesion") or "").encode("cp1252", "replace")[:128]
    b  = struct.pack("<I", int(pareja.get("anillo") or 0) & 0xFFFFFFFF)   # A
    b += bytes([len(_conf)]) + _conf             # ★ texto 1 = LA CONFESIÓN (132 B en el cliente)
    b += bytes([1 if _cid else 0])               # ★★ B = HAY MUÑECO (el gate de 0x5E9794)
    b += bytes([len(_nb)]) + _nb                 # ★ texto 2 = el NICK de la pareja (32 B)
    b += bytes([min(int(pareja.get("nivel") or 0), 0xFF)])  # C   ★ el NIVEL de la pareja (medido)
    b += bytes([int(pareja.get("licencia") or 0) & 0xFF])   # E   [H] la licencia de la pareja
    # ★ Sin `char_id` no hay cuerpo que dibujar (es el mismo gate que el @25 del avatar propio):
    #   B va en 0 y el cliente salta directo a la FECHA, que se lee siempre.
    if _cid:
        b += struct.pack("<I", _cid)             # ★ el CUERPO de la pareja
        b += bytes([0])                          # D   [NM]
        b += b"".join(struct.pack("<I", p) for p in seis_ranuras(pareja.get("partes")))
    return b + _fecha


def build_ff77_myinfo(char_id, partes=(), pareja=None, columnas=None, medallas=None, ranking=0,
                      circulo="", marca=0, circulo_exp=0, presentacion=None, lista=None):
    """FF77 MyInfo subtipo 0 — el récord de "mi info", con el mini char VESTIDO.

    Calcado byte a byte de un server que funciona (captura 2026-09-02, ver
    `documentacion/FF77_MYINFO.md`). Hasta hoy respondíamos **un solo byte** `0x01`
    (subtipo 1 = el camino corto del cliente, que no parsea nada): por eso el mini char
    salía por defecto y **sin las alas puestas**.

    ★★ LAYOUT LEÍDO DEL HANDLER REAL (`0x5E92D0`), no adivinado del corpus:

        [u8 subtipo]         @0   0 = el récord entero · 1 = el camino corto
        [u32 char_id]        @1   ★ el CUERPO — 130900 varón · 130901 mujer
        [u32] x5             @5   cinco campos del récord
        [u32 char_id]        @25  otra vez, el mismo valor (gate del render)
        [u8]                 @29  ⚠ NO es relleno: es un campo (0 en todo el corpus)
        [u32] x6             @30  ★ LAS SEIS RANURAS DEL AVATAR
        [u8 cuenta]          @54  cuántas prendas van a continuación
        [u32 item] x cuenta       la lista de ropa (alimenta la grilla "Cambiar Ropa")
        [u32 wing_id]             el índice del efecto en el wing.txt del cliente
        [60 B de cola]            desarmada abajo, campo por campo

    Largo = **119 + 4*cuenta**, y cierra exacto en las tres muestras del corpus: 119 B
    (desnudo), 123 B (1 prenda) y 135 B (4 prendas). El paquete termina justo donde el
    handler hace su última lectura — es la prueba de que el layout está completo.

    ⛔ **`documentacion/FF77_MYINFO.md` nombraba el handler equivocado**: decía `0x5E9910`,
    que es el del **`FF78`**. Con esa función los números no cierran (lee el 2º byte del
    paquete como *cuenta*, y ahí el `FF77` tiene `0x55` = 85 ítems en un paquete de 135 B).
    La tabla buena es la que extrae `taller/re2013/tabla_rx.py`. ⚠ `taller/re2013/mitm.py` todavía rotula
    `handler=0x5E99F0` en el dump: usa la tabla vieja.

    ⚠ **El personaje de la captura estaba DESNUDO**: su `FF0C` de la misma sesión dice
    `itemcount=1`, o sea sólo el cuerpo. Por eso su arreglo traía un único elemento —el
    aura— y por eso, al copiar el paquete tal cual, el mini char salía con alas y sin
    ropa aunque el jugador tuviera ropa puesta. Acá va **todo lo puesto**.

    El récord en sí (ganadas/perdidas/empate, gremio, medallas) va en cero: los dos
    personajes del corpus no tenían partidas jugadas, así que no hay una sola muestra con
    datos. Mandar ceros es exactamente lo que el cliente ya está aceptando hoy.

    ★★ EL GÉNERO (2026-09-04). Comparadas byte a byte la muestra de VARÓN (`TunTunSahur`,
    02-sep) y la de MUJER (`asdfff`, 04-sep), aparecieron **dos** diferencias y nada más:
    el `char_id` (130900 / 130901), que ya mandábamos bien, y **un `u8` de la cola** que
    vale `1` en la mujer y `0` en el varón. Es el **único byte no nulo de toda la cola** en
    las dos muestras, y cae justo donde nosotros mandábamos ceros.

    ⚠ Es UNA muestra de cada género, y de cuentas distintas: podría ser gremio, casado, lo
      que sea que esa jugadora tenga y ese jugador no. Va como `char_id & 1`, que es la
      misma regla que ya usan el `FF0C` (`occ6`) y el `MyRecord`. **Si el iconito no cambia
      en pantalla, la hipótesis se cae y hay que revertir esta línea** — no dejarla puesta
      "por las dudas", que es como se acumulan los ceros que nadie sabe de dónde salieron.

    ⚠ El largo tiene que ser EXACTO o el cliente se desincroniza. Por eso se arma por
    concatenación y no escribiendo sobre un buffer fijo: con el `u32` del aura de por
    medio, todo lo que sigue se corre 4 bytes.
    """
    cid = char_id & 0xFFFFFFFF
    puestas = [id_wire(p) & 0xFFFFFFFF for p in (partes or []) if p]
    # ★ 12-oct: `lista` = lo que va en la grilla de @54, que es la pestaña «Mis Preferidos» del perfil (el carrito,
    #   `PERFIL_LISTA_PREFERIDOS`). None = la ropa puesta, como antes (y como en las muestras del corpus).
    if lista is not None:
        puestas = [int(x) & 0xFFFFFFFF for x in lista if x][:0xFF]
    wid = wing_id_con_aura(partes)                   # ★ 30-oct: + el aura de suelo arriba (AURA_DE_SUELO.md)
    # ★★★ EL MINI CHAR NO SE VISTE CON LA LISTA DE ABAJO, sino con SEIS RANURAS DE PIEZAS.
    #   Reversado en el server del CBT (`D:\\R2Beat\\server\\server-clean.py`, `build_userinfo`,
    #   2026-07-13): la lista de ropa «cae en un std::vector que el cliente DESCARTA», y el
    #   avatar 3D del popup se arma con ranuras fijas. En el 2013 esas seis ranuras son los
    #   seis `u32` de @30..@53, que en el corpus vinieron todos en cero.
    #   Confirmado en pantalla: con la lista llena, la grilla "Cambiar Ropa" se poblaba pero
    #   el muñeco seguía desvestido.
    #
    #   ⚠⚠ VAN SÓLO LAS 4 PRENDAS BASE (pelo · top · bottom · zapatillas). El CBT lo dejó
    #      anotado con sangre: el panel pasa cada pieza por el resolver de AVATAR, y la CARA,
    #      la mascota y los accesorios **no son piezas de avatar** ⇒ el resolver devuelve
    #      null y el cliente CRASHEA. El aura tampoco va acá: viaja por `wing_id`.
    #   ★ 2026-09-15: la cuenta se mudó a `seis_ranuras()` porque el mini char de la PAREJA usa
    #     exactamente la misma regla. Una sola copia: si el filtro cambiara en un lado y no en el
    #     otro, el avatar de la pareja crashearía el cliente y el propio no, que es el peor
    #     síntoma posible — *"a veces se cierra"*.
    piezas = seis_ranuras(partes)
    b  = bytes([0])                                  # @0  subtipo 0 = el récord entero
    # ★★ 24-sep: los «5 campos del récord» ya no van en cero. `columnas` = `{9: n, 13: n, 17: n}`
    #   (ver `medallas.columnas_ff77`): el cliente dibuja @9, @17, @13 y el % de victorias =
    #   @9 / (@9+@13+@17). @21 = la suma (= jugadas), igual que la calcula el otro setter del
    #   panel (`0x451550`). @5 = la EXP del círculo (el nivel de la insignia, ver @1 abajo).
    _col = {int(k): int(v) for k, v in (columnas or {}).items()}
    # ★★ @1 = LA MARCA DEL CÍRCULO (25-sep, `documentacion/CIRCULO_EXE_MARCA.md`): el handler
    #   (`0x4516C0`) la copia a `panel+0x2358`, cuyo ÚNICO lector es el dibujo del emblema
    #   (`0x44B2E0` -> `cCircleMark` `0x6190A0`), y sólo si el nombre del círculo (cola, str1) no es
    #   vacío. El cuerpo sale del @25. Hasta hoy iba el char_id (como en el referente, cuyas cuentas
    #   no tenían círculo). ⚠ Sin círculo o sin marca sigue yendo el char_id: la ficha queda IGUAL
    #   que antes para todos los demás. @5 = la EXP del círculo -> el nivel de la insignia
    #   (`0x527300`, los mismos topes del círculo).
    _con_marca = bool(circulo) and bool(marca)
    b += struct.pack("<I", (int(marca) & 0xFFFFFFFF) if _con_marca else cid)   # @1  la marca (o el char_id)
    b += struct.pack("<IIIII", (int(circulo_exp) & 0xFFFFFFFF) if circulo else 0,
                     _col.get(9, 0), _col.get(13, 0), _col.get(17, 0),
                     _col.get(9, 0) + _col.get(13, 0) + _col.get(17, 0))   # @5 @9 @13 @17 @21
    b += struct.pack("<I", cid)                      # @25 cuerpo otra vez (gate del render)
    b += bytes(1)                                    # @29 relleno
    b += b"".join(struct.pack("<I", p) for p in piezas)   # @30..@53 ★ LAS 6 PIEZAS
    b += bytes([len(puestas) & 0xFF])                # @54 la lista (la grilla «Mis Preferidos»)
    b += b"".join(struct.pack("<I", it) for it in puestas)
    b += struct.pack("<I", wid)                      # el efecto del aura (wing.txt)
    # ── LA COLA, CAMPO POR CAMPO ────────────────────────────────────────────────────
    #   Antes iba `bytes(60)` a ciegas: 60 ceros que "andaban" porque cada largo de
    #   string cae en 0 y cada flag apaga su bloque opcional. Ahora está desarmada
    #   contra el handler REAL (`0x5E92D0`), y la cuenta cierra: el paquete termina
    #   exactamente donde termina la última lectura, en las tres muestras del corpus
    #   (119 B desnudo · 123 B con alas · 135 B con 4 prendas).
    # ★ string 1 = la casilla «Círculo» del perfil (24-sep) — ⏳ [D] por analogía con el CBT
    #   (`PERFIL_CASILLA_CIRCULO.md`: str1 -> view+0x1896) y porque el 2º pasa por el filtro de
    #   `0x40A060`; se confirma en pantalla. Vacío = el paquete de siempre, byte por byte.
    _circ = str(circulo or "").encode("cp1252", "replace")[:0x40]
    cola  = bytes([len(_circ)]) + _circ  # +0  u8 largo del string 1 + el nombre del círculo
    # +1 ★ string 2 = el TEXTO de la PRESENTACIÓN y +2 = la EDAD (29-sep): van a `cAccount+0x436` y
    #   `+0x4D4`, que es de donde la pestaña «Presentación personal» dibuja la de OTRO (`0x44DE25`; la
    #   propia sale de `+0x398/+0x394`, que llena el FF03). `presentacion` = `(edad, texto)`.
    #   ⏳ [D] leído del exe, se confirma en pantalla. None = vacío, como antes.
    _p_edad, _p_txt = presentacion or (0, "")
    _p_txt = str(_p_txt or "").encode("cp1252", "replace")[:0x9F]
    cola += bytes([len(_p_txt)]) + _p_txt          # +1  u8 largo del string 2 + el texto
    cola += bytes([int(_p_edad or 0) & 0xFF])      # +2  u8 la edad -> [[0x9314e0]+0x4d4]
    # +3  ★★ SIETE u32 = EL RÉCORD DE LAS MEDALLAS (24-sep), no «un 2º bloque de ranuras»:
    #     [medalla puesta][contador escalera 1..6]. El panel «Mis Medallas» (`0x449F50`) indexa
    #     este vector con `MedalID // 100`; en el 2019 el mismo bucle lee 71 (1 + 70 escaleras).
    #     Lo arma `medallas.bloque_ff77`. Ver `documentacion/MEDALLAS_Y_RECORD.md` §3.
    _med = bytes(medallas or b"")
    assert len(_med) in (0, 28), len(_med)
    cola += _med or bytes(28)
    cola += bytes([0, 0, 0])          # +31 +32 +33
    cola += bytes([sexo(cid)])        # +34 ★★ EL GÉNERO (0 varón · 1 mujer) — ver `gacha.sexo`
    # +35 ★ EL PUESTO EN EL RANKING (`struct+0x214` -> `%dº`, «más de 1000º» si pasa de 1000) · +39
    cola += struct.pack("<II", int(ranking or 0) & 0xFFFFFFFF, 0)
    cola += bytes(16)                 # +43  -> [[0x931628]+0x27ec .. +0x2800]
    # +59 ★★★★★ EL FLAG DE LA PAREJA. Hasta el 2026-09-15 iba en cero y el comentario decía
    #     *"abre un bloque opcional grande"* sin saber de qué. **Ese bloque es la PAREJA**, y con
    #     él aparece el mini char de la pareja al lado del propio. Ver `_bloque_pareja_ff77`.
    cola += bytes([1 if pareja else 0])
    assert len(cola) == 60 + len(_circ) + len(_p_txt), len(cola)   # 60 con los dos strings vacíos
    return b + cola + (_bloque_pareja_ff77(pareja) if pareja else b"")


def build_ff80_cupones(jugadores):
    """`FF80` = `CNetwork::CmdGameCoupon`: los cupones ACTIVADOS de cada jugador de la carrera.

        [u8 n]  n × { [u8 asiento] [u8 m]  m × [u32 ítem] }       (handler 2013 `0x5E76F0`)

    `jugadores` = `[(asiento, [ítems]), …]`. Va TODO jugador, aunque no tenga ninguno (m = 0): el
    cliente deja la tabla de ese asiento con lo que tenía, y un «sin cupones» explícito no deja
    colgado el cupón de la carrera anterior. Ver `FF80_CUPONES_DE_PARTIDA` en `ajustes.py`.
    """
    js = [(int(s) & 0xFF, [int(i) & 0xFFFFFFFF for i in (its or [])][:0xFF]) for s, its in jugadores][:0xFF]
    b = bytes([len(js)])
    for s, its in js:
        b += bytes([s, len(its)]) + b"".join(struct.pack("<I", i) for i in its)
    return b


def build_ff78_verinfo(partes=(), char_id=0, pareja=None, tarjeta=0):
    """FF78 — la ficha de OTRO jugador (clic sobre un ocupante).

    ★★★ HANDLER REAL: **`0x5E9910`**. ⛔ No es `0x5EA020` (eso venía de la tabla vieja), y
    tampoco es el del `FF77`: `documentacion/FF77_MYINFO.md` le atribuía **esta** función al
    `FF77`, y las lecturas que lista ahí son las de acá. La tabla buena la extrae
    `taller/re2013/tabla_rx.py`: `FF77 -> 0x5E92D0` · `FF78 -> 0x5E9910`.

    Layout LEÍDO DEL HANDLER y verificado contra **9 muestras de 4 tamaños distintos**:

        [u8 result=0]
        [u8 cuenta]
        [u32 item] x cuenta       la LISTA (lo que TIENE, no lo que lleva puesto)
        [u32] x3 [u8 len][str][u8]   los "14 B en cero" del doc viejo, ahora con nombre
        [u32] x7                  ★★ SIETE RANURAS, no cuatro
        [u8][u8][u8][u8]          el 4º es el candidato a GÉNERO (0 en las 9 muestras)
        [u32][u32][16 B][u8 flag] flag != 0 abre un bloque opcional grande

    El largo sale exacto de la cuenta: **`73 + cuenta*4`** — cuenta 7 → 101 B · 8 → 105 ·
    13 → 125 · 19 → 149. Por eso se sabe que el bloque de ranuras **sigue a la lista** y no
    está en un offset fijo: con una sola muestra las dos hipótesis eran indistinguibles.

    ★★ LO QUE CORRIGE ESTA PASADA. El doc decía «[u32] x4 ranuras + 41 B en cero salvo
    `+8`, un u32 con mascota/accesorio». Ese `+8` misterioso **es la 7ª ranura**: 4 ranuras
    (16 B) + 8 = 24 = exactamente donde arranca el 7º `u32` del bloque. No había un campo
    suelto escondido en el relleno; el bloque siempre fue de siete.

    Y con las 9 muestras se ve qué familia va en cada una:

        1 pelo · 2 top · 3 bottom · 4 zapatillas · 5 **pet** · 6 (sin muestra) · 7 **wand**

    (`600008` = pet y `830009` = wand, cruzados contra nuestro `shop_lt`.) Un mismo jugador
    aparece dos veces con 1'30" de diferencia, la segunda con la mascota puesta y la
    primera sin ella: la ranura 5 se pobló sola. Eso es lo que la vuelve identificación y
    no coincidencia.

    ★ La prueba de que la lista y lo puesto son cosas distintas: en la muestra de 101 B las
    ranuras traen `212053` y `518048`, que **no son los primeros de la lista** (ahí están
    `210565` y `510429`). Ese jugador tiene dos pelos y dos calzados, y el avatar usa uno
    de cada. Mismo hallazgo que en el `FF77` (ver `build_ff77_myinfo`).

    ⚠ La advertencia del CBT sobre la CARA es de **otro bloque**: son las SEIS ranuras del
      `FF77` (`@30`), que pasan por el resolver de AVATAR y crashean con lo que no sea
      prenda base. Éste no es ese bloque — el server de referencia le mete pet y wand a
      jugadores reales, y nadie se cayó.
    """
    lista = [id_wire(p) & 0xFFFFFFFF for p in (partes or []) if p]
    # las 7 ranuras, en el orden del corpus. La 6 nunca vino con datos: queda en 0.
    ORDEN = ("wardrobe_hair", "wardrobe_top", "wardrobe_bottom", "wardrobe_shoes",
             "pet", None, "wand")
    ranuras = []
    for fam in ORDEN:
        if fam is None:
            ranuras.append(0)
            continue
        ranuras.append(next((id_wire(p) & 0xFFFFFFFF for p in (partes or [])
                             if p and familia_de(p) == fam), 0))
    b  = bytes([0, len(lista) & 0xFF])
    b += b"".join(struct.pack("<I", it) for it in lista)
    b += bytes(14)                                        # u32 x3 + len(str)=0 + u8
    b += b"".join(struct.pack("<I", r) for r in ranuras)   # ★ las SIETE ranuras
    # ★★ EL GÉNERO, en el 4º de los cuatro `u8` — la MISMA posición que en el `FF77`.
    #   Los dos handlers leen este tramo con la misma forma y en el mismo orden
    #   (cuatro `u8`, después dos `u32`, después 16 B, después el flag), y el 4º cae en
    #   `+1` del sub-bloque en los dos. En el `FF77` ese byte resultó ser el género —
    #   confirmado en pantalla el 04-sep — así que acá va el mismo.
    #   ⚠ En las 9 muestras del corpus vale 0 en todas, pero las 9 son de un panel que
    #     abrimos nosotros sobre gente cuyo género no conocemos: el corpus no lo
    #     desmiente, sólo no lo confirma. Si el muñequito no cambia, se revierte.
    # ★★ Y EL 2º ES LA TARJETA DE NOMBRE (2026-09-23): el `index` de `namecard.xml`. Leído en el
    #   handler `0x5E9910`, con la ficha en `R = esp+0x40` (la que recibe `0x5957B0`):
    #       0x5E9AF4 -> R+0xE0 · ★0x5E9B05 -> R+0xE8 · 0x5E9B16 -> R+0xE9 · 0x5E9B27 -> R+0xE1 (género)
    #   y `0x451621` copia `R+0xE8` al panel (`+0x2356`), que dibuja el recuadro del apodo con esa
    #   fila (`0x450840` -> `0x4829F0`/`0x482A80`). Iba en 0 = sin tarjeta.
    b += bytes([0, tarjeta & 0xFF, 0, sexo(char_id)])   # 4 u8; 2º = tarjeta · 4º = género
    b += bytes(24)                         # u32 + u32 + 16 B
    # ★★ EL FLAG DE LA PAREJA y su bloque (2026-09-23): el MISMO bloque que el `FF77`, leído
    #   igual por este handler (0x5E9BD2 el flag · 0x5E9C80 `cmp` del byte B = hay muñeco).
    #   Antes iba en 0: al tocar a alguien en la sala, su ficha nunca mostraba a su pareja.
    return b + bytes([1 if pareja else 0]) + (_bloque_pareja_ff77(pareja) if pareja else b"")


def build_ff15_2013(slot, char_id, worn, face_index, wing_id=0, pareja_slot=0xFF,
                    equipo=0, capitan=False, joyas=(), marco=0, tarjeta=0, medalla=0, color_apodo=0):
    """FF15 = apariencia completa de UN ocupante + reload del mesh.

    ★★★ EL `#13` ES EL ASIENTO DE LA PAREJA, y **es lo que sincroniza el recuadro** (2026-09-12).

      ⛔ IBA EN 0, que para el cliente es *"mi pareja está en el asiento 0"* — exactamente el
        mismo bug que ya habíamos arreglado en la cola del `FF0C`, vivo acá por otra puerta.

      ★★ Y ES LA PIEZA QUE FALTABA PARA QUE EL ENLACE SE ACTUALICE. El `FF0C` **no re-dibuja a
        quien ya está en la sala**: `cRoom::OnRoomUser` (`0x59FDF0`) es *create-if-absent*, y si
        el ocupante ya existe el aplicador ni corre — que es la única ruta del `FF0C` hacia el
        escritor del enlace. ⇒ el que YA estaba adentro nunca se entera de que el otro llegó.
        El `FF15` sí entra siempre: su handler lee este byte (`0x5F3977`) y lo lleva al MISMO
        campo del nodo (`0x591FD0` → `nodo+0xC4`), y esa función tiene **un solo xref en todo el
        binario**: este handler.
      ⇒ Es el reload que el CBT ya había descubierto (`ANILLO.md`: *"el FF0C no re-dibuja a
        alguien ya dibujado; el FF15 fuerza el reload"*).

      ⚠ `0xFF` = soltero, y no es elección nuestra: es el valor con el que el propio cliente
        presetea el campo.

    ★★★★★ LA COLA COMPLETA (2026-09-23). Hasta hoy el paquete se cortaba en la mitad de lo que el
      handler (`0x5F3780`) lee, y el lector del cliente (`0x67D200`), cuando se queda sin bytes,
      **vuelve sin escribir**: cada campo de la cola quedaba con lo que hubiera en la pila. Es
      `CNetwork::CmdRoomUserInfo` (nombre del cliente 2019, que lo tiene sin optimizar), el
      comando que ACTUALIZA a un ocupante que ya está en la sala. Leído campo por campo, con la
      pila normalizada contra el cuerpo de la función:

          #11  u8   -> 0x59FB90(slot, #11) ★ el MARCO de asiento (`slotpack.txt`), ver `MARCO_DE_ASIENTO`
          #7   u8   -> 0x592D90(slot, #7, T11||T12) ★ el EQUIPO al PADRÓN (el camino del FF37:
                        nuestro `FF37` manda `[equipo, slot, slot, capitán]` a la MISMA función)
          T1   u8   -> 0x597960 -> sRoomUser+0x1E5  ★ la TARJETA DE NOMBRE (el recuadro del apodo)
          T2   u16  ·  T3 u8 -> escena+0x164  ·  T4 u32 -> 0x5B0C70 si !=0  ·  T5 u32 -> 0x5B0CE0 si !=0
          T6   u8   (se compara con #14)  ·  T7 u32 -> escena+0x208 ★ LA MEDALLA PUESTA (24-sep): el
                        mismo campo que el FF0C llena desde `cola[28..31]`, y el que dibuja su nombre
                        arriba de la cabeza (`0x59ED53`). Así se ve EN VIVO al ponérsela.
          [u8 N][N × Id]  ★★ LAS JOYAS DEL ALMA -> 0x5B0AA0, el mismo dibujo que el FF0C
          T9   u8   -> 0x5B1120 -> sRoomUser+0x196 ★★ el GÉNERO (el mismo campo que el FF0C llena con
                        `cola[41]`, `0x5B32A2`). ⛔ IBA EN 0: cada FF15 volvía VARÓN al ocupante, y la
                        mascota de pareja se re-creaba en la versión de chico (`0x5A0FA2` ->
                        `0x5B0050` -> `0x525550`: +1000 sólo si género = 1). anonimo03, 23-sep: *"ambos
                        reciben la misma versión"*.
          (u32 + u8 SÓLO si `[sala+0x9580] ^ 0x1FEF != 0`; su único escritor lo deja en 0 ⇒ se
           saltean. Se mandan 5 ceros AL FINAL: si alguna sala los leyera, las joyas —que van
           antes— no se corren)
          T10  u32  -> escena+0x1E8  ·  T11 u8 · T12 u8 -> ★ la bandera de CAPITÁN (T11 || T12)
      ★ Los [NM] van en 0 porque es lo que el `FF0C` les da a sus gemelos del descriptor
        (escena+0x164 <- desc+0x3F · +0x208 <- desc+0x48 · +0x1E8 <- desc+0x74, todos en 0).
      ⛔⛔ Y ESTO EXPLICA UNA FAMILIA ENTERA DE BUGS: con `#7 = 0` y la cola cortada, **cada
        `FF15` sacaba al jugador de su equipo** y el capitán salía de basura de la pila. Por eso
        existía la regla *"repintar los equipos detrás de cada FF15"* (el «sexto caso»).
    """
    worn = worn_seguro(worn, f"FF15 slot={slot & 0x7F}")
    b  = bytes([slot & 0xFF])                          # #1  slot (identifica al ocupante)
    b += bytes([0])                                    # #2
    b += struct.pack("<I", char_id & 0xFFFFFFFF)       # #3  char_id (valida la cara)
    b += struct.pack("<I", 0)                          # #4
    b += bytes([len(worn) & 0xFF])                     # #5  cuántas prendas
    for it in worn:
        b += struct.pack("<I", it & 0xFFFFFFFF)        # #6  worn COMPLETO = [char_id] + prendas
    b += bytes([equipo & 0xFF])                        # #7  ★ el EQUIPO (-> 0x592D90, el padrón)
    b += struct.pack("<I", 0)                          # #8
    b += struct.pack("<I", wing_id & 0xFFFFFFFF)       # #9  ★ Wing.Id (cambios de ala EN VIVO)
    b += bytes([0])                                    # #10
    b += bytes([(marco if MARCO_DE_ASIENTO else 0) & 0xFF])  # #11 ★ MARCO de asiento -> 0x59FB90
    b += bytes([face_index & 0xFF])                    # #12 ★ faceByte -> [occ+0x1a1]
    _ca = int(color_apodo or 0) if FF0C_COLOR_APODO else 0
    _ca = _ca if 0 <= _ca < _colores_apodo() else 0               # ★ 23-oct: hasta 12 (era «<= 6»)
    b += bytes([pareja_slot & 0xFF, _ca])   # ★ #13 = ASIENTO DE LA PAREJA · ★ #14 = COLOR DEL APODO (0x5F399D)
    # ── la COLA, completa (ver el docstring) ──
    b += bytes([(tarjeta if TARJETA_DE_NOMBRE else 0) & 0xFF])  # T1 ★ TARJETA DE NOMBRE -> 0x597960 -> sRoomUser+0x1E5
    b += struct.pack("<H", 0)                          # T2
    b += bytes([0])                                    # T3  -> escena+0x164
    b += struct.pack("<II", 0, 0)                      # T4 T5  (0 = no-op)
    b += bytes([0])                                    # T6
    b += struct.pack("<I", (medalla if FF0C_MEDALLA else 0) & 0xFFFFFFFF)  # T7 ★ LA MEDALLA -> escena+0x208
    _jy = [int(j) & 0xFF for j in (joyas or ())][:3]   # ⛔ tope 3: lo que se dibuja con posición propia
    b += bytes([len(_jy)]) + bytes(_jy)                # ★★ LAS JOYAS DEL ALMA
    b += bytes([sexo(char_id) & 0xFF])                 # T9  ★ el GÉNERO -> 0x5B1120 -> sRoomUser+0x196
    b += struct.pack("<I", 0)                          # T10 -> escena+0x1E8
    b += bytes([1 if capitan else 0] * 2)              # T11 T12 ★ CAPITÁN
    b += bytes(5)                                      # los 5 condicionales, al final (ver arriba)
    return b


def build_ff0c_2013(occupants):
    """FF0C ROOM_USERLIST (handler cliente 0x5E89C0). Header [H0][count:u8 en off1][H2][H3] +
    1 ocupante por jugador. LAYOUT del ocupante mapeado byte-a-byte de la secuencia de lecturas
    (trace_ff0c_reads, total 80B+items+strings). Campos clave (occ-relativo):
      occ0 EXP u32 · occ4 mission u16 · ⚠occ6 (ver abajo) · occ7..occ10 ceros · ★occ11 = EL SLOT ·
      occ14 CHAR_ID u32 ·
      occ18 u32 · occ22 ITEMCOUNT u8 + items(4B×n) · CHAR_ID2 u32 · u32 · NAMELEN u8+name · u32 ·
      STR2LEN u8+str2 · u32 · 6×u8 · u16 · 2×u8 · u32 · u32 · u8 · u32 · u32 · u32 · 2×u8 · SLOT u32 · 2×u8.
    identity = slot del ocupante: si == [me+0x40] del que recibe -> me-detect = 'soy yo'.

    ⛔⛔ **`occ6` NO ES EL GÉNERO, y `occ7` NO ES EL IDENTITY** (medido 2026-09-04). Decía
    `occ6 [gender, IDENTITY, 0, 0]`, y las dos mitades están mal. Sobre **19 jugadores
    distintos** del corpus del server de referencia:

      · `occ6` toma **1, 3 y 7** — nunca 0 — y es CONSTANTE por jugador entre paquetes
        (`jugador30` siempre 7, `jugador38` siempre 1, `jugador39` siempre 3). Las **3
        MUJERES** del corpus traen ahí **7, 0 y 7** — el mismo 7 que varios varones.
        ⇒ es una **máscara acumulativa** por jugador (`2^n - 1`), no un flag de género.
        ⚠ **Nosotros mandamos `char_id & 1`, o sea 0 o 1** — y el referente nunca manda 0.
           Candidato a mirar si algún distintivo de la fila sale en blanco.
      · `occ7` vale **0 en las 19 filas**. El que lleva el slot es **`occ11`** (0..5, y
        coincide con el asiento).

    ★★★ **EL GÉNERO ESTÁ EN LA COLA, en `cola+41`** (2026-09-04). Es el que pinta el
      distintivo de arriba de la cabeza en la sala. Medido sobre **22 ocupantes** de cuatro
      capturas: **1 en las 3 mujeres · 0 en los 19 varones**, sin excepción. Ver el
      comentario en el punto donde se escribe.
      ⛔ Acá decía «en el FF0C no hay ningún byte de género». Estaba mal: lo que no hay es un
        byte de género **en el prefijo**. Se encontró restando nuestro paquete del capturado
        para el mismo ocupante — con las mismas entradas dan los dos 110 B y quedaban tres
        bytes distintos, y éste era el único que partía a la gente por `char_id`."""
    b = bytearray([0, len(occupants) & 0xFF, 0, 0])   # header: H0, COUNT(off1), H2, H3
    for occ in occupants:
        cid   = occ.get("char_id", 0) & 0xFFFFFFFF
        items = [p & 0xFFFFFFFF for p in occ.get("parts", []) if p]
        name  = (occ.get("nick", "") or "").encode("cp1252", "replace")[:0xFF]
        gname = (occ.get("guild", "") or "").encode("cp1252", "replace")[:0xFF]   # str2 = GREMIO/círculo
        if gname:
            gname = _marca_circulo(occ) + gname      # ★ 23-oct: el crayón de círculo
        ident = occ.get("identity", occ.get("slot", 0)) & 0xFF
        slot  = occ.get("slot", 0) & 0x7F
        exp   = occ.get("exp", 0) & 0xFFFFFFFF
        gen   = occ.get("gender", sexo(cid)) & 0xFF
        o = bytearray()
        o += struct.pack("<I", exp)                    # occ0  EXP
        o += struct.pack("<H", 0)                       # occ4  mission
        o += bytes([gen, 0, 0, 0])                      # occ6  gender, 0, 0, 0
        o += bytes([0, ident, 0, 0])                     # occ10 → ★ IDENTITY en occ+11 (me-detect lee offset 11, no 7)
        o += struct.pack("<I", cid)                     # occ14 CHAR_ID (cuerpo)
        o += struct.pack("<I", 0)                       # occ18 u32
        o += bytes([len(items) & 0xFF])                 # occ22 ITEMCOUNT
        for it in items:
            o += struct.pack("<I", it)                  #       items (parts = ropa)
        o += struct.pack("<I", cid)                     # CHAR_ID2 (se repite)
        o += struct.pack("<I", 0)                       # u32
        o += bytes([len(name) & 0xFF]) + name           # NAMELEN + name
        o += struct.pack("<I", 0)                       # u32
        o += bytes([len(gname) & 0xFF]) + gname          # STR2LEN + str2 = GREMIO/círculo (era 0 -> "(null)")
        o += struct.pack("<I", 0)                       # u32 (read 0x5E8D5F) - NO es slot accesorio (revertido)
        # ★★★ 2026-08-05 — EL DISTINTIVO FANTASMA DEL ASIENTO ("ticket"/cupón junto al rótulo).
        #   El 4º de estos 6 bytes (índice 3) el CLIENTE lo pre-carga con **0xFF** antes de leerlo:
        #       0x5E8CB3  mov byte [esp+0x2a], 0xFF     <- default = NINGUNO
        #       0x5E8CB8  call 0x67CFE0                 <- y lo pisa con lo que mandemos
        #   Va a `desc+0x42` -> `0x5287C0(slot, ...)`, un setter de distintivo POR ASIENTO.
        #   Mandando **0** no estábamos diciendo "ninguno": estábamos pidiendo **el índice 0 de la
        #   lista**, o sea el primer distintivo. De ahí el ícono que nadie pidió.
        #   ⇒ Se manda el MISMO default que usa el cliente. (INFERIDO que 0xFF = ninguno, por ser el
        #     valor con el que él mismo inicializa; si con esto no desaparece, el otro candidato es
        #     `desc+0x40`, que NINGÚN byte del paquete alimenta: sería basura de pila del cliente y
        #     no habría paquete que lo arregle.)
        o += bytes([0, 0, 0, FF0C_DISTINTIVO, 0, 0])    # 6×u8 (el #4 = distintivo del asiento)
        o += struct.pack("<H", 0)                       # u16
        o += bytes([0, 0])                              # 2×u8
        o += struct.pack("<I", 0)                       # u32 (read 0x5E8D71)
        o += struct.pack("<I", 0)                       # u32 (read 0x5E8D9A)
        o += bytes([0])                                 # u8
        o += struct.pack("<I", 0)                       # u32 (read 0x5E8DAB)
        o += struct.pack("<I", 0)                       # u32 (read 0x5E8DBC)
        o += struct.pack("<I", 0)                       # u32 (read 0x5E8DC3)
        o += bytes([0, 0])                              # 2×u8
        o += struct.pack("<I", slot)                    # SLOT
        o += bytes([0, 0])                              # 2×u8
        b += o
    return bytes(b)

def build_ff6e_roomlist(salas, paginas=0, tipo=None):
    """Arma la respuesta del FF6E con salas reales (layout de arriba).

    ★★★ `paginas` = EL PRIMER BYTE, y es **el número total de páginas**, no un tipo ni un eco del
    pedido. MEDIDO en el handler del cliente (`0x5E0800`):

        005e084c  mov  cl, byte [esp+0x19]   ; este byte
        005e0850  cmp  cl, 1
        005e0853  jbe  0x5e0887              ; <=1  -> NO dibuja las pestañas de página
        005e0877  dec  cx                    ; >1   -> arma la barra con cl-1
        005e08f8  mov  byte [ecx+0x16fe], dl ; y lo guarda como el total de páginas

    ⚠ `salas` son SÓLO las de la página que se manda; el total va aparte, en este byte. Mandar
      todas y poner el total acá le desincroniza el conteo al cliente.
    ⛔ El nombre viejo era `tipo`, de cuando se creía que era "1 = hay salas · 0 = vacía". Esa
      lectura salía de 221 respuestas del server de referencia **que nunca tuvieron más de una
      página**: ahí los dos significados dan el mismo número. Se acepta `tipo=` por compatibilidad.
    """
    if tipo is not None:
        paginas = tipo
    p = bytes([paginas & 0xFF]) + struct.pack("<H", len(salas) & 0xFFFF)
    for s in salas:
        nb = str(s.get("nombre", "sala")).encode("cp1252", "replace")[:0x3E]
        a  = (s.get("roomid", 1) & 0x7FF) | ((s.get("A_alto", 0) & 0x1F) << 11)
        p += struct.pack("<H", a)
        p += bytes([s.get("B", 0) & 0xFF])
        p += struct.pack("<H", s.get("C", 0) & 0xFFFF)
        p += struct.pack("<H", s.get("D", 0) & 0xFFFF)
        p += bytes([s.get("E", 0) & 0xFF, s.get("F", 0) & 0xFF, s.get("G", 6) & 0xFF])
        p += bytes([len(nb)]) + nb
        p += bytes([s.get("H", 0) & 0xFF, s.get("I", 0) & 0xFF])
        p += struct.pack("<I", s.get("J", 0) & 0xFFFFFFFF)
        p += struct.pack("<I", s.get("K", 0) & 0xFFFFFFFF)
        p += bytes([s.get("L", 0) & 0xFF, s.get("M", 0) & 0xFF,
                    s.get("N", 0) & 0xFF, s.get("O", 0) & 0xFF])
    return p
